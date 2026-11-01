# -*- coding: utf-8 -*-
"""tagger 包的单元测试

覆盖标签解析、平台结果筛选与择优。全部用假客户端，不联网。
"""

import base64
import os
import shutil
import tempfile
import unittest
from unittest import mock

import tagger
from core.model import Track


class FakeQQ:
    """假的 QQ 音乐客户端"""

    def __init__(self, songs, lyric=None):
        self.songs = songs
        self.lyric = lyric

    def getQQMusicSearch(self, query, page=1, size=5):
        return {'data': self.songs}

    def getQQMusicMediaLyric(self, mid):
        return self.lyric or {}


class FakeNetease:
    """假的网易云客户端"""

    def __init__(self, songs, lyric=None):
        self.songs = songs
        self.lyric = lyric
        self.lyric_calls = 0
        self.fetch_id3_calls = 0

    def fetch_id3_by_title(self, title):
        self.fetch_id3_calls += 1
        return self.songs

    def fetch_lyric(self, song_id):
        self.lyric_calls += 1
        return self.lyric


class FakeFingerprint:
    """假的声纹匹配器（也可模拟异常）"""

    def __init__(self, recordings=None, raise_error=False):
        self.recordings = recordings or []
        self.calls = 0
        self.raise_error = raise_error

    def match_file(self, path):
        self.calls += 1
        if self.raise_error:
            raise RuntimeError('boom')
        recs = self.recordings

        class _Match:
            success = True
            recordings = recs

        return _Match()


class TestParseMusicBrainz(unittest.TestCase):
    """MusicBrainz recording -> 标签字典"""

    def test_full_recording(self):
        recording = {
            'title': '晴天',
            'artist-credit': [{'artist': {'name': '周杰伦'}}],
            'releases': [{'title': '叶惠美', 'date': '2003-07-31', 'id': 'abc-123'}],
            'genre': 'Pop',
        }
        tags = tagger.parse_musicbrainz_recording(recording)
        self.assertEqual(tags['title'], '晴天')
        self.assertEqual(tags['artist'], '周杰伦')
        self.assertEqual(tags['album'], '叶惠美')
        self.assertEqual(tags['year'], '2003')
        self.assertEqual(tags['genre'], 'Pop')
        self.assertIn('abc-123', tags['album_img'])

    def test_multiple_artists_joined(self):
        recording = {
            'title': 'Song',
            'artist-credit': [{'artist': {'name': 'A'}}, {'artist': {'name': 'B'}}],
        }
        self.assertEqual(tagger.parse_musicbrainz_recording(recording)['artist'], 'A; B')

    def test_empty_recording(self):
        self.assertEqual(tagger.parse_musicbrainz_recording({}), {})

    def test_bad_date_ignored(self):
        recording = {'title': 'X', 'releases': [{'date': 'unknown'}]}
        self.assertNotIn('year', tagger.parse_musicbrainz_recording(recording))


class TestArtistMatches(unittest.TestCase):
    """艺人匹配"""

    def test_empty_query_always_true(self):
        self.assertTrue(tagger._artist_matches('', '任何人'))

    def test_exact_and_partial(self):
        self.assertTrue(tagger._artist_matches('周杰伦', '周杰伦'))
        self.assertTrue(tagger._artist_matches('Jay', 'Jay Chou'))
        self.assertFalse(tagger._artist_matches('周杰伦', '林俊杰'))

    def test_multi_artist_query(self):
        self.assertTrue(tagger._artist_matches('林俊杰;周杰伦', '周杰伦'))


