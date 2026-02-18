# -*- coding: utf-8 -*-
"""
Fingerprint 模块 - 音乐文件指纹匹配
从 AcoustID API 查询指纹并从 MusicBrainz 获取标签信息
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
