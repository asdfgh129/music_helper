# -*- coding: utf-8 -*-
"""music_tagger - 在线音乐平台客户端

只保留主流程真正使用的两个平台客户端，供 services.tagger 延迟导入。
标签匹配、择优与写盘逻辑统一在 core.scoring 与 services.tagger，
这里不再保留第二套「MusicTagger」实现。
"""

from .platforms import NetEaseMusicClient, QQMusicApi

__version__ = '1.1.0'
__all__ = ['NetEaseMusicClient', 'QQMusicApi']
