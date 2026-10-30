# -*- coding: utf-8 -*-
"""music_tagger - 在线音乐平台客户端

只保留主流程真正使用的两个平台客户端，供 services.tagger 延迟导入。
标签匹配、择优与写盘逻辑统一在 core.scoring 与 services.tagger，
这里不再保留第二套「MusicTagger」实现。

包名沿用上游项目名（历史原因，内容已不是"打标签"）；版本号不再单独维护，
全仓唯一版本号是 config.__version__，与 CHANGELOG.md 对齐。
"""

from .platforms import NetEaseMusicClient, QQMusicApi

__all__ = ['NetEaseMusicClient', 'QQMusicApi']
