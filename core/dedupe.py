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

from core import quality
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
    """一个待入库文件与「已有库」的比对结论

    status 的四种取值对应四种处理方式：
      unique    库里没有 → 照常归档
      duplicate 库里已有同等或更好音质 → 移走**工作区**这份
      upgrade   库里已有但音质更低 → 移走**库里**那份，工作区这份归档
      unknown   判不出来（时长/规格读不出来） → 交人工

    `basis` 说明 upgrade 的依据，只在 upgrade 时有值：
      quality   库里那份音质更低（无损/有损、采样率、位深或码率）
      format    音质相同，但工作区这份是压缩无损（FLAC/APE），库里是 WAV

    一个工作区文件可能同时对上库里**多个**文件（同一首的不同版本、不同目录的
    副本），`matched` 与 `comparisons` 会全部列出，由页面逐条让用户确认。
    """

    track: object
    status: str = 'unique'      # unique | duplicate | upgrade | unknown
    kind: str = ''              # 命中的维度：标签 / 文件名
    reason: str = ''
    basis: str = ''             # upgrade 的依据：quality | format
    matched: list = field(default_factory=list)      # 相关的库内文件（Track）
    target_info: dict = field(default_factory=dict)  # 待入库文件的音频规格
    comparisons: list = field(default_factory=list)  # [{'track','info','relation','basis'}]


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


def _same_recording(left, right, tolerance, info_of):
    """两份文件是否同一录音

    优先比文件大小：同一个文件的复制/移动，字节数一定相同，比读时长还可靠。
    大小不同时退回时长容差；两者都拿不到返回 None（交给人工）。

    库里那份起初只有文件名索引、duration 为 0，所以这里通过 `info_of` 按需
    触发一次规格读取——只在命中候选后发生，个数很少。
    """
    if left.size and right.size and left.size == right.size:
        return True
    left_duration = info_of(left).get('duration') or 0
    right_duration = info_of(right).get('duration') or 0
    if left_duration > 0 and right_duration > 0:
        return abs(left_duration - right_duration) <= tolerance
    return None


def _probe_info(track, probe, cache):
    """取音质相关字段：Track 自带的先用，probe 只补缺的

    probe 失败（文件损坏、mutagen 缺失、权限不足）时静默降级，让上层用现有
    字段判；此时音质比较会得到 unknown，转人工而不是误判。
    """
    cached = cache.get(track.path)
    if cached is not None:
        return cached

    info = {'ext': track.ext, 'size': track.size, 'duration': track.duration}
    if probe is not None:
        try:
            extra = probe(track) or {}
        except Exception:  # noqa: BLE001 - 读不出来就按已知字段判
            extra = {}
        for key in ('duration', 'bitrate', 'sample_rate', 'bit_depth'):
            if extra.get(key):
                info[key] = extra[key]
    cache[track.path] = info
    return info


