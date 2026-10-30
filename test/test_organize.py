# -*- coding: utf-8 -*-
"""core.organize 的单元测试：年代目录、归档路径、计划生成"""

import os
import unittest

import core.ops as ops
from core.model import Track
from core import organize


def make(path, **tags):
    return Track(path=path, tags=tags)


class TestDecadeLabel(unittest.TestCase):

    def test_boundaries(self):
        self.assertEqual(organize.decade_label(1950), '1950-1979')
        self.assertEqual(organize.decade_label(1979), '1950-1979')
        self.assertEqual(organize.decade_label(1980), '1980-1989')
        self.assertEqual(organize.decade_label(1985), '1980-1989')
        self.assertEqual(organize.decade_label(2000), '2000-2009')
        self.assertEqual(organize.decade_label(2026), '2020-2029')


class TestMissingFields(unittest.TestCase):

    def test_reports_missing_in_fixed_order(self):
        self.assertEqual(organize.missing_fields(make('a.flac')), ['歌曲名', '歌手', '年份'])

    def test_partial(self):
        self.assertEqual(organize.missing_fields(make('a.flac', title='T', artist='A')), ['年份'])

    def test_complete(self):
        self.assertEqual(organize.missing_fields(
            make('a.flac', title='T', artist='A', year='1999')), [])


class TestTargetPath(unittest.TestCase):

    def test_builds_decade_and_year(self):
        track = make('x.flac', title='T', artist='A', year='1985')
        path = organize.target_path(track, 'D:/lib')
        self.assertEqual(path, os.path.join('D:/lib', '1980-1989', '1985', 'x.flac'))

    def test_returns_none_without_year(self):
        self.assertIsNone(organize.target_path(make('x.flac', title='T', artist='A'), 'D:/lib'))

    def test_returns_none_on_bad_year(self):
        track = make('x.flac', title='T', artist='A', year='18xx')
        self.assertIsNone(organize.target_path(track, 'D:/lib'))

    def test_unknown_path(self):
        self.assertEqual(organize.unknown_path(make('x.flac'), 'D:/lib'),
                         os.path.join('D:/lib', 'unknown', 'x.flac'))


class TestPlanOrganize(unittest.TestCase):

    def test_splits_organized_and_unknown(self):
        good = make('D:/temp/a.flac', title='T', artist='A', year='2001')
        bad = make('D:/temp/b.flac', title='T')
        plan = ops.Plan('t')
        organized, unknown = organize.plan_organize([good, bad], 'D:/lib', plan)

        self.assertEqual([t.path for t in organized], ['D:/temp/a.flac'])
        self.assertEqual([t.path for t in unknown], ['D:/temp/b.flac'])
        self.assertEqual(len(plan), 2)

    def test_unknown_can_skip_moving(self):
        bad = make('D:/temp/b.flac')
        plan = ops.Plan('t')
        organize.plan_organize([bad], 'D:/lib', plan, sort_unknown=False)
        self.assertEqual(len(plan), 0)

    def test_reason_mentions_year(self):
        good = make('D:/temp/a.flac', title='T', artist='A', year='2001')
        plan = ops.Plan('t')
        organize.plan_organize([good], 'D:/lib', plan)
        self.assertIn('2001', plan.operations[0].reason)


if __name__ == '__main__':
    unittest.main()
