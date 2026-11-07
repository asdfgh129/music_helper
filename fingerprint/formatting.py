# -*- coding: utf-8 -*-
"""MusicBrainz recording → 标签字典 / 人类可读文本

`map_recording_to_tags()` 参照 Picard 的 `const/tags.py` 实现了 120+ 个字段中的常用
子集，供「想看这条匹配到底带了什么信息」时使用。**主流程写标签不走这里**——
`tagger` 只用 title/artist/album/year/genre 五个字段，那种精简映射在
`tagger.parse_musicbrainz_recording()`，两处不要混。

`format_complete_tags()` 与 `format_recording_info()` 是给人看的（CLI 与调试），
输出格式改了不影响任何判定逻辑。
"""

import logging
from typing import Optional

from .models import AcoustIDConfig
from .similarity import extract_year_from_date

logger = logging.getLogger(__name__)


def format_recording_info(recording: dict, show_similarity: bool = False) -> str:
    """格式化成一段可读摘要（标题、艺术家、分数、最多 3 张发行）"""
    title = recording.get('title', 'Unknown')
    artists = []

    for artist_credit in recording.get('artist-credit', []):
        artist = artist_credit.get('artist', {})
        artists.append(artist.get('name', 'Unknown'))
        if 'joinphrase' in artist_credit:
            artists[-1] += artist_credit['joinphrase']

    artist_str = ' '.join(artists)
    score = recording.get('score', 0)
    sources = recording.get('sources', 0)
    acoustid = recording.get('acoustid', 'N/A')
    mbid = recording.get('id', 'N/A')

    info = f"\n{'=' * 60}\n"
    info += f"Title: {title}\n"
    info += f"Artist: {artist_str}\n"
    info += f"AcoustID Score: {score:.1f}%\n"
    info += f"Sources: {sources}\n"

    if show_similarity and '_calculated_similarity' in recording:
        similarity = recording['_calculated_similarity']
        info += f"Calculated Similarity: {similarity * 100:.1f}%\n"

    info += f"AcoustID: {acoustid}\n"
    info += f"MusicBrainz ID: {mbid}\n"

    releases = recording.get('releases', [])
    if releases:
        info += f"Releases ({len(releases)}):\n"
        for release in releases[:3]:  # 只显示前 3 个发行
            release_title = release.get('title', 'Unknown')
            release_date = release.get('date', 'N/A')
            release_group = release.get('release-group', {})
            release_type = release_group.get('primary-type', 'N/A')
            info += f"  - {release_title} ({release_date}) [{release_type}]\n"

    info += f"{'=' * 60}"
    return info


def get_cover_art_url(release_id: str) -> Optional[str]:
    """拼 Cover Art Archive 的 500px 封面地址（只拼不下载）"""
    try:
        return f"{AcoustIDConfig.COVER_ART_ARCHIVE_URL}/release/{release_id}/front-500.jpg"
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Failed to get cover art URL: {e}")
        return None