def match_against(targets, pool, tolerance=None, probe=None):
    """把一批文件逐个与「已在库里的文件」比对，判断是新的、重复的还是要替换的

    与 `find_duplicates()` 的区别：
    - 这里是**两个集合之间**的比对，不是同一堆文件内部找重复；
    - 要回答的是「这份该不该入库」，以及「库里那份该不该让位」。

    判定沿用库内查重的两条规则，但更保守：
    - 大小与时长都拿不到时只标 `unknown`，不判重复（损坏文件不应被自动移走）；
    - 文件名维度要求有「歌手 - 歌名」结构，`Intro.flac` 这类不跨目录比对。

    确认同一录音之后，再用 `core.quality` 比音质：
    - 库里有同等或更好的 → `duplicate`（工作区这份是多余的）
    - 库里全都是更差的   → `upgrade`（库里旧版本让位，这份才是要入库的）

    音质「相同」时还有一层格式偏好：同规格的 WAV 与 FLAC 解码结果完全一致，
    留 FLAC 更省磁盘，此时同样判 `upgrade`，但 `basis` 标成 `format`，
    与真正的音质升级（`basis='quality'`）区分开。

    Args:
        targets: 待判定的文件（如工作区文件）
        pool: 已有文件（如库目录索引；可以只填 size 与文件名解析出的标签）
        probe: 可选的 `callable(track) -> dict`，补读 duration / bitrate /
            sample_rate / bit_depth。只在命中候选后调用。

    Returns:
        list[CrossMatch]，顺序与 targets 一致
    """
    tolerance = default_tolerance() if tolerance is None else tolerance
    by_tag, by_name = _build_index(pool)
    cache = {}

    def info_of(track):
        return _probe_info(track, probe, cache)

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

        same_recordings, unresolved = [], []
        for other in candidates:
            same = _same_recording(track, other, tolerance, info_of)
            if same is None:
                unresolved.append(other)
            elif same:
                same_recordings.append(other)

        if not same_recordings:
            if unresolved:
                results.append(CrossMatch(
                    track=track, status='unknown', kind=kind, matched=unresolved,
                    reason=f'{kind}相同，但大小与时长都无法确认，需人工'))
            else:
                results.append(CrossMatch(
                    track=track, status='unique', kind=kind, matched=candidates,
                    reason=f'{kind}相同但大小与时长都不一致，视为不同版本'))
            continue

        target_info = info_of(track)
        better, keep_library, unclear, comparisons = [], [], [], []
        for other in same_recordings:
            other_info = info_of(other)
            relation = quality.compare(target_info, other_info)
            basis = 'quality'
            # 规格读不出来（损坏、dff 这类容器 mutagen 不支持）时，只有同格式才
            # 降级成「音质相同」——同格式同录音没有可靠的升级依据，保守不动库。
            # 格式不同却读不到规格，说明连无损/有损都判不了，留给人工。
            if relation == 'unknown' and track.ext == other.ext:
                relation = 'same'
            # 音质打平时再看格式：同规格的 FLAC 与 WAV 解码结果一致，但 FLAC
            # 体积只有一半，留 FLAC 更划算。这不是音质升级，basis 单独标记。
            if relation == 'same':
                preference = quality.storage_preference(target_info, other_info)
                if preference == 'better':
                    relation, basis = 'better', 'format'
            if relation == 'unknown':
                basis = ''
            comparisons.append({'track': other, 'info': other_info,
                                'relation': relation, 'basis': basis})
            if relation == 'better':
                better.append(other)
            elif relation in ('same', 'worse'):
                keep_library.append(other)
            else:
                unclear.append(other)

        if keep_library:
            results.append(CrossMatch(
                track=track, status='duplicate', kind=kind, matched=keep_library,
                target_info=target_info, comparisons=comparisons,
                reason=f'{kind}相同，库中已有同音质或更好的版本'))
        elif better and not unclear:
            # 全部是「同音质、换更省磁盘的格式」才算 format；只要有一条是真
            # 的音质提升，整体按音质升级表述（逐条依据仍在 comparisons 里）
            bases = {cmp['basis'] for cmp in comparisons
                     if cmp['relation'] == 'better'}
            basis = 'format' if bases == {'format'} else 'quality'
            reason = (f'{kind}相同，音质一致但库里那份更占地方，可用这份替换'
                      if basis == 'format'
                      else f'{kind}相同，库里版本音质更低，可被这份替换')
            results.append(CrossMatch(
                track=track, status='upgrade', kind=kind, basis=basis,
                matched=better, target_info=target_info,
                comparisons=comparisons, reason=reason))
        elif unclear:
            results.append(CrossMatch(
                track=track, status='unknown', kind=kind, matched=unclear,
                target_info=target_info, comparisons=comparisons,
                reason=f'{kind}相同，但音质规格读不出来，需人工确认'))
        else:
            results.append(CrossMatch(
                track=track, status='unique', kind=kind, matched=same_recordings,
                target_info=target_info, comparisons=comparisons,
                reason=f'{kind}相同但音质一致且无替换必要，视为不同版本'))

    return results
