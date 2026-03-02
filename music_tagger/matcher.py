# -*- coding: utf-8 -*-
"""
音乐标签智能匹配模块
"""
import os
from concurrent.futures import ThreadPoolExecutor

try:
    from music_tag import load_file
except ImportError:
    raise ImportError("需要安装 music_tag 模块")

from .platforms import MusicResource
# from .utils import match_score


def match_artist(my_value, u_value):
    """
    艺术家匹配算法(支持多艺术家)
    
    Args:
        my_value: 本地艺术家名称
        u_value: 在线艺术家名称(可能包含多个, 用逗号分隔)
    
    Returns:
        int: 匹配得分
    """
    if "," in u_value:
        return match_score(my_value, u_value.split(",")[0].replace(" ", "")) \
               + match_score(my_value, u_value.split(",")[1].replace(" ", ""))
    else:
        return match_score(my_value, u_value)

def match_score(my_value, u_value):
    """
    字符串匹配评分算法
    
    Args:
        my_value: 本地值
        u_value: 在线值
    
    Returns:
        int: 2(完全匹配) | 1(包含匹配) | 0(不匹配)
    """
    try:
        my_value = my_value.lower().replace(" ", "")
        u_value = u_value.lower().replace(" ", "")
        
        # 繁简转换
        # if not issimp(my_value):
        #     my_value = convert(my_value, 'zh-cn')
        # if not issimp(u_value):
        #     u_value = convert(u_value, 'zh-cn')
        
        if not my_value or not u_value:
            return 0
        
        # 完全匹配
        if my_value == u_value:
            return 2
        # 包含匹配
        elif my_value in u_value or u_value in my_value:
            return 1
        # 不匹配
        return 0
    except Exception:
        return 0


class SmartTagClient:
    """智能标签匹配客户端 - 多平台并行搜索"""

    def fetch_lyric(self, song_id):
        """智能匹配不直接获取歌词"""
        pass

    def run(self, resource, title):
        """
        从指定平台搜索
        
        Args:
            resource: 平台名称
            title: 搜索关键词
        
        Returns:
            list: 搜索结果列表
        """
        from .platforms import MusicResource
        songs = MusicResource(resource).fetch_id3_by_title(title)
        for song in songs:
            song["resource"] = resource
        return songs

    def fetch_id3_by_title(self, info):
        """
        智能匹配 - 并行搜索多个平台
        
        Args:
            info: {"title": "歌曲名", "full_path": "文件路径"}
        
        Returns:
            list: 按匹配度排序的结果列表(前15个)
        """
        title = info["title"]
        full_path = info["full_path"]
        
        file = load_file(full_path)
        artist = file["artist"].value or ""
        album = file["album"].value or ""
        
        order_songs = []
        max_score = 0
        
        # 并行搜索多个平台
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = pool.map(self.run, ["qmusic", "netease", "migu", "kugou"], [title] * 4)

        for songs in results:
            for song in songs:
                title_score = match_score(title, song["name"])
                artist_score = match_artist(artist if artist else title, song["artist"])
                album_score = match_score(album if album else title, song["album"])
                
                if artist and artist_score == 0:
                    artist_score = -2
                
                # 标题包含艺术家信息
                if not artist and artist_score >= 1:
                    if title_score >= 1:
                        title_score = 2
                
                song["score"] = title_score + artist_score + album_score
                max_score = max(max_score, song["score"])
                
                if title_score == 0:
                    continue
                
                order_songs.append(song)
        
        # 按得分降序排序
        order_songs.sort(key=lambda x: x["score"], reverse=True)
        return order_songs[:15]


# 导出函数
# from .utils import match_score
__all__ = ["SmartTagClient", "match_score", "match_artist"]
