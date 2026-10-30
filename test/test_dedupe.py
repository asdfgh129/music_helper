# -*- coding: utf-8 -*-
"""单元测试 - 重复判定与年份归档"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.dedupe import (
    DuplicateGroup,
    find_by_filename,
    find_by_tag,
    find_duplicates,
    pick_keep,
    strip_suffix,
)
from core.model import Track
from core.ops import Plan
from core.organize import decade_label, missing_fields, plan_organize, target_path


def track(path, duration=200.0, size=1000, **tags):
    return Track(path=path, tags=dict(tags), duration=duration, size=size)


class TestDedupe(unittest.TestCase):
    def test_strip_suffix(self):
        self.assertEqual(strip_suffix('晴天 (1)'), '晴天')
        self.assertEqual(strip_suffix('晴天（2）'), '晴天')
        self.assertEqual(strip_suffix('晴天'), '晴天')

    def test_same_tag_and_duration_is_duplicate(self):
        a = track('a.flac', 200, 5000, title='晴天', artist='周杰伦')
        b = track('b.flac', 201, 4000, title='晴天', artist='周杰伦')
        groups = find_by_tag([a, b])
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].keep, a)          # 同格式优先更大文件
        self.assertEqual(len(groups[0].drop), 1)

    def test_duration_out_of_tolerance_not_duplicate(self):
        a = track('a.flac', 200, 5000, title='晴天', artist='周杰伦')
        b = track('b.flac', 260, 5000, title='晴天', artist='周杰伦')
        self.assertEqual(find_by_tag([a, b]), [])

    def test_different_artist_not_duplicate(self):
        a = track('a.flac', 200, 5000, title='晴天', artist='周杰伦')
        b = track('b.flac', 200, 5000, title='晴天', artist='罗大佑')
        self.assertEqual(find_by_tag([a, b]), [])

    def test_pick_keep_prefers_lossless(self):
        mp3 = track('a.mp3', 200, 9000, title='x', artist='y')
        flac = track('b.flac', 200, 5000, title='x', artist='y')
        self.assertEqual(pick_keep([mp3, flac]), flac)

    def test_filename_suffix_group(self):
        a = track('晴天.flac', 200, 5000)
        b = track('晴天 (1).flac', 200, 5000)
        groups = find_by_filename([a, b])
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].kind, '文件名')

    def test_find_duplicates_merges_strategies(self):
        a = track('晴天.flac', 200, 5000, title='晴天', artist='周杰伦')
        b = track('晴天 (1).flac', 200, 5000, title='晴天', artist='周杰伦')
        groups = find_duplicates([a, b])
        self.assertEqual(len(groups), 1)             # 不应重复计两次
        self.assertEqual(len(groups[0].drop), 1)

    def test_duration_unknown_flagged(self):
        a = track('a.flac', 0, 5000, title='晴天', artist='周杰伦')
        b = track('b.flac', 0, 5000, title='晴天', artist='周杰伦')
        groups = find_by_tag([a, b])
        self.assertTrue(groups[0].duration_unknown)


class TestOrganize(unittest.TestCase):
    def test_decade_label(self):
        self.assertEqual(decade_label(1965), '1950-1979')
        self.assertEqual(decade_label(1979), '1950-1979')
        self.assertEqual(decade_label(1980), '1980-1989')
        self.assertEqual(decade_label(2024), '2020-2029')

    def test_target_path(self):
        item = track('x.flac', 200, 100, title='晴天', artist='周杰伦', year='2003')
        expected = os.path.join('base', '2000-2009', '2003', 'x.flac')
        self.assertEqual(target_path(item, 'base'), expected)

    def test_target_path_none_without_year(self):
        item = track('x.flac', 200, 100, title='晴天', artist='周杰伦')
        self.assertIsNone(target_path(item, 'base'))

    def test_missing_fields(self):
        item = track('x.flac', 0, 0, title='晴天')
        self.assertIn('歌手', missing_fields(item))
        self.assertIn('年份', missing_fields(item))

    def test_plan_organize(self):
        good = track('g.flac', 200, 100, title='晴天', artist='周杰伦', year='2003')
        bad = track('b.flac', 200, 100, title='未知')
        plan = Plan('test', dry_run=True)
        organized, unknown = plan_organize([good, bad], 'base', plan)
        self.assertEqual([t.path for t in organized], ['g.flac'])
        self.assertEqual([t.path for t in unknown], ['b.flac'])
        self.assertEqual(len(plan), 2)                # 一个归档 + 一个 unknown


if __name__ == '__main__':
    unittest.main()
