# -*- coding: utf-8 -*-
"""
音乐文件管理系统 - 主程序入口

三条流程：
    默认 / --archive     WORKSPACE_DIR 流水线：解密 → 去重 → 标签 → 检查 → 移出待补全 → 年份归档
    --check              LIBRARY_DIR 检查
    --manual-archive     WORKSPACE_DIR 人工确认后按年份并入 LIBRARY_DIR

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
import tagger
import utils
from core.naming import format_filename
from core.report import Report
from services import decrypt, soundalike

EPILOG = '''
使用示例:
  python main.py                         # WORKSPACE_DIR 完整流水线（当前月份）
  python main.py --month 202406          # 指定月份
  python main.py --dry-run               # 只出计划，不动文件
  python main.py --check                 # 检查最终库 LIBRARY_DIR
  python main.py --check --fix           # 检查并执行修复（重命名/移动不一致文件）
  python main.py --manual-archive        # 把工作区按年份并入 LIBRARY_DIR
  python main.py --only-decrypt          # 只解密
  python main.py --only-update-tag temp  # 只更新工作区标签
  python main.py --only-check-file-name master
  python main.py --only-archive          # 只对工作区做年份归档
  python main.py --init                  # 初始化/更新声纹库
  python main.py --checkdb               # 检查声纹库与文件一致性
'''


def _ensure_console_encoding():
    """让中文输出在非 UTF-8 控制台（如英文 Windows 的 cp1252）不再崩溃

    不改变控制台原有编码，只把错误策略放宽为 replace：能显示的正常显示，
    显示不了的退化成 ?，而不是抛 UnicodeEncodeError 让 --help 直接崩掉。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors='replace')
        except (AttributeError, ValueError):  # 被重定向或非 TextIOWrapper 时跳过
            pass


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
    parser.add_argument('--trash-dup', action='store_true', help='重复文件直接移入回收站（默认移到 DUPLICATE_DIR）')

    parser.add_argument('--check', action='store_true', help=f'检查最终库 {config.LIBRARY_DIR}')
    parser.add_argument('--fix', action='store_true', help='--check 时执行修复动作（默认只报告）')
    parser.add_argument('--init', action='store_true', help='初始化/更新声纹库（不含工作区）')
    parser.add_argument('--soundalike', action='store_true', help='运行声纹去重')
    parser.add_argument('--checkdb', action='store_true', help='检查声纹库与目录文件一致性')
    parser.add_argument('--archive', action='store_true', help='WORKSPACE_DIR 归档（等同于默认流程）')
    parser.add_argument('--archive-manual', '--manual-archive', dest='manual_archive',
                        action='store_true', help='手动归档：WORKSPACE_DIR → 按年份并入 LIBRARY_DIR')
    parser.add_argument('--only-decrypt', action='store_true', help='只执行解密')
    parser.add_argument('--only-update-tag', type=str, choices=['master', 'temp'], help='只更新标签')
    parser.add_argument('--only-check-file-name', type=str, choices=['master', 'temp'], help='只检查文件名')
    parser.add_argument('--only-archive', action='store_true', help='只对 WORKSPACE_DIR 做年份归档（先移出待补全）')

    parser.add_argument('--skip-vip', action='store_true', help='跳过解密与普通文件拷贝')
    parser.add_argument('--skip-fingerprint', action='store_true', help='跳过去重')
    parser.add_argument('--skip-tag-update', action='store_true', help='跳过标签更新')
    parser.add_argument('--skip-check', action='store_true', help='跳过检查')
    parser.add_argument('--skip-organize', action='store_true', help='跳过工作区的年份归档')
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


