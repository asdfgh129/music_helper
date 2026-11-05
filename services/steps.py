# -*- coding: utf-8 -*-
"""Web 向导六步的业务编排（CLI 与 Web 共用）

分工：
- `core/` 提供判定（哪些文件算可就绪、怎么归档、怎么建 Plan）；
- `services/` 提供副作用（调外部程序、读写标签、搬文件）；
- 本模块只做「一步 = 一件事」的编排，不新增任何判定规则。

所有破坏性动作仍然只经 `core.ops.Plan`；拷贝不是破坏性动作，走 `core.ops.copy_items`。
每个长任务都接受 `progress(done, total, item)` 回调，供前端画逐条进度。
"""

import os
import time

import config
import core.check as checker
import core.library as library
import core.ops as ops
import core.organize as organizer
import core.scan as scanner
import utils
from services import decrypt as decrypt_service
from services import settings_store, soundalike

# 第 3 步「普通文件拷贝」的源目录：(标签, 下载目录属性, VIP 子目录属性)
COPY_SOURCES = (
    ('网易云', 'NETEASE_DIR', 'NETEASE_VIP_DIR'),
    ('QQ音乐', 'QQ_DIR', 'QQ_VIP_DIR'),
)


def _log():
    return getattr(utils, 'main_logger', None)


def _emit(progress, done, total, item):
    if progress is None:
        return
    try:
        progress(done, total, item)
    except Exception:  # noqa: BLE001 - 进度回调失败不该打断业务
        pass


def _in_dir(path, directory):
    if not directory:
        return False
    try:
        return os.path.commonpath([os.path.abspath(path), os.path.abspath(directory)]) \
            == os.path.abspath(directory)
    except ValueError:
        return False


# --------------------------------------------------------------------------- #
# 第 1 步：目录设置                                                           #
# --------------------------------------------------------------------------- #

def directories():
    """八个目录的当前值 + 现状 + 来源（向导第一步）"""
    items = settings_store.current()
    for item in items:
        # VIP 目录默认跟随下载目录，页面上要知道「留空时实际用哪个」
        if item['key'] in settings_store.VIP_PARENT and not item['value']:
            item['value'] = item['vip_default']
            item['inherited'] = True
    return {
        'items': items,
        'fields': settings_store.fields(),
        'ini_path': config.ini_path(),
        'env_overrides': {item['key']: settings_store.env_key(item['attr'])
                          for item in items if item['source'] == 'env'},
    }


def save_directories(values):
    """保存目录设置；返回 (problems, directories())"""
    problems, items = settings_store.save(values)
    if problems:
        return problems, {'items': items, 'fields': settings_store.fields()}
    return [], directories()


# --------------------------------------------------------------------------- #
# 第 2 步：库状态                                                             #
# --------------------------------------------------------------------------- #

def library_status():
    info = library.status(config.LIBRARY_DIR, config.DB_PATH)
    info['actions'] = library.init_actions(info)
    info['tool'] = {
        'soundalike_ok': not soundalike.exe_problem(),
        'soundalike_problem': soundalike.exe_problem(),
        'db_settings_problem': soundalike.settings_problem(),
    }
    return info


# --------------------------------------------------------------------------- #
# 第 2a 步：初始化                                                            #
# --------------------------------------------------------------------------- #

