# -*- coding: utf-8 -*-
"""
音乐文件管理系统 - 主程序入口

三条流程与 项目规划.md 一一对应：
    默认 / --archive     临时目录流水线（规划 2.x）
    --check              主目录检查（规划 1.x）
    --manual-archive     手动归档：更新标签 → 重命名 → 按年份入库（规划 3.x）

所有破坏性动作都会先形成计划（--dry-run 可预览），统一写入 log/journal.jsonl，
删除一律进 log/_trash 而不是真正删除。
"""

import argparse
import os
import sys
import time

import config
import core.check as checker
import core.ops as ops
import core.organize as organizer
import core.scan as scanner
import utils
from core.naming import format_filename
from core.report import Report
from services import decrypt, soundalike, tagger

EPILOG = '''
使用示例:
  python main.py                         # 临时目录完整流水线（当前月份）
  python main.py --month 202406          # 指定月份
  python main.py --dry-run               # 只出计划，不动文件
  python main.py --check                 # 检查主目录 D:\\music
  python main.py --check --fix           # 检查并执行修复（重命名/移动不一致文件）
  python main.py --archive               # 同默认：临时目录归档
  python main.py --manual-archive        # 更新标签 → 重命名 → 按年份移入主目录
  python main.py --only-decrypt          # 只解密
  python main.py --only-update-tag temp  # 只更新临时目录标签
  python main.py --only-check-file-name master
  python main.py --only-archive          # 只做年份归档
  python main.py --init                  # 初始化/更新声纹库
  python main.py --checkdb               # 检查声纹库与文件一致性
'''


def build_parser():
    parser = argparse.ArgumentParser(
        description=f'音乐文件管理系统 v{config.__version__}',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=EPILOG,
    )
    parser.add_argument('--version', action='version', version=f'%(prog)s v{config.__version__}')
    parser.add_argument('--debug', action='store_true', help='输出详细运行信息')
    parser.add_argument('--month', type=str, default=None, help='指定月份 (YYYYMM，默认当前月)')
    parser.add_argument('--dry-run', action='store_true', help='只生成操作计划，不实际移动/改名')
    parser.add_argument('--report-dir', type=str, default=None, help=f'报告输出目录（默认 {config.REPORT_DIR}）')
    parser.add_argument('--limit', type=int, default=0, help='最多处理 N 个文件（调试用，0 表示不限制）')
    parser.add_argument('--no-move', action='store_true', help='流水线中不移动不一致文件')
    parser.add_argument('--trash-dup', action='store_true', help='重复文件直接移入回收站（默认移到待处理目录）')

    parser.add_argument('--check', action='store_true', help=f'检查主目录 {config.MAIN_DIR}')
    parser.add_argument('--fix', action='store_true', help='--check 时执行修复动作（默认只报告）')
    parser.add_argument('--init', action='store_true', help='初始化/更新声纹库（不含临时目录）')
    parser.add_argument('--soundalike', action='store_true', help='运行声纹去重')
    parser.add_argument('--checkdb', action='store_true', help='检查声纹库与目录文件一致性')
    parser.add_argument('--archive', action='store_true', help='临时目录归档（等同于默认流程）')
    parser.add_argument('--archive-manual', '--manual-archive', dest='manual_archive',
                        action='store_true', help='手动归档：更新标签→重命名→按年份移入主目录')
    parser.add_argument('--only-decrypt', action='store_true', help='只执行解密')
    parser.add_argument('--only-update-tag', type=str, choices=['master', 'temp'], help='只更新标签')
    parser.add_argument('--only-check-file-name', type=str, choices=['master', 'temp'], help='只检查文件名')
    parser.add_argument('--only-archive', action='store_true', help='只做年份归档')

    parser.add_argument('--skip-vip', action='store_true', help='跳过解密与普通文件拷贝')
    parser.add_argument('--skip-fingerprint', action='store_true', help='跳过去重')
    parser.add_argument('--skip-tag-update', action='store_true', help='跳过标签更新')
    parser.add_argument('--skip-check', action='store_true', help='跳过检查')
    parser.add_argument('--skip-organize', action='store_true', help='跳过按年份归档')
    return parser


