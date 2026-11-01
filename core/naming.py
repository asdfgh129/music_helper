# -*- coding: utf-8 -*-
"""
文件名规则模块 - 解析、规范化、生成音乐文件名

全项目只有这一处定义「[歌手] - [歌曲]」的解析规则，
其他模块必须复用这里，避免出现多套互相矛盾的实现。
"""

import os
import re

from config import AUDIO_EXTENSIONS

# Windows / Linux 均不允许出现在文件名中的字符
_ILLEGAL_CHARS = re.compile(r'[\\/:*?"<>|\r\n\t]')

# 名字里需要忽略的噪声片段（如 "(1)"、"[无损]"）
_NOISE = re.compile(r'[\[(（【][^\])）】]*[\])）】]')

# 括号内容，用于识别「版本标记」
_BRACKET = re.compile(r'[\[(（【]([^\])）】]*)[\])）】]')

# 同一个歌名下，这些标记代表不同的录音/版本，不能互相判重。
# 左值是归一化后的版本类别，右值是识别用的同义词。
_VERSION_ALIASES = (
    ('live', ('live', '现场', '演唱会', 'concert')),
    ('remix', ('remix', '混音', 'dj', 'bootleg', 'rework')),
    ('instrumental', ('instrumental', '伴奏', 'karaoke', 'offvocal', '纯音乐')),
    ('acoustic', ('acoustic', 'unplugged', '不插电')),
    ('demo', ('demo', '小样', 'session', 'outtake', '未发行')),
    ('cover', ('cover', '翻唱')),
    ('feat', ('feat', 'featuring', 'ft.', 'ft ')),
)

_AUDIO_EXTS = AUDIO_EXTENSIONS


def normalize_text(text):
    """标准化文本：去掉全部空白，转小写（用于文件名/标签一致性比较）"""
    if not text:
        return ''
    return re.sub(r'\s+', '', str(text)).lower()


def normalize_key(text):
    """标准化文本并去掉括号噪声，用于宽松比对"""
    if not text:
        return ''
    return normalize_text(_NOISE.sub('', str(text)))


def _normalize_marker(text):
    """版本词匹配：去掉空白与常见标点，避免 ft. / ft 之类的写法差异"""
    return re.sub(r'[\s._\-·•]+', '', str(text).lower())


def version_markers(text):
    """提取文本中的版本标记类别，例如 live / remix / instrumental / feat"""
    if not text:
        return ()
    found = []
    for group in _BRACKET.findall(str(text)):
        probe = _normalize_marker(group)
        for canonical, aliases in _VERSION_ALIASES:
            if any(_normalize_marker(alias) in probe for alias in aliases):
                found.append(canonical)
                break
    return tuple(sorted(set(found)))


def version_key(text):
    """去重键：保留版本标记，去掉下载序号和其他无关括号内容

    "晴天"            -> "晴天"
    "晴天 (1)"        -> "晴天"
    "晴天 (Live)"     -> "晴天|live"
    "晴天（现场版）"  -> "晴天|live"
    "晴天 (Remix)"    -> "晴天|remix"
    """
    if not text:
        return ''
    raw = str(text)
    markers = version_markers(raw)
    base = normalize_text(_BRACKET.sub('', raw))
    return f'{base}|{",".join(markers)}' if markers else base


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


# 合辑/未知歌手这类占位串没有可比性，一致性检查遇到时应放弃该维度而不是判矛盾
_PLACEHOLDER_ARTISTS = frozenset({
    'variousartists', 'various', 'va', '群星', '合集', '合辑', '精选集',
    'unknown', 'unknownartist', '未知', '未知艺人', '佚名', 'anonymous',
})


def is_placeholder_artist(text):
    """是否为「群星/未知」这类占位歌手名

    `合辑`里每个文件的标签歌手都是 `Various Artists`，而文件名通常是具体歌手；
    这类差异不是错误，按矛盾处理会把整张合辑搬进待补全目录。
    """
    if not text:
        return False
    entries = split_artist(text) or [str(text)]
    return all(normalize_text(name) in _PLACEHOLDER_ARTISTS for name in entries)


def artist_tokens(artist):
    """把歌手串拆成可比较的 token 集合

    收录三种写法：拆分后的每个歌手、去掉别名括号的主名、括号里的别名。
    `周杰伦 (Jay Chou)` -> {'周杰伦(jaychou)', '周杰伦', 'jaychou'}
    """
    tokens = set()
    for name in split_artist(artist):
        norm = normalize_text(name)
        if norm:
            tokens.add(norm)
        base = normalize_text(_BRACKET.sub('', name))
        if base:
            tokens.add(base)
        for inner in _BRACKET.findall(name):
            for part in split_artist(inner):
                norm_inner = normalize_text(part)
                if norm_inner:
                    tokens.add(norm_inner)
    return tokens



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
