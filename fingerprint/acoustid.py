# -*- coding: utf-8 -*-
"""AcoustID 查询与候选排序

流程：
    指纹 + 时长 → POST /v2/lookup → RecordingResolver 聚合候选
      → 有本地元数据时用 Picard 那套加权相似度挑最佳（`_find_best_match`）
      → 没有元数据就按 AcoustID 自己的 score 取最高

权重表是这一层最需要理解的东西：`title` 13 与 `releasetype` 14 最高，`length` 10，
`artist`/`date`/`totaltracks` 各 4，`releasecountry`/`format` 各 2。也就是说
**「像专辑」比「像这首歌」更重要**——同为官方 Album，宁可标题差一点，也不要挑中
一张拼盘里的同名曲。这是 Picard 的取舍，这里照抄，改之前先想清楚后果。
"""

import json
import logging
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from .http_client import HTTPClient
from .models import AcoustIDConfig, MatchResult
from .musicbrainz import RecordingResolver, ReleaseLoader
from .similarity import (
    artist_credit_from_node,
    extract_year_from_date,
    get_score,
    length_score,
    linear_combination_of_weights,
    similarity2,
    trackcount_score,
)

logger = logging.getLogger(__name__)


class AcoustIDClient:
    """AcoustID 客户端——查询、聚合、选最佳"""

    def __init__(self, client_version: Optional[str] = None, debug_mode: bool = False):
        self.http_client = HTTPClient(debug_mode=debug_mode)
        self.client_key = AcoustIDConfig.ACOUSTID_KEY
        self.client_version = client_version or AcoustIDConfig.DEFAULT_CLIENT_VERSION
        self.resolver = RecordingResolver(self.http_client, debug_mode=debug_mode)
        self.release_loader = ReleaseLoader(self.http_client, debug_mode=debug_mode)
        self.debug_mode = debug_mode
        if debug_mode:
            logger.debug("AcoustIDClient 初始化")
            logger.debug(f"  client_key = {self.client_key}")
            logger.debug(f"  client_version = {self.client_version}")

    def _encode_acoustid_args(self, args: Dict[str, Any]) -> str:
        """手动编码参数（与 Picard 一致，空格要编码成 %20 而非 +）"""
        args['client'] = self.client_key
        args['clientversion'] = self.client_version
        args['format'] = 'json'
        return '&'.join(f"{key}={quote(str(value), safe='')}" for key, value in args.items())

    def query_acoustid(self, fingerprint: str, duration: int) -> tuple[Optional[dict], Optional[str]]:
        """用指纹查 AcoustID，返回 (原始文档, 错误串)"""
        if self.debug_mode:
            logger.debug("=" * 60)
            logger.debug("开始查询 AcoustID API")
            logger.debug("=" * 60)

        params = {
            'fingerprint': fingerprint,
            'duration': str(duration),
            'meta': 'recordings releasegroups releases tracks artists usermeta compress sources',
        }

        url = f"{AcoustIDConfig.ACOUSTID_URL}/lookup"

        if self.debug_mode:
            logger.debug("AcoustID 查询参数:")
            logger.debug(f"  url = {url}")
            logger.debug(f"  fingerprint length = {len(fingerprint)}")
            logger.debug(f"  fingerprint = {fingerprint[:50]}...")
            logger.debug(f"  duration = {duration}s")
            logger.debug("  meta = recordings releasegroups releases tracks artists usermeta compress sources")

        logger.info(f"Querying AcoustID with fingerprint ({len(fingerprint)} chars, {duration}s)")

        body = self._encode_acoustid_args(params)

        if self.debug_mode:
            logger.debug(f"  请求体长度 = {len(body)} chars")

        document, error = self.http_client.post(url, body)

        if error or document is None:
            if self.debug_mode:
                logger.debug(f"  查询失败: {error}")
            logger.error(f"AcoustID query error: {error}")
            return None, error

        if self.debug_mode:
            logger.debug(f"  响应状态: {document.get('status')}")

        status = document.get('status')
        if status != 'ok':
            error_msg = document.get('error', {}).get('message', 'Unknown error')
            if self.debug_mode:
                logger.debug(f"  API 错误: {error_msg}")
            logger.error(f"AcoustID API error: {error_msg}")
            return None, error_msg

        results = document.get('results', [])
        logger.info(f"AcoustID returned {len(results)} results")

        if self.debug_mode:
            logger.debug(f"  返回结果数 = {len(results)}")
            if results:
                logger.debug(f"  第一个结果: {json.dumps(results[0], ensure_ascii=False, indent=2)[:500]}...")

        return document, None

    def match_fingerprint(self, fingerprint: str, duration: int,
                          metadata: Optional[Dict] = None) -> MatchResult:
        """匹配指纹，返回 MatchResult（含 best_match）"""
        if self.debug_mode:
            logger.debug("=" * 60)
            logger.debug("开始匹配指纹")
            logger.debug("=" * 60)
            logger.debug(f"fingerprint length = {len(fingerprint)}")
            logger.debug(f"duration = {duration}s")
            logger.debug(f"metadata = {json.dumps(metadata, ensure_ascii=False) if metadata else None}")

        document, error = self.query_acoustid(fingerprint, duration)

        if error or document is None:
            if self.debug_mode:
                logger.debug(f"查询失败: {error}")
            return MatchResult(success=False, recordings=[], error=error or "Unknown error")

        try:
            if self.debug_mode:
                logger.debug("开始解析录音信息...")

            recordings = self.resolver.resolve(document)
            logger.info(f"Resolved {len(recordings)} recordings")

            if self.debug_mode:
                logger.debug(f"解析出 {len(recordings)} 条录音")

            if metadata and recordings:
                if self.debug_mode:
                    logger.debug("使用元数据进行最佳匹配...")

                best_match = self._find_best_match(recordings, metadata, duration * 1000)
                logger.info(f"Best match selected with score: {best_match.get('score', 0):.1f}%")

                if self.debug_mode:
                    logger.debug(f"最佳匹配分数: {best_match.get('score', 0):.1f}%")
                    logger.debug(f"最佳匹配: {json.dumps(best_match, ensure_ascii=False, indent=2)[:500]}...")

                return MatchResult(success=True, recordings=recordings, best_match=best_match)
            else:
                # 没有本地元数据可比，只能信 AcoustID 自己的分数
                if self.debug_mode:
                    logger.debug("未提供元数据，使用 AcoustID 分数选择最佳匹配...")

                best_match = max(recordings, key=lambda r: r.get('score', 0), default=None)
                if best_match:
                    logger.info(f"Best match by AcoustID score: {best_match.get('score', 0):.1f}%")
                    if self.debug_mode:
                        logger.debug(f"AcoustID 最佳匹配分数: {best_match.get('score', 0):.1f}%")
                return MatchResult(success=True, recordings=recordings, best_match=best_match)
        except Exception as e:  # noqa: BLE001
            error_msg = f"Failed to resolve recordings: {e}"
            if self.debug_mode:
                logger.debug(f"解析录音失败: {e}")
            logger.error(error_msg)
            return MatchResult(success=False, recordings=[], error=error_msg)

    def _find_best_match(self, recordings: List[Dict], metadata: Dict,
                         file_duration_ms: int) -> Optional[Dict]:
        """用 Picard 的加权相似度挑出最佳候选，结果写回 `_calculated_similarity`"""
        if not recordings:
            return None

        FILE_COMPARISON_WEIGHTS = {
            'title': 13,           # 最高权重之一——标题匹配最关键
            'releasetype': 14,     # 最高——偏好官方发行
            'length': 10,          # 时长匹配
            'artist': 4,           # 艺术家名称匹配
            'date': 4,             # 发行日期匹配
            'totaltracks': 4,      # 曲目数量匹配
            'releasecountry': 2,   # 国家偏好
            'format': 2,           # 格式偏好 (CD, vinyl 等)
            'isvideo': 2,          # 视频标志匹配
        }

        RELEASE_TYPE_SCORES = {
            'Album': 1.0,
            'Single': 0.8,
            'EP': 0.7,
            'Other': 0.5,
            'Broadcast': 0.4,
            'Compilation': 0.6,
        }

        best_recording = None
        best_similarity = -1.0

        for recording in recordings:
            parts = []

            # 1. 标题相似度
            if 'title' in metadata:
                a = metadata['title']
                b = recording.get('title', '')
                parts.append((similarity2(a, b), FILE_COMPARISON_WEIGHTS['title']))

            # 2. 艺术家相似度
            if 'artist' in metadata:
                a = metadata['artist']
                artist_credits = recording.get('artist-credit', [])
                b, _ = artist_credit_from_node(artist_credits)
                parts.append((similarity2(a, b), FILE_COMPARISON_WEIGHTS['artist']))

            # 3. 时长分数
            file_length = file_duration_ms
            if file_length > 0 and 'length' in recording:
                track_length = recording['length']
                score = length_score(file_length, track_length)
                parts.append((score, FILE_COMPARISON_WEIGHTS['length']))

            # 4. AcoustID 自己的搜索分数
            search_score = get_score(recording)

            # 5. 发行信息：逐张打分取最高，因为一张录音可能出现在多张专辑里
            releases = recording.get('releases', [])
            if releases:
                best_release_similarity = -1.0

                for release in releases:
                    release_parts = parts.copy()

                    # 5.1 专辑标题相似度
                    if 'album' in metadata:
                        album_title = metadata['album']
                        release_title = release.get('title', '')
                        release_parts.append((similarity2(album_title, release_title), 8))

                    # 5.2 曲目数量分数
                    if 'totaltracks' in metadata:
                        try:
                            metadata_totaltracks = int(metadata['totaltracks'])
                            release_trackcount = release.get('track-count', 0)
                            if release_trackcount:
                                score = trackcount_score(metadata_totaltracks, release_trackcount)
                                release_parts.append((score, FILE_COMPARISON_WEIGHTS['totaltracks']))
                        except (ValueError, TypeError):
                            pass

                    # 5.3 日期匹配：完全同日 1.0，同年 0.95，相差 2 年内 0.85，否则 0
                    if 'date' in metadata:
                        metadata_date = metadata['date']
                        release_date = release.get('date', '')
                        if release_date:
                            if release_date == metadata_date:
                                date_match_factor = 1.00
                            else:
                                release_year = extract_year_from_date(release_date)
                                metadata_year = extract_year_from_date(metadata_date)
                                if release_year is not None and metadata_year is not None:
                                    if release_year == metadata_year:
                                        date_match_factor = 0.95
                                    elif abs(release_year - metadata_year) <= 2:
                                        date_match_factor = 0.85
                                    else:
                                        date_match_factor = 0.0
                                else:
                                    date_match_factor = 0.0
                        else:
                            date_match_factor = 0.25
                        release_parts.append((date_match_factor, FILE_COMPARISON_WEIGHTS['date']))

                    # 5.4 发行类型分数
                    if 'release-group' in release:
                        release_group = release['release-group']
                        release_type = release_group.get('primary-type', 'Other')
                        type_score = RELEASE_TYPE_SCORES.get(release_type, RELEASE_TYPE_SCORES['Other'])
                        release_parts.append((type_score, FILE_COMPARISON_WEIGHTS['releasetype']))

                    # 5.5 国家偏好（未实现具体策略，给中等分）
                    release_parts.append((0.5, FILE_COMPARISON_WEIGHTS['releasecountry']))

                    # 5.6 格式偏好（未实现具体策略，给中等分）
                    release_parts.append((0.5, FILE_COMPARISON_WEIGHTS['format']))

                    similarity = linear_combination_of_weights(release_parts) * search_score
                    if similarity > best_release_similarity:
                        best_release_similarity = similarity

                similarity = best_release_similarity
            else:
                # 没有任何发行信息时，用 Other 的类型分兜底
                default_type_score = RELEASE_TYPE_SCORES['Other']
                parts.append((default_type_score, FILE_COMPARISON_WEIGHTS['releasetype']))
                similarity = linear_combination_of_weights(parts) * search_score

            if similarity > best_similarity:
                best_similarity = similarity
                best_recording = recording

        if best_recording:
            best_recording['_calculated_similarity'] = best_similarity

        return best_recording