def init_library(make_db=True, progress=None):
    """初始化库目录：建目录结构 → （可选）建声纹库

    「初始化」只做两件事，都是幂等的：目录不存在就建；声纹库不存在就扫库建索引。
    已有文件一个都不动。
    """
    logger = _log()
    info = library.status(config.LIBRARY_DIR, config.DB_PATH)
    steps = []

    if not info['is_dir']:
        os.makedirs(config.LIBRARY_DIR, exist_ok=True)
        steps.append({'key': 'mkdir', 'label': '创建库目录',
                      'detail': config.LIBRARY_DIR, 'ok': True})

    created = []
    try:
        created = utils.ensure_dirs()
    except Exception as exc:  # noqa: BLE001
        steps.append({'key': 'dirs', 'label': '创建工作目录', 'detail': str(exc), 'ok': False})
    else:
        steps.append({'key': 'dirs', 'label': '创建工作目录',
                      'detail': '；'.join(created) if created else '已存在，无需创建',
                      'ok': True})

    unknown_dir = os.path.join(config.LIBRARY_DIR, library.UNKNOWN_DIRNAME)
    if not os.path.isdir(unknown_dir):
        try:
            os.makedirs(unknown_dir, exist_ok=True)
            steps.append({'key': 'layout', 'label': '建立归档结构',
                          'detail': unknown_dir, 'ok': True})
        except OSError as exc:
            steps.append({'key': 'layout', 'label': '建立归档结构',
                          'detail': str(exc), 'ok': False})
    else:
        steps.append({'key': 'layout', 'label': '建立归档结构',
                      'detail': '已存在，无需创建', 'ok': True})

    if make_db:
        problem = soundalike.exe_problem() or soundalike.settings_problem()
        if problem:
            steps.append({'key': 'db', 'label': '建立声纹库', 'detail': problem, 'ok': False})
        else:
            _emit(progress, 0, 1, {'name': '声纹库', 'message': '正在扫描库目录…'})
            if logger:
                logger.info('初始化：开始建立声纹库')
            result = soundalike.init_db()
            steps.append({'key': 'db', 'label': '建立声纹库',
                          'detail': result.summary() or '完成', 'ok': result.ok})
            _emit(progress, 1, 1, {'name': '声纹库', 'ok': result.ok,
                                   'message': result.summary()})
    else:
        steps.append({'key': 'db', 'label': '建立声纹库',
                      'detail': '已跳过（可稍后在初始化页补建）', 'ok': True})

    status = library_status()
    return {'steps': steps, 'status': status,
            'ok': all(step['ok'] for step in steps)}


# --------------------------------------------------------------------------- #
# 第 3 步：拷贝普通文件                                                       #
# --------------------------------------------------------------------------- #

def _month_of(path):
    return scanner.month_of(path)


def copy_candidates(month=None, month_from=None, month_to=None):
    """待拷贝的普通音频文件（不含 VIP 子目录），按源目录分组

    与旧流程唯一的区别：这里把「哪些算普通文件」显式算出来给页面看，而旧流程
    在拷贝时才现算，用户看不到将要发生什么。
    """
    groups = []
    total = 0
    total_bytes = 0
    for label, base_attr, vip_attr in COPY_SOURCES:
        base = getattr(config, base_attr, '')
        vip = getattr(config, vip_attr, '')
        if not base or not os.path.isdir(base):
            groups.append({'label': label, 'root': base, 'files': [],
                           'missing': True, 'count': 0, 'bytes': 0})
            continue
        tracks = scanner.scan([base], with_tags=False, recursive=True,
                              month=month, month_from=month_from, month_to=month_to)
        by_dir = {}
        for track in tracks:
            if _in_dir(track.path, vip):
                continue
            by_dir.setdefault(os.path.dirname(track.path), []).append(track)
        sub_groups = []
        for root in sorted(by_dir):
            files = []
            for track in sorted(by_dir[root], key=lambda t: t.filename):
                target = os.path.join(config.WORKSPACE_DIR, track.filename)
                files.append({
                    'path': track.path,
                    'name': track.filename,
                    'size': track.size,
                    'month': _month_of(track.path),
                    'target': target,
                    'existing': os.path.exists(target),
                })
            sub_groups.append({'label': label, 'root': root, 'files': files,
                               'count': len(files),
                               'bytes': sum(item['size'] for item in files)})
            total += len(files)
            total_bytes += sum(item['size'] for item in files)
        groups.extend(sub_groups)
    return {'groups': groups, 'total': total, 'bytes': total_bytes,
            'target_dir': config.WORKSPACE_DIR}


