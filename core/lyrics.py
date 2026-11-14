# -*- coding: utf-8 -*-
"""歌词模块 - 合并 lrc.py / file_operations / archive.py 三套实现

除缺失 / 孤立判定外，本模块还是 LRC 读取与解析的**唯一实现**：
    lrc_path_for(path)   同名 .lrc 的实际路径（扩展名大小写不敏感）
    read_lrc_text(path)  (全文, 实际编码)，编码按 BOM / utf-8 / gb18030 回退
    parse_lrc(text)      结构化歌词（时间戳、元数据、offset、双语、逐字、纯文本降级）
    set_offset(text, ms) 改 [offset:] 后的 LRC 全文（纯文本变换，不读写文件）

Web 试听、单曲编辑与自检都复用这里，前端不再解析一遍 LRC。
"""

import os
import re

from config import AUDIO_EXTENSIONS
from core.scan import iter_files

MUSIC_EXTS = tuple(sorted(AUDIO_EXTENSIONS))
MUSIC_EXTS_SET = set(MUSIC_EXTS)
LRC_EXT = '.lrc'

# [00:12.34] / [00:12:34] / [00:12]；一行行首允许多个时间戳（合唱叠句）
_TIME_TAG_RE = re.compile(r'\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]')
# 增强 LRC 的行内（逐字）时间戳：<00:12.34> 或正文里的 [00:12.34]。
# 两组捕获并存，_tag_seconds() 按「非空分组」取 mm / ss / frac，两种写法共用一套换算。
_INLINE_TAG_RE = re.compile(
    r'<(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?>'
    r'|\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]')
_META_RE = re.compile(r'^\[\s*(ti|ar|al|by|offset|re|ve)\s*:\s*([^\]]*)\]\s*$', re.I)
_TRANS_MARK_RE = re.compile(r'^\[\s*(?:翻译|trans|translate|译文)\s*\]\s*$', re.I)
_OFFSET_RE = re.compile(r'^[+-]?\d+(?:\.\d+)?$')
_OFFSET_LINE_RE = re.compile(r'^\[\s*offset\s*:\s*[+-]?\d+(?:\.\d+)?\s*\]\s*$', re.I)

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
    """[mm:ss.xx] / <mm:ss.xx> → 秒；两位小数当百分秒，三位当毫秒

    行内正则有两组并列捕获（尖括号 / 方括号），只取非空的前三组。
    """
    parts = [group for group in match.groups() if group is not None]
    minutes = int(parts[0])
    seconds = int(parts[1])
    frac = parts[2] if len(parts) > 2 else ''
    value = minutes * 60 + seconds
    if frac:
        value += int(frac) / (10 ** len(frac))
    return round(value, 3)


def _leading_time_tags(line):
    """只认行首连续的时间戳，返回 ``(matches, 正文起点)``

    旧实现用 ``finditer`` 全文找 ``[mm:ss.xx]``，遇到增强 LRC 会把正文里的逐字
    时间戳也当成行首标签，正文只剩最后一个标签之后的几个字。行首与行内必须分开。
    """
    tags = []
    pos = 0
    while pos < len(line):
        matched = _TIME_TAG_RE.match(line, pos)
        if not matched:
            break
        tags.append(matched)
        pos = matched.end()
        while pos < len(line) and line[pos].isspace():
            pos += 1
    return tags, pos


def _split_inline(content, line_time):
    """拆增强 LRC 的正文，返回 ``(纯文本, syllables)``

    ``syllables -> [{time, text}]``，time 是该片段开始唱的秒数，片段可能是一个字、
    一个词或一句；保证 ``''.join(seg['text']) == 纯文本``，前端可以放心地只渲染片段。

    常见写法 ``<00:12.00>晴<00:12.40>天`` 与正文里的 ``晴[00:12.40]天`` 都支持。
    合唱叠句（``[00:01.00][00:31.00]`` 共用同一段逐字时间轴）里，若首个行内时间与
    行时间相差超过 1 秒，整段按差值平移，否则保留原绝对时间。
    """
    matches = list(_INLINE_TAG_RE.finditer(content))
    if not matches:
        return content, []
    first = _tag_seconds(matches[0])
    base = first if line_time is None else line_time
    delta = 0.0
    if line_time is not None and abs(line_time - first) > 1.0:
        delta = line_time - first

    segments = []
    cursor = 0
    pending = base
    for matched in matches:
        before = content[cursor:matched.start()]
        if before:
            segments.append((pending, before))
        moment = round(_tag_seconds(matched) + delta, 3)
        pending = max(pending, moment)   # 时间倒流的文件不让前端二分查错行
        cursor = matched.end()
    tail = content[cursor:]
    if tail:
        segments.append((pending, tail))

    plain = ''.join(part for _, part in segments)
    syllables = [{'time': when, 'text': part} for when, part in segments]
    return plain, syllables


