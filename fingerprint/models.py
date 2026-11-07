# -*- coding: utf-8 -*-
"""AcoustID / MusicBrainz 的常量与数据结构

这里只有数据和类型，不含任何 IO 或算法——`http_client`、`acoustid`、`matcher`
都依赖本模块，反过来本模块不依赖包内任何其他模块。
"""

from typing import Dict, List, Optional


class AcoustIDConfig:
    """AcoustID / MusicBrainz 服务地址与默认参数"""

    ACOUSTID_KEY = 'v8pQ6oyB'
    ACOUSTID_URL = 'https://api.acoustid.org/v2'
    MUSICBRAINZ_URL = 'https://musicbrainz.org/ws/2'
    COVER_ART_ARCHIVE_URL = 'https://coverartarchive.org'
    FPCALC_NAMES = ['fpcalc', 'pyfpcalc']
    DEFAULT_CLIENT_VERSION = '2.12.0'


class FingerprintResult:
    """指纹查询结果"""

    def __init__(self, fingerprint: str, duration: int, success: bool = True):
        self.fingerprint = fingerprint
        self.duration = duration
        self.success = success
        self.error = None


class Recording:
    """录音信息（带来源计数，用于在多条 AcoustID 结果间加权）"""

    def __init__(self, recording: dict, result_score: float = 1.0, sources: int = 1):
        self.recording = recording
        self.result_score = result_score
        self.sources = sources


class MatchResult:
    """一次匹配的完整结果"""

    def __init__(self, success: bool, recordings: Optional[List[Dict]] = None,
                 error: Optional[str] = None, best_match: Optional[Dict] = None):
        self.success = success
        self.recordings = recordings or []
        self.error = error
        self.best_match = best_match  # 最佳匹配的录音
