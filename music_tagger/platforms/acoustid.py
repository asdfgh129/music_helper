# -*- coding: utf-8 -*-
"""
声纹识别API客户端
"""
import os
import sys

try:
    from component.mz import acoustid
except ImportError:
    print("警告: 无法导入 acoustid 模块")
    acoustid = None


# API密钥
APIKEY = "cSpUJKpD"


def get_acoustid(path):
    """
    使用声纹识别获取音乐信息
    
    Args:
        path: 音乐文件路径
    
    Returns:
        list: 识别结果列表
    """
    if acoustid is None:
        return []
    
    try:
        return acoustid.match(APIKEY, path)
    except Exception as e:
        print(f"声纹识别失败: {e}")
        return []


class AcoustidClient:
    """声纹识别客户端"""

    def fetch_lyric(self, song_id):
        raise Exception("声纹识别不支持获取歌词")

    def fetch_id3_by_title(self, title):
        """
        使用声纹识别匹配音乐
        
        Args:
            title: 实际上是音乐文件路径
        
        Returns:
            list: 匹配结果列表
        """
        songs = []
        res = get_acoustid(title)
        for each in res:
            songs.append({
                "id": each[1],
                "name": each[2],
                "artist": each[3],
                "artist_id": "",
                "album": each[4],
                "album_id": "",
                "album_img": "",
                "year": "",
            })
        return songs
