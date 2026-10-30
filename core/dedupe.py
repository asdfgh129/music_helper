# -*- coding: utf-8 -*-
"""
重复判定模块 - 实现规划中的模块 5

判定规则（与 项目规划.md 一致）：
1. 标签维度：歌手 + 歌名 相同，且时长相差不超过 TOLERANCE 秒；
2. 文件名维度：去掉 (1)(2)(3) 后缀后同名，且时长相差不超过 TOLERANCE 秒；
3. 时长未知（读取失败）时，只要名称一致即视为候选，但会在报告中标注「时长未知」。

保留策略：优先无损格式，其次文件更大者（同格式下通常码率更高）。
"""

import os
import re
from dataclasses import dataclass, field

DURATION_TOLERANCE = 3.0

# 数值越大越优先保留
_QUALITY = {'.flac': 5, '.wav': 4, '.ape': 4, '.ogg': 3, '.mp3': 2}

_SUFFIX = re.compile(r'\s*[\(（]\s*(\d+)\s*[\)）]\s*$')


@dataclass
class DuplicateGroup:
    """一组判定为重复的曲目"""

    kind: str
    key: object
    tracks: list = field(default_factory=list)
    keep: object = None
    drop: list = field(default_factory=list)
    duration_unknown: bool = False

    def describe(self):
        kept = f'{self.keep.filename} ({self.keep.ext})' if self.keep else '-'
        return f'{self.kind} | {self.key} | 保留 {kept} | 待处理 {len(self.drop)}'


def _rank(track):
    return (_QUALITY.get(track.ext, 0), track.size)


def pick_keep(tracks):
    """在候选集合中选出应保留的文件"""
    return max(tracks, key=_rank)


def _cluster_by_duration(tracks, tolerance):
    """按时长把曲目聚成若干簇（时长 0 视为未知，并入第一簇）"""
    known = sorted((t for t in tracks if t.duration > 0), key=lambda t: t.duration)
    unknown = [t for t in tracks if t.duration <= 0]

    clusters = []
    for track in known:
        if clusters and track.duration - clusters[-1][0].duration <= tolerance:
            clusters[-1].append(track)
        else:
            clusters.append([track])

    if unknown:
        if clusters:
            clusters[0].extend(unknown)
        else:
            clusters.append(unknown)
    return clusters


def _build_groups(kind, buckets, tolerance):
    groups = []
    for key, tracks in buckets.items():
        if len(tracks) < 2:
            continue
        for cluster in _cluster_by_duration(tracks, tolerance):
            if len(cluster) < 2:
                continue
            keep = pick_keep(cluster)
            drop = [t for t in cluster if t is not keep]
            groups.append(DuplicateGroup(
                kind=kind,
                key=key,
                tracks=list(cluster),
                keep=keep,
                drop=drop,
                duration_unknown=any(t.duration <= 0 for t in cluster),
            ))
    return groups


def find_by_tag(tracks, tolerance=DURATION_TOLERANCE):
    """按 歌手 + 歌名 + 时长 判定"""
    buckets = {}
    for track in tracks:
        artist, title = track.key
        if not title:
            continue
        buckets.setdefault((artist, title), []).append(track)
    return _build_groups('标签', buckets, tolerance)


def strip_suffix(stem):
    """去掉文件名中的 (1)(2)... 后缀"""
    return _SUFFIX.sub('', stem).strip()


def find_by_filename(tracks, tolerance=DURATION_TOLERANCE):
    """按 去掉 (n) 后缀的文件名 + 时长 判定"""
    buckets = {}
    for track in tracks:
        buckets.setdefault(strip_suffix(track.stem), []).append(track)
    return _build_groups('文件名', buckets, tolerance)


def find_duplicates(tracks, tolerance=DURATION_TOLERANCE):
    """合并两种规则；同一个文件只会出现在一个组里"""
    groups = find_by_tag(tracks, tolerance)
    claimed = set()
    for group in groups:
        claimed.update(t.path for t in group.tracks)

    for group in find_by_filename(tracks, tolerance):
        if any(t.path in claimed for t in group.tracks):
            continue
        groups.append(group)

    return groups


def all_drop(groups):
    """摊平出所有待处理（可移走/可删）的文件"""
    return [track for group in groups for track in group.drop]