# ---------------- 内部工具 ----------------

def _new_plan(name, args):
    return ops.Plan(name, dry_run=args.dry_run,
                    journal_path=config.JOURNAL_PATH,
                    trash_dir=config.TRASH_DIR)


def _execute(plan, args):
    if plan.is_empty:
        utils.main_logger.info(f'{plan.name}: 无需处理')
        return None
    utils.main_logger.info(f'{plan.name}: 共 {len(plan)} 项')
    utils.main_logger.debug(plan.describe())
    result = plan.execute()
    utils.main_logger.info(f'{plan.name}: {result.summary()}')
    return result


def _report_dir(args):
    return args.report_dir or config.REPORT_DIR


def _save(report, args):
    paths = report.save(_report_dir(args))
    utils.main_logger.info(f'报告已生成: {paths["md"]}')
    utils.main_logger.info(f'待处理清单: {paths["csv"]}')
    return paths


def _limited(tracks, args):
    if args.limit and len(tracks) > args.limit:
        utils.main_logger.info(f'--limit 生效：只处理前 {args.limit} 个文件')
        return tracks[:args.limit]
    return tracks


def _copy_normal_files(month, args):
    """下载目录中的普通文件拷贝到临时目录（排除 VIP 子目录）"""
    items = []
    for base, vip_dir in ((config.NETEASE_DIR, config.NETEASE_VIP_DIR),
                          (config.QQ_DIR, config.QQ_VIP_DIR)):
        for track in scanner.scan([base], month=month, with_tags=False):
            if vip_dir and os.path.abspath(track.path).startswith(os.path.abspath(vip_dir)):
                continue
            items.append((track.path, os.path.join(config.TEMP_COMPLETED_DIR, track.filename)))
    copied = ops.copy_items(items, utils.main_logger)
    utils.main_logger.info(f'普通文件拷贝完成: {copied} 个')
    return copied


def _update_tags(tracks, args):
    service = tagger.Tagger(dry_run=args.dry_run,
                            with_fingerprint=not args.skip_fingerprint)
    processed = updated = 0
    for track in _limited(tracks, args):
        result = service.update(track)
        processed += 1
        if result.updated:
            updated += 1
            utils.main_logger.info(
                f'标签更新 {track.filename} <- {result.source or "本地"} '
                f'{[f for f in result.fields]}{" +封面" if result.cover else ""}'
                f'{" +歌词" if result.lyric else ""}'
            )
        elif result.error:
            utils.main_logger.warning(f'{track.filename}: {result.error}')
    utils.main_logger.info(f'标签更新完成: 处理 {processed}，变更 {updated}')
    return processed, updated


def _check(directories, args, title, allow_fix, report=None, move_bad=False,
           only_filename=False):
    """执行检查并按需修复

    Args:
        only_filename: True 时只做文件名格式检查，跳过标签/重复/歌词
                       （供 --only-check-file-name 使用，避免名不副实）
    """
    tracks = _limited(scanner.scan(directories), args)
    utils.main_logger.info(f'扫描到 {len(tracks)} 个音频文件')
    result = checker.check_library(
        tracks, directories,
        check_tags=not only_filename,
        check_lyrics=not only_filename,
        check_duplicates=not only_filename,
    )

    report = report or Report(title)
    checker.report_into(result, report)

    plan = _new_plan(f'{title}-修复', args)
    if allow_fix:
        checker.plan_fixes(
            result, plan,
            review_dir=config.TEMP_REVIEW_DIR,
            rename_canonical=True,
            move_bad=move_bad,
            delete_duplicates=args.trash_dup,
        )
        _execute(plan, args)

    counts = result.counts()
    utils.main_logger.info('检查结果: ' + '，'.join(f'{k} {v}' for k, v in counts.items()))
    return result, report


