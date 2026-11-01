# -*- coding: utf-8 -*-
"""
重复判定模块 - 实现规划中的模块 5

判定规则（与 项目规划.md 一致）：
1. 标签维度：歌手 + 歌名 相同，且时长相差不超过 TOLERANCE 秒；
2. 文件名维度：去掉 (1)(2)/_1/_2 后缀后同名，且时长相差不超过 TOLERANCE 秒；
3. 时长未知（读取失败）时，只要名称一致即视为候选，但会在报告中标注「时长未知」，
   并由 plan_fixes() 转人工——损坏文件不应被自动搬走。

保留策略：优先无损格式，其次文件更大者（同格式下通常码率更高）。
"""

import os
import re
from dataclasses import dataclass, field

from core.naming import normalize_text

# 数值越大越优先保留
_QUALITY = {'.flac': 5, '.dsf': 5, '.wav': 4, '.ape': 4,
            '.ogg': 3, '.opus': 3, '.mp3': 2, '.m4a': 2, '.wma': 1}

# 下载序号：`(1)`、`（2）`，以及 copy_items / Plan 重名时加的 `_1`
_SUFFIX = re.compile(r'\s*(?:[\(（]\s*(\d+)\s*[\)）]|_(\d+))\s*$')


def default_tolerance():
    """允许的时长误差，唯一来源是 config.DURATION_TOLERANCE"""
    from config import DURATION_TOLERANCE

    return DURATION_TOLERANCE


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


def _build_groups(kind, buckets, tolerance, display=None):
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
                key=display(key) if display else key,
                tracks=list(cluster),
                keep=keep,
                drop=drop,
                duration_unknown=any(t.duration <= 0 for t in cluster),
            ))
    return groups


def find_by_tag(tracks, tolerance=None):
    """按 歌手 + 歌名 + 时长 判定"""
    tolerance = default_tolerance() if tolerance is None else tolerance
    buckets = {}
    for track in tracks:
        artist, title = track.key
        if not title:
            continue
        buckets.setdefault((artist, title), []).append(track)
    return _build_groups('标签', buckets, tolerance)


def strip_suffix(stem):
    """去掉文件名中的 (1)(2)... 或 _1/_2 后缀"""
    return _SUFFIX.sub('', stem).strip()


def find_by_filename(tracks, tolerance=None):
    """按 去掉下载序号的文件名 + 时长 判定

    文件名里没有「 - 」时（如 `Intro.flac`）拿不到歌手信息，跨目录同名多半是
    不同专辑里的不同曲目，因此这类文件名只在同一目录内比对；
    带「歌手 - 歌名」结构的才允许跨目录，且比较时忽略大小写与空白差异。
    """
    tolerance = default_tolerance() if tolerance is None else tolerance
    buckets = {}
    for track in tracks:
        stem = strip_suffix(track.stem)
        norm = normalize_text(stem)
        if not norm:
            continue
        scope = '' if ' - ' in stem else os.path.normcase(track.dirpath)
        buckets.setdefault((norm, scope), []).append(track)
    return _build_groups('文件名', buckets, tolerance, display=lambda key: key[0])


def find_duplicates(tracks, tolerance=None):
    """合并两种规则；同一个文件只会出现在一个组里

    标签维度先跑。文件名维度里已被标签组认领的文件直接剔除，剩下的仍有 2 个以上
    才成组——不能因为「组里有一个已被认领」就把整组丢掉，否则会漏掉真正的重复。
    """
    tolerance = default_tolerance() if tolerance is None else tolerance
    groups = find_by_tag(tracks, tolerance)
    claimed = {track.path for group in groups for track in group.tracks}

    for group in find_by_filename(tracks, tolerance):
        remaining = [track for track in group.tracks if track.path not in claimed]
        if len(remaining) < 2:
            continue
        keep = pick_keep(remaining)
        groups.append(DuplicateGroup(
            kind=group.kind,
            key=group.key,
            tracks=remaining,
            keep=keep,
            drop=[track for track in remaining if track is not keep],
            duration_unknown=any(track.duration <= 0 for track in remaining),
        ))

    return groups


def all_drop(groups):
    """摊平出所有待处理（可移走/可删）的文件"""
    return [track for group in groups for track in group.drop]