def parse_lrc(text):
    """把 LRC 全文解析成结构化歌词

    返回 ``{has_timing, word_timing, offset, meta, lines, plain}``：
      lines -> [{time, text, translation, syllables}]，按时间稳定排序、去重；
      syllables -> [{time, text}]，逐字片段；普通 LRC 恒为 ``[]``；
      word_timing -> 是否至少有一行带可用的逐字时间轴（片段数 > 1）；
      offset -> 毫秒（``[offset:±N]``）；
      plain -> 去掉时间戳与元数据后的全文，供无时间戳歌词静态展示。
    """
    meta = {'ti': '', 'ar': '', 'al': '', 'by': ''}
    offset = 0
    timed = []          # 原文：(time, text, syllables)
    translated = []     # [翻译] 段：同上，但逐字时间轴不参与前端高亮
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
        tags, body_start = _leading_time_tags(line)
        content = line[body_start:].strip()
        if not tags and not _INLINE_TAG_RE.search(content):
            plain_parts.append(line)
            continue
        target = translated if in_translation else timed
        if tags:
            plain = ''
            for tag in tags:
                seconds = _tag_seconds(tag)
                plain, syllables = _split_inline(content, seconds)
                target.append((seconds, plain, syllables))
            if plain:   # 合唱叠句只记一次，保持旧版 plain 的语义
                plain_parts.append(plain)
        else:
            # 没有行首时间戳的纯逐字行：用第一个片段的时间当行时间
            plain, syllables = _split_inline(content, None)
            if syllables:
                target.append((syllables[0]['time'], plain, syllables))
            if plain:
                plain_parts.append(plain)

    # 排序 + 合并：同一时间戳的第二行视为译文，完全重复的行去掉
    lines = []
    index_of = {}
    seen = set()
    for seconds, content, syllables in sorted(timed, key=lambda item: item[0]):
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
            lines.append({'time': seconds, 'text': content,
                          'translation': '', 'syllables': syllables})

    for seconds, content, _syllables in sorted(translated, key=lambda item: item[0]):
        if seconds in index_of:
            row = lines[index_of[seconds]]
            if not row['translation']:
                row['translation'] = content
        else:
            lines.append({'time': seconds, 'text': '',
                          'translation': content, 'syllables': []})
            index_of[seconds] = len(lines) - 1
    lines.sort(key=lambda row: row['time'])

    return {
        'has_timing': bool(lines),
        'word_timing': any(len(row['syllables']) > 1 for row in lines),
        'offset': offset,
        'meta': meta,
        'lines': lines,
        'plain': '\n'.join(plain_parts),
    }


def set_offset(text, offset_ms):
    """返回把 ``[offset:N]`` 改成指定毫秒数后的 LRC 全文（纯文本变换，不读写文件）

    已有 offset 行就地替换以保留原位置；没有则插到开头的元数据之后、第一行歌词之前。
    Web 播放器的「±0.5s 微调」用这里生成新文本，再由已有的
    ``POST /api/track/save`` 落盘，媒体层不新增写接口。
    """
    source = str(text or '')
    value = int(offset_ms)
    lines = source.splitlines()
    replacement = '[offset:%d]' % value
    for index, line in enumerate(lines):
        if _OFFSET_LINE_RE.match(line.strip()):
            lines[index] = replacement
            return '\n'.join(lines) + ('\n' if source.endswith('\n') else '')
    insert_at = 0
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        if _META_RE.match(line.strip()):
            insert_at = index + 1
        else:
            break
    lines.insert(insert_at, replacement)
    return '\n'.join(lines) + '\n'


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