def _copy_normal_files(month, args, dry_run=False):
    """下载目录中的普通文件拷贝到 WORKSPACE_DIR（排除 VIP 子目录）"""
    items = []
    for base, vip_dir in ((config.NETEASE_DIR, config.NETEASE_VIP_DIR),
                          (config.QQ_DIR, config.QQ_VIP_DIR)):
        for track in scanner.scan([base], month=month, with_tags=False):
            if vip_dir and os.path.abspath(track.path).startswith(os.path.abspath(vip_dir)):
                continue
            items.append((track.path, os.path.join(config.WORKSPACE_DIR, track.filename)))
    if dry_run:
        utils.main_logger.info(f'[试运行] 拟拷贝 {len(items)} 个普通文件')
        return len(items)
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
           only_filename=False, review_dir=None, dup_dir=None):
    """执行检查并按需修复

    Args:
        only_filename: True 时只做文件名格式检查，跳过标签/重复/歌词
                       （供 --only-check-file-name 使用，避免名不副实）
        review_dir: 标签严重缺失/文件名矛盾的目标目录
        dup_dir: 重复文件的目标目录
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
            review_dir=review_dir if review_dir is not None else config.INCOMPLETE_DIR,
            rename_canonical=True,
            move_bad=move_bad,
            delete_duplicates=args.trash_dup,
            dup_dir=dup_dir if dup_dir is not None else config.DUPLICATE_DIR,
        )
        _execute(plan, args)

    counts = result.counts()
    utils.main_logger.info('检查结果: ' + '，'.join(f'{k} {v}' for k, v in counts.items()))
    return result, report


def _split_incomplete(args, report=None):
    """把 WORKSPACE_DIR 顶层未达入库标准的文件移入 INCOMPLETE_DIR

    标签完整的文件原地保留；只处理顶层，解密暂存区与已归档子目录不参与。
    """
    tracks = _limited(scanner.scan([config.WORKSPACE_DIR], recursive=False), args)
    plan = _new_plan('待补全分流', args)
    kept = moved = 0
    for track in tracks:
        problems = checker.readiness_problems(track)
        if not problems:
            kept += 1
            continue
        plan.add_move(track.path, os.path.join(config.INCOMPLETE_DIR, track.filename),
                      '未达入库标准: ' + '；'.join(problems))
        moved += 1
    _execute(plan, args)
    utils.main_logger.info(f'工作区分流: 保留 {kept}，移入待补全 {moved}')
    if report is not None:
        report.add_summary('工作区保留', kept)
        report.add_summary('待补全', moved)
    return kept, moved


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
    utils.main_logger.info(f'运行声纹去重（含工作区: {with_temp}）')
    if not soundalike.db_exists():
        utils.main_logger.info(f'声纹库不存在，将由 soundalike 扫描 {config.LIBRARY_DIR} 自动建库')
    result = soundalike.run(debug=args.debug, with_temp=with_temp)
    utils.main_logger.info(f'声纹去重: {result.summary()}')
    return result


def flow_pipeline(month, args):
    """WORKSPACE_DIR 完整流水线"""
    report = Report(f'工作区流水线（{month}）')
    report.add_summary('月份', month)
    report.add_summary('试运行', '否' if not args.dry_run else '是')
    start = time.time()

    if not args.skip_vip:
        flow_decrypt(month, args, report)
        copied = _copy_normal_files(month, args, dry_run=args.dry_run)
        report.add_summary('普通文件拷贝', f'{copied} 个')
    else:
        utils.main_logger.info('已跳过 VIP 解密与普通文件拷贝')

    if not args.skip_fingerprint:
        if args.dry_run:
            utils.main_logger.info('[试运行] 跳过声纹去重（外部工具无 dry-run）')
        else:
            result = flow_dedupe(args, with_temp=True)
            report.add_summary('声纹去重', result.summary())
    else:
        utils.main_logger.info('已跳过声纹去重')

    if not args.skip_tag_update:
        processed, updated = _update_tags(scanner.scan([config.WORKSPACE_DIR]), args)
        report.add_summary('标签更新', f'处理 {processed} / 变更 {updated}')
    else:
        utils.main_logger.info('已跳过标签更新')

    if not args.skip_check:
        _check([config.WORKSPACE_DIR], args, '工作区检查', allow_fix=True,
               report=report, move_bad=not args.no_move,
               review_dir=config.INCOMPLETE_DIR, dup_dir=config.DUPLICATE_DIR)
    else:
        utils.main_logger.info('已跳过检查')

    _split_incomplete(args, report)

    if not args.skip_organize:
        _organize(config.WORKSPACE_DIR, args, report)
    else:
        utils.main_logger.info('已跳过工作区年份归档')

    report.add_summary('总耗时', f'{time.time() - start:.1f} 秒')
    _save(report, args)
    return report


def flow_check(args):
    """最终库检查"""
    report = Report(f'最终库检查（{config.LIBRARY_DIR}）')
    start = time.time()

    if not args.dry_run:
        utils.main_logger.info('步骤 1: 声纹库与目录一致性')
        db = soundalike.check()
        utils.main_logger.info(f'数据库检查: {db.summary()}')
        report.add_summary('声纹库检查', db.summary())

    utils.main_logger.info('步骤 2-6: 文件名 / 元数据 / 标签 / 重复 / 歌词')
    _check([config.LIBRARY_DIR], args, '最终库检查',
           allow_fix=args.fix, report=report,
           move_bad=args.fix and not args.no_move,
           review_dir=config.INCOMPLETE_DIR, dup_dir=config.DUPLICATE_DIR)

    report.add_summary('总耗时', f'{time.time() - start:.1f} 秒')
    _save(report, args)
    return report


def flow_manual_archive(args):
    """人工确认后：WORKSPACE_DIR → LIBRARY_DIR（按年代/年份）"""
    report = Report('手动归档')
    start = time.time()

    tracks = _limited(scanner.scan([config.WORKSPACE_DIR]), args)
    utils.main_logger.info(f'工作区待归档 {len(tracks)} 个文件')

    processed, updated = _update_tags(tracks, args)
    report.add_summary('标签更新', f'处理 {processed} / 变更 {updated}')

    tracks = _limited(scanner.scan([config.WORKSPACE_DIR]), args)
    rename_plan = _new_plan('按标签重命名', args)
    for track in tracks:
        if track.title and not checker.readiness_problems(track):
            new_name = format_filename(track.artist, track.title, track.ext)
            if new_name != track.filename:
                rename_plan.add_rename(track.path, new_name, '按标签规范化文件名')
    _execute(rename_plan, args)

    tracks = _limited(scanner.scan([config.WORKSPACE_DIR]), args)
    complete = [t for t in tracks if not checker.readiness_problems(t)]
    incomplete = [t for t in tracks if checker.readiness_problems(t)]

    plan = _new_plan('按年份入库', args)
    organized, unknown = organizer.plan_organize(complete, config.LIBRARY_DIR, plan)
    for track in incomplete:
        plan.add_move(track.path, os.path.join(config.INCOMPLETE_DIR, track.filename),
                      '未达入库标准: ' + '；'.join(checker.readiness_problems(track)))
    result = _execute(plan, args)
    executed = len(organized) if args.dry_run else (len(result.done) if result else 0)

    report.add_summary('入库成功', executed)
    report.add_summary('待人工', len(incomplete) + len(unknown))

    waiting = scanner.scan([config.INCOMPLETE_DIR])
    report.add_summary('待补全区', len(waiting))
    if waiting:
        utils.main_logger.warning(f'INCOMPLETE_DIR 仍有 {len(waiting)} 个文件待人工处理')

    report.add_summary('总耗时', f'{time.time() - start:.1f} 秒')
    _save(report, args)
    return report


# ---------------- 入口 ----------------

def main(argv=None):
    _ensure_console_encoding()
    parser = build_parser()
    args = parser.parse_args(argv)

    utils.setup_logging(debug_mode=args.debug)
    utils.main_logger.info(f'配置: {config.as_dict()}')
    for problem in config.validate():
        utils.main_logger.warning(problem)

    if not args.dry_run:
        created = utils.ensure_dirs()
        if created:
            utils.main_logger.info(f'已创建目录: {len(created)} 个')

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
        target = config.LIBRARY_DIR if args.only_update_tag == 'master' else config.WORKSPACE_DIR
        _update_tags(scanner.scan([target]), args)
        return 0

    if args.only_check_file_name:
        target = config.LIBRARY_DIR if args.only_check_file_name == 'master' else config.WORKSPACE_DIR
        _check([target], args, '文件名检查', allow_fix=args.fix, only_filename=True,
               review_dir=config.INCOMPLETE_DIR, dup_dir=config.DUPLICATE_DIR)
        return 0

    if args.only_archive:
        _split_incomplete(args)
        _organize(config.WORKSPACE_DIR, args)
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
