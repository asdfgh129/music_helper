# -*- coding: utf-8 -*-
"""音乐平台客户端

只导出仍在使用的两个平台。酷狗/酷我/咪咕客户端已删除：上游接口不可用，
主流程也只走 QQ 音乐与网易云（见 docs/features.md）。
"""

from .netease import NetEaseMusicClient
from .qqmusic import QQMusicApi

__all__ = ['NetEaseMusicClient', 'QQMusicApi']
