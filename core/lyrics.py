# -*- coding: utf-8 -*-
"""歌词文件模块 - 合并 lrc.py / file_operations / archive.py 三套实现"""

import os

from config import AUDIO_EXTENSIONS
from core.scan import iter_files

MUSIC_EXTS = tuple(sorted(AUDIO_EXTENSIONS))
MUSIC_EXTS_SET = set(MUSIC_EXTS)


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
            if lower.endswith('.lrc'):
                lrc_paths.append(path)
            elif os.path.splitext(lower)[1] in MUSIC_EXTS_SET:
                audio_stems.add(os.path.splitext(path)[0].lower())

    return [p for p in lrc_paths
            if os.path.splitext(p)[0].lower() not in audio_stems]
