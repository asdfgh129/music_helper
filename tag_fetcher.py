# -*- coding: utf-8 -*-
"""
标签获取模块 - 从音乐平台获取标签信息
"""

import re
from utils import main_logger

# 延迟导入以避免条件导入问题
try:
    from config import QQMusicApi, NetEaseMusicClient
except ImportError:
    QQMusicApi = None
    NetEaseMusicClient = None


def parse_musicbrainz_recording(recording):
    """解析MusicBrainz录音记录为标签字典"""
    tags = {}

    try:
        # 歌曲标题
        title = recording.get('title', '')
        if title:
            tags['title'] = title

        # 艺术家
        artist_credit = recording.get('artist-credit', [])
        if artist_credit:
            artists = []
            for credit in artist_credit:
                artist = credit.get('artist', {})
                artists.append(artist.get('name', ''))
            tags['artist'] = '; '.join(artists)

        # 专辑
        releases = recording.get('releases', [])
        if releases:
            # 选择第一个发行的专辑
            album = releases[0].get('title', '')
            if album:
                tags['album'] = album

        # 年份
        if releases:
            date = releases[0].get('date', '')
            if date:
                # 提取年份（日期格式可能是YYYY-MM-DD或YYYY）
                year_match = re.search(r'(\d{4})', date)
                if year_match:
                    tags['year'] = year_match.group(1)

        # 流派（MusicBrainz不一定有）
        genre = recording.get('genre', '')
        if genre:
            tags['genre'] = genre

        return tags if tags else None

    except Exception as e:
        main_logger.error(f'解析MusicBrainz记录失败: {e}')
        return None


def fetch_qq_music_tags(qq_api, title, artist):
    """从QQ音乐获取标签信息"""
    try:
        # 构建搜索关键词
        query = f"{artist} {title}".strip() if artist else title

        # 搜索歌曲
        search_result = qq_api.getQQMusicSearch(query, page=1, size=5)

        if search_result and search_result.get('data'):
            songs = search_result['data']

            # 查找最佳匹配
            for song in songs:
                song_title = song.get('name', '')
                song_artists = song.get('singer', [])
                song_artist_names = ','.join([s.get('name', '') for s in song_artists])

                # 简单匹配逻辑
                title_match = title.lower() in song_title.lower() or song_title.lower() in title.lower()

                artist_match = True
                if artist:
                    song_artist_lower = song_artist_names.lower()
                    # 检查是否有艺术家名称匹配
                    artist_match = any(a.lower() in song_artist_lower or song_artist_lower in a.lower()
                                     for a in artist.replace(';', ',').split(','))

                if title_match and (not artist or artist_match):
                    # 获取详细信息
                    album = song.get('album', {}).get('title', '')
                    mid = song.get('mid', '')

                    # 构建标签信息
                    tags = {
                        'title': song_title,
                        'artist': song_artist_names,
                        'album': album,
                        'year': '',
                        'genre': ''
                    }

                    # 获取封面URL
                    if mid:
                        tags['album_img'] = f"http://y.qq.com/music/photo_new/T002R300x300M000{mid}.jpg"

                    return tags

        return None

    except Exception as e:
        main_logger.error(f'从QQ音乐获取标签失败: {e}')
        return None


def fetch_netease_tags(netease_api, title, artist):
    """从网易云音乐获取标签信息"""
    try:
        # 搜索歌曲
        songs = netease_api.fetch_id3_by_title(title)

        if songs:
            # 查找最佳匹配
            for song in songs:
                song_title = song.get('name', '')
                song_artist = song.get('artist', '')
                song_album = song.get('album', '')
                song_year = song.get('year', '')
                song_album_img = song.get('album_img', '')

                # 简单匹配逻辑
                title_match = title.lower() in song_title.lower() or song_title.lower() in title.lower()

                artist_match = True
                if artist:
                    song_artist_lower = song_artist.lower()
                    # 检查是否有艺术家名称匹配
                    artist_match = any(a.lower() in song_artist_lower or song_artist_lower in a.lower()
                                     for a in artist.replace(';', ',').split(','))

                if title_match and (not artist or artist_match):
                    # 构建标签信息
                    tags = {
                        'title': song_title,
                        'artist': song_artist,
                        'album': song_album,
                        'year': song_year,
                        'genre': ''
                    }

                    # 添加封面
                    if song_album_img:
                        tags['album_img'] = song_album_img

                    return tags

        return None

    except Exception as e:
        main_logger.error(f'从网易云音乐获取标签失败: {e}')
        return None


def fetch_album_cover(qq_api, netease_api, title, artist):
    """从音乐平台获取专辑封面"""
    try:
        # 先尝试QQ音乐
        if qq_api:
            search_result = qq_api.getQQMusicSearch(f"{artist} {title}".strip(), page=1, size=1)
            if search_result and search_result.get('data'):
                song = search_result['data'][0]
                mid = song.get('mid', '')
                if mid:
                    return f"http://y.qq.com/music/photo_new/T002R300x300M000{mid}.jpg"

        # 再尝试网易云音乐
        if netease_api:
            songs = netease_api.fetch_id3_by_title(title)
            if songs:
                album_img = songs[0].get('album_img', '')
                if album_img:
                    return album_img

        return None

    except Exception as e:
        main_logger.error(f'获取专辑封面失败: {e}')
        return None