def copy_pairs(month=None, month_from=None, month_to=None):
    """(源, 目标) 列表；CLI 的 `_copy_normal_files` 复用这一份"""
    pairs = []
    for group in copy_candidates(month=month, month_from=month_from,
                                 month_to=month_to)['groups']:
        for item in group['files']:
            pairs.append((item['path'], item['target']))
    return pairs


def run_copy(paths=None, month=None, month_from=None, month_to=None, progress=None):
    """执行拷贝，返回逐条结果

    Args:
        paths: 只拷贝这些文件；None 表示按月份取全部候选
    """
    logger = _log()
    candidates = copy_candidates(month=month, month_from=month_from, month_to=month_to)
    pairs = []
    names = {}
    for group in candidates['groups']:
        for item in group['files']:
            if paths and os.path.normcase(item['path']) not in {
                    os.path.normcase(p) for p in paths}:
                continue
            pairs.append((item['path'], item['target']))
            names[os.path.normcase(item['path'])] = item['name']

    total = len(pairs)
    results = []

    def on_item(index, src, final, error):
        item = {'name': names.get(os.path.normcase(src), os.path.basename(src)),
                'source': src, 'output': final, 'ok': not error, 'message': error}
        results.append(item)
        _emit(progress, index + 1, total, item)

    started = time.time()
    copied = ops.copy_items(pairs, logger, on_item=on_item)
    failed = [item for item in results if not item['ok']]
    return {
        'total': total,
        'copied': copied,
        'failed': failed,
        'skipped': total - len(results),
        'elapsed': round(time.time() - started, 1),
        'target_dir': config.WORKSPACE_DIR,
        'copied_any': copied > 0,
    }


# --------------------------------------------------------------------------- #
# 第 4 步：解密                                                               #
# --------------------------------------------------------------------------- #

DECRYPT_SOURCES = (('网易云', 'netease'), ('QQ音乐', 'qq'))


def decrypt_candidates(month_from=None, month_to=None):
    """待解密的 VIP 文件，按来源分组（不移动任何文件）"""
    groups = []
    total = 0
    total_bytes = 0
    for label, target in DECRYPT_SOURCES:
        _name, vip_dir, _exts = decrypt_service.target_info(target)
        items = decrypt_service.encrypted_candidates(target, month_from, month_to)
        files = []
        for item in items:
            files.append({
                'path': item['path'],
                'name': item['name'],
                'size': item['size'],
                'expect': item['expect'],
                'existing': item['existing'],
                'target': item['target_dir'],
                'month': _month_of(item['path']),
                'source': target,
            })
        groups.append({'label': label, 'root': vip_dir, 'files': files,
                       'count': len(files),
                       'bytes': sum(f['size'] for f in files),
                       'missing': not os.path.isdir(vip_dir),
                       'target': target})
        total += len(files)
        total_bytes += sum(f['size'] for f in files)
    return {'groups': groups, 'total': total, 'bytes': total_bytes,
            'target_dir': config.WORKSPACE_DIR}


