# -*- coding: utf-8 -*-
"""
文件名规则模块 - 解析、规范化、生成音乐文件名

全项目只有这一处定义「[歌手] - [歌曲]」的解析规则，
其他模块必须复用这里，避免出现多套互相矛盾的实现。
"""

import os
import re

# Windows / Linux 均不允许出现在文件名中的字符
_ILLEGAL_CHARS = re.compile(r'[\\/:*?"<>|\r\n\t]')

# 名字里需要忽略的噪声片段（如 "(1)"、"[无损]"）
_NOISE = re.compile(r'[\[(（【][^\])）】]*[\])）】]')

_AUDIO_EXTS = {'.flac', '.mp3', '.wav', '.ape', '.ogg'}


def normalize_text(text):
    """标准化文本：去掉全部空白，转小写（用于文件名/标签一致性比较）"""
    if not text:
        return ''
    return re.sub(r'\s+', '', str(text)).lower()


def normalize_key(text):
    """标准化文本并去掉括号噪声，用于去重时的宽松比对"""
    if not text:
        return ''
    return normalize_text(_NOISE.sub('', str(text)))


def split_artist(artist):
    """拆分多艺术家字符串，返回去空后的列表"""
    if not artist:
        return []
    separators = ['；', ';', '，', ',', '&', '/', '、', '•', '·', '|', '｜', '+', '＋']
    result = [str(artist)]
    for sep in separators:
        new_result = []
        for item in result:
            new_result.extend([a.strip() for a in item.split(sep)])
        result = new_result
    return [a for a in result if a]


def parse_filename(filename):
    """解析文件名为 (artist, title)

    优先按 " - " 分割；其次在第一个 "-" 处分割；都不存在时 artist 为空。
    """
    name = os.path.splitext(os.path.basename(filename))[0]

    if ' - ' in name:
        artist, title = name.split(' - ', 1)
        return artist.strip(), title.strip()

    if '-' in name:
        artist, title = name.split('-', 1)
        return artist.strip(), title.strip()

    return '', name.strip()


def is_canonical(filename):
    """文件名是否符合「[歌手] - [歌曲]」格式"""
    artist, title = parse_filename(filename)
    return bool(artist and title and ' - ' in os.path.splitext(filename)[0])


def canonicalize(filename):
    """返回规范化的文件名；无需规范化时返回 None

    只在「恰好一个 '-' 且没有 ' - '」时改写，避免误伤 "AC-DC - Back" 这类名字。
    """
    name, ext = os.path.splitext(os.path.basename(filename))
    if ' - ' in name or name.count('-') != 1:
        return None
    left, right = name.split('-', 1)
    if not left.strip() or not right.strip():
        return None
    return f'{left.strip()} - {right.strip()}{ext}'


def sanitize_component(value):
    """清理不能用于文件名的字符"""
    if not value:
        return ''
    cleaned = _ILLEGAL_CHARS.sub('_', str(value)).strip()
    return cleaned.strip('. ')


def format_filename(artist, title, ext):
    """按「[歌手] - [歌曲]」生成文件名"""
    artist = sanitize_component(artist)
    title = sanitize_component(title)
    ext = ext if ext.startswith('.') else f'.{ext}'
    if artist and title:
        return f'{artist} - {title}{ext}'
    return f'{title or artist}{ext}'


def is_audio(filename):
    """是否为受支持的音频文件"""
    return os.path.splitext(filename)[1].lower() in _AUDIO_EXTS
