# -*- coding: utf-8 -*-
"""
元数据读写模块 - 音乐文件元数据读取和写入
"""

import os
import re
from config import (
    mutagen_available, MP3, FLAC, WAVE, APEv2File, OggVorbis,
    TIT2, TPE1, TALB, TDRC, TCON
)
from utils import main_logger


def get_music_metadata(filepath):
    """获取音乐文件元数据"""
    if not mutagen_available:
        return None

    try:
        ext = os.path.splitext(filepath)[1].lower()

        if ext == '.mp3':
            audio = MP3(filepath)
            year = str(audio.get('TDRC', '')) if audio.get('TDRC') else ''
            tags = {
                'title': str(audio.get('TIT2', '')) if audio.get('TIT2') else '',
                'artist': str(audio.get('TPE1', '')) if audio.get('TPE1') else '',
                'album': str(audio.get('TALB', '')) if audio.get('TALB') else '',
                'year': year,
                'genre': str(audio.get('TCON', '')) if audio.get('TCON') else ''
            }
        elif ext == '.flac':
            audio = FLAC(filepath)
            tags = {
                'title': audio.get('title', [''])[0] if audio.get('title') else '',
                'artist': audio.get('artist', [''])[0] if audio.get('artist') else '',
                'album': audio.get('album', [''])[0] if audio.get('album') else '',
                'year': audio.get('date', [''])[0] if audio.get('date') else '',
                'genre': audio.get('genre', [''])[0] if audio.get('genre') else ''
            }
        elif ext == '.wav':
            audio = WAVE(filepath)
            tags = {
                'title': str(audio.get('TIT2', '')) if audio.get('TIT2') else '',
                'artist': str(audio.get('TPE1', '')) if audio.get('TPE1') else '',
                'album': str(audio.get('TALB', '')) if audio.get('TALB') else '',
                'year': str(audio.get('TDRC', '')) if audio.get('TDRC') else '',
                'genre': str(audio.get('TCON', '')) if audio.get('TCON') else ''
            }
        elif ext == '.ape':
            audio = APEv2File(filepath)
            tags = {
                'title': str(audio.get('Title', '')) if audio.get('Title') else '',
                'artist': str(audio.get('Artist', '')) if audio.get('Artist') else '',
                'album': str(audio.get('Album', '')) if audio.get('Album') else '',
                'year': str(audio.get('Year', '')) if audio.get('Year') else '',
                'genre': str(audio.get('Genre', '')) if audio.get('Genre') else ''
            }
        elif ext == '.ogg':
            audio = OggVorbis(filepath)
            tags = {
                'title': audio.get('title', [''])[0] if audio.get('title') else '',
                'artist': audio.get('artist', [''])[0] if audio.get('artist') else '',
                'album': audio.get('album', [''])[0] if audio.get('album') else '',
                'year': audio.get('date', [''])[0] if audio.get('date') else '',
                'genre': audio.get('genre', [''])[0] if audio.get('genre') else ''
            }
        else:
            return None

        # 提取年份的前4位数字
        if tags['year']:
            year_match = re.search(r'(\d{4})', str(tags['year']))
            if year_match:
                tags['year'] = year_match.group(1)

        return tags
    except Exception as e:
        main_logger.error(f'读取元数据失败 {filepath}: {e}')
        return None


def set_music_metadata(filepath, tags):
    """设置音乐文件元数据"""
    if not mutagen_available:
        return False

    try:
        ext = os.path.splitext(filepath)[1].lower()

        if ext == '.mp3':
            try:
                audio = MP3(filepath)
            except Exception:
                audio = MP3()
                audio.save(filepath)
                audio = MP3(filepath)

            if audio.tags is None:
                audio.add_tags()

            if tags.get('title'):
                audio.tags['TIT2'] = TIT2(encoding=3, text=tags['title'])
            if tags.get('artist'):
                audio.tags['TPE1'] = TPE1(encoding=3, text=tags['artist'])
            if tags.get('album'):
                audio.tags['TALB'] = TALB(encoding=3, text=tags['album'])
            if tags.get('year'):
                audio.tags['TDRC'] = TDRC(encoding=3, text=tags['year'])
            if tags.get('genre'):
                audio.tags['TCON'] = TCON(encoding=3, text=tags['genre'])

            audio.save()

        elif ext == '.flac':
            audio = FLAC(filepath)
            if tags.get('title'):
                audio['title'] = tags['title']
            if tags.get('artist'):
                audio['artist'] = tags['artist']
            if tags.get('album'):
                audio['album'] = tags['album']
            if tags.get('year'):
                audio['date'] = tags['year']
            if tags.get('genre'):
                audio['genre'] = tags['genre']
            audio.save()

        elif ext == '.wav':
            audio = WAVE(filepath)
            if audio.tags is None:
                audio.add_tags()
            if tags.get('title'):
                audio.tags['TIT2'] = TIT2(encoding=3, text=tags['title'])
            if tags.get('artist'):
                audio.tags['TPE1'] = TPE1(encoding=3, text=tags['artist'])
            if tags.get('album'):
                audio.tags['TALB'] = TALB(encoding=3, text=tags['album'])
            if tags.get('year'):
                audio.tags['TDRC'] = TDRC(encoding=3, text=tags['year'])
            if tags.get('genre'):
                audio.tags['TCON'] = TCON(encoding=3, text=tags['genre'])
            audio.save()

        elif ext == '.ogg':
            audio = OggVorbis(filepath)
            if tags.get('title'):
                audio['title'] = tags['title']
            if tags.get('artist'):
                audio['artist'] = tags['artist']
            if tags.get('album'):
                audio['album'] = tags['album']
            if tags.get('year'):
                audio['date'] = tags['year']
            if tags.get('genre'):
                audio['genre'] = tags['genre']
            audio.save()

        else:
            return False

        return True
    except Exception as e:
        main_logger.error(f'写入元数据失败 {filepath}: {e}')
        return False