def run_decrypt(months=None, paths=None, progress=None):
    """直接解密：VIP 目录 → 工作区，不经过暂存区

    相比旧流程少一次「加密文件搬进暂存区、完事再搬回去」的跨盘复制：
    um 是「读源 → 逐字节写目标」，输入输出在两个盘符也没问题（见
    `docs/web-wizard.md` 的核实结论）。

    Args:
        months: (from, to)，None 表示不按月份筛
        paths: 只解密这些文件；None 表示该来源下全部候选
    """
    month_from, month_to = months or (None, None)
    logger = _log()

    # 先算出每个来源要处理几个，才能画全局进度（两个来源合起来算 100%）
    plan = []
    total = 0
    for label, target in DECRYPT_SOURCES:
        items = decrypt_service.encrypted_candidates(target, month_from, month_to)
        if paths:
            wanted = {os.path.normcase(p) for p in paths}
            items = [item for item in items if os.path.normcase(item['path']) in wanted]
        plan.append((label, target, [item['path'] for item in items]))
        total += len(items)

    if not total:
        return {'items': [], 'total': 0, 'produced': 0, 'ok': True,
                'message': '没有需要解密的文件', 'target_dir': config.WORKSPACE_DIR}

    offset = 0
    results = []
    for label, target, selected in plan:
        if not selected:
            continue

        def on_progress(done, _target_total, item, _label=label, _offset=offset):
            _emit(progress, _offset + done, total, {**item, 'label': _label})

        result = decrypt_service.decrypt_direct(
            target, paths=selected, logger=logger, progress=on_progress)
        offset += len(selected)
        results.append({'label': label, 'ok': result.ok, 'encrypted': result.encrypted,
                        'produced': result.produced, 'message': result.message})
        if logger:
            logger.info(f'{label}：{result.message}')

    return {
        'items': results,
        'total': total,
        'produced': sum(item['produced'] for item in results),
        'ok': all(item['ok'] for item in results),
        'target_dir': config.WORKSPACE_DIR,
    }


# --------------------------------------------------------------------------- #
# 第 5 步：标签与歌词补全                                                     #
# --------------------------------------------------------------------------- #

def tag_candidates():
    """工作区顶层待补全的文件（与「待补全分流」用同一份就绪判定）"""
    tracks = scanner.scan([config.WORKSPACE_DIR], with_tags=True, recursive=False)
    items = []
    for track in tracks:
        problems = checker.readiness_problems(track)
        items.append({
            'path': track.path,
            'name': track.filename,
            'artist': track.artist,
            'title': track.title,
            'album': track.album,
            'year': track.year,
            'duration': round(track.duration, 1),
            'size': track.size,
            'has_cover': bool(track.has_cover),
            'has_lrc': track.has_lrc,
            'problems': problems,
            'ready': not problems,
        })
    return {
        'dir': config.WORKSPACE_DIR,
        'items': items,
        'total': len(items),
        'ready': sum(1 for item in items if item['ready']),
        'missing_tags': sum(1 for item in items
                            if any(problem.startswith('缺少') for problem in item['problems'])),
        'missing_lrc': sum(1 for item in items if not item['has_lrc']),
        'missing_cover': sum(1 for item in items if not item['has_cover']),
    }


def run_fill_tags(paths=None, with_fingerprint=True, write_cover=True,
                  write_lyrics=True, progress=None):
    """补全标签 / 封面 / 歌词（只填空缺，不覆盖已有值）

    判定「有没有必要处理」仍由 `tagger.Tagger.update` 内部决定，这里不预筛，
    免得两边规则不一致。
    """
    import tagger as tagger_service

    logger = _log()
    if not paths:
        paths = [item['path'] for item in tag_candidates()['items']]
    service = tagger_service.Tagger(with_fingerprint=with_fingerprint,
                                    write_cover=write_cover,
                                    write_lyrics=write_lyrics)
    total = len(paths)
    items = []
    updated = failed = 0
    for index, path in enumerate(paths, 1):
        try:
            track = scanner.build_track(path, with_tags=True)
        except OSError as exc:
            item = {'name': os.path.basename(path), 'path': path, 'ok': False,
                    'fields': [], 'cover': False, 'lyric': False, 'message': f'读取失败: {exc}'}
            failed += 1
            items.append(item)
            _emit(progress, index, total, item)
            continue
        result = service.update(track)
        item = {
            'name': track.filename,
            'path': path,
            'ok': not result.error,
            'fields': list(result.fields),
            'source': result.source,
            'cover': bool(result.cover),
            'lyric': bool(result.lyric),
            'message': result.error or ('已更新' if result.updated else '无需更新'),
            'updated': bool(result.updated),
        }
        if result.updated:
            updated += 1
        if result.error:
            failed += 1
        items.append(item)
        _emit(progress, index, total, item)
        if logger and result.updated:
            logger.info(f'标签更新 {track.filename} <- {result.source or "本地"} {result.fields}')

    return {'total': total, 'updated': updated, 'failed': failed,
            'items': items, 'preview': False}


