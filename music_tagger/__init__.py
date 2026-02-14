# -*- coding: utf-8 -*-
"""
Music Tagger - 音乐文件标签管理工具
"""

from .core import MusicTagger
from .matcher import SmartTagClient, match_score, match_artist
from .platforms import MusicResource

__version__ = "1.0.0"
__all__ = [
    "MusicTagger",
    "MusicResource",
    "SmartTagClient",
    "match_score",
    "match_artist",
    "auto_tag",
    "batch_update_tags",
]

from .core import auto_tag, batch_update_tags