def map_recording_to_tags(recording: dict) -> dict:
    """把 MusicBrainz recording 映射成 Picard 风格的完整标签字典"""
    tags = {}

    # ========== 基本信息 ==========
    tags['title'] = recording.get('title', '')

    tags['musicbrainz_recordingid'] = recording.get('id', '')
    tags['acoustid_id'] = recording.get('acoustid', '')

    length_ms = recording.get('length', 0)
    if length_ms:
        tags['length'] = f"{length_ms // 60000}:{(length_ms % 60000) // 1000:02d}"

    # ========== 艺术家信息 ==========
    artist_credit = recording.get('artist-credit', [])
    if artist_credit:
        # 艺术家名称（带连接词）
        artists = []
        for credit in artist_credit:
            if isinstance(credit, dict):
                artist = credit.get('artist', {})
                name = artist.get('name', '')
                joinphrase = credit.get('joinphrase', '')
                if name:
                    artists.append(name + joinphrase)
        tags['artist'] = ''.join(artists).rstrip()

        # 艺术家名称列表
        artists_list = []
        for credit in artist_credit:
            if isinstance(credit, dict):
                name = credit.get('artist', {}).get('name', '')
                if name:
                    artists_list.append(name)
        tags['artists'] = artists_list

        # 艺术家 ID
        artist_ids = []
        for credit in artist_credit:
            if isinstance(credit, dict):
                artist_id = credit.get('artist', {}).get('id', '')
                if artist_id:
                    artist_ids.append(artist_id)
        tags['musicbrainz_artistid'] = artist_ids

        # 排序名称
        artists_sort = []
        for credit in artist_credit:
            if isinstance(credit, dict):
                artist = credit.get('artist', {})
                sort_name = artist.get('sort-name', '')
                joinphrase = credit.get('joinphrase', '')
                if sort_name:
                    artists_sort.append(sort_name + joinphrase)
        tags['artistsort'] = ''.join(artists_sort).rstrip()

        # 排序名称列表
        artists_sort_list = []
        for credit in artist_credit:
            if isinstance(credit, dict):
                sort_name = credit.get('artist', {}).get('sort-name', '')
                if sort_name:
                    artists_sort_list.append(sort_name)
        tags['artists_sort'] = artists_sort_list

        # 艺术家所属国家
        countries = []
        for credit in artist_credit:
            if isinstance(credit, dict):
                countries.append(credit.get('artist', {}).get('country', 'XX'))
        tags['artists_countries'] = countries

    # ========== ISRC 信息 ==========
    isrcs = recording.get('isrcs', [])
    if isrcs:
        tags['isrc'] = isrcs

    # ========== Release / Album 信息 ==========
    releases = recording.get('releases', [])
    if releases:
        release = releases[0]

        tags['album'] = release.get('title', '')
        tags['musicbrainz_releaseid'] = release.get('id', '')

        date = release.get('date', '')
        if date:
            tags['date'] = date
            year = extract_year_from_date(date)
            if year:
                tags['originalyear'] = str(year)
                tags['originaldate'] = date

        country = release.get('country', '')
        if country:
            tags['releasecountry'] = country
            tags['releasecountries'] = [country]

        status = release.get('status', '')
        if status:
            tags['releasestatus'] = status

        release_group = release.get('release-group', {})
        if release_group:
            tags['musicbrainz_releasegroupid'] = release_group.get('id', '')
            tags['releasegroup'] = release_group.get('title', '')

            primary_type = release_group.get('primary-type', '')
            if primary_type:
                tags['primaryreleasetype'] = primary_type
                tags['releasetype'] = [primary_type]

            secondary_types = release_group.get('secondary-types', [])
            if secondary_types:
                tags['secondaryreleasetype'] = secondary_types
                tags['releasetype'] = tags.get('releasetype', []) + secondary_types

            first_release_date = release_group.get('first-release-date', '')
            if first_release_date:
                tags['releasegroup_firstreleasedate'] = first_release_date

        # 唱片公司与目录编号
        label_info = release.get('label-info', [])
        labels = []
        catalog_numbers = []
        for info in label_info:
            label_name = info.get('label', {}).get('name', '')
            if label_name:
                labels.append(label_name)
            catalog_number = info.get('catalog-number', '')
            if catalog_number:
                catalog_numbers.append(catalog_number)
        if labels:
            tags['label'] = labels
        if catalog_numbers:
            tags['catalognumber'] = catalog_numbers

        barcode = release.get('barcode', '')
        if barcode:
            tags['barcode'] = barcode

        asin = release.get('asin', '')
        if asin:
            tags['asin'] = asin

        # 媒体信息（格式、碟号、音轨号）
        media_list = release.get('media', [])
        if media_list:
            formats = []
            for medium in media_list:
                fmt = medium.get('format', '')
                if fmt:
                    formats.append(fmt)
            if formats:
                tags['media'] = ', '.join(formats)

            total_tracks = 0
            total_discs = len(media_list)

            for medium in media_list:
                track_count = medium.get('track-count', 0)
                total_tracks += track_count

                # 找到「当前录音」在专辑里的位置，才有碟号/音轨号
                for track in medium.get('track', []):
                    track_recording = track.get('recording', {})
                    if track_recording.get('id') == recording.get('id'):
                        tags['discnumber'] = str(medium.get('position', 1))
                        tags['tracknumber'] = str(track.get('position', 0))
                        tags['musicbrainz_trackid'] = track.get('id', '')

                        disc_subtitle = medium.get('title', '')
                        if disc_subtitle:
                            tags['discsubtitle'] = disc_subtitle

                        tags['totaldiscs'] = str(total_discs)
                        tags['totaltracks'] = str(track_count)
                        tags['totalalbumtracks'] = str(total_tracks)

                        break

        # ========== 专辑艺术家 ==========
        release_artist_credit = release.get('artist-credit', [])
        if release_artist_credit:
            album_artists = []
            for credit in release_artist_credit:
                if isinstance(credit, dict):
                    artist = credit.get('artist', {})
                    name = artist.get('name', '')
                    joinphrase = credit.get('joinphrase', '')
                    if name:
                        album_artists.append(name + joinphrase)
            tags['albumartist'] = ''.join(album_artists).rstrip()

            album_artists_list = []
            for credit in release_artist_credit:
                if isinstance(credit, dict):
                    name = credit.get('artist', {}).get('name', '')
                    if name:
                        album_artists_list.append(name)
            tags['albumartists'] = album_artists_list

            album_artist_ids = []
            for credit in release_artist_credit:
                if isinstance(credit, dict):
                    artist_id = credit.get('artist', {}).get('id', '')
                    if artist_id:
                        album_artist_ids.append(artist_id)
            tags['musicbrainz_albumartistid'] = album_artist_ids

            album_artists_sort = []
            for credit in release_artist_credit:
                if isinstance(credit, dict):
                    artist = credit.get('artist', {})
                    sort_name = artist.get('sort-name', '')
                    joinphrase = credit.get('joinphrase', '')
                    if sort_name:
                        album_artists_sort.append(sort_name + joinphrase)
            tags['albumartistsort'] = ''.join(album_artists_sort).rstrip()

            album_artists_sort_list = []
            for credit in release_artist_credit:
                if isinstance(credit, dict):
                    sort_name = credit.get('artist', {}).get('sort-name', '')
                    if sort_name:
                        album_artists_sort_list.append(sort_name)
            tags['albumartists_sort'] = album_artists_sort_list

    # ========== 流派 / 标签 ==========
    tags_dict = recording.get('tags', [])
    if tags_dict:
        genres = []
        folksonomy_tags = []
        for tag in tags_dict:
            tag_name = tag.get('name', '')
            if tag_name:
                folksonomy_tags.append(tag_name)
                # 目前不区分流派与普通标签，两者取同一份（后续可加白名单过滤）
                genres.append(tag_name)
        if genres:
            tags['genre'] = genres
            tags['genres'] = folksonomy_tags
            tags['folksonomy_tags'] = folksonomy_tags

    # ========== 备注 ==========
    disambiguation = recording.get('disambiguation', '')
    if disambiguation:
        tags['recordingcomment'] = disambiguation

    # ========== 相似度 / 得分 ==========
    score = recording.get('score', 0)
    if score:
        tags['score'] = str(score)

    sources = recording.get('sources', 0)
    if sources:
        tags['sources'] = str(sources)

    return tags


