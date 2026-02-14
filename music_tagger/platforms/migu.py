# -*- coding: utf-8 -*-
"""
咪咕音乐API客户端
"""
import requests


class MiGuMusicClient:
    """咪咕音乐客户端"""
    
    BASE_URL = "https://m.music.migu.cn/"
    header = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:80.0) Gecko/20100101 Firefox/80.0',
        'Referer': 'https://m.music.migu.cn/'
    }

    def fetch_lyric(self, song_id):
        """获取歌词"""
        url = f'https://music.migu.cn/v3/api/music/audioPlayer/getLyric?copyrightId={song_id}'
        res = requests.get(url, headers=self.header)
        return res.json()["lyric"]

    def fetch_id3_by_title(self, title):
        """搜索音乐"""
        url = self.BASE_URL + f"migu/remoting/scr_search_tag?rows=10&type=2&keyword={title}&pgc=1"
        res = requests.get(url, headers=self.header)
        songs = res.json()["musics"]
        for song in songs:
            song["id"] = song['copyrightId']
            song["name"] = song['songName']
            song["artist"] = song['singerName']
            song["artist_id"] = song['singerId']
            song["album"] = song['albumName']
            song["album_id"] = song['albumId']
            song["album_img"] = song['cover']
            song["year"] = ""
        return songs