def _organize(base_dir, args, report=None, title='按年份归档', source_dirs=None):
    """按年份归档

    Args:
        base_dir: 目标根目录（归档目录建在它下面）
        source_dirs: 要扫描的源目录，默认与 base_dir 相同
    """
    tracks = scanner.scan(source_dirs or [base_dir])
    plan = _new_plan(title, args)
    organized, unknown = organizer.plan_organize(tracks, base_dir, plan)
    result = _execute(plan, args)
    executed = len(result.done) if result else 0

    if args.dry_run:
        utils.main_logger.info(f'[试运行] 计划归档 {len(organized)} 个，待人工 {len(unknown)} 个')
        executed = len(organized)
    else:
        utils.main_logger.info(f'归档完成: 成功 {executed}，待人工 {len(unknown)}')

    if report is not None:
        report.add_summary('归档成功', executed)
        report.add_summary('待人工处理', len(unknown))
        if unknown:
            report.add_review('无法归档清单',
                              [('无法归档', track.path, '/'.join(organizer.missing_fields(track)))
                               for track in unknown])
    return organized, unknown


# ---------------- 流程 ----------------

def flow_decrypt(month, args, report=None):
    results = []
    for name, func in (('网易云', decrypt.decrypt_netease), ('QQ音乐', decrypt.decrypt_qq)):
        result = func(month=month, dry_run=args.dry_run, logger=utils.main_logger)
        results.append(result)
        utils.main_logger.info(result.summary())
    if report is not None:
        for result in results:
            report.add_summary(f'{result.name}解密', f'{result.encrypted} 个加密 / {result.produced} 个产出')
            if not result.ok:
                report.add_review('解密异常', [('解密失败', result.name, result.message)])
    return results


def flow_dedupe(args, with_temp=True):
    utils.main_logger.info(f'运行声纹去重（含临时目录: {with_temp}）')
    result = soundalike.run(debug=args.debug, with_temp=with_temp)
    utils.main_logger.info(f'声纹去重: {result.summary()}')
    return result


def flow_pipeline(month, args):
    """规划 2.x：临时目录完整流水线"""
    report = Report(f'临时目录流水线（{month}）')
    report.add_summary('月份', month)
    report.add_summary('试运行', '否' if not args.dry_run else '是')
    start = time.time()

    if not args.skip_vip:
        flow_decrypt(month, args, report)
        copied = _copy_normal_files(month, args)
        report.add_summary('普通文件拷贝', f'{copied} 个')
    else:
        utils.main_logger.info('已跳过 VIP 解密与普通文件拷贝')

    if not args.skip_fingerprint:
        result = flow_dedupe(args, with_temp=True)
        report.add_summary('声纹去重', result.summary())
    else:
        utils.main_logger.info('已跳过声纹去重')

    if not args.skip_tag_update:
        processed, updated = _update_tags(scanner.scan([config.TEMP_COMPLETED_DIR]), args)
        report.add_summary('标签更新', f'处理 {processed} / 变更 {updated}')
    else:
        utils.main_logger.info('已跳过标签更新')

    if not args.skip_check:
        _check([config.TEMP_COMPLETED_DIR], args, '临时目录检查', allow_fix=True,
               report=report, move_bad=not args.no_move)
    else:
        utils.main_logger.info('已跳过检查')

    if not args.skip_organize:
        _organize(config.TEMP_COMPLETED_DIR, args, report)
    else:
        utils.main_logger.info('已跳过年份归档')

    report.add_summary('总耗时', f'{time.time() - start:.1f} 秒')
    _save(report, args)
    return report


def flow_check(args):
    """规划 1.x：主目录检查"""
    report = Report(f'主目录检查（{config.MAIN_DIR}）')
    start = time.time()

    utils.main_logger.info('步骤 1: 声纹库与目录一致性')
    db = soundalike.check()
    utils.main_logger.info(f'数据库检查: {db.summary()}')
    report.add_summary('声纹库检查', db.summary())

    utils.main_logger.info('步骤 2-6: 文件名 / 元数据 / 标签 / 重复 / 歌词')
    _check([config.MAIN_DIR], args, '主目录检查',
           allow_fix=args.fix, report=report,
           move_bad=args.fix and not args.no_move)

    report.add_summary('总耗时', f'{time.time() - start:.1f} 秒')
    _save(report, args)
    return report