def format_complete_tags(recording: dict, show_cover: bool = True) -> str:
    """把标签字典渲染成「人看的」多段文本（CLI 与排障用）"""
    tags = map_recording_to_tags(recording)

    lines = []
    lines.append("=" * 80)
    lines.append("完整标签信息")
    lines.append("=" * 80)

    lines.append("\n【基本信息】")
    lines.append(f"歌曲名称: {tags.get('title', 'Unknown')}")

    artist = tags.get('artist', '')
    if artist:
        lines.append(f"艺术家: {artist}")

    album = tags.get('album', '')
    if album:
        lines.append(f"专辑: {album}")

    length = tags.get('length', '')
    if length:
        lines.append(f"时长: {length}")

    acoustid = tags.get('acoustid_id', '')
    if acoustid:
        lines.append(f"AcoustID: {acoustid}")

    mb_recording_id = tags.get('musicbrainz_recordingid', '')
    if mb_recording_id:
        lines.append(f"MusicBrainz 录音ID: {mb_recording_id}")

    mb_release_id = tags.get('musicbrainz_releaseid', '')
    if mb_release_id:
        lines.append(f"MusicBrainz 专辑ID: {mb_release_id}")

    mb_releasegroup_id = tags.get('musicbrainz_releasegroupid', '')
    if mb_releasegroup_id:
        lines.append(f"MusicBrainz 专辑组ID: {mb_releasegroup_id}")

    mb_track_id = tags.get('musicbrainz_trackid', '')
    if mb_track_id:
        lines.append(f"MusicBrainz 音轨ID: {mb_track_id}")

    artist_ids = tags.get('musicbrainz_artistid', [])
    if artist_ids:
        lines.append(f"MusicBrainz 艺术家ID: {', '.join(artist_ids)}")

    albumartist = tags.get('albumartist', '')
    if albumartist:
        lines.append(f"专辑艺术家: {albumartist}")

    albumartist_ids = tags.get('musicbrainz_albumartistid', [])
    if albumartist_ids:
        lines.append(f"MusicBrainz 专辑艺术家ID: {', '.join(albumartist_ids)}")

    artistsort = tags.get('artistsort', '')
    if artistsort:
        lines.append(f"艺术家排序顺序: {artistsort}")

    albumartistsort = tags.get('albumartistsort', '')
    if albumartistsort:
        lines.append(f"专辑艺术家排序顺序: {albumartistsort}")

    tracknumber = tags.get('tracknumber', '')
    if tracknumber:
        lines.append(f"音轨号: {tracknumber}")

    discnumber = tags.get('discnumber', '')
    if discnumber:
        lines.append(f"碟号: {discnumber}")

    totaltracks = tags.get('totaltracks', '')
    if totaltracks:
        lines.append(f"总音轨数: {totaltracks}")

    totaldiscs = tags.get('totaldiscs', '')
    if totaldiscs:
        lines.append(f"总碟数: {totaldiscs}")

    totalalbumtracks = tags.get('totalalbumtracks', '')
    if totalalbumtracks:
        lines.append(f"专辑总音轨数: {totalalbumtracks}")

    date = tags.get('date', '')
    if date:
        lines.append(f"发行日期: {date}")

    originaldate = tags.get('originaldate', '')
    if originaldate:
        lines.append(f"首发日期: {originaldate}")

    originalyear = tags.get('originalyear', '')
    if originalyear:
        lines.append(f"首发年份: {originalyear}")

    country = tags.get('releasecountry', '')
    if country:
        lines.append(f"发行国/地区: {country}")

    status = tags.get('releasestatus', '')
    if status:
        lines.append(f"专辑状态: {status}")

    releasetype = tags.get('releasetype', [])
    if releasetype:
        lines.append(f"专辑类型: {', '.join(releasetype)}")

    primaryreleasetype = tags.get('primaryreleasetype', '')
    if primaryreleasetype:
        lines.append(f"主要专辑类型: {primaryreleasetype}")

    secondaryreleasetype = tags.get('secondaryreleasetype', [])
    if secondaryreleasetype:
        lines.append(f"次要专辑类型: {', '.join(secondaryreleasetype)}")

    labels = tags.get('label', [])
    if labels:
        lines.append(f"专辑唱片公司: {', '.join(labels)}")

    catalog_numbers = tags.get('catalognumber', [])
    if catalog_numbers:
        lines.append(f"编号: {', '.join(catalog_numbers)}")

    barcode = tags.get('barcode', '')
    if barcode:
        lines.append(f"条码: {barcode}")

    asin = tags.get('asin', '')
    if asin:
        lines.append(f"ASIN: {asin}")

    media = tags.get('media', '')
    if media:
        lines.append(f"媒体格式: {media}")

    genres = tags.get('genre', [])
    if genres:
        lines.append(f"流派: {', '.join(genres)}")

    isrcs = tags.get('isrc', [])
    if isrcs:
        lines.append(f"ISRC: {', '.join(isrcs)}")

    discsubtitle = tags.get('discsubtitle', '')
    if discsubtitle:
        lines.append(f"碟片标题: {discsubtitle}")

    recordingcomment = tags.get('recordingcomment', '')
    if recordingcomment:
        lines.append(f"备注: {recordingcomment}")

    score = tags.get('score', '')
    if score:
        lines.append(f"匹配得分: {score}")

    sources = tags.get('sources', '')
    if sources:
        lines.append(f"提交来源: {sources}")

    if show_cover:
        release_id = tags.get('musicbrainz_releaseid', '')
        if release_id:
            cover_url = get_cover_art_url(release_id)
            if cover_url:
                lines.append(f"\n封面图片: {cover_url}")

    lines.append("\n【备注】")
    lines.append("※ 封面图片来源于 Cover Art Archive (coverartarchive.org)")
    lines.append("※ 流派标签可能不完整，MusicBrainz 使用社区贡献的标签系统")
    lines.append("※ 更多详细信息请访问: https://musicbrainz.org/recording/" + recording.get('id', ''))

    lines.append("\n" + "=" * 80)

    return '\n'.join(lines)
