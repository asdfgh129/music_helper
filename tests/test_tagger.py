# -*- coding: utf-8 -*-
"""tagger 包的单元测试

覆盖标签解析、平台结果筛选与择优。全部用假客户端，不联网。
"""

import base64
import unittest

from core.model import Track
import tagger


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

    def fetch_id3_by_title(self, title):
        return self.songs

    def fetch_lyric(self, song_id):
        self.lyric_calls += 1
        return self.lyric


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


if __name__ == '__main__':
    unittest.main()
