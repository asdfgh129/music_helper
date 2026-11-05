# -*- coding: utf-8 -*-
"""Web 向导八步的业务编排（CLI 与 Web 共用）

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
import core.tags as core_tags
import utils
from core import dedupe as dedupe_mod
from core import naming, quality
from core.model import Track
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
    # 库目录可能被改到别处，丢弃查重用的库索引，避免下一次比对拿旧目录的文件
    if items is not None:
        invalidate_library_cache()
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

# 页面上可勾选写入的标签字段（顺序即展示顺序）
WORKSPACE_TAG_FIELDS = ('title', 'artist', 'album', 'year', 'genre')


def _workspace_tracks():
    """工作区顶层曲目

    第 5 步补全、第 6 步查重、第 7 步自检都用这一份扫描口径：
    只扫顶层、只扫音频，避免「补全看到 10 个文件、自检看到 12 个」。
    """
    return scanner.scan([config.WORKSPACE_DIR], with_tags=True, recursive=False)


def tag_candidates():
    """工作区顶层待补全的文件（与「待补全分流」用同一份就绪判定）"""
    tracks = _workspace_tracks()
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
            'genre': track.genre,
            'duration': round(track.duration, 1),
            'size': track.size,
            'ext': track.ext,
            'has_cover': bool(track.has_cover),
            'has_lrc': track.has_lrc,
            'canonical': naming.is_canonical(track.filename),
            'consistency': checker.consistency_report(track),
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
        'mismatch': sum(1 for item in items if not item['consistency']['ok']),
    }


def run_fill_tags(paths=None, with_fingerprint=True, write_cover=True,
                  write_lyrics=True, fields=None, progress=None):
    """补全标签 / 封面 / 歌词（只填空缺，不覆盖已有值）

    判定「有没有必要处理」仍由 `tagger.Tagger.update` 内部决定，这里不预筛，
    免得两边规则不一致。

    Args:
        fields: 允许写入的标签键；None 表示全部。空列表表示只补封面/歌词。
    """
    import tagger as tagger_service

    logger = _log()
    if not paths:
        paths = [item['path'] for item in tag_candidates()['items']]
    service = tagger_service.Tagger(with_fingerprint=with_fingerprint,
                                    write_cover=write_cover,
                                    write_lyrics=write_lyrics,
                                    fields=fields)
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


# ---------------- 单曲编辑（第 5 步的「编辑」抽屉） ----------------

def _audio_in_workspace(path):
    """校验路径是工作区内的音频文件

    单曲读写接口都会调它，避免前端传个任意路径就能改到别处的文件。
    """
    target = os.path.abspath(str(path or ''))
    if not target or not os.path.isfile(target):
        raise ValueError(f'文件不存在: {path}')
    if not _in_dir(target, config.WORKSPACE_DIR):
        raise ValueError(f'只允许操作工作区内的文件: {config.WORKSPACE_DIR}')
    if not naming.is_audio(target):
        raise ValueError('不是受支持的音频文件')
    return target


def _read_lrc(path):
    """读同名 .lrc 全文；没有或读不了返回空串"""
    lrc_path = os.path.splitext(path)[0] + '.lrc'
    if not os.path.exists(lrc_path):
        return ''
    try:
        with open(lrc_path, 'r', encoding='utf-8', errors='replace') as handle:
            return handle.read()
    except OSError:
        return ''


def track_detail(path):
    """单曲详情：标签、封面/歌词状态、文件名一致性、可入库判定"""
    target = _audio_in_workspace(path)
    track = scanner.build_track(target, with_tags=True)
    return {
        'path': track.path,
        'name': track.filename,
        'ext': track.ext,
        'size': track.size,
        'duration': round(track.duration, 1),
        'tags': {key: track.tag(key) for key in WORKSPACE_TAG_FIELDS},
        'has_cover': bool(track.has_cover),
        'has_lrc': track.has_lrc,
        'lyric': _read_lrc(track.path),
        'canonical': naming.is_canonical(track.filename),
        'consistency': checker.consistency_report(track),
        'problems': checker.readiness_problems(track),
    }


def save_track(path, tags=None, lyric=None):
    """手工保存单曲标签 / 歌词

    只写传入的字段，**不改文件名**：改名牵动重复判定、归档路径与 journal，
    属于归档环节的事；手工编辑只负责把标签改对。
    空字符串不会被写入（`write_tags` 只写非空值），会原样保留旧值。
    """
    target = _audio_in_workspace(path)
    track = scanner.build_track(target, with_tags=True)

    changes, ignored = {}, []
    for key in WORKSPACE_TAG_FIELDS:
        if not tags or key not in tags:
            continue
        value = str(tags.get(key) or '').strip()
        if value == track.tag(key):
            continue
        if not value:
            ignored.append(key)
            continue
        changes[key] = value

    written = []
    if changes:
        if not core_tags.write_tags(target, changes):
            return {'ok': False, 'path': target, 'changed': [],
                    'error': '写入标签失败（格式不支持或文件被占用）'}
        written = sorted(changes)

    lyric_saved = None
    if lyric is not None:
        lrc_path = os.path.splitext(target)[0] + '.lrc'
        try:
            with open(lrc_path, 'w', encoding='utf-8') as handle:
                handle.write(str(lyric))
            lyric_saved = True
        except OSError as exc:
            return {'ok': False, 'path': target, 'changed': written,
                    'error': f'写歌词失败: {exc}'}

    detail = track_detail(target)
    detail.update({'ok': True, 'changed': written,
                   'ignored': ignored, 'lyric_saved': lyric_saved})
    return detail


def fetch_track_online(path, fields=None):
    """在线取标签（只填空缺、不写盘），把合并后的值返回给用户确认

    与 `run_fill_tags` 的区别：这里 dry_run=True，不碰文件。用户看过之后再调
    `save_track` 落盘，避免「点一下就把标签改了」。
    """
    import tagger as tagger_service

    target = _audio_in_workspace(path)
    track = scanner.build_track(target, with_tags=True)
    service = tagger_service.Tagger(dry_run=True, write_cover=False,
                                    write_lyrics=False, fields=fields)
    result = service.update(track)
    return {
        'ok': not result.error,
        'path': target,
        'source': result.source,
        'fields': list(result.fields),
        'tags': {key: track.tag(key) for key in WORKSPACE_TAG_FIELDS},
        'error': result.error,
    }


# --------------------------------------------------------------------------- #
# 第 6 步：查重（工作区 ↔ 库目录）                                            #
# --------------------------------------------------------------------------- #

DUPLICATE_STATUS_LABELS = {'unique': '库中不存在', 'duplicate': '库中已有',
                           'upgrade': '库中音质更低', 'unknown': '需人工确认'}

# 库目录索引比较贵（上万次要 stat + 解析文件名），缓存到目录变化为止
_library_cache = {'dir': '', 'tracks': None}

# 音频规格只在命中候选后按需读取，单独缓存：重建库索引不必连带丢掉
_quality_cache = {}


def _quality_probe(track):
    """按需读取音频规格（采样率 / 位深 / 码率）

    只在「已确认是同一录音、要决定保留哪一份」时调用，通常个位数文件。
    读不出来返回空字典，上层音质比较会落到 unknown 转人工。
    """
    cached = _quality_cache.get(track.path)
    if cached is not None:
        return cached
    try:
        info = core_tags.read_quality(track.path)
    except Exception:  # noqa: BLE001 - 读不出来就降级成 unknown
        info = {}
    _quality_cache[track.path] = info
    return info


def invalidate_library_cache():
    """库目录或配置变了，丢弃查重用的两份缓存"""
    _library_cache['dir'] = ''
    _library_cache['tracks'] = None
    _quality_cache.clear()


def _library_tracks(refresh=False):
    """库目录索引：只做 stat + 从文件名解析歌手/歌名，不读标签

    库里的文件是归档流程按「歌手 - 歌名.ext」写进去的，文件名本身就是可信的
    歌手/歌名来源。为 1 万多首逐个用 mutagen 打开要十几分钟，而查重只需要
    「歌手 + 歌名 + 大小」三项，没有理由付那个代价。

    Returns:
        list[Track]，tags 只有 artist/title，duration 为 0（未读）
    """
    cached = _library_cache
    if (not refresh and cached['tracks'] is not None
            and cached['dir'] == config.LIBRARY_DIR):
        return cached['tracks']
    if not os.path.isdir(config.LIBRARY_DIR):
        return []

    tracks = []
    for path in scanner.iter_files(config.LIBRARY_DIR, recursive=True):
        if not naming.is_audio(path):
            continue
        try:
            stat = os.stat(path)
        except OSError:
            continue
        artist, title = naming.parse_filename(path)
        track = Track(path=os.path.abspath(path), size=stat.st_size,
                      mtime=stat.st_mtime)
        track.tags = {'artist': artist, 'title': title}
        tracks.append(track)

    tracks.sort(key=lambda item: item.path)
    _library_cache['dir'] = config.LIBRARY_DIR
    _library_cache['tracks'] = tracks
    return tracks


def dedupe_preview(refresh=False):
    """第 6 步：工作区文件与库目录比对，判断哪些库里已经有

    入库前必须先确认不是重复：库中已有一份的文件再归档一次，年份目录里会出现
    两条相同记录，声纹库也会重复。判定规则见 `core.dedupe.match_against`。
    """
    workspace = _workspace_tracks()
    library_tracks = _library_tracks(refresh=refresh)
    if refresh:
        # 文件可能刚被替换/移走，规格缓存跟着作废
        _quality_cache.clear()
    matches = dedupe_mod.match_against(workspace, library_tracks,
                                       probe=_quality_probe)

    items = []
    for match in matches:
        track = match.track
        problems = checker.readiness_problems(track)
        by_path = {cmp['track'].path: cmp for cmp in match.comparisons}
        matched = sorted(match.matched, key=lambda item: (item.size, item.path),
                         reverse=True)
        matched_items = []
        for other in matched[:10]:
            cmp = by_path.get(other.path) or {}
            info = cmp.get('info') or {}
            matched_items.append({
                'path': other.path, 'name': other.filename, 'dir': other.dirpath,
                'size': other.size,
                'duration': round(info.get('duration') or other.duration, 1),
                'quality': quality.describe(info),
                'relation': cmp.get('relation', ''),
            })
        # upgrade 时真正要被移走的是库里那批音质更低的文件
        replace = [entry for entry in matched_items if entry['relation'] == 'better']
        items.append({
            'path': track.path,
            'name': track.filename,
            'artist': track.artist,
            'title': track.title,
            'album': track.album,
            'year': track.year,
            'duration': round(track.duration, 1),
            'size': track.size,
            'ext': track.ext,
            'status': match.status,
            'status_label': DUPLICATE_STATUS_LABELS.get(match.status, match.status),
            'kind': match.kind,
            'reason': match.reason,
            'quality': quality.describe(match.target_info),
            'matched': matched_items,
            'matched_total': len(matched),
            'replace': replace if match.status == 'upgrade' else [],
            'problems': problems,
            'ready': not problems,
            # unique 照常入库；upgrade 的工作区文件同样要入库，只是库里旧版本先让位
            'archive_ok': match.status in ('unique', 'upgrade') and not problems,
        })

    return {
        'workspace': config.WORKSPACE_DIR,
        'library': config.LIBRARY_DIR,
        'library_exists': os.path.isdir(config.LIBRARY_DIR),
        'library_count': len(library_tracks),
        'items': items,
        'total': len(items),
        'unique': sum(1 for item in items if item['status'] == 'unique'),
        'duplicate': sum(1 for item in items if item['status'] == 'duplicate'),
        'upgrade': sum(1 for item in items if item['status'] == 'upgrade'),
        'unknown': sum(1 for item in items if item['status'] == 'unknown'),
        'replace_count': sum(len(item['replace']) for item in items),
        'ready_to_archive': sum(1 for item in items if item['archive_ok']),
    }


def run_dedupe(paths=None, action='move', refresh=False, statuses=None,
               progress=None):
    """处理确认过的重复文件

    - `duplicate`：移走**工作区**那份（库里已有同等或更好音质）
    - `upgrade`：移走**库里**那份（音质更低），工作区这份留给第 8 步归档
    - `unknown`：一律不处理，留给人工

    `upgrade` 无论 `action` 选什么，都移入 `DUPLICATE_DIR` 而不是回收站——
    动的是库里的存量文件，留一份可对照的副本比进回收站更稳妥。

    移动/删除仍走 `core.ops.Plan`，删除只是进 `log/_trash`。
    """
    logger = _log()
    wanted_statuses = set(statuses or ['duplicate'])
    # 动库目录是这条流程里风险最高的动作，不接受「不指定就全做」：
    # 必须由调用方逐条列出要替换哪些文件，避免一次误触把整个库的旧版本搬走。
    if 'upgrade' in wanted_statuses and not paths:
        raise ValueError('替换库内旧版本时必须明确指定 paths，不允许全量处理')

    preview = dedupe_preview(refresh=refresh)
    wanted = {os.path.normcase(path) for path in paths} if paths else None
    targets = [item for item in preview['items']
               if item['status'] in wanted_statuses
               and item['status'] != 'unknown'
               and (wanted is None or os.path.normcase(item['path']) in wanted)]

    if not targets:
        return {'action': action, 'planned': 0, 'executed': 0, 'failed': 0,
                'library_replaced': 0, 'items': [],
                'summary': '没有需要处理的文件'}

    plan = ops.Plan('工作区查重', dry_run=False,
                    journal_path=config.JOURNAL_PATH, trash_dir=config.TRASH_DIR)
    sides = {}
    for item in targets:
        if item['status'] == 'upgrade':
            for old in item['replace']:
                plan.add_move(old['path'],
                              os.path.join(config.DUPLICATE_DIR, old['name']),
                              f'音质更低，由工作区「{item["name"]}」替换')
                sides[os.path.normcase(old['path'])] = 'library'
            continue
        other = item['matched'][0]['name'] if item['matched'] else ''
        reason = f'库中已有：{other}' if other else item['reason']
        if action == 'trash':
            plan.add_trash(item['path'], reason)
        else:
            plan.add_move(item['path'],
                          os.path.join(config.DUPLICATE_DIR, item['name']), reason)
        sides[os.path.normcase(item['path'])] = 'workspace'

    if logger:
        logger.info(f'查重处理：{len(plan.operations)} 个文件，方式 {action}，'
                    f'其中库内替换 {sum(1 for side in sides.values() if side == "library")} 个')
    result = plan.execute()

    items = []
    for index, op in enumerate(plan.operations, 1):
        status = 'ok'
        if op in result.failed:
            status = 'failed'
        elif op in result.skipped:
            status = 'skipped'
        side = sides.get(os.path.normcase(op.src), 'workspace')
        item = {'name': os.path.basename(op.src), 'source': op.src,
                'target': op.dst, 'reason': op.reason, 'status': status,
                'side': side}
        items.append(item)
        _emit(progress, index, len(plan.operations), item)

    # upgrade 永远进重复目录，进回收站的只可能是工作区那份，所以要分开报
    destinations = []
    if any(side == 'workspace' for side in sides.values()):
        destinations.append(config.TRASH_DIR if action == 'trash'
                            else config.DUPLICATE_DIR)
    if any(side == 'library' for side in sides.values()):
        destinations.append(config.DUPLICATE_DIR)

    return {
        'action': action,
        'planned': len(plan.operations),
        'executed': len(result.done),
        'failed': len(result.failed),
        'library_replaced': sum(1 for item in items
                                if item['side'] == 'library' and item['status'] == 'ok'),
        'moved_to': '、'.join(dict.fromkeys(destinations)),
        'items': items,
        'summary': result.summary(),
    }


# --------------------------------------------------------------------------- #
# 第 7 步：工作区自检                                                         #
# --------------------------------------------------------------------------- #

def workspace_check():
    """工作区自检（只读，不动任何文件）

    检查项与库自检完全一致（同一份 `core.check`），区别是范围限在工作区顶层，
    并且把「文件名 ↔ 标签」的逐项比对结果一并返回，页面不用自己再算一遍。
    查到的问题由第 5 步（改标签）或第 8 步（未达标进待确认目录）处理。
    """
    tracks = _workspace_tracks()
    result = checker.check_library(tracks, directories=[config.WORKSPACE_DIR],
                                   check_tags=True, check_lyrics=True,
                                   check_duplicates=True)

    items = []
    for track in tracks:
        problems = checker.readiness_problems(track)
        items.append({
            'path': track.path, 'name': track.filename,
            'artist': track.artist, 'title': track.title,
            'album': track.album, 'year': track.year, 'genre': track.genre,
            'duration': round(track.duration, 1), 'size': track.size,
            'has_cover': bool(track.has_cover), 'has_lrc': track.has_lrc,
            'canonical': naming.is_canonical(track.filename),
            'consistency': checker.consistency_report(track),
            'problems': problems,
            'ready': not problems,
        })

    findings = [{
        'kind': finding.kind,
        'path': finding.path,
        'name': os.path.basename(finding.path),
        'detail': finding.detail,
        'fixable': finding.fixable,
        'severe': finding.severe,
    } for finding in result.findings]

    counts = result.counts()
    return {
        'dir': config.WORKSPACE_DIR,
        'items': items,
        'findings': findings,
        'counts': counts,
        'total': len(items),
        'ready': sum(1 for item in items if item['ready']),
        'mismatch': sum(1 for item in items if not item['consistency']['ok']),
        'not_canonical': sum(1 for item in items if not item['canonical']),
        'dup_groups': len(result.groups),
        'no_lrc': len(result.by_kind(checker.KIND_NO_LRC)),
        'orphan_lrc': len(result.by_kind(checker.KIND_ORPHAN_LRC)),
    }


# --------------------------------------------------------------------------- #
# 第 8 步：归档                                                               #
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