# --------------------------------------------------------------------------- #
# 第 6 步：归档                                                               #
# --------------------------------------------------------------------------- #

def archive_preview(into_library=True):
    """归档预览：按 <年代>/<年份> 分组，另列出无法归档的

    Args:
        into_library: True 归档到 LIBRARY_DIR（直接入库），False 在工作区内整理
    """
    base_dir = config.LIBRARY_DIR if into_library else config.WORKSPACE_DIR
    tracks = scanner.scan([config.WORKSPACE_DIR], with_tags=True, recursive=False)
    buckets = {}
    incomplete = []
    for track in tracks:
        problems = checker.readiness_problems(track)
        if problems:
            incomplete.append({'path': track.path, 'name': track.filename,
                               'problems': problems})
            continue
        target = organizer.target_path(track, base_dir)
        if not target:
            incomplete.append({'path': track.path, 'name': track.filename,
                               'problems': ['无法确定年份目录']})
            continue
        decade = organizer.decade_label(track.year_int)
        key = (decade, str(track.year_int))
        bucket = buckets.setdefault(key, {'decade': decade, 'year': str(track.year_int),
                                          'files': [], 'bytes': 0})
        bucket['files'].append({'path': track.path, 'name': track.filename,
                                'size': track.size, 'target': target})
        bucket['bytes'] += track.size

    groups = []
    for key in sorted(buckets):
        bucket = buckets[key]
        bucket['count'] = len(bucket['files'])
        bucket['dir'] = os.path.join(base_dir, bucket['decade'], bucket['year'])
        groups.append(bucket)

    return {
        'base_dir': base_dir,
        'target': base_dir,
        'into_library': into_library,
        'groups': groups,
        'total': sum(group['count'] for group in groups),
        'bytes': sum(group['bytes'] for group in groups),
        'incomplete': incomplete,
        'workspace': config.WORKSPACE_DIR,
    }


def run_archive(into_library=True, move_incomplete=True, progress=None):
    """执行归档

    可归档的进 <年代>/<年份>/；不可归档的（缺年份/缺歌手/文件名矛盾）按既有规则
    移入待确认目录，不留在工作区挡路。
    """
    logger = _log()
    preview = archive_preview(into_library=into_library)
    base_dir = preview['base_dir']
    tracks = scanner.scan([config.WORKSPACE_DIR], with_tags=True, recursive=False)
    total = len(tracks)

    plan = ops.Plan(f"归档-{'入库' if into_library else '工作区'}",
                    dry_run=False, journal_path=config.JOURNAL_PATH,
                    trash_dir=config.TRASH_DIR)
    organized, unknown = organizer.plan_organize(tracks, base_dir, plan)
    if move_incomplete:
        for track in unknown:
            plan.add_move(track.path,
                          os.path.join(config.INCOMPLETE_DIR, track.filename),
                          '未达入库标准: ' + '；'.join(checker.readiness_problems(track)))

    if logger:
        logger.info(f'归档计划：可归档 {len(organized)}，待确认 {len(unknown)}')
    result = plan.execute() if not plan.is_empty else None

    items = []
    for index, op in enumerate(plan.operations, 1):
        status = 'ok'
        if result and op in result.failed:
            status = 'failed'
        elif result and op in result.skipped:
            status = 'skipped'
        item = {'name': os.path.basename(op.src), 'source': op.src,
                'target': op.dst, 'reason': op.reason, 'status': status}
        items.append(item)
        _emit(progress, index, max(total, len(plan.operations)), item)

    executed = len(result.done) if result else 0
    return {
        'planned': len(plan.operations),
        'executed': executed,
        'failed': len(result.failed) if result else 0,
        'unknown': len(unknown),
        'base_dir': base_dir,
        'items': items,
        'summary': result.summary() if result else '无需归档',
    }
