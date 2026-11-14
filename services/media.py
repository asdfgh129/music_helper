# -*- coding: utf-8 -*-
"""Web 试听的只读媒体层

只做五件事：路径白名单、Range 参数解析、分块迭代、只读元数据与歌词封面、
LRC 纯文本变换。**不写任何文件**，不生成 ``core.ops.Plan``，不进
``web/tasks.py`` 串行队列。歌词落盘仍只走 ``services.steps.save_track()``。

本模块只依赖标准库 + ``config`` / ``core``，不 import Web 框架：组装
``StreamingResponse`` 是 ``web/api.py`` 的职责。契约见 docs/media-player.md。
"""

import os
import re

import config
import core.lyrics as lyrics
import core.tags as tags_reader

# 必须覆盖 config.AUDIO_EXTENSIONS 全集；tests/test_media.py 有断言。
# 新增音频格式时漏了这里，试听会把内容标成 application/octet-stream。
MEDIA_MIME = {
    '.mp3': 'audio/mpeg',
    '.flac': 'audio/flac',
    '.wav': 'audio/wav',
    '.m4a': 'audio/mp4',
    '.ogg': 'audio/ogg',
    '.opus': 'audio/ogg',
    '.ape': 'audio/x-ape',
    '.wma': 'audio/x-ms-wma',
    '.dsf': 'audio/dsf',
}

BROWSER_PLAYABLE = frozenset({
    '.mp3', '.flac', '.wav', '.m4a', '.ogg', '.opus',
})

NOT_PLAYABLE_REASON = {
    '.ape': 'Monkey\'s Audio (.ape)：浏览器无法解码此格式',
    '.wma': 'Windows Media Audio (.wma)：浏览器无法解码此格式（带 DRM 的更无法处理）',
    '.dsf': 'DSD/DSF (.dsf)：浏览器无法解码 1bit DSD 流',
}

CHUNK_SIZE = 1024 * 1024
_RANGE_RE = re.compile(r'^(\d*)-(\d*)$')


class MediaError(ValueError):
    """路径或格式不合法 → HTTP 400"""


class RangeError(ValueError):
    """Range 头不合法或越界 → HTTP 416"""


def mime_for(path):
    return MEDIA_MIME.get(os.path.splitext(str(path or ''))[1].lower(),
                          'application/octet-stream')


def allowed_roots():
    """允许试听的目录（config 声明的那些），返回 realpath 后的元组

    归档后文件在库目录的 ``<年代>/<年份>`` 子目录里，用 commonpath 递归覆盖，
    不必把每种子目录都列出来。
    """
    names = (
        'LIBRARY_DIR', 'WORKSPACE_DIR', 'INCOMPLETE_DIR', 'DUPLICATE_DIR',
        'NETEASE_DIR', 'NETEASE_VIP_DIR', 'QQ_DIR', 'QQ_VIP_DIR',
        'DECRYPT_STAGING_DIR',
    )
    roots = []
    for name in names:
        value = getattr(config, name, '')
        if not value:
            continue
        try:
            roots.append(os.path.realpath(os.path.abspath(value)))
        except OSError:  # pragma: no cover - 路径本身坏掉时跳过
            continue
    return tuple(dict.fromkeys(roots))


def _in_allowed_dir(target, roots):
    for root in roots:
        try:
            if os.path.commonpath([target, root]) == root:
                return True
        except ValueError:
            # 不同盘符（Windows）会抛，换下一个根目录继续比
            continue
    return False


def in_workspace(target):
    """是否落在工作区内：决定前端能否显示「歌词偏移写回」按钮

    与 ``services.steps._audio_in_workspace`` 用的是同一套 commonpath 口径；
    这里不 import steps，避免只读媒体层被八步编排的依赖拖进来。
    """
    root = getattr(config, 'WORKSPACE_DIR', '')
    if not root:
        return False
    return _in_allowed_dir(target,
                           (os.path.realpath(os.path.abspath(root)),))


def resolve_media(path):
    """校验并返回可直接 open 的绝对路径，不合法一律抛 MediaError

    顺序：非空 → 绝对路径 → realpath（防符号链接逃逸）→ 扩展名白名单
    → commonpath 落在允许目录 → 必须是普通文件。
    """
    raw = str(path or '').strip()
    if not raw:
        raise MediaError('缺少 path 参数')
    if not os.path.isabs(raw):
        raise MediaError('path 必须是绝对路径')
    target = os.path.realpath(os.path.abspath(raw))
    ext = os.path.splitext(target)[1].lower()
    if ext not in config.AUDIO_EXTENSIONS:
        raise MediaError(f'不是受支持的音频文件: {ext or "(无扩展名)"}')
    if not _in_allowed_dir(target, allowed_roots()):
        raise MediaError('文件不在允许试听的目录内（库 / 工作区 / 下载 / 结果目录）')
    if not os.path.isfile(target):
        raise MediaError('文件不存在或不是普通文件')
    return target


