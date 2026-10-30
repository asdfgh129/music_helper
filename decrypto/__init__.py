# -*- coding: utf-8 -*-
"""decrypto - QQ 音乐解密（Frida 注入 + 来源检索）

对外只暴露四个入口，具体编排在 services/decrypt.py；包名统一小写，与 core/services 一致。
"""

from .qq import run_decrypt, list_download_songs
from .source_finder import guess_song_url, parse_filename_to_artist_title

__all__ = [
    'run_decrypt',
    'list_download_songs',
    'guess_song_url',
    'parse_filename_to_artist_title',
]
