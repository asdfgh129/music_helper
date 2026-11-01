# -*- coding: utf-8 -*-
"""
标签读写模块 - 合并原先 metadata.py 与 archive.py 两套实现

对外主要接口：
    read_meta(path)          -> (tags, duration, has_cover)  一次打开，扫描阶段用
    read_tags(path)          -> dict
    write_tags(path, t)      -> bool
    has_cover(path)          -> bool
    duration(path)           -> float
    missing_tag_fields(track) -> list
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
    _mutagen_file = None
    FLAC = MP3 = WAVE = OggVorbis = APEv2File = None
    TIT2 = TPE1 = TALB = TDRC = TCON = None

# 以下是加分格式：老版本 mutagen 缺某个模块时只少支持一种格式，
# 不能让整块降级（否则一个可选格式会拖垮全部标签读取）
try:
    from mutagen.mp4 import MP4
except ImportError:  # pragma: no cover - 取决于安装的 mutagen 版本
    MP4 = None
try:
    from mutagen.oggopus import OggOpus
except ImportError:  # pragma: no cover
    OggOpus = None
try:
    from mutagen.asf import ASF
except ImportError:  # pragma: no cover
    ASF = None
try:
    from mutagen.dsf import DSF
except ImportError:  # pragma: no cover
    DSF = None

# 统一的小写标签键
TAG_KEYS = ('title', 'artist', 'album', 'year', 'genre')

_ID3_KEYS = {'title': 'TIT2', 'artist': 'TPE1', 'album': 'TALB', 'year': 'TDRC', 'genre': 'TCON'}
_VORBIS_KEYS = {'title': 'title', 'artist': 'artist', 'album': 'album', 'year': 'date', 'genre': 'genre'}
_APE_KEYS = {'title': 'Title', 'artist': 'Artist', 'album': 'Album', 'year': 'Year', 'genre': 'Genre'}
_MP4_KEYS = {'title': '\xa9nam', 'artist': '\xa9ART', 'album': '\xa9alb',
             'year': '\xa9day', 'genre': '\xa9gen'}
_ASF_KEYS = {'title': 'Title', 'artist': 'Author', 'album': 'WM/AlbumTitle',
             'year': 'WM/Year', 'genre': 'WM/Genre'}


# ---------------- 读取 ----------------

def _first(value):
    """容器类标签（Vorbis / MP4 / ASF）取第一个值"""
    if not value:
        return ''
    if isinstance(value, (list, tuple)):
        return str(value[0]) if value else ''
    return str(value)


def _read_id3(audio):
    tags = {}
    for key, frame in _ID3_KEYS.items():
        value = audio.get(frame)
        tags[key] = str(value) if value else ''
    return tags


def _read_vorbis(audio):
    tags = {}
    for key, field in _VORBIS_KEYS.items():
        tags[key] = _first(audio.get(field))
    return tags


def _read_ape(audio):
    tags = {}
    for key, field in _APE_KEYS.items():
        tags[key] = _first(audio.get(field))
    return tags


def _read_mp4(audio):
    tags = {}
    for key, field in _MP4_KEYS.items():
        tags[key] = _first(audio.get(field))
    return tags


def _read_asf(audio):
    tags = {}
    for key, field in _ASF_KEYS.items():
        tags[key] = _first(audio.get(field))
    return tags


# 格式 -> (加载器, 读取器)；加载器为 None 表示当前 mutagen 不支持该格式
_READERS = {
    '.mp3': (MP3, _read_id3),
    '.wav': (WAVE, _read_id3),
    '.flac': (FLAC, _read_vorbis),
    '.ogg': (OggVorbis, _read_vorbis),
    '.ape': (APEv2File, _read_ape),
    '.opus': (OggOpus, _read_vorbis),
    '.m4a': (MP4, _read_mp4),
    '.wma': (ASF, _read_asf),
    '.dsf': (DSF, _read_id3),
}

def _reader_for(ext):
    entry = _READERS.get(ext)
    if not entry or entry[0] is None:
        return None
    return entry


def _normalize_year(tags):
    if tags.get('year'):
        match = re.search(r'(\d{4})', tags['year'])
        tags['year'] = match.group(1) if match else ''
    return tags


def read_tags(path):
    """读取标签，失败返回空字典（不抛异常）"""
    return read_meta(path)[0]


def read_meta(path):
    """一次打开读出 (tags, duration, has_cover)

    分别调用 read_tags / duration / has_cover 会把同一个文件完整解析三遍；
    扫描阶段每个文件只需要一遍。
    """
    empty = ({}, 0.0, False)
    if not MUTAGEN_AVAILABLE:
        return empty
    ext = os.path.splitext(path)[1].lower()
    reader = _reader_for(ext)
    if reader is None:
        return empty

    try:
        audio = _mutagen_file(path)
    except Exception:  # noqa: BLE001 - 损坏文件不应中断批处理
        return empty
    if audio is None:
        return empty

    try:
        tags = _normalize_year(reader[1](audio))
    except Exception:  # noqa: BLE001
        tags = {}

    try:
        length = audio.info.length if audio.info else 0.0
        duration = round(float(length), 2)
    except Exception:  # noqa: BLE001
        duration = 0.0

    try:
        cover = bool(_COVER_READERS[ext](audio))
    except Exception:  # noqa: BLE001
        cover = False

    return tags, duration, cover


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


def _write_mp4(audio, tags):
    for key, field in _MP4_KEYS.items():
        if tags.get(key):
            audio[field] = [tags[key]]
    audio.save()


def _write_asf(audio, tags):
    for key, field in _ASF_KEYS.items():
        if tags.get(key):
            audio[field] = tags[key]
    audio.save()


# 格式 -> (加载器, 写入器)；定义在写入函数之后，避免前向引用
_WRITERS = {
    '.mp3': (MP3, _write_id3),
    '.wav': (WAVE, _write_id3),
    '.flac': (FLAC, _write_vorbis),
    '.ogg': (OggVorbis, _write_vorbis),
    '.ape': (APEv2File, _write_ape),
    '.opus': (OggOpus, _write_vorbis),
    '.m4a': (MP4, _write_mp4),
    '.wma': (ASF, _write_asf),
    '.dsf': (DSF, _write_id3),
}


def write_tags(path, tags):
    """写入标签（只覆盖传入的非空字段），成功返回 True"""
    if not MUTAGEN_AVAILABLE or not tags:
        return False
    entry = _WRITERS.get(os.path.splitext(path)[1].lower())
    if not entry or entry[0] is None or entry[1] is None:
        return False
    loader, writer = entry
    try:
        writer(loader(path), tags)
        return True
    except Exception:  # noqa: BLE001
        return False


# ---------------- 封面 ----------------

def _cover_id3(audio):
    return bool(audio.tags) and any(str(k).startswith('APIC') for k in audio.tags.keys())


def _cover_flac(audio):
    return bool(getattr(audio, 'pictures', None))


def _cover_vorbis(audio):
    """ogg / opus 的内嵌封面存在 Vorbis 注释里（base64 的 FLAC picture block）"""
    return bool(audio.get('metadata_block_picture'))


def _cover_ape(audio):
    return any(str(key).lower().startswith('cover art') for key in (audio.tags or {}))


def _cover_mp4(audio):
    return bool(audio.tags and audio.tags.get('covr'))


def _cover_asf(audio):
    return bool(audio.tags and audio.tags.get('WM/Picture'))


_COVER_READERS = {
    '.mp3': _cover_id3,
    '.wav': _cover_id3,
    '.dsf': _cover_id3,
    '.flac': _cover_flac,
    '.ogg': _cover_vorbis,
    '.opus': _cover_vorbis,
    '.ape': _cover_ape,
    '.m4a': _cover_mp4,
    '.wma': _cover_asf,
}


def has_cover(path):
    """是否已内嵌封面

    只认内嵌，不认同目录的 cover.jpg：补封面写的是内嵌图，
    判定也应看同一个位置，否则「报告说没有、工具认为已有」会互相打脸。
    """
    if not MUTAGEN_AVAILABLE:
        return False
    ext = os.path.splitext(path)[1].lower()
    reader = _reader_for(ext)
    cover = _COVER_READERS.get(ext)
    if reader is None or cover is None:
        return False
    try:
        return bool(cover(reader[0](path)))
    except Exception:  # noqa: BLE001
        return False


# ---------------- 其他属性 ----------------

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
    """标签完整性检查：返回缺失项中文名列表（歌曲名/歌手/专辑/年份/封面）

    优先用扫描阶段缓存的封面结果，避免为了一行报告把文件再解析一遍。
    """
    labels = (('title', '歌曲名'), ('artist', '歌手'), ('album', '专辑'), ('year', '年份'))
    missing = [label for key, label in labels if not track.tag(key)]
    cached = getattr(track, 'has_cover', None)
    cover = has_cover(track.path) if cached is None else cached
    if not cover:
        missing.append('封面')
    return missing


def _guess_mime(data):
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return 'image/png'
    return 'image/jpeg'


def write_cover(path, data, desc='Cover'):
    """写入内嵌封面（mp3/wav/flac/ogg/opus/m4a），成功返回 True"""
    if not data or not MUTAGEN_AVAILABLE:
        return False
    ext = os.path.splitext(path)[1].lower()
    mime = _guess_mime(data)
    try:
        if ext in ('.mp3', '.wav', '.dsf'):
            from mutagen.id3 import APIC
            loader = {'.mp3': MP3, '.wav': WAVE, '.dsf': DSF}.get(ext)
            if loader is None:
                return False
            audio = loader(path)
            if audio.tags is None:
                audio.add_tags()
            audio.tags.add(APIC(encoding=3, mime=mime, type=3, desc=desc, data=data))
            audio.save()
            return True

        if ext == '.m4a':
            if MP4 is None:
                return False
            from mutagen.mp4 import MP4Cover

            audio = MP4(path)
            fmt = MP4Cover.FORMAT_PNG if mime == 'image/png' else MP4Cover.FORMAT_JPEG
            audio['covr'] = [MP4Cover(data, imageformat=fmt)]
            audio.save()
            return True

        if ext in ('.flac', '.ogg', '.opus'):
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
                loader = OggVorbis if ext == '.ogg' else OggOpus
                if loader is None:
                    return False
                audio = loader(path)
                audio['metadata_block_picture'] = [base64.b64encode(picture.write()).decode('ascii')]
            audio.save()
            return True
    except Exception:  # noqa: BLE001 - 封面失败不影响标签
        return False
    return False