class TestFetchQQ(unittest.TestCase):
    """QQ 音乐结果筛选"""

    def test_matching_song_with_lyric(self):
        lyric = base64.b64encode('[00:01]歌词'.encode('utf-8')).decode()
        api = FakeQQ([{'name': '晴天', 'singer': [{'name': '周杰伦'}],
                       'album': {'title': '叶惠美'}, 'mid': 'mid1'}],
                     lyric={'lyric': lyric})
        tags = tagger.fetch_qq_tags(api, '晴天', '周杰伦')
        self.assertIsNotNone(tags)
        self.assertEqual(tags['artist'], '周杰伦')
        self.assertEqual(tags['album'], '叶惠美')
        self.assertIn('mid1', tags['album_img'])
        self.assertIn('歌词', tags['lyrics'])

    def test_lyric_with_translation(self):
        data = {'lyric': base64.b64encode('原文'.encode()).decode(),
                'trans': base64.b64encode('译文'.encode()).decode()}
        tags = tagger.fetch_qq_tags(FakeQQ([{'name': 'S', 'mid': 'm'}], lyric=data), 'S', '')
        self.assertIn('[翻译]', tags['lyrics'])

    def test_title_mismatch_returns_none(self):
        api = FakeQQ([{'name': '七里香', 'singer': [{'name': '周杰伦'}]}])
        self.assertIsNone(tagger.fetch_qq_tags(api, '晴天', '周杰伦'))

    def test_artist_mismatch_returns_none(self):
        api = FakeQQ([{'name': '晴天', 'singer': [{'name': '林俊杰'}]}])
        self.assertIsNone(tagger.fetch_qq_tags(api, '晴天', '周杰伦'))


class TestFetchNetease(unittest.TestCase):
    """网易云结果筛选"""

    def test_matching_song(self):
        api = FakeNetease([{'name': '晴天', 'artist': '周杰伦', 'album': '叶惠美',
                            'year': '2003', 'album_img': 'http://x/c.jpg', 'id': 1}],
                          lyric='[00:01]歌词')
        tags = tagger.fetch_netease_tags(api, '晴天', '周杰伦')
        self.assertEqual(tags['year'], '2003')
        self.assertEqual(tags['lyrics'], '[00:01]歌词')
        self.assertEqual(api.lyric_calls, 1)

    def test_no_match_returns_none(self):
        api = FakeNetease([{'name': '别的歌', 'artist': '别人'}])
        self.assertIsNone(tagger.fetch_netease_tags(api, '晴天', '周杰伦'))


class TestFetchBest(unittest.TestCase):
    """双平台择优"""

    def test_picks_higher_score(self):
        qq = FakeQQ([{'name': '晴天', 'singer': [{'name': '周杰伦'}], 'mid': 'm'}])
        netease = FakeNetease([{'name': '晴天', 'artist': '周杰伦', 'album': '叶惠美',
                                'year': '2003', 'id': 2}])
        best = tagger.fetch_best_tags(qq, netease, '晴天', '周杰伦')
        self.assertEqual(best['source'], '网易云音乐')
        self.assertGreater(best['score'], 0)

    def test_missing_platform_ignored(self):
        netease = FakeNetease([])
        best = tagger.fetch_best_tags(None, netease, '晴天', '周杰伦')
        self.assertIsNone(best)

    def test_both_fail_returns_none(self):
        self.assertIsNone(tagger.fetch_best_tags(FakeQQ([]), FakeNetease([]), 'X', 'Y'))

    def test_broken_platform_does_not_break_other(self):
        class Broken:
            def getQQMusicSearch(self, *a, **k):
                raise RuntimeError('boom')

        netease = FakeNetease([{'name': '晴天', 'artist': '周杰伦'}])
        best = tagger.fetch_best_tags(Broken(), netease, '晴天', '周杰伦')
        self.assertEqual(best['source'], '网易云音乐')


class TestMissingTagFields(unittest.TestCase):
    """标签完整性（别名仍可用）"""

    def test_empty_track_lists_all(self):
        track = Track(path='C:/not/exists/x.flac')
        missing = tagger.missing_tag_fields(track)
        for label in ('歌曲名', '歌手', '专辑', '年份', '封面'):
            self.assertIn(label, missing)

    def test_complete_track_has_no_missing(self):
        track = Track(path='C:/not/exists/x.flac',
                      tags={'title': 't', 'artist': 'a', 'album': 'b', 'year': '2000'})
        self.assertEqual(tagger.missing_tag_fields(track), ['封面'])


FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', '1.flac')


def _copy_fixture():
    dst = os.path.join(tempfile.mkdtemp(prefix='mh_upd_'), 'song.flac')
    shutil.copy(FIXTURE, dst)
    return dst


