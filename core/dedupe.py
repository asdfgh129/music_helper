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


# --------------------------------------------------------------------------- #
# 跨集合比对：这批文件库里有没有                                          #
# --------------------------------------------------------------------------- #

@dataclass
class CrossMatch:
    """一个待入库文件与「已有库」的比对结论"""

    track: object
    status: str = 'unique'      # unique | duplicate | unknown
    kind: str = ''              # 命中的维度：标签 / 文件名
    reason: str = ''
    matched: list = field(default_factory=list)


def _build_index(tracks):
    """为「已有库」建两个索引：标签键、归一化文件名"""
    by_tag, by_name = {}, {}
    for track in tracks:
        artist, title = track.key
        if title:
            by_tag.setdefault((artist, title), []).append(track)
        stem = strip_suffix(track.stem)
        norm = normalize_text(stem)
        if norm:
            by_name.setdefault(norm, []).append(track)
    return by_tag, by_name


def _same_recording(left, right, tolerance):
    """两份文件是否同一录音

    优先比文件大小：同一个文件的复制/移动，字节数一定相同，比读时长还可靠。
    大小不同时退回时长容差；两者都拿不到返回 None（交给人工）。

    库里那份可能只有文件名索引、没有读时长，所以不能只靠 duration。
    """
    if left.size and right.size and left.size == right.size:
        return True
    if left.duration > 0 and right.duration > 0:
        return abs(left.duration - right.duration) <= tolerance
    return None


def match_against(targets, pool, tolerance=None):
    """把一批文件逐个与「已在库里的文件」比对，判断是新的还是重复的

    与 `find_duplicates()` 的区别：
    - 这里是**两个集合之间**的比对，不是同一堆文件内部找重复；
    - 不需要决定「保留哪个」——库里那份天然保留，只需回答「这份该不该入库」。

    判定沿用库内查重的两条规则，但更保守：
    - 大小与时长都拿不到时只标 `unknown`，不判重复（损坏文件不应被自动移走）；
    - 文件名维度要求有「歌手 - 歌名」结构，`Intro.flac` 这类不跨目录比对。

    Args:
        targets: 待判定的文件（如工作区文件）
        pool: 已有文件（如库目录索引；可以只填 size 与文件名解析出的标签）

    Returns:
        list[CrossMatch]，顺序与 targets 一致
    """
    tolerance = default_tolerance() if tolerance is None else tolerance
    by_tag, by_name = _build_index(pool)

    results = []
    for track in targets:
        _artist, title = track.key
        candidates = list(by_tag.get((_artist, title), [])) if title else []
        kind = '歌手+歌名'
        if not candidates:
            stem = strip_suffix(track.stem)
            norm = normalize_text(stem)
            # 没有「 - 」结构时拿不到歌手，跨目录同名多半是不同曲目，不参与比对
            if norm and ' - ' in stem:
                candidates = list(by_name.get(norm, []))
                kind = '文件名'

        if not candidates:
            results.append(CrossMatch(track=track, status='unique',
                                      reason='库中没有同名或同歌手+歌名的曲目'))
            continue

        confirmed, unknown = [], []
        for other in candidates:
            same = _same_recording(track, other, tolerance)
            if same is None:
                unknown.append(other)
            elif same:
                confirmed.append(other)

        if confirmed:
            results.append(CrossMatch(track=track, status='duplicate', kind=kind,
                                      matched=confirmed,
                                      reason=f'{kind}相同，判定为同一文件'))
        elif unknown:
            results.append(CrossMatch(track=track, status='unknown', kind=kind,
                                      matched=unknown,
                                      reason=f'{kind}相同，但大小与时长都无法确认，需人工'))
        else:
            results.append(CrossMatch(
                track=track, status='unique', kind=kind, matched=candidates,
                reason=f'{kind}相同但大小与时长都不一致，视为不同版本'))

    return results
