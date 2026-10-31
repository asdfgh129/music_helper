# -*- coding: utf-8 -*-
"""单元测试 - 入库判定规则（INCOMPLETE_DIR 的唯一判定来源）"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.check import readiness_problems
from core.model import Track


class TestReadiness(unittest.TestCase):
    def _track(self, filename='Artist - Title.flac', **tags):
        base = {'title': 'Title', 'artist': 'Artist', 'album': 'Album', 'year': '2000'}
        base.update(tags)
        return Track(path=os.path.join('C:/lib', filename), tags=base)

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

    def test_cover_is_not_required(self):
        """封面缺失只提示，不应挡在 INCOMPLETE_DIR 之外"""
        self.assertEqual(readiness_problems(self._track()), [])


if __name__ == '__main__':
    unittest.main()
