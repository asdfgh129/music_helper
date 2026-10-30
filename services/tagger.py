# -*- coding: utf-8 -*-
"""
标签服务 - 合并原 tag_fetcher.py + tag_updater.py

职责：
    1. 声纹（MusicBrainz）→ 标签
    2. 文件名 → QQ音乐 / 网易云 → 标签
    3. 顺带下载封面与歌词

可选依赖（Fingerprint、music_tagger.platforms、requests）全部延迟导入，
缺失时只降级对应能力，不影响程序启动。
"""

from dataclasses import dataclass, field

import config
import core.tags as core_tags
from core.naming import parse_filename
from core.scoring import tag_score

TAG_KEYS = ('title', 'artist', 'album', 'year', 'genre')


@dataclass
class UpdateResult:
    path: str
    source: str = ''
    fields: list = field(default_factory=list)
    cover: bool = False
    lyric: bool = False
    error: str = ''

    @property
    def updated(self):
        return bool(self.fields or self.cover or self.lyric)


# ---------------- MusicBrainz 解析 ----------------

def parse_musicbrainz_recording(recording):
    """把 FingerprintMatcher 返回的 recording 转成统一标签字典"""
    tags = {}
    try:
        if recording.get('title'):
            tags['title'] = recording['title']

        credits = recording.get('artist-credit') or []
        artists = [c.get('artist', {}).get('name', '') for c in credits if isinstance(c, dict)]
        artists = [name for name in artists if name]
        if artists:
            tags['artist'] = '; '.join(artists)

        releases = recording.get('releases') or []
        if releases:
            release = releases[0]
            if release.get('title'):
                tags['album'] = release['title']
            if release.get('date'):
                year = str(release['date'])[:4]
                if year.isdigit():
                    tags['year'] = year
            if release.get('id'):
                tags['album_img'] = f'https://coverartarchive.org/release/{release["id"]}/front-500.jpg'

        if recording.get('genre'):
            tags['genre'] = recording['genre']
    except Exception:  # noqa: BLE001 - 结构异常时返回已解析部分
        pass
    return tags


# ---------------- 在线平台 ----------------

def _artist_matches(query_artist, online_artist):
    if not query_artist:
        return True
    online = online_artist.lower()
    for name in query_artist.replace(';', ',').replace('；', ',').split(','):
        name = name.strip().lower()
        if name and (name in online or online in name):
            return True
    return False


def fetch_qq_tags(qq_api, title, artist):
    """从 QQ 音乐查询标签（含歌词）"""
    query = f'{artist} {title}'.strip() if artist else title
    result = qq_api.getQQMusicSearch(query, page=1, size=5)
    songs = (result or {}).get('data') or []

    for song in songs:
        song_title = song.get('name', '')
        singers = song.get('singer') or []
        song_artist = ','.join(s.get('name', '') for s in singers)
        title_ok = title.lower() in song_title.lower() or song_title.lower() in title.lower()
        if not title_ok or not _artist_matches(artist, song_artist):
            continue

        mid = song.get('mid', '')
        tags = {
            'title': song_title,
            'artist': song_artist,
            'album': (song.get('album') or {}).get('title', ''),
            'year': '',
            'genre': '',
        }
        if mid:
            tags['album_img'] = f'http://y.qq.com/music/photo_new/T002R300x300M000{mid}.jpg'
            lyric = fetch_qq_lyric(qq_api, mid)
            if lyric:
                tags['lyrics'] = lyric
        return tags
    return None


def fetch_qq_lyric(qq_api, mid):
    import base64

    try:
        data = qq_api.getQQMusicMediaLyric(mid) or {}
    except Exception:  # noqa: BLE001
        return None

    def decode(value):
        if not value:
            return ''
        try:
            return base64.b64decode(value).decode('utf-8')
        except Exception:  # noqa: BLE001
            return value

    lyric = decode(data.get('lyric'))
    trans = decode(data.get('trans'))
    if lyric and trans:
        return f'{lyric}\n\n[翻译]\n{trans}'
    return lyric or trans or None


def fetch_netease_tags(netease_api, title, artist):
    """从网易云音乐查询标签（含歌词）"""
    songs = netease_api.fetch_id3_by_title(title) or []
    for song in songs:
        song_title = song.get('name', '')
        title_ok = title.lower() in song_title.lower() or song_title.lower() in title.lower()
        if not title_ok or not _artist_matches(artist, song.get('artist', '')):
            continue

        tags = {
            'title': song_title,
            'artist': song.get('artist', ''),
            'album': song.get('album', ''),
            'year': song.get('year', ''),
            'genre': '',
        }
        if song.get('album_img'):
            tags['album_img'] = song['album_img']
        if song.get('id'):
            try:
                lyric = netease_api.fetch_lyric(song['id'])
            except Exception:  # noqa: BLE001
                lyric = None
            if lyric:
                tags['lyrics'] = lyric
        return tags
    return None


