# -*- coding: utf-8 -*-
"""歌词文件模块 - 合并 lrc.py / file_operations / archive.py 三套实现"""

import os

from config import AUDIO_EXTENSIONS
from core.scan import iter_files

MUSIC_EXTS = tuple(sorted(AUDIO_EXTENSIONS))


def missing_lrc(tracks):
    """缺少同名 .lrc 的曲目"""
    return [track for track in tracks if not track.has_lrc]


def orphan_lrc(directories):
    """没有对应音频文件的 .lrc 路径列表"""
    if isinstance(directories, (str, bytes, os.PathLike)):
        directories = [directories]

    orphans = []
    for directory in directories:
        for path in iter_files(directory):
            if not path.lower().endswith('.lrc'):
                continue
            stem = os.path.splitext(path)[0]
            if not any(os.path.exists(stem + ext) for ext in MUSIC_EXTS):
                orphans.append(path)
    return orphans
