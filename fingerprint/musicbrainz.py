# -*- coding: utf-8 -*-
"""MusicBrainz 侧的三件事：节点转换、录音聚合、Release 加载

AcoustID 返回的数据结构与 MusicBrainz 不一样（前者是 `releasegroups/releases/
mediums`，后者是 `releases/media/...`），`JSONHelpers` 负责把前者拍成后者的形状，
这样下游的打分与标签映射只需要认一种结构。

`RecordingResolver` 解决的是**元数据缺失**问题：AcoustID 的查询结果里，热门曲目
自带完整信息，冷门曲目只有 mbid。这时按「来源数占比 > 0.25 且每张 AcoustID 结果
最多补 3 条」的规则回查 MusicBrainz，既补全信息又不会把一次查询放大成几十个请求。
"""

import logging
from typing import List, Optional

from .http_client import HTTPClient
from .models import AcoustIDConfig, Recording

logger = logging.getLogger(__name__)


class JSONHelpers:
    """AcoustID 结构 → MusicBrainz 结构的转换工具（纯函数，无状态）"""

    @staticmethod
    def _make_releases_node(recording: dict) -> List[dict]:
        """把 AcoustID 的 releasegroups/releases 拍平成 MusicBrainz 的 releases"""
        release_list = []
        for release_group in recording.get('releasegroups', []):
            for release in release_group.get('releases', []):
                release_mb = {
                    'id': release['id'],
                    'release-group': {
                        'id': release_group['id'],
                    }
                }

                if 'type' in release_group:
                    release_mb['release-group']['primary-type'] = release_group['type']
                if 'secondarytypes' in release_group:
                    release_mb['release-group']['secondary-types'] = release_group['secondarytypes']

                release_mb['title'] = release.get('title', release_group.get('title', ''))

                if 'country' in release:
                    release_mb['country'] = release['country']
                if 'date' in release:
                    release_mb['date'] = release['date']
                if 'medium_count' in release:
                    release_mb['medium-count'] = release['medium_count']
                if 'track_count' in release:
                    release_mb['track-count'] = release['track_count']

                release_mb['media'] = []
                for medium in release.get('mediums', []):
                    media_mb = {}
                    if 'format' in medium:
                        media_mb['format'] = medium['format']
                    if 'track_count' in medium:
                        media_mb['track-count'] = medium['track_count']
                    if 'position' in medium:
                        media_mb['position'] = medium['position']
                    if 'tracks' in medium:
                        media_mb['track'] = medium['tracks']
                        for track_mb in media_mb['track']:
                            track_mb['number'] = track_mb['position']
                    release_mb['media'].append(media_mb)

                # 一张 release 可能有多个发行地区/日期，每个都单列一条供打分挑选
                if 'releaseevents' in release:
                    for releaseevent in release['releaseevents']:
                        release_copy = release_mb.copy()
                        release_copy['country'] = releaseevent.get('country', '')
                        release_copy['date'] = releaseevent.get('date', '')
                        release_list.append(release_copy)
                else:
                    release_list.append(release_mb)

        return release_list

    @staticmethod
    def _make_artist_node(artist: dict) -> dict:
        """创建 MusicBrainz 风格的艺术家节点"""
        node = {
            'name': artist['name'],
            'sort-name': artist.get('sort-name', artist['name']),
            'id': artist['id'],
        }
        if 'type' in artist:
            node['type'] = artist['type']
        return node

    @staticmethod
    def _make_artist_credit_node(artists: List[dict]) -> List[dict]:
        """创建 artist-credit 数组（第二个起带 `; ` 连接符）"""
        artist_list = []
        for i, artist in enumerate(artists):
            node = {
                'artist': JSONHelpers._make_artist_node(artist),
                'name': artist['name'],
            }
            if i > 0:
                node['joinphrase'] = '; '
            artist_list.append(node)
        return artist_list

    @staticmethod
    def parse_recording(recording: dict) -> Optional[dict]:
        """AcoustID recording → MusicBrainz recording；无 id 时返回 None"""
        if 'id' not in recording:
            return None

        recording_mb = {'id': recording['id']}

        if 'title' in recording:
            recording_mb['title'] = recording['title']

        if 'artists' in recording:
            recording_mb['artist-credit'] = JSONHelpers._make_artist_credit_node(recording['artists'])

        if 'releasegroups' in recording:
            recording_mb['releases'] = JSONHelpers._make_releases_node(recording)

        if 'duration' in recording:
            try:
                # AcoustID 的 duration 是秒，MusicBrainz 的 length 是毫秒
                recording_mb['length'] = int(recording['duration']) * 1000
            except (TypeError, ValueError):
                pass

        if 'sources' in recording:
            recording_mb['sources'] = recording['sources']

        return recording_mb

    @staticmethod
    def recording_has_metadata(recording: dict) -> bool:
        """标题存在即视为元数据齐全（缺标题的一定要回查）"""
        return 'id' in recording and recording.get('title') is not None