def fetch_best_tags(qq_api, netease_api, title, artist):
    """同时查询两个平台，按 tag_score 择优"""
    candidates = []
    for name, api, fetcher in (('QQ音乐', qq_api, fetch_qq_tags),
                               ('网易云音乐', netease_api, fetch_netease_tags)):
        if not api:
            continue
        try:
            tags = fetcher(api, title, artist)
        except Exception:  # noqa: BLE001 - 单平台失败不影响另一个
            continue
        if tags:
            tags['source'] = name
            candidates.append((tag_score(tags, title, artist), tags))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    score, best = candidates[0]
    best['score'] = score
    return best


def download_cover(url):
    """下载封面，超过 MAX_COVER_SIZE 直接放弃"""
    try:
        import requests
    except ImportError:
        return None
    try:
        response = requests.get(url, timeout=15)
        if response.status_code != 200:
            return None
        data = response.content
        if not data or len(data) > config.MAX_COVER_SIZE:
            return None
        return data
    except Exception:  # noqa: BLE001
        return None


# ---------------- 服务主体 ----------------

class Tagger:
    """标签更新服务"""

    def __init__(self, threshold=None, dry_run=False, with_fingerprint=True):
        self.threshold = config.FINGERPRINT_THRESHOLD if threshold is None else threshold
        self.dry_run = dry_run
        self.with_fingerprint = with_fingerprint
        self._fingerprint = None
        self._fingerprint_ready = False
        self._qq = None
        self._netease = None
        self._online_ready = False

    # ---------- 延迟加载 ----------

    def _get_fingerprint(self):
        if self._fingerprint_ready:
            return self._fingerprint
        self._fingerprint_ready = True
        if not self.with_fingerprint:
            return None
        try:
            from Fingerprint import FingerprintMatcher
            self._fingerprint = FingerprintMatcher()
        except Exception:  # noqa: BLE001 - 缺 acoustid/fpcalc 时降级
            self._fingerprint = None
        return self._fingerprint

    def _get_online(self):
        if self._online_ready:
            return self._qq, self._netease
        self._online_ready = True
        try:
            from music_tagger.platforms.qqmusic import QQMusicApi
            self._qq = QQMusicApi()
        except Exception:  # noqa: BLE001
            self._qq = None
        try:
            from music_tagger.platforms.netease import NetEaseMusicClient
            self._netease = NetEaseMusicClient()
        except Exception:  # noqa: BLE001
            self._netease = None
        return self._qq, self._netease

    # ---------- 主流程 ----------

    @staticmethod
    def _merge(current, new):
        """已有标签优先，只填补空缺"""
        merged = dict(current)
        for key in TAG_KEYS:
            if not merged.get(key) and new.get(key):
                merged[key] = new[key]
        return merged

    def update(self, track):
        """更新单个文件，返回 UpdateResult（不改动 tag 以外的内容）"""
        result = UpdateResult(path=track.path)
        current = dict(track.tags)
        merged = dict(current)
        extra = {}

        # 第一步：声纹
        matcher = self._get_fingerprint()
        if matcher:
            try:
                match = matcher.match_file(track.path)
                if match.success and match.recordings:
                    best = max(match.recordings, key=lambda r: r.get('score', 0))
                    score = float(best.get('score') or 0)
                    if score >= self.threshold:
                        found = parse_musicbrainz_recording(best)
                        merged = self._merge(merged, found)
                        extra = found
                        result.source = f'MusicBrainz({score:.0f})'
            except Exception as exc:  # noqa: BLE001
                result.error = f'声纹查询失败: {exc}'

        # 第二步：在线平台
        if not result.source:
            qq, netease = self._get_online()
            title = merged.get('title') or parse_filename(track.filename)[1]
            artist = merged.get('artist') or parse_filename(track.filename)[0]
            if title and (qq or netease):
                try:
                    found = fetch_best_tags(qq, netease, title, artist)
                except Exception as exc:  # noqa: BLE001
                    found = None
                    result.error = f'在线查询失败: {exc}'
                if found:
                    merged = self._merge(merged, found)
                    extra = found
                    result.source = found.get('source', '')

        # 写回标签
        changed = {key: merged[key] for key in TAG_KEYS
                   if merged.get(key) and merged[key] != current.get(key)}
        if changed:
            result.fields = sorted(changed)
            if not self.dry_run:
                core_tags.write_tags(track.path, changed)
            track.tags.update(changed)

        # 封面
        cover_url = extra.get('album_img')
        if cover_url and not core_tags.has_cover(track.path):
            data = download_cover(cover_url)
            if data and not self.dry_run:
                result.cover = core_tags.write_cover(track.path, data)
            elif data:
                result.cover = True

        # 歌词
        if extra.get('lyrics') and not track.has_lrc:
            result.lyric = True
            if not self.dry_run:
                try:
                    with open(track.lrc_path, 'w', encoding='utf-8') as handle:
                        handle.write(extra['lyrics'])
                except OSError:
                    result.lyric = False

        return result


def missing_tag_fields(track):
    """标签完整性检查（实现已收敛到 core.tags，此处保留别名）"""
    return core_tags.missing_tag_fields(track)
