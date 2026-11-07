# -*- coding: utf-8 -*-
"""单元测试 - 入库判定规则（INCOMPLETE_DIR 的唯一判定来源）"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.check import _consistency_problem, _filename_from_tags, consistency_report, readiness_problems
from core.model import Track


def make_track(filename='Artist - Title.flac', has_cover=True, **tags):
    base = {'title': 'Title', 'artist': 'Artist', 'album': 'Album', 'year': '2000'}
    base.update(tags)
    return Track(path=os.path.join('C:/lib', filename), tags=base, has_cover=has_cover)


class TestReadiness(unittest.TestCase):
    def _track(self, filename='Artist - Title.flac', **tags):
        return make_track(filename, **tags)

    def test_complete_track_is_ready(self):
        self.assertEqual(readiness_problems(self._track()), [])

    def test_missing_year_is_unready(self):
        problems = readiness_problems(self._track(year=''))
        self.assertIn('缺少年份', problems)

    def test_missing_album_is_unready(self):
        problems = readiness_problems(self._track(album=''))
        self.assertIn('缺少专辑', problems)

    def test_mismatched_artist_is_unready(self):
        problems = readiness_problems(self._track(artist='Someone Else'))
        self.assertTrue(any('歌手' in problem for problem in problems))

    def test_mismatched_title_is_unready(self):
        problems = readiness_problems(self._track(filename='Artist - Other.flac'))
        self.assertTrue(any('歌名' in problem for problem in problems))

    def test_missing_cover_is_unready(self):
        """缺内嵌封面与缺核心标签一样，不能入库"""
        problems = readiness_problems(self._track(has_cover=False))
        self.assertIn('缺少封面', problems)

    def test_cover_present_is_ready(self):
        self.assertEqual(readiness_problems(self._track(has_cover=True)), [])

    def test_unparseable_year_is_unready(self):
        """年份非空但读不出四位数字时，归档会落进 unknown/，必须提前挡住"""
        for year in ('0', '3013', '未知', '999'):
            problems = readiness_problems(self._track(year=year))
            self.assertTrue(any('年份' in problem for problem in problems), year)

    def test_valid_year_variants_are_ready(self):
        for year in ('2004', '2004-05-01', ' 1999 '):
            self.assertEqual(readiness_problems(self._track(year=year)), [], year)


class TestArtistConsistency(unittest.TestCase):
    """歌手维度是「宽松」判定：宁可漏判，也不能把正常文件判成矛盾"""

    def assertConsistent(self, filename, artist):
        track = make_track(filename, artist=artist, title='晴天')
        self.assertIsNone(_consistency_problem(track), f'{filename} vs {artist}')

    def assertConflict(self, filename, artist):
        track = make_track(filename, artist=artist, title='晴天')
        self.assertIsNotNone(_consistency_problem(track), f'{filename} vs {artist}')

    def test_alias_in_brackets(self):
        self.assertConsistent('周杰伦 - 晴天.flac', '周杰伦 (Jay Chou)')

    def test_feat_artist(self):
        self.assertConsistent('周杰伦 - 晴天.flac', '周杰伦 feat. 杨瑞代')

    def test_multi_artist_intersection(self):
        self.assertConsistent('周杰伦 - 晴天.flac', '周杰伦 & 方文山')

    def test_partial_name_is_substring(self):
        self.assertConsistent('Jay - 晴天.flac', 'Jay Chou')

    def test_placeholder_artists_are_ignored(self):
        for artist in ('Various Artists', '群星', '未知艺人'):
            self.assertConsistent('周杰伦 - 晴天.flac', artist)

    def test_real_conflict_still_detected(self):
        self.assertConflict('周杰伦 - 晴天.flac', '罗大佑')
        self.assertConflict('周杰伦 - 晴天.flac', 'Taylor Swift')


class TestFilenameFromTags(unittest.TestCase):
    def test_suggests_name_when_tags_are_trustworthy(self):
        track = make_track('晴天.flac', title='晴天', artist='周杰伦')
        self.assertEqual(_filename_from_tags(track), '周杰伦 - 晴天.flac')

    def test_refuses_when_tags_conflict(self):
        track = make_track('晴天.flac', title='晴天', artist='周杰伦')
        track.tags['artist'] = '罗大佑'
        track.tags['title'] = '童年'
        self.assertIsNone(_filename_from_tags(track))

    def test_returns_none_when_name_already_matches(self):
        track = make_track('周杰伦 - 晴天.flac', title='晴天', artist='周杰伦')
        self.assertIsNone(_filename_from_tags(track))


class TestConsistencyReport(unittest.TestCase):
    """第 7 步自检展示用的结构化比对结果"""

    def test_items_cover_artist_and_title(self):
        report = consistency_report(make_track())
        self.assertEqual([item['field'] for item in report['items']], ['artist', 'title'])
        self.assertTrue(report['ok'])
        self.assertIsNone(report['problem'])
        self.assertEqual(report['file'], {'artist': 'Artist', 'title': 'Title'})
        self.assertEqual(report['tag'], {'artist': 'Artist', 'title': 'Title'})

    def test_problem_text_matches_legacy_helper(self):
        """新接口与旧私有函数的结论必须逐字一致，否则报告和自检会互相打脸"""
        cases = [
            make_track('Artist - Title.flac'),
            make_track('Artist - Other.flac'),
            make_track('某人 - Title.flac'),
            make_track('无结构.flac'),
            make_track('Various - Title.flac', artist='Various Artists'),
        ]
        for track in cases:
            self.assertEqual(consistency_report(track)['problem'],
                             _consistency_problem(track), track.filename)

    def test_mismatch_states(self):
        report = consistency_report(make_track('Artist - Other.flac'))
        states = {item['field']: item['state'] for item in report['items']}
        self.assertEqual(states['artist'], 'ok')
        self.assertEqual(states['title'], 'mismatch')
        self.assertIn('歌名', report['problem'])

    def test_skipped_when_filename_has_no_artist(self):
        """文件名没有「歌手 - 歌名」结构时，歌手维度不可比，不是错误"""
        report = consistency_report(make_track('晴天.flac', artist='周杰伦', title='晴天'))
        artist_item = report['items'][0]
        self.assertEqual(artist_item['state'], 'skipped')
        self.assertIn('结构', artist_item['reason'])
        self.assertTrue(report['ok'])

    def test_skipped_when_tag_missing(self):
        report = consistency_report(make_track('周杰伦 - 晴天.flac', artist='', title=''))
        self.assertTrue(report['ok'])
        self.assertEqual([item['state'] for item in report['items']],
                         ['skipped', 'skipped'])

    def test_placeholder_artist_is_not_a_conflict(self):
        """合辑里文件写具体歌手、标签写 Various Artists，不算矛盾"""
        report = consistency_report(
            make_track('周杰伦 - 晴天.flac', artist='Various Artists', title='晴天'))
        self.assertTrue(report['ok'])
        self.assertEqual(report['items'][0]['state'], 'skipped')


if __name__ == '__main__':
    unittest.main()