class RecordingResolver:
    """把 AcoustID 查询结果聚合成候选录音列表，并按需回查 MusicBrainz"""

    SOURCE_THRESHOLD_NO_METADATA = 0.25
    MAX_NO_METADATA_RECORDINGS = 3

    def __init__(self, http_client: HTTPClient, debug_mode: bool = False):
        self.http_client = http_client
        self.recording_cache = {}
        self.missing_metadata = []
        self.debug_mode = debug_mode
        if debug_mode:
            logger.debug("RecordingResolver 初始化")

    def _get_score(self, node: dict) -> float:
        try:
            return float(node.get('score', 1.0))
        except (TypeError, ValueError):
            return 1.0

    def _max_source_count(self, recordings: List[Recording]) -> int:
        sources = {r.sources for r in recordings}
        sources.add(1)
        return max(sources)

    def _max_source_count_raw(self, recordings: List[dict]) -> int:
        sources = {r.get('sources', 1) for r in recordings}
        sources.add(1)
        return max(sources)

    def resolve(self, doc: dict) -> List[dict]:
        """解析 AcoustID 的 lookup 响应，返回带 score/acoustid/sources 的录音列表"""
        if self.debug_mode:
            logger.debug("=" * 60)
            logger.debug("RecordingResolver.resolve 开始")
            logger.debug("=" * 60)

        results = doc.get('results') or []
        recording_map = {}
        incomplete_counts = {}

        if self.debug_mode:
            logger.debug(f"results count = {len(results)}")

        for i, result in enumerate(results):
            recordings = result.get('recordings') or []
            result_score = self._get_score(result)
            acoustid = result.get('id')
            max_sources = self._max_source_count_raw(recordings)

            if self.debug_mode:
                logger.debug(f"\n结果 {i + 1}/{len(results)}:")
                logger.debug(f"  acoustid = {acoustid}")
                logger.debug(f"  result_score = {result_score}")
                logger.debug(f"  recordings count = {len(recordings)}")
                logger.debug(f"  max_sources = {max_sources}")

            # 来源数高的排前面：sources 表示有多少次提交指向这条录音，是可信度代理指标
            for j, recording in enumerate(sorted(recordings, key=lambda r: r.get('sources', 1), reverse=True)):
                mbid = recording.get('id')
                sources = recording.get('sources', 1)

                if self.debug_mode:
                    logger.debug(f"  录音 {j + 1}:")
                    logger.debug(f"    mbid = {mbid}")
                    logger.debug(f"    sources = {sources}")
                    logger.debug(f"    title = {recording.get('title', 'N/A')}")

                if acoustid not in recording_map:
                    recording_map[acoustid] = {}

                if JSONHelpers.recording_has_metadata(recording):
                    mb_recording = JSONHelpers.parse_recording(recording)
                    if mb_recording:
                        self.recording_cache[mbid] = mb_recording
                        recording_map[acoustid][recording['id']] = Recording(
                            recording=mb_recording,
                            result_score=result_score,
                            sources=sources,
                        )
                else:
                    # 只在「该录音占本结果来源数 1/4 以上」且「本 AcoustID 结果尚未补满 3 条」时回查，
                    # 避免一次查询触发几十个 MusicBrainz 请求（有速率限制，每秒 1 次）
                    if (sources / max_sources > self.SOURCE_THRESHOLD_NO_METADATA
                            and incomplete_counts.get(acoustid, 0) < self.MAX_NO_METADATA_RECORDINGS):
                        self.missing_metadata.append({
                            'mbid': mbid,
                            'acoustid': acoustid,
                            'result_score': result_score,
                            'sources': sources,
                        })
                        incomplete_counts[acoustid] = incomplete_counts.get(acoustid, 0) + 1

        self._load_missing_metadata(recording_map)

        return list(self._parse_recording_map(recording_map))

    def _load_missing_metadata(self, recording_map: dict):
        """对缺元数据的录音逐条回查 MusicBrainz"""
        for item in self.missing_metadata:
            mbid = item['mbid']

            if mbid in self.recording_cache:
                mb_recording = self.recording_cache[mbid]
            else:
                url = f"{AcoustIDConfig.MUSICBRAINZ_URL}/recording/{mbid}"
                params = {'inc': 'artists+release-groups+releases+media+artist-credits+isrcs+tags'}

                mb_recording, error = self.http_client.get(url, params)
                if error:
                    logger.warning(f"Failed to load metadata for {mbid}: {error}")
                    continue

                if mb_recording and 'id' in mb_recording:
                    self.recording_cache[mbid] = mb_recording

            if mb_recording and mb_recording.get('id'):
                acoustid = item['acoustid']
                if acoustid not in recording_map:
                    recording_map[acoustid] = {}

                if mbid not in recording_map[acoustid]:
                    recording_map[acoustid][mbid] = Recording(
                        recording=mb_recording,
                        result_score=item['result_score'],
                        sources=item['sources'],
                    )
                else:
                    recording_map[acoustid][mbid].sources += item['sources']

    def _parse_recording_map(self, recording_map: dict):
        """把聚合结果摊平，并写入归一化的分数"""
        for acoustid, recordings in recording_map.items():
            recording_list = recordings.values()
            max_sources = self._max_source_count(recording_list)

            for recording in recording_list:
                parsed_recording = recording.recording
                if parsed_recording is not None:
                    # 两条 AcoustID 结果指向同一录音时，sources 会累加，这里按最大值归一
                    score = min(recording.sources / max_sources, 1.0) * 100
                    parsed_recording['score'] = score * recording.result_score
                    parsed_recording['acoustid'] = acoustid
                    parsed_recording['sources'] = recording.sources
                yield parsed_recording


