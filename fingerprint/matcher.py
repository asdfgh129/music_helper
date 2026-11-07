# -*- coding: utf-8 -*-
"""对外的门面：`FingerprintMatcher`

把「算指纹」和「查 AcoustID」两件事串起来，主流程只需要 `match_file(path)`。
拆包之后这个文件是唯一被 `tagger` 间接依赖的入口，其余模块都是它的实现细节。
"""

import json
import logging
import os
from typing import Dict, Optional

from .acoustid import AcoustIDClient
from .fpcalc import FingerprintCalculator
from .models import MatchResult

logger = logging.getLogger(__name__)


class FingerprintMatcher:
    """指纹匹配器——整合指纹计算与 AcoustID 查询"""

    def __init__(self, fpcalc_path: Optional[str] = None,
                 client_version: Optional[str] = None, debug_mode: bool = False):
        self.calculator = FingerprintCalculator(fpcalc_path)
        self.acoustid_client = AcoustIDClient(client_version)
        self.debug_mode = debug_mode
        if debug_mode:
            # debug_mode 只管开关：真正让 DEBUG 记录可见还得把级别放开。
            # 主程序已配好根 handler 时只调级别，不抢它的输出目标。
            logging.getLogger('fingerprint').setLevel(logging.DEBUG)
            if not logging.getLogger().handlers:
                logging.basicConfig(level=logging.DEBUG,
                                    format='%(levelname)s: %(message)s')
            logger.debug("=" * 60)
            logger.debug("FingerprintMatcher 初始化")
            logger.debug(f"  debug_mode = {debug_mode}")
            logger.debug(f"  fpcalc_path = {fpcalc_path}")
            logger.debug(f"  client_version = {client_version}")
            logger.debug("=" * 60)

    def match_file(self, audio_file_path: str, metadata: Optional[Dict] = None) -> MatchResult:
        """匹配音频文件：算指纹 → 查 AcoustID → 返回 MatchResult"""
        if self.debug_mode:
            logger.debug("=" * 60)
            logger.debug("开始匹配音频文件")
            logger.debug("=" * 60)
            logger.debug(f"audio_file_path = {audio_file_path}")
            logger.debug(f"metadata = {json.dumps(metadata, ensure_ascii=False) if metadata else None}")
            logger.debug(f"文件存在: {os.path.exists(audio_file_path)}")
            if os.path.exists(audio_file_path):
                logger.debug(f"文件大小: {os.path.getsize(audio_file_path)} bytes")

        logger.info(f"Processing file: {audio_file_path}")

        fingerprint_result = self.calculator.calculate(audio_file_path)

        if self.debug_mode:
            logger.debug("指纹计算结果:")
            logger.debug(f"  success = {fingerprint_result.success}")
            logger.debug(f"  fingerprint = {fingerprint_result.fingerprint[:50]}..."
                         if fingerprint_result.fingerprint else "  fingerprint = None")
            logger.debug(f"  duration = {fingerprint_result.duration}")
            logger.debug(f"  error = {fingerprint_result.error}")

        if not fingerprint_result.success:
            if self.debug_mode:
                logger.debug(f"指纹计算失败: {fingerprint_result.error}")
            return MatchResult(
                success=False,
                recordings=[],
                error="Failed to calculate fingerprint"
            )

        if self.debug_mode:
            logger.debug("开始查询 AcoustID API...")

        result = self.acoustid_client.match_fingerprint(
            fingerprint_result.fingerprint,
            fingerprint_result.duration,
            metadata
        )

        if self.debug_mode:
            logger.debug("AcoustID 查询结果:")
            logger.debug(f"  success = {result.success}")
            logger.debug(f"  recordings count = {len(result.recordings)}")
            if result.recordings:
                logger.debug(f"  最佳匹配: {result.recordings[0].get('title', 'N/A')}")
            logger.debug(f"  error = {result.error}")
            logger.debug("=" * 60)

        return result

    def match_from_fingerprint(self, fingerprint: str, duration: int,
                               metadata: Optional[Dict] = None) -> MatchResult:
        """从已有指纹直接匹配（跳过 fpcalc）"""
        logger.info(f"Matching from existing fingerprint ({len(fingerprint)} chars, {duration}s)")
        return self.acoustid_client.match_fingerprint(fingerprint, duration, metadata)

    def load_full_release_for_best_match(self, best_match: Dict,
                                         inc: Optional[list] = None) -> Optional[Dict]:
        """为最佳匹配补全完整 Release 信息

        与 Picard 的流程一致：
        AcoustID 匹配 → 选最佳 recording → 取 release_id → 加载完整 release
        """
        releases = best_match.get('releases', [])
        if not releases:
            logger.warning("No releases found in best match, cannot load full release")
            return None

        release_id = releases[0].get('id')
        if not release_id:
            logger.warning("No release ID found in best match")
            return None

        logger.info(f"Loading full release information for {release_id}")

        release_data = self.acoustid_client.release_loader.load_release_by_id(release_id, inc)

        if release_data and best_match.get('releases'):
            self._merge_release_to_recording(best_match, release_data)

        return release_data

    def _merge_release_to_recording(self, recording: Dict, release: Dict):
        """把完整 Release 合并进 recording 的第一张发行"""
        if recording.get('releases'):
            recording['releases'][0].update(release)
            if 'release-group' in release:
                recording['releases'][0]['release-group'] = release['release-group']

        logger.debug(f"Merged full release data into recording for release {release.get('id')}")
