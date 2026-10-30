# -*- coding: utf-8 -*-
"""fingerprint - 音乐文件指纹匹配

用 fpcalc 算指纹 → AcoustID 查 recording → MusicBrainz 取标签与封面。
包名统一小写，与 core/services 一致；主流程经 services/tagger.py 延迟导入。
"""

from .musicbrainz_matcher import (
    FingerprintMatcher,
    format_recording_info,
    AcoustIDConfig,
    FingerprintResult,
    Recording,
    MatchResult,
    HTTPClient,
    FingerprintCalculator,
    JSONHelpers,
    RecordingResolver,
    AcoustIDClient,
)

__all__ = [
    'FingerprintMatcher',
    'format_recording_info',
    'AcoustIDConfig',
    'FingerprintResult',
    'Recording',
    'MatchResult',
    'HTTPClient',
    'FingerprintCalculator',
    'JSONHelpers',
    'RecordingResolver',
    'AcoustIDClient',
]