class TestParseMusicBrainzGenre(unittest.TestCase):
    """MusicBrainz 的 genre 可能是字符串/列表/字典列表，必须统一成字符串"""

    def test_string_passthrough(self):
        self.assertEqual(
            tagger.parse_musicbrainz_recording({'title': 'x', 'genre': 'Pop'})['genre'], 'Pop')

    def test_list_of_strings(self):
        rec = {'title': 'x', 'genre': ['Pop', 'Rock']}
        self.assertEqual(tagger.parse_musicbrainz_recording(rec)['genre'], 'Pop, Rock')

    def test_list_of_dicts(self):
        rec = {'title': 'x', 'genre': [{'name': 'Pop'}, {'name': 'Rock'}]}
        self.assertEqual(tagger.parse_musicbrainz_recording(rec)['genre'], 'Pop, Rock')

    def test_no_genre_absent(self):
        self.assertNotIn('genre', tagger.parse_musicbrainz_recording({'title': 'x'}))


class TestFetchBestShortCircuit(unittest.TestCase):
    def test_short_circuits_on_perfect_score(self):
        """某个平台已满分就不应再问另一个平台"""
        qq = FakeQQ([{'name': '晴天', 'singer': [{'name': '周杰伦'}], 'mid': 'm'}])
        netease = FakeNetease([{'name': '晴天', 'artist': '周杰伦'}])
        with mock.patch.object(tagger, 'tag_score', return_value=100):
            best = tagger.fetch_best_tags(qq, netease, '晴天', '周杰伦')
        self.assertEqual(best['source'], 'QQ音乐')
        self.assertEqual(netease.fetch_id3_calls, 0)


