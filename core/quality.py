# -*- coding: utf-8 -*-
"""
音质比较 - 同一录音的两份文件，哪一份的声音更好

用途是「工作区 ↔ 库目录」查重：确认是同一录音之后，还要回答「库里那份该不该
让位给新的这份」。只看文件大小会给出错误答案——WAV 是未压缩，体积一定比同源
FLAC 大，但两者音质完全等同；反过来 128k MP3 也可能比高压缩的 FLAC 大。

所以分两层判：
1. 无损 / 有损：无损永远更好；
2. 同一层内部：无损比「采样率 × 位深」，有损比码率（容器报的码率优先，
   拿不到才用 大小 ÷ 时长 估算）。

规格读不出来时一律返回 'unknown'，由调用方转人工——宁可少替换一次，也不要
因为读不到 header 就把库里更好的那份搬走。
"""

# 无损格式：解码结果与源 PCM 逐字节一致
LOSSLESS_EXTS = frozenset({
    '.flac', '.ape', '.wav', '.dsf', '.dff', '.aif', '.aiff', '.alac',
})

# 有损码率相差在这个比例以内视为同一水平：同一次转码的不同产物不该互相替换
BITRATE_TOLERANCE = 0.10


def is_lossless(ext):
    """扩展名是否为无损格式"""
    return (ext or '').lower() in LOSSLESS_EXTS


def _bitrate(info):
    """有效码率（bps）：优先用容器报的，否则用 大小 ÷ 时长 估算"""
    try:
        rate = float(info.get('bitrate') or 0)
    except (TypeError, ValueError):
        rate = 0.0
    if rate > 0:
        return rate
    try:
        duration = float(info.get('duration') or 0)
        size = float(info.get('size') or 0)
    except (TypeError, ValueError):
        return 0.0
    if duration > 0 and size > 0:
        return size * 8 / duration
    return 0.0


def _spec(info):
    """无损规格 (采样率, 位深)；任一项缺失返回 None"""
    try:
        rate = int(info.get('sample_rate') or 0)
        depth = int(info.get('bit_depth') or 0)
    except (TypeError, ValueError):
        return None
    if rate <= 0 or depth <= 0:
        return None
    return rate, depth


def compare(left, right):
    """left 相对 right 的音质

    Args:
        left / right: `core.tags.read_quality()` 返回的规格字典，
            至少要有 `ext`；缺 `sample_rate` / `bitrate` 时降级判 unknown。

    Returns:
        'better' / 'worse' / 'same' / 'unknown'
    """
    if not left or not right:
        return 'unknown'
    left_lossless = is_lossless(left.get('ext'))
    right_lossless = is_lossless(right.get('ext'))
    if left_lossless != right_lossless:
        return 'better' if left_lossless else 'worse'

    if left_lossless:
        left_spec, right_spec = _spec(left), _spec(right)
        if left_spec is None or right_spec is None:
            return 'unknown'
        if left_spec == right_spec:
            return 'same'
        return 'better' if left_spec > right_spec else 'worse'

    left_rate, right_rate = _bitrate(left), _bitrate(right)
    if left_rate <= 0 or right_rate <= 0:
        return 'unknown'
    if abs(left_rate - right_rate) <= max(left_rate, right_rate) * BITRATE_TOLERANCE:
        return 'same'
    return 'better' if left_rate > right_rate else 'worse'


def describe(info):
    """一句话描述音质，页面直接显示

    例：`FLAC 无损 44.1kHz/16bit`、`MP3 有损 320kbps`
    """
    if not info:
        return '—'
    ext = (info.get('ext') or '').lstrip('.').upper() or '未知格式'
    if is_lossless(info.get('ext')):
        spec = _spec(info)
        if spec:
            return f'{ext} 无损 {spec[0] / 1000:g}kHz/{spec[1]}bit'
        return f'{ext} 无损'
    rate = _bitrate(info)
    if rate > 0:
        return f'{ext} 有损 {rate / 1000:.0f}kbps'
    return f'{ext} 有损'
