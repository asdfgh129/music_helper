# -*- coding: utf-8 -*-
"""
音乐平台API接口模块
"""

from .netease import NetEaseMusicClient
from .qqmusic import QQMusicApi, QmusicClient
# from .migu import MiGuMusicClient
# from .kugou import KugouClient
# from .kuwo import KuwoClient
from .acoustid import AcoustidClient

from .netease import send as netease_send

__all__ = [
    "NetEaseMusicClient",
    "QQMusicApi",
    "QmusicClient",
    "MiGuMusicClient",
    "KugouClient",
    "KuwoClient",
    "AcoustidClient",
    "MusicResource",
]


class MusicResource:
    """音乐资源统一管理类"""

    def __init__(self, info):
        self.resource = self.get_resource(info)

    def get_resource(self, info):
        """根据平台名称获取对应的客户端"""
        if info == "netease":
            return NetEaseMusicClient()
        # elif info == "migu":
        #     return MiGuMusicClient()
        elif info == "qmusic":
            return QmusicClient()
        # elif info == "kugou":
        #     return KugouClient()
        # elif info == "kuwo":
        #     return KuwoClient()
        elif info == "acoustid":
            return AcoustidClient()
        raise Exception(f"暂不支持该音乐平台: {info}")

    def fetch_lyric(self, song_id):
        """获取歌词"""
        try:
            return self.resource.fetch_lyric(song_id)
        except Exception as e:
            print(f"音乐平台歌词获取失败: {e}")
            return ""

    def fetch_id3_by_title(self, title):
        """搜索音乐"""
        try:
            return self.resource.fetch_id3_by_title(title)
        except Exception as e:
            print(f"音乐平台搜索失败: {e}")
            return []
