# -*- coding: utf-8 -*-
"""fingerprint - 音乐文件指纹匹配

用 fpcalc 算指纹 → AcoustID 查 recording → MusicBrainz 取标签与封面。

包内分工（依赖方向自上而下，无环）：

| 模块 | 职责 |
|---|---|
| `models` | 常量与数据结构，不依赖包内任何模块 |
| `textconv` | 繁体 → 简体，HTTP 响应解析后立即转换 |
| `similarity` | Picard 的相似度打分，纯函数 |
| `http_client` | urllib 封装，失败统一收敛成 `(None, 错误串)` |
| `fpcalc` | 调用 fpcalc 算指纹 |
| `musicbrainz` | 节点转换、候选聚合、Release 加载 |
| `acoustid` | 查询 + 权重打分选最佳 |
| `formatting` | 标签映射与人类可读输出 |
| `matcher` | 门面 `FingerprintMatcher`，主流程只用这个 |

命令行验证单条链路：`python -m fingerprint <audio_file>`。
"""

import logging

from .acoustid import AcoustIDClient
from .formatting import format_complete_tags, format_recording_info, map_recording_to_tags
from .fpcalc import FingerprintCalculator
from .http_client import HTTPClient
from .matcher import FingerprintMatcher
from .models import AcoustIDConfig, FingerprintResult, MatchResult, Recording
from .musicbrainz import JSONHelpers, RecordingResolver, ReleaseLoader

# 原单文件模块在导入时就配好日志；拆包后统一放在包初始化处，行为不变
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

__all__ = [
    'FingerprintMatcher',
    'format_recording_info',
    'format_complete_tags',
    'map_recording_to_tags',
    'AcoustIDConfig',
    'FingerprintResult',
    'Recording',
    'MatchResult',
    'HTTPClient',
    'FingerprintCalculator',
    'JSONHelpers',
    'RecordingResolver',
    'ReleaseLoader',
    'AcoustIDClient',
]
