# -*- coding: utf-8 -*-
"""
网易云音乐API客户端
"""
import time
from random import randint

import requests

from ..encrypt import linuxEncrypt, weEncrypt


def timestamp_to_dt(timestamp, format_type="%Y-%m-%d %H:%M:%S"):
    """时间戳转日期时间字符串"""
    time_local = time.localtime(timestamp)
    dt = time.strftime(format_type, time_local)
    return dt


userAgents = [
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/60.0.3112.90 Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 9_1 like Mac OS X) AppleWebKit/601.1.46 (KHTML, like Gecko) Version/9.0 Mobile/13B143 Safari/601.1',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 9_1 like Mac OS X) AppleWebKit/601.1.46 (KHTML, like Gecko) Version/9.0 Mobile/13B143 Safari/601.1',
    'Mozilla/5.0 (Linux; Android 5.0; SM-G900P Build/LRX21T) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/59.0.3071.115 Mobile Safari/537.36',
    'Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/59.0.3071.115 Mobile Safari/537.36',
    'Mozilla/5.0 (Linux; Android 5.1.1; Nexus 6 Build/LYZ28E) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/59.0.3071.115 Mobile Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 10_3_2 like Mac OS X) AppleWebKit/603.2.4 (KHTML, like Gecko) Mobile/14F89;GameHelper',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 10_0 like Mac OS X) AppleWebKit/602.1.38 (KHTML, like Gecko) Version/10.0 Mobile/14A300 Safari/602.1',
    'Mozilla/5.0 (iPad; CPU OS 10_0 like Mac OS X) AppleWebKit/602.1.38 (KHTML, like Gecko) Version/10.0 Mobile/14A300 Safari/602.1',
    'Mozilla/5.0 (Linux; U; Android 8.1.0; zh-cn; BKK-AL10 Build/HONORBKK-AL10) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/66.0.3359.126 MQQBrowser/10.6 Mobile Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.12; rv:46.0) Gecko/20100101 Firefox/46.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/59.0.3071.115 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_5) AppleWebKit/603.2.4 (KHTML, like Gecko) Version/10.1.1 Safari/603.2.4',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:46.0) Gecko/20100101 Firefox/46.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/51.0.2704.103 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/42.0.2311.135 Safari/537.36 Edge/13.10586'
]


class send:
    """网易云音乐HTTP请求发送器"""

    def __init__(self, data={}, encrypt_method="weapi", timeout=10, url=""):
        self.BASE_URL = "https://music.163.com/"
        self.headers = {
            "User-Agent": userAgents[randint(0, len(userAgents)) - 1],
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": self.BASE_URL
        }
        self.session = requests.session()
        self.encrypt_method = encrypt_method
        self.data = data
        self.timeout = timeout
        self.url = url

    def __url(self, url):
        if url == "":
            return self.BASE_URL + "api/linux/forward"
        if url[:4] == "http":
            return url
        return self.BASE_URL + url

    def encrypt(self, data):
        """加密请求数据"""
        if self.encrypt_method == "linuxapi":
            self.headers["User-Agent"] = userAgents[0]
            data["method"] = "POST"
            return linuxEncrypt(data)
        elif self.encrypt_method == "weapi":
            return weEncrypt(data)
        return data

    def POST(self, url, cookie={}):
        """POST请求"""
        response = self.session.post(
            self.__url(url),
            data=self.encrypt(self.data),
            headers=self.headers,
            cookies=cookie,
            timeout=self.timeout
        )
        return response

    def GET(self, url, cookie={}):
        """GET请求"""
        response = self.session.get(
            self.__url(url),
            headers=self.headers,
            cookies=cookie,
            timeout=self.timeout
        )
        return response


class NetEaseMusicClient:
    """网易云音乐客户端"""

    BASE_URL = "https://music.163.com/"

    def fetch_lyric(self, song_id):
        """获取歌词"""
        data = send(
            {"url": self.BASE_URL + "api/song/lyric?lv=-1&kv=-1&tv=-1", "params": {"id": song_id}},
            "linuxapi"
        ).POST("")
        return data.json().get("lrc", {}).get("lyric")

    def fetch_id3_by_title(self, title):
        """搜索音乐"""
        data = send({'s': title, 'type': '1', 'limit': '10', 'offset': '0'}).POST("weapi/cloudsearch/pc")
        try:
            songs = data.json().get("result", {}).get("songs", [])
        except Exception as e:
            print("网易云音乐搜索失败", e, data.text)
            songs = []

        for song in songs:
            artists = song.get("ar", [])
            album = song.get("al", {})
            if artists:
                artist = ",".join([artist.get("name", "") for artist in artists])
                artist_id = artists[0].get("id", "")
            else:
                artist = ""
                artist_id = ""
            year = song.get("publishTime", "")
            if year:
                year = timestamp_to_dt(year / 1000, "%Y")
            song["artist"] = artist
            song["artist_id"] = artist_id
            song["album"] = album.get("name", "")
            song["album_id"] = album.get("id", "")
            song["album_img"] = album.get("picUrl", {})
            song["year"] = year or ""
        return songs
