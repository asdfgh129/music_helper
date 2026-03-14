# -*- coding: utf-8 -*-
"""
标签获取模块 - 从音乐平台获取标签信息
"""

import re
import utils


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

            # Release ID (用于获取封面)
            release_id = releases[0].get('id', '')
            if release_id:
                tags['musicbrainz_releaseid'] = release_id

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

        # 封面URL (从Cover Art Archive获取)
        if tags.get('musicbrainz_releaseid'):
            tags['album_img'] = f"https://coverartarchive.org/release/{tags['musicbrainz_releaseid']}/front-500.jpg"

        return tags if tags else None

    except Exception as e:
        utils.main_logger.error(f'解析MusicBrainz记录失败: {e}')
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

                    # 获取歌词
                    if mid:
                        lyrics = fetch_qq_music_lyric(qq_api, mid)
                        if lyrics:
                            tags['lyrics'] = lyrics

                    return tags

        return None

    except Exception as e:
        utils.main_logger.error(f'从QQ音乐获取标签失败: {e}')
        return None


def fetch_qq_music_lyric(qq_api, mid):
    """从QQ音乐获取歌词

    Args:
        qq_api: QQ音乐API客户端
        mid: 歌曲ID

    Returns:
        歌词文本，如果获取失败返回None
    """
    try:
        lyric_data = qq_api.getQQMusicMediaLyric(mid)
        if not lyric_data:
            return None

        # 解析歌词数据
        lyric = lyric_data.get('lyric', '')
        trans = lyric_data.get('trans', '')

        # 如果有歌词，进行解码
        import base64
        if lyric:
            try:
                # 尝试base64解码
                decoded_lyric = base64.b64decode(lyric).decode('utf-8')
            except Exception:
                # 如果解码失败，直接使用原字符串
                decoded_lyric = lyric
        else:
            decoded_lyric = ''

        # 如果有翻译，合并
        if trans:
            try:
                decoded_trans = base64.b64decode(trans).decode('utf-8')
            except Exception:
                decoded_trans = trans

            # 合并歌词和翻译（简单拼接）
            if decoded_lyric and decoded_trans:
                return decoded_lyric + '\n\n[翻译]\n' + decoded_trans
            elif decoded_trans:
                return decoded_trans

        return decoded_lyric if decoded_lyric else None

    except Exception as e:
        utils.main_logger.error(f'获取QQ音乐歌词失败: {e}')
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
                song_id = song.get('id', '')

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

                    # 获取歌词
                    if song_id:
                        lyrics = fetch_netease_lyric(netease_api, song_id)
                        if lyrics:
                            tags['lyrics'] = lyrics

                    return tags

        return None

    except Exception as e:
        utils.main_logger.error(f'从网易云音乐获取标签失败: {e}')
        return None


def fetch_netease_lyric(netease_api, song_id):
    """从网易云音乐获取歌词

    Args:
        netease_api: 网易云音乐API客户端
        song_id: 歌曲ID

    Returns:
        歌词文本，如果获取失败返回None
    """
    try:
        lyric_data = netease_api.fetch_lyric(song_id)
        if not lyric_data:
            return None

        # 网易云音乐直接返回歌词文本
        return lyric_data

    except Exception as e:
        utils.main_logger.error(f'获取网易云音乐歌词失败: {e}')
        return None


def calculate_tag_score(tags, query_title, query_artist):
    """计算标签匹配度和完整性得分

    Args:
        tags: 标签字典
        query_title: 查询的标题
        query_artist: 查询的艺术家

    Returns:
        得分(0-100),分数越高表示越匹配且标签越完整
    """
    score = 0

    # 完整性得分(最高40分)
    completeness_score = 0
    if tags.get('title'):
        completeness_score += 10
    if tags.get('artist'):
        completeness_score += 10
    if tags.get('album'):
        completeness_score += 10
    if tags.get('year'):
        completeness_score += 5
    if tags.get('genre'):
        completeness_score += 5

    score += completeness_score

    # 匹配度得分(最高60分)
    match_score = 0

    # 标题匹配(最高30分)
    tag_title = tags.get('title', '')
    if tag_title:
        if query_title.lower() == tag_title.lower():
            match_score += 30  # 完全匹配
        elif query_title.lower() in tag_title.lower() or tag_title.lower() in query_title.lower():
            match_score += 20  # 包含匹配

    # 艺术家匹配(最高30分)
    tag_artist = tags.get('artist', '')
    if tag_artist and query_artist:
        query_artists = [a.strip().lower() for a in query_artist.replace(';', ',').split(',') if a.strip()]
        tag_artists = [a.strip().lower() for a in tag_artist.replace(';', ',').split(',') if a.strip()]

        for qa in query_artists:
            if any(ta == qa or qa in ta or ta in qa for ta in tag_artists):
                match_score += 30
                break

    score += match_score

    return score


def fetch_best_tags(qq_api, netease_api, title, artist):
    """从QQ音乐和网易云音乐获取最佳标签

    同时查询两个平台,选择标签最完整且匹配度最高的结果

    Args:
        qq_api: QQ音乐API客户端
        netease_api: 网易云音乐API客户端
        title: 歌曲标题
        artist: 艺术家(可选)

    Returns:
        最佳标签字典,如果都失败返回None
    """
    candidates = []

    # 查询QQ音乐
    if qq_api:
        try:
            qq_tags = fetch_qq_music_tags(qq_api, title, artist)
            if qq_tags:
                qq_tags['source'] = 'QQ音乐'
                score = calculate_tag_score(qq_tags, title, artist)
                candidates.append((score, qq_tags))
                utils.main_logger.debug(f'QQ音乐候选标签: 标题={qq_tags.get("title")}, 艺术家={qq_tags.get("artist")}, 得分={score}')
        except Exception as e:
            utils.main_logger.warning(f'查询QQ音乐失败: {e}')

    # 查询网易云音乐
    if netease_api:
        try:
            netease_tags = fetch_netease_tags(netease_api, title, artist)
            if netease_tags:
                netease_tags['source'] = '网易云音乐'
                score = calculate_tag_score(netease_tags, title, artist)
                candidates.append((score, netease_tags))
                utils.main_logger.debug(f'网易云音乐候选标签: 标题={netease_tags.get("title")}, 艺术家={netease_tags.get("artist")}, 得分={score}')
        except Exception as e:
            utils.main_logger.warning(f'查询网易云音乐失败: {e}')

    # 选择得分最高的
    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        best_score, best_tags = candidates[0]
        best_tags['score'] = best_score
        utils.main_logger.info(f'选择最佳标签: 来源={best_tags.get("source")}, 得分={best_score:.1f}')
        return best_tags

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
        utils.main_logger.error(f'获取专辑封面失败: {e}')
        return None
