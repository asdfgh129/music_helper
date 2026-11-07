# -*- coding: utf-8 -*-
"""
QQ音乐API客户端
"""
import base64
import json
import uuid

import requests

QQMUSIC_SONG_COVER = "http://y.qq.com/music/photo_new/T002R300x300M000{id}.jpg"


class HttpRequest:
    """HTTP请求封装"""

    __session = None

    def __init__(self):
        self.__session = requests.Session()

    def getHttp(self, url: str, method: int = 0, data=b"", header=None) -> requests.Response:
        """Http请求-提交二进制流"""
        if header is None:
            header = {}
        if method == 0:
            d = self.__session.get(url, headers=header)
        else:
            d = self.__session.post(url, data, headers=header)
        return d

    def getHttp2Json(self, url: str, method: int = 0, data=None, header=None):
        """Http请求-提交json数据"""
        if header is None:
            header = {}
        if data is None:
            data = {}
        d = json.dumps(data, ensure_ascii=False)
        d = d.encode('utf-8')
        return self.getHttp(url, method, d, header)

    def getSession(self):
        return self.__session


class QQMusicApi:
    """QQ音乐API类"""

    QQHttpServer = HttpRequest()

    def getHead(self):
        return {
            "User-Agent": "QQ音乐/73222 CFNetwork/1406.0.2 Darwin/22.4.0".encode("utf-8"),
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh-Hans;q=0.9",
            "Referer": "http://y.qq.com",
            'Content-Type': 'application/json; charset=UTF-8',
        }

    def getQQServersCallback(self, url: str, method: int = 0, data=None):
        """重新设计了Http接口"""
        if data is None:
            data = {}
        return self.QQHttpServer.getHttp2Json(url, method, data, self.getHead())

    def getQQMusicMediaLyric(self, mid: str) -> dict:
        """获取歌词"""
        d = self.getQQServersCallback(
            "https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg?g_tk=5381&format=json&inCharset=utf-8&outCharset=utf-8&notice=0&platform=h5&needNewCode=1&ct=121&cv=0&songmid=" + mid)
        d = d.text
        return json.loads(d)

    def getQQMusicSearch(self, key: str = "", page: int = 1, size: int = 15):
        """搜索音乐"""
        url = "https://u.y.qq.com/cgi-bin/musicu.fcg"

        data = {
            "comm": {
                "wid": "",
                "tmeAppID": "qqmusic",
                "authst": "",
                "uid": "",
                "gray": "0",
                "OpenUDID": "2d484d3157d4ed482e406e6c5fdcf8c3d3275deb",
                "ct": "6",
                "patch": "2",
                "psrf_qqopenid": "",
                "sid": "",
                "psrf_access_token_expiresAt": "",
                "cv": "80600",
                "gzip": "0",
                "qq": "",
                "nettype": "2",
                "psrf_qqunionid": "",
                "psrf_qqaccess_token": "",
                "tmeLoginType": "2"
            },
            "music.search.SearchCgiService.DoSearchForQQMusicDesktop": {
                "module": "music.search.SearchCgiService",
                "method": "DoSearchForQQMusicDesktop",
                "param": {
                    "num_per_page": size,
                    "page_num": page,
                    "remoteplace": "txt.mac.search",
                    "search_type": 0,
                    "query": key,
                    "grp": 1,
                    "searchid": uuid.uuid1().__str__(),
                    "nqc_flag": 0
                }
            }
        }

        res = self.QQHttpServer.getHttp2Json(
            url, 1, data, {
                "referer": "https://y.qq.com/portal/profile.html",
                "Content-Type": "json/application;charset=utf-8",
                "user-agent": "QQ%E9%9F%B3%E4%B9%90/73222 CFNetwork/1406.0.3 Darwin/22.4.0"
            })
        jsons = res.json()
        res = jsons['music.search.SearchCgiService.DoSearchForQQMusicDesktop']['data']
        lst = res['body']['song']['list']
        meta = res['meta']

        list_clear = []
        for i in lst:
            list_clear.append({
                'album': i['album'],
                'docid': i['docid'],
                'id': i['id'],
                'mid': i['mid'],
                'name': i['title'],
                'singer': i['singer'],
                'time_public': i['time_public'],
                'title': i['title'],
                'file': i['file'],
            })

        return {
            'data': list_clear,
            'page': {
                'size': meta['sum'],
                'next': meta['nextpage'],
                'cur': meta['curpage'],
                'searchKey': key
            }
        }

    def getQQMusicMatchSong(self, name):
        """匹配歌曲"""
        song_list = self.getQQMusicSearch(name)
        songs = self.formatList(song_list["data"])
        if len(songs) == 0:
            return []
        return songs

    def formatList(self, mlist):
        """处理音乐列表"""
        songs = []
        for i in mlist:
            singer = ",".join([i["name"] for i in i["singer"]])

            _id = i["file"]
            code = ""
            format = ""
            qStr = ""
            fsize = 0
            mid = _id['media_mid']

            if int(_id['size_hires']) != 0:
                code = "RS01"
                format = "flac"
                qStr = "高解析无损 Hi-Res"
                fsize = int(_id['size_hires'])
            elif int(_id['size_flac']) != 0:
                code = "F000"
                format = "flac"
                qStr = "无损品质 FLAC"
                fsize = int(_id['size_flac'])
            elif int(_id['size_320mp3']) != 0:
                code = "M800"
                format = "mp3"
                qStr = "超高品质 320kbps"
                fsize = int(_id['size_320mp3'])
            elif int(_id['size_192ogg']) != 0:
                code = "O600"
                format = "ogg"
                qStr = "高品质 OGG"
                fsize = int(_id['size_192ogg'])
            elif int(_id['size_128mp3']) != 0:
                code = "M500"
                format = "mp3"
                qStr = "标准品质 128kbps"
                fsize = int(_id['size_128mp3'])
            elif int(_id['size_96aac']) != 0:
                code = "C400"
                format = "m4a"
                qStr = "低品质 96kbps"
                fsize = int(_id['size_96aac'])
            else:
                code = ""
                format = ""
                qStr = ""
                fsize = 0

            albumName = str(i["album"]['title']).strip(" ")
            if albumName == '':
                albumName = "未分类专辑"

            time_publish = i["time_public"]
            if time_publish == '':
                time_publish = ""

            songs.append({
                'prefix': code,
                'extra': format,
                'notice': qStr,
                'mid': mid,
                'musicid': i['id'],
                'id': i['mid'],
                'size': "%.2fMB" % (fsize / 1024 / 1024),
                'name': i["title"],
                'artist': singer,
                'album': albumName,
                "album_id": i["album"]['mid'],
                'year': time_publish,
                'readableText': f'{time_publish} {singer} - {i["title"]} | {qStr}',
                "album_img": QQMUSIC_SONG_COVER.format(id=i["album"]['mid'])
            })
        return songs


class QmusicClient:
    """QQ音乐客户端"""

    def fetch_lyric(self, song_id):
        a = QQMusicApi()
        res = a.getQQMusicMediaLyric(song_id)
        decoded_str = base64.b64decode(res.get("lyric", "")).decode("utf-8")
        return decoded_str

    def fetch_id3_by_title(self, title):
        a = QQMusicApi()
        songs = a.getQQMusicMatchSong(title)
        return songs
