# -*- coding: utf-8 -*-
"""歌词模块 - 合并 lrc.py / file_operations / archive.py 三套实现

除缺失 / 孤立判定外，本模块还是 LRC 读取与解析的**唯一实现**：
    lrc_path_for(path)   同名 .lrc 的实际路径（扩展名大小写不敏感）
    read_lrc_text(path)  (全文, 实际编码)，编码按 BOM / utf-8 / gb18030 回退
    parse_lrc(text)      结构化歌词（时间戳、元数据、offset、双语、纯文本降级）

Web 试听、单曲编辑与自检都复用这里，前端不再解析一遍 LRC。
"""

import os
import re

from config import AUDIO_EXTENSIONS
from core.scan import iter_files

MUSIC_EXTS = tuple(sorted(AUDIO_EXTENSIONS))
MUSIC_EXTS_SET = set(MUSIC_EXTS)
LRC_EXT = '.lrc'

# [00:12.34] / [00:12:34] / [00:12]；一行允许多个时间戳
_TIME_TAG_RE = re.compile(r'\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]')
_META_RE = re.compile(r'^\[\s*(ti|ar|al|by|offset|re|ve)\s*:\s*([^\]]*)\]\s*$', re.I)
_TRANS_MARK_RE = re.compile(r'^\[\s*(?:翻译|trans|translate|译文)\s*\]\s*$', re.I)
_OFFSET_RE = re.compile(r'^[+-]?\d+(?:\.\d+)?$')

# 目录清单缓存：lrc_path_for 在「精确小写 .lrc 不存在」时要扫一次目录，
# 大库扫描时不能对每个音频都 listdir 一遍。key 为目录，value 为 (mtime_ns, 映射)。
_LRC_DIR_CACHE = {}
_CACHE_LIMIT = 512


def _lrc_variants(directory):
    """目录下所有 .lrc（大小写不敏感）的 {小写主名: 实际文件名}"""
    try:
        stamp = os.stat(directory).st_mtime_ns
    except OSError:
        return {}
    cached = _LRC_DIR_CACHE.get(directory)
    if cached and cached[0] == stamp:
        return cached[1]
    variants = {}
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                stem, ext = os.path.splitext(entry.name)
                if ext.lower() == LRC_EXT and entry.is_file():
                    variants.setdefault(stem.lower(), entry.name)
    except OSError:
        return {}
    if len(_LRC_DIR_CACHE) >= _CACHE_LIMIT:
        _LRC_DIR_CACHE.clear()
    _LRC_DIR_CACHE[directory] = (stamp, variants)
    return variants


def clear_lrc_cache():
    """写入 / 移动歌词后清缓存（目录 mtime 粒度不总是可靠）"""
    _LRC_DIR_CACHE.clear()


def lrc_path_for(audio_path):
    """同名 .lrc 的实际路径；不存在时返回默认的小写 .lrc 路径（供写入用）

    与 ``orphan_lrc`` 的配对口径一致：主名与扩展名都大小写不敏感。
    """
    base = os.path.splitext(str(audio_path or ''))[0]
    if not base:
        return ''
    exact = base + LRC_EXT
    if os.path.isfile(exact):
        return exact
    directory = os.path.dirname(base) or '.'
    name = _lrc_variants(directory).get(os.path.basename(base).lower())
    return os.path.join(directory, name) if name else exact


def read_lrc_text(path):
    """读歌词全文，返回 ``(text, encoding)``；不存在或读不了返回 ``('', '')``

    编码顺序：UTF-8 BOM → UTF-8 严格 → GB18030 → UTF-8 replace 兜底。
    旧实现固定用 ``utf-8 errors=replace``，GBK 中文歌词会整篇乱码。
    """
    if not path or not os.path.isfile(path):
        return '', ''
    try:
        with open(path, 'rb') as handle:
            raw = handle.read()
    except OSError:
        return '', ''
    if raw.startswith(b'\xef\xbb\xbf'):
        return raw.decode('utf-8-sig', errors='replace'), 'utf-8-sig'
    for encoding in ('utf-8', 'gb18030'):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', errors='replace'), 'utf-8(replace)'


