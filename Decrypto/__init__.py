# -*- coding: utf-8 -*-
"""
Decrypto 模块 - QQ 音乐解密工具
提供 QQ 音乐加密音频文件的解密和转换功能
"""

from .qq import run_decrypt, list_download_songs
from .source_finder import guess_song_url, parse_filename_to_artist_title

__all__ = [
    'run_decrypt',
    'list_download_songs',
    'guess_song_url',
    'parse_filename_to_artist_title',
]