class ReleaseLoader:
    """按 release_id 加载完整 Release（带缓存，同一专辑的曲目只请求一次）"""

    def __init__(self, http_client: HTTPClient, debug_mode: bool = False):
        self.http_client = http_client
        self._cache = {}
        self.debug_mode = debug_mode
        if debug_mode:
            logger.debug("ReleaseLoader 初始化")

    def load_release_by_id(self, release_id: str, inc: Optional[list] = None) -> Optional[dict]:
        """加载完整 Release；`inc` 为 None 时用与 Picard 一致的默认集合"""
        if self.debug_mode:
            logger.debug("=" * 60)
            logger.debug("ReleaseLoader.load_release_by_id 开始")
            logger.debug("=" * 60)
            logger.debug(f"release_id = {release_id}")

        if release_id in self._cache:
            if self.debug_mode:
                logger.debug("从缓存返回")
            return self._cache[release_id]

        if inc is None:
            inc = [
                'aliases',                   # 别名
                'annotation',                # 注释
                'artist-credits',            # 艺术家 credits
                'artists',                   # 艺术家
                'collections',               # 集合
                'discids',                   # Disc ID
                'isrcs',                     # ISRC 代码
                'labels',                    # 唱片公司
                'media',                     # 媒体格式
                'recordings',                # 录音列表(包含所有音轨)
                'release-groups',            # 发行组
                'artist-rels',               # 艺术家关系
                'recording-rels',            # 录音关系
                'label-rels',                # 唱片公司关系
                'release-group-level-rels',  # 发行组级关系
                'release-rels',              # 发行关系
                'series-rels',               # 系列关系
                'url-rels',                  # URL 关系
                'work-rels',                 # 作品关系
                'recording-level-rels',      # 录音级关系
                'work-level-rels',           # 作品级关系
            ]

        inc_param = '+'.join(inc)
        url = f"{AcoustIDConfig.MUSICBRAINZ_URL}/release/{release_id}"

        if self.debug_mode:
            logger.debug(f"inc = {', '.join(inc[:5])}... (共{len(inc)}项)")
            logger.debug(f"url = {url}?inc={inc_param}")
        params = {'inc': inc_param}

        logger.info(f"Loading release {release_id} from MusicBrainz with inc={inc_param}")

        release_data, error = self.http_client.get(url, params)

        if error or release_data is None:
            logger.error(f"Failed to load release {release_id}: {error}")
            return None

        self._cache[release_id] = release_data
        return release_data

    def clear_cache(self):
        """清除缓存"""
        self._cache.clear()