def _tag_seconds(match):
    """[mm:ss.xx] → 秒；两位小数当百分秒，三位当毫秒，语义都由位数决定"""
    minutes = int(match.group(1))
    seconds = int(match.group(2))
    frac = match.group(3) or ''
    value = minutes * 60 + seconds
    if frac:
        value += int(frac) / (10 ** len(frac))
    return round(value, 3)


def parse_lrc(text):
    """把 LRC 全文解析成结构化歌词

    返回 ``{has_timing, offset, meta, lines, plain}``：
      lines -> [{time: float, text: str, translation: str}]，按时间稳定排序、去重；
      offset -> 毫秒（``[offset:±N]``）；
      plain -> 去掉时间戳与元数据后的全文，供无时间戳歌词静态展示。
    """
    meta = {'ti': '', 'ar': '', 'al': '', 'by': ''}
    offset = 0
    timed = []          # 原文：(time, text)
    translated = []     # [翻译] 段：(time, text)
    plain_parts = []    # 按原文顺序，去时间戳后的展示文本
    in_translation = False

    for raw_line in str(text or '').splitlines():
        line = raw_line.strip()
        if not line:
            continue
        matched = _META_RE.match(line)
        if matched:
            key, value = matched.group(1).lower(), matched.group(2).strip()
            if key in meta:
                meta[key] = value
            elif key == 'offset' and _OFFSET_RE.match(value):
                offset = int(float(value))
            continue
        if _TRANS_MARK_RE.match(line):
            in_translation = True
            continue
        tags = list(_TIME_TAG_RE.finditer(line))
        if not tags:
            plain_parts.append(line)
            continue
        content = line[tags[-1].end():].strip()
        if content:
            plain_parts.append(content)
        target = translated if in_translation else timed
        for tag in tags:
            target.append((_tag_seconds(tag), content))

    # 排序 + 合并：同一时间戳的第二行视为译文，完全重复的行去掉
    lines = []
    index_of = {}
    seen = set()
    for seconds, content in sorted(timed, key=lambda item: item[0]):
        key = (seconds, content)
        if key in seen:
            continue
        seen.add(key)
        if seconds in index_of:
            row = lines[index_of[seconds]]
            if not row['translation']:
                row['translation'] = content
        else:
            index_of[seconds] = len(lines)
            lines.append({'time': seconds, 'text': content, 'translation': ''})

    for seconds, content in sorted(translated, key=lambda item: item[0]):
        if seconds in index_of:
            row = lines[index_of[seconds]]
            if not row['translation']:
                row['translation'] = content
        else:
            lines.append({'time': seconds, 'text': '', 'translation': content})
            index_of[seconds] = len(lines) - 1
    lines.sort(key=lambda row: row['time'])

    return {
        'has_timing': bool(lines),
        'offset': offset,
        'meta': meta,
        'lines': lines,
        'plain': '\n'.join(plain_parts),
    }


def missing_lrc(tracks):
    """缺少同名 .lrc 的曲目"""
    return [track for track in tracks if not track.has_lrc]


def orphan_lrc(directories):
    """没有对应音频文件的 .lrc 路径列表

    先一次性收集所有音频文件的「主名」，再用集合判重，避免对每首 .lrc 都做
    len(MUSIC_EXTS) 次 os.path.exists 探测（大库下是数量级的开销差）。
    """
    if isinstance(directories, (str, bytes, os.PathLike)):
        directories = [directories]

    audio_stems = set()
    lrc_paths = []
    for directory in directories:
        for path in iter_files(directory):
            lower = path.lower()
            if lower.endswith(LRC_EXT):
                lrc_paths.append(path)
            elif os.path.splitext(lower)[1] in MUSIC_EXTS_SET:
                audio_stems.add(os.path.splitext(path)[0].lower())

    return [p for p in lrc_paths
            if os.path.splitext(p)[0].lower() not in audio_stems]
