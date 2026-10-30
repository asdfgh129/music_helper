# -*- coding: utf-8 -*-
"""
标签读写模块 - 合并原先 metadata.py 与 archive.py 两套实现

对外只暴露 4 个函数：
    read_tags(path)      -> dict
    write_tags(path, t)  -> bool
    has_cover(path)      -> bool
    duration(path)       -> float
"""

import os
import re

try:
    from mutagen import File as _mutagen_file
    from mutagen.apev2 import APEv2File
    from mutagen.flac import FLAC
    from mutagen.id3 import TALB, TCON, TDRC, TIT2, TPE1
    from mutagen.mp3 import MP3
    from mutagen.oggvorbis import OggVorbis
    from mutagen.wave import WAVE

    MUTAGEN_AVAILABLE = True
except ImportError:  # 没装 mutagen 时整个项目仍可启动
    MUTAGEN_AVAILABLE = False
    FLAC = MP3 = WAVE = OggVorbis = APEv2File = None
    TIT2 = TPE1 = TALB = TDRC = TCON = None

# 统一的小写标签键
TAG_KEYS = ('title', 'artist', 'album', 'year', 'genre')

_ID3_KEYS = {'title': 'TIT2', 'artist': 'TPE1', 'album': 'TALB', 'year': 'TDRC', 'genre': 'TCON'}
_VORBIS_KEYS = {'title': 'title', 'artist': 'artist', 'album': 'album', 'year': 'date', 'genre': 'genre'}
_APE_KEYS = {'title': 'Title', 'artist': 'Artist', 'album': 'Album', 'year': 'Year', 'genre': 'Genre'}


# ---------------- 读取 ----------------

def _read_id3(audio):
    tags = {}
    for key, frame in _ID3_KEYS.items():
        value = audio.get(frame)
        tags[key] = str(value) if value else ''
    return tags


def _read_vorbis(audio):
    tags = {}
    for key, field in _VORBIS_KEYS.items():
        value = audio.get(field)
        tags[key] = str(value[0]) if value else ''
    return tags


def _read_ape(audio):
    tags = {}
    for key, field in _APE_KEYS.items():
        value = audio.get(field)
        tags[key] = str(value) if value else ''
    return tags


_READERS = {}
_WRITERS = {}


def read_tags(path):
    """读取标签，失败返回空字典（不抛异常）"""
    if not MUTAGEN_AVAILABLE:
        return {}
    reader = _READERS.get(os.path.splitext(path)[1].lower())
    if reader is None:
        return {}
    loader, read = reader
    try:
        tags = read(loader(path))
    except Exception:  # noqa: BLE001 - 损坏文件不应中断批处理
        return {}

    if tags.get('year'):
        match = re.search(r'(\d{4})', tags['year'])
        tags['year'] = match.group(1) if match else ''
    return tags


# ---------------- 写入 ----------------

def _write_id3(audio, tags):
    if audio.tags is None:
        audio.add_tags()
    frames = {'title': TIT2, 'artist': TPE1, 'album': TALB, 'year': TDRC, 'genre': TCON}
    for key, frame_cls in frames.items():
        if tags.get(key):
            audio.tags[_ID3_KEYS[key]] = frame_cls(encoding=3, text=tags[key])
    audio.save()


def _write_vorbis(audio, tags):
    for key, field in _VORBIS_KEYS.items():
        if tags.get(key):
            audio[field] = tags[key]
    audio.save()


def _write_ape(audio, tags):
    for key, field in _APE_KEYS.items():
        if tags.get(key):
            audio[field] = tags[key]
    audio.save()


def write_tags(path, tags):
    """写入标签（只覆盖传入的非空字段），成功返回 True"""
    if not MUTAGEN_AVAILABLE or not tags:
        return False
    writer = _WRITERS.get(os.path.splitext(path)[1].lower())
    if writer is None:
        return False
    loader, write = writer
    try:
        write(loader(path), tags)
        return True
    except Exception:  # noqa: BLE001
        return False


# ---------------- 其他属性 ----------------

def has_cover(path):
    """是否已内嵌封面（仅 mp3 / flac 可检测）"""
    if not MUTAGEN_AVAILABLE:
        return False
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in ('.mp3', '.wav'):
            audio = (MP3 if ext == '.mp3' else WAVE)(path)
            return bool(audio.tags) and any(str(k).startswith('APIC') for k in audio.tags.keys())
        if ext == '.flac':
            return bool(FLAC(path).pictures)
    except Exception:  # noqa: BLE001
        return False
    return False


def duration(path):
    """音频时长（秒），失败返回 0.0"""
    if not MUTAGEN_AVAILABLE:
        return 0.0
    try:
        audio = _mutagen_file(path)
        return round(float(audio.info.length), 2) if audio and audio.info else 0.0
    except Exception:  # noqa: BLE001
        return 0.0


def missing_tag_fields(track):
    """标签完整性检查：返回缺失项中文名列表（歌曲名/歌手/专辑/年份/封面）"""
    labels = (('title', '歌曲名'), ('artist', '歌手'), ('album', '专辑'), ('year', '年份'))
    missing = [label for key, label in labels if not track.tag(key)]
    if not has_cover(track.path):
        missing.append('封面')
    return missing


_READERS.update({
    '.mp3': (MP3, _read_id3),
    '.wav': (WAVE, _read_id3),
    '.flac': (FLAC, _read_vorbis),
    '.ogg': (OggVorbis, _read_vorbis),
    '.ape': (APEv2File, _read_ape),
})

_WRITERS.update({
    '.mp3': (MP3, _write_id3),
    '.wav': (WAVE, _write_id3),
    '.flac': (FLAC, _write_vorbis),
    '.ogg': (OggVorbis, _write_vorbis),
    '.ape': (APEv2File, _write_ape),
})


def _guess_mime(data):
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return 'image/png'
    return 'image/jpeg'


def write_cover(path, data, desc='Cover'):
    """写入内嵌封面（mp3/wav/flac/ogg），成功返回 True"""
    if not data or not MUTAGEN_AVAILABLE:
        return False
    ext = os.path.splitext(path)[1].lower()
    mime = _guess_mime(data)
    try:
        if ext in ('.mp3', '.wav'):
            from mutagen.id3 import APIC
            audio = (MP3 if ext == '.mp3' else WAVE)(path)
            if audio.tags is None:
                audio.add_tags()
            audio.tags.add(APIC(encoding=3, mime=mime, type=3, desc=desc, data=data))
            audio.save()
            return True

        if ext in ('.flac', '.ogg'):
            import base64

            from mutagen.flac import Picture

            picture = Picture()
            picture.data = data
            picture.type = 3
            picture.mime = mime
            picture.desc = desc

            if ext == '.flac':
                audio = FLAC(path)
                audio.clear_pictures()
                audio.add_picture(picture)
            else:
                audio = OggVorbis(path)
                audio['metadata_block_picture'] = [base64.b64encode(picture.write()).decode('ascii')]
            audio.save()
            return True
    except Exception:  # noqa: BLE001 - 封面失败不影响标签
        return False
    return False