class TestTaggerUpdate(unittest.TestCase):
    """Tagger.update 端到端：声纹 / 在线平台 / 封面 / 歌词 / 合并策略"""

    def _recording(self, score=100):
        return {
            'title': '晴天', 'score': score,
            'artist-credit': [{'artist': {'name': '周杰伦'}}],
            'releases': [{'title': '叶惠美', 'date': '2003-07-31', 'id': 'abc'}],
            'genre': 'Pop',
        }

    def _make_tagger(self, fingerprint=None, qq=None, netease=None,
                     with_fingerprint=True, dry_run=False):
        t = tagger.Tagger(dry_run=dry_run, with_fingerprint=with_fingerprint)
        t._fingerprint_ready = True
        t._fingerprint = fingerprint
        t._online_ready = True
        t._qq = qq
        t._netease = netease
        return t

    def test_fingerprint_fills_and_writes(self):
        track = Track(path=_copy_fixture())
        self.addCleanup(shutil.rmtree, os.path.dirname(track.path), True)
        t = self._make_tagger(fingerprint=FakeFingerprint([self._recording()]))
        res = t.update(track)

        self.assertTrue(res.updated)
        self.assertEqual(res.source, 'MusicBrainz(100)')
        self.assertIn('album', res.fields)
        got = tagger.core_tags.read_tags(track.path)
        self.assertEqual(got['album'], '叶惠美')
        self.assertEqual(got['year'], '2003')
        self.assertEqual(got['artist'], '周杰伦')
        self.assertEqual(got['genre'], 'Pop')

    def test_merge_preserves_existing_title(self):
        """已有非空字段不被声纹结果覆盖，只填空缺"""
        track = Track(path=_copy_fixture(), tags={'title': '我的歌', 'artist': '我'})
        self.addCleanup(shutil.rmtree, os.path.dirname(track.path), True)
        t = self._make_tagger(fingerprint=FakeFingerprint([self._recording()]))
        res = t.update(track)

        got = tagger.core_tags.read_tags(track.path)
        # 声纹想写 '晴天'，但文件已有歌名，所以磁盘上既不是 '晴天' 也不是内存里的
        # '我的歌'（track.tags 只是内存，未变化则不写盘），而是 fixture 原有歌名
        self.assertEqual(got['title'], '小城故事')   # 未被声纹覆盖
        self.assertEqual(got['album'], '叶惠美')      # 缺失专辑被补全
        self.assertNotIn('title', res.fields)
        self.assertIn('album', res.fields)

    def test_online_fills_lyrics_and_cover(self):
        lyric = base64.b64encode('歌词内容'.encode()).decode()
        qq = FakeQQ([{'name': '晴天', 'singer': [{'name': '周杰伦'}],
                      'album': {'title': '叶惠美'}, 'mid': 'm1'}],
                    lyric={'lyric': lyric})
        track = Track(path=_copy_fixture(), tags={'title': '晴天', 'artist': '周杰伦'})
        self.addCleanup(shutil.rmtree, os.path.dirname(track.path), True)
        t = self._make_tagger(with_fingerprint=False, qq=qq, netease=None)

        with mock.patch.object(tagger, 'download_cover',
                              return_value=b'\x89PNG\r\n\x1a\n' + b'\x00' * 20):
            res = t.update(track)

        self.assertIn('album', res.fields)
        self.assertTrue(res.lyric)
        self.assertTrue(res.cover)
        # 歌词文件确实落盘
        self.assertTrue(os.path.exists(track.lrc_path))
        with open(track.lrc_path, 'r', encoding='utf-8') as handle:
            self.assertEqual(handle.read(), '歌词内容')
        # 封面确实写入
        self.assertTrue(tagger.core_tags.has_cover(track.path))

    def test_dry_run_does_not_write(self):
        lyric = base64.b64encode('歌词内容'.encode()).decode()
        qq = FakeQQ([{'name': '晴天', 'singer': [{'name': '周杰伦'}],
                      'album': {'title': '叶惠美'}, 'mid': 'm1'}],
                    lyric={'lyric': lyric})
        track = Track(path=_copy_fixture(), tags={'title': '晴天', 'artist': '周杰伦'})
        self.addCleanup(shutil.rmtree, os.path.dirname(track.path), True)
        t = self._make_tagger(with_fingerprint=False, qq=qq, dry_run=True)

        with mock.patch.object(tagger, 'download_cover',
                              return_value=b'\x89PNG\r\n\x1a\n' + b'\x00' * 20):
            res = t.update(track)

        # 仍然标记「会改动」，但磁盘上一概不动
        self.assertTrue(res.updated)
        self.assertTrue(res.lyric)
        self.assertTrue(res.cover)
        self.assertFalse(os.path.exists(track.lrc_path))
        self.assertNotEqual(tagger.core_tags.read_tags(track.path).get('album'), '叶惠美')
        self.assertFalse(tagger.core_tags.has_cover(track.path))

    def test_skip_when_already_complete(self):
        """已完整（核心标签+封面+歌词齐）应直接跳过，不再查声纹/网络"""
        track = Track(path=_copy_fixture(),
                      tags={'title': 'T', 'artist': 'A', 'album': 'X',
                            'year': '2000', 'genre': 'Pop'},
                      has_cover=True)
        with open(track.lrc_path, 'w', encoding='utf-8') as handle:
            handle.write('x')
        self.addCleanup(shutil.rmtree, os.path.dirname(track.path), True)

        fp = FakeFingerprint([self._recording()])
        qq = FakeQQ([{'name': 'x', 'singer': [{'name': 'y'}]}])
        t = self._make_tagger(fingerprint=fp, qq=qq, netease=None)

        res = t.update(track)
        self.assertFalse(res.updated)
        self.assertEqual(fp.calls, 0)  # 声纹未触发
        # 没有任何标签被写入
        self.assertNotEqual(tagger.core_tags.read_tags(track.path).get('title'), '晴天')

    def test_fingerprint_error_is_isolated(self):
        """声纹抛异常不应中断，应降级到在线/空结果"""
        track = Track(path=_copy_fixture(), tags={'title': '晴天', 'artist': '周杰伦'})
        self.addCleanup(shutil.rmtree, os.path.dirname(track.path), True)
        t = self._make_tagger(fingerprint=FakeFingerprint(raise_error=True),
                              qq=None, netease=None)
        res = t.update(track)  # 不应抛异常
        self.assertFalse(res.updated)
        self.assertIn('声纹查询失败', res.error)


if __name__ == '__main__':
    unittest.main()