def parse_range(header, size):
    """解析单段 Range，返回 ``(start, end, partial)``（闭区间）

    支持 ``bytes=start-end`` / ``bytes=start-`` / ``bytes=-N``；多段只取第一段
    （单流播放不需要 multipart）。无 Range 返回全文且 ``partial=False``。
    """
    if size <= 0:
        raise RangeError('空文件不支持 Range')
    if not header:
        return 0, size - 1, False
    value = str(header).strip()
    if not value.lower().startswith('bytes='):
        raise RangeError(f'只支持 bytes 单位的 Range: {value}')
    spec = value[6:].split(',')[0].strip()
    matched = _RANGE_RE.match(spec)
    if not matched:
        raise RangeError(f'Range 语法不合法: {value}')
    start_text, end_text = matched.group(1), matched.group(2)
    if not start_text and not end_text:
        raise RangeError(f'Range 语法不合法: {value}')
    if not start_text:
        length = int(end_text)
        if length <= 0:
            raise RangeError('后缀长度必须大于 0')
        return max(0, size - length), size - 1, True
    start = int(start_text)
    end = int(end_text) if end_text else size - 1
    if start > end:
        raise RangeError('Range 的 start 不能大于 end')
    end = min(end, size - 1)
    if start >= size:
        raise RangeError(f'Range 越界: start={start}, size={size}')
    return start, end, True


def iter_chunks(path, start, end):
    """按 1 MiB 同步生成字节块；由 StreamingResponse 在线程池里迭代"""
    remaining = end - start + 1
    with open(path, 'rb') as handle:
        handle.seek(start)
        while remaining > 0:
            chunk = handle.read(min(CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def media_info(target):
    """试听前的只读元数据（duration / 封面 / 歌词状态只用于展示，不参与判定）"""
    ext = os.path.splitext(target)[1].lower()
    stat = os.stat(target)
    try:
        duration = round(float(tags_reader.duration(target)), 2)
        has_cover = bool(tags_reader.has_cover(target))
    except Exception:  # noqa: BLE001 - 标签库异常不该让试听整个挂掉
        duration, has_cover = 0.0, False
    return {
        'path': target,
        'name': os.path.basename(target),
        'ext': ext,
        'mime': mime_for(target),
        'size': stat.st_size,
        'duration': duration,
        'browser_playable': ext in BROWSER_PLAYABLE,
        'playable_reason': NOT_PLAYABLE_REASON.get(ext, ''),
        'has_lrc': os.path.isfile(lyrics.lrc_path_for(target)),
        'has_cover': has_cover,
        'writable': in_workspace(target),
    }


def cover_payload(target):
    """内嵌封面 -> ``(bytes, mime)``；没有返回 ``(None, '')``

    与 ``has_cover()`` 同源分派，只读，不找同目录的 cover.jpg。
    """
    return tags_reader.read_cover(target)


def lyric_payload(target):
    """结构化歌词；解析口径的唯一实现是 core.lyrics.parse_lrc

    ``raw`` 是编码探测后的 LRC 全文，供 P1 的 offset 微调生成新文本，
    前端不自己做 LRC 解析。
    """
    lrc_path = lyrics.lrc_path_for(target)
    text, encoding = lyrics.read_lrc_text(lrc_path)
    return {
        'ok': True,
        'exists': os.path.isfile(lrc_path),
        'encoding': encoding,
        'raw': text,
        **lyrics.parse_lrc(text),
    }


def parse_lyric_text(text):
    """编辑抽屉的实时预览：纯文本 -> 结构化歌词，不读写任何文件"""
    return {'ok': True, **lyrics.parse_lrc(text)}


def lyric_with_offset(text, offset_ms):
    """偏移微调：返回改写后的 LRC 全文，由前端交给 POST /api/track/save 落盘

    限幅 ±60 秒，避免一次误点击把歌词整体推到音轨之外。
    """
    value = max(-60000, min(60000, int(offset_ms)))
    return {'ok': True, 'text': lyrics.set_offset(text, value), 'offset': value}
