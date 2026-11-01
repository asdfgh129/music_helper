# -*- coding: utf-8 -*-
"""扫描模块 - 一次遍历建立文件索引

替代原先对同一目录反复 os.walk 4 次的实现。
"""

import os
from datetime import datetime

import core.tags as tags_reader
from core.model import Track
from core.naming import is_audio

# 不参与扫描的目录名（回收站、临时残留、隐藏目录）
SKIP_DIRS = {'_trash', '_decrypt', '.git', '__pycache__', '.sisyphus', 'unknown'}


def iter_files(directory, recursive=True):
    if not os.path.isdir(directory):
        return
    if recursive:
        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]
            for name in files:
                yield os.path.join(root, name)
    else:
        for name in os.listdir(directory):
            path = os.path.join(directory, name)
            if os.path.isfile(path):
                yield path


def month_of(path):
    """文件最后修改月份（YYYYMM）"""
    try:
        return datetime.fromtimestamp(os.path.getmtime(path)).strftime('%Y%m')
    except OSError:
        return ''


def build_track(path, with_tags=True):
    """构造 Track 对象

    with_tags=True 时只打开文件一次，同时拿到标签、时长与封面探测结果。
    """
    stat = os.stat(path)
    track = Track(
        path=os.path.abspath(path),
        size=stat.st_size,
        mtime=stat.st_mtime,
    )
    if with_tags:
        tags, duration, cover = tags_reader.read_meta(track.path)
        track.tags = tags
        track.duration = duration
        track.has_cover = cover
    return track


def scan(paths, month=None, with_tags=True, recursive=True, extensions=None):
    """扫描目录中的音频文件

    Args:
        paths: 目录或目录列表
        month: 只保留该月份（YYYYMM）修改过的文件；None 表示不过滤
        with_tags: 是否读取标签与时长（关闭可显著加速纯文件名检查）
        recursive: 是否递归子目录
        extensions: 自定义扩展名集合（默认只认普通音频，传入 VIP 扩展名可扫描加密文件）

    Returns:
        list[Track]，按路径去重并排序
    """
    if isinstance(paths, (str, bytes, os.PathLike)):
        paths = [paths]

    wanted = {ext.lower() for ext in extensions} if extensions else None
    seen = set()
    tracks = []
    for directory in paths:
        for path in iter_files(directory, recursive=recursive):
            if wanted is not None:
                if os.path.splitext(path)[1].lower() not in wanted:
                    continue
            elif not is_audio(path):
                continue
            real = os.path.abspath(path)
            if real in seen:
                continue
            if month and month_of(real) != month:
                continue
            seen.add(real)
            try:
                tracks.append(build_track(real, with_tags=with_tags))
            except OSError:
                continue

    tracks.sort(key=lambda t: t.path)
    return tracks