def flow_manual_archive(args):
    """规划 3.x：手动归档，最终把文件按年份移入主目录"""
    report = Report('手动归档')
    start = time.time()

    tracks = _limited(scanner.scan([config.TEMP_COMPLETED_DIR]), args)
    utils.main_logger.info(f'临时目录待归档 {len(tracks)} 个文件')

    processed, updated = _update_tags(tracks, args)
    report.add_summary('标签更新', f'处理 {processed} / 变更 {updated}')

    # 按标签重命名（[歌手] - [歌名]）
    rename_plan = _new_plan('按标签重命名', args)
    for track in tracks:
        if track.title:
            new_name = format_filename(track.artist, track.title, track.ext)
            if new_name != track.filename:
                rename_plan.add_rename(track.path, new_name, '按标签规范化文件名')
    _execute(rename_plan, args)

    # 重新扫描后直接归档进主目录
    organized, unknown = _organize(config.MAIN_DIR, args, report, title='按年份入库',
                                   source_dirs=[config.TEMP_COMPLETED_DIR])
    report.add_summary('入库成功', len(organized))
    report.add_summary('待人工', len(unknown))
    report.add_summary('总耗时', f'{time.time() - start:.1f} 秒')

    _save(report, args)
    return report


# ---------------- 入口 ----------------

def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    utils.setup_logging(debug_mode=args.debug)
    utils.main_logger.info(f'配置: {config.as_dict()}')
    for problem in config.validate():
        utils.main_logger.warning(problem)

    if args.dry_run:
        utils.main_logger.info('=== 试运行：只生成计划，不改动任何文件 ===')

    # 单一动作模式
    if args.init:
        result = soundalike.run(debug=args.debug, with_temp=False)
        utils.main_logger.info(f'声纹库初始化: {result.summary()}')
        return 0 if result.ok else 1

    if args.checkdb:
        result = soundalike.check()
        utils.main_logger.info(f'数据库检查: {result.summary()}')
        return 0 if result.ok else 1

    if args.soundalike:
        result = flow_dedupe(args, with_temp=True)
        return 0 if result.ok else 1

    if args.only_decrypt:
        month = _resolve_month(args)
        if month is None:
            return 1
        flow_decrypt(month, args)
        return 0

    if args.only_update_tag:
        target = config.MAIN_DIR if args.only_update_tag == 'master' else config.TEMP_COMPLETED_DIR
        _update_tags(scanner.scan([target]), args)
        return 0

    if args.only_check_file_name:
        target = config.MAIN_DIR if args.only_check_file_name == 'master' else config.TEMP_COMPLETED_DIR
        _check([target], args, '文件名检查', allow_fix=args.fix, only_filename=True)
        return 0

    if args.only_archive:
        _organize(config.TEMP_COMPLETED_DIR, args)
        return 0

    if args.manual_archive:
        flow_manual_archive(args)
        return 0

    if args.check:
        flow_check(args)
        return 0

    month = _resolve_month(args)
    if month is None:
        return 1
    flow_pipeline(month, args)
    return 0


def _resolve_month(args):
    month = args.month
    if month is None:
        month = utils.get_current_month()
        utils.main_logger.info(f'使用当前月份: {month}')
        return month
    if not utils.validate_month_format(month):
        utils.main_logger.error(f'月份格式错误: {month}，应为 YYYYMM（如 202406）')
        return None
    utils.main_logger.info(f'使用指定月份: {month}')
    return month


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        utils.main_logger.warning('用户中断')
        sys.exit(130)
    except Exception:  # noqa: BLE001 - 兜底：异常写进日志而不是裸崩
        utils.main_logger.exception('未处理的异常，已中止')
        sys.exit(1)
