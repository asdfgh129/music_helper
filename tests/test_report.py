# -*- coding: utf-8 -*-
"""单元测试 - 报告与检查逻辑"""

import csv
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import check as checker
from core.model import Track
from core.ops import Plan
from core.report import Report


def track(path, duration=200.0, size=1000, **tags):
    return Track(path=path, tags=dict(tags), duration=duration, size=size)


class TestReport(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='mh_report_')

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_render_contains_summary_and_table(self):
        report = Report('测试报告')
        report.add_summary('文件数', 3)
        report.add('明细', ['文件', '说明'], [('a.flac', '缺少封面')])
        text = report.render()
        self.assertIn('# 测试报告', text)
        self.assertIn('文件数：3', text)
        self.assertIn('| a.flac | 缺少封面 |', text)

    def test_export_section_only_pointer(self):
        report = Report('测试')
        report.add_review('清单', [('类型', 'p', 'd')])
        text = report.render()
        self.assertIn('明细见同目录下的 review-*.csv', text)
        self.assertNotIn('| 类型 | p | d |', text)

    def test_save_writes_md_and_csv(self):
        report = Report('测试')
        report.add_review('清单', [('重复文件', 'C:/a.flac', '重复于 b.flac')])
        paths = report.save(self.dir)
        self.assertTrue(os.path.exists(paths['md']))
        self.assertTrue(os.path.exists(paths['csv']))
        with open(paths['csv'], encoding='utf-8-sig', newline='') as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(rows[0], ['类型', '路径', '说明'])
        self.assertEqual(rows[1][0], '重复文件')

    def test_long_table_is_truncated_in_markdown(self):
        """大库上不能生成上万行的 Markdown 表格，正文只留前 N 条"""
        result = checker.CheckResult()
        for index in range(checker.MAX_TABLE_ROWS + 5):
            result.add(checker.KIND_NO_LRC, f'C:/lib/Artist - Song{index}.flac', '没有同名 .lrc')
        report = Report('大库')
        checker.report_into(result, report)
        text = report.render()

        self.assertEqual(text.count('没有同名 .lrc'), checker.MAX_TABLE_ROWS)
        self.assertIn(f'共 {checker.MAX_TABLE_ROWS + 5} 条', text)
        self.assertIn('review-*.csv', text)

        rows = [row for section in report.sections if section.export for row in section.rows]
        self.assertEqual(len(rows), checker.MAX_TABLE_ROWS + 5)   # CSV 仍是全量

    def test_duplicate_section_lists_full_path(self):
        """重复明细要带路径，跨年代目录同名时文件名不足以定位"""
        tracks = [
            track('C:/lib/2000-2009/2000/Artist - Song.flac', 200, 9000,
                  title='Song', artist='Artist'),
            track('C:/lib/tmp/Artist - Song.mp3', 200, 1000,
                  title='Song', artist='Artist'),
        ]
        result = checker.check_library(tracks, [], check_lyrics=False)
        report = Report('重复')
        checker.report_into(result, report)
        markdown = report.render()
        self.assertIn('C:/lib/tmp/Artist - Song.mp3', markdown)


class TestCheck(unittest.TestCase):
    def test_filename_format_finding(self):
        tracks = [track('C:/lib/A-B.flac', title='B', artist='A', album='x', year='2000')]
        result = checker.check_library(tracks, [], check_lyrics=False, check_duplicates=False)
        self.assertEqual(len(result.by_kind(checker.KIND_FILENAME)), 1)
        self.assertTrue(result.by_kind(checker.KIND_FILENAME)[0].fixable)

    def test_tag_missing_finding(self):
        tracks = [track('C:/lib/A - B.flac', title='B', artist='A')]
        result = checker.check_library(tracks, [], check_lyrics=False, check_duplicates=False)
        details = ' '.join(item.detail for item in result.by_kind(checker.KIND_TAGS))
        self.assertIn('专辑', details)
        self.assertIn('年份', details)
        self.assertIn('封面', details)

    def test_mismatch_finding(self):
        tracks = [track('C:/lib/周杰伦 - 晴天.flac', title='晴天', artist='罗大佑',
                        album='x', year='2003')]
        result = checker.check_library(tracks, [], check_lyrics=False, check_duplicates=False)
        self.assertEqual(len(result.by_kind(checker.KIND_MISMATCH)), 1)

    def test_duplicate_finding_and_plan(self):
        tracks = [
            track('C:/lib/晴天.flac', 200, 9000, title='晴天', artist='周杰伦'),
            track('C:/lib/晴天 (1).flac', 200, 5000, title='晴天', artist='周杰伦'),
        ]
        result = checker.check_library(tracks, [], check_lyrics=False)
        self.assertEqual(len(result.by_kind(checker.KIND_DUP)), 1)

        plan = Plan('fix', dry_run=True)
        checker.plan_fixes(result, plan, review_dir='C:/review', move_bad=True)
        actions = [op.action for op in plan]
        self.assertIn('move', actions)
        self.assertTrue(any('重复于' in op.reason for op in plan))

    def test_plan_fixes_renames_canonical(self):
        tracks = [track('C:/lib/A-B.flac', title='B', artist='A', album='x', year='2000')]
        result = checker.check_library(tracks, [], check_lyrics=False, check_duplicates=False)
        plan = Plan('fix', dry_run=True)
        checker.plan_fixes(result, plan, review_dir=None, rename_canonical=True)
        renames = [op for op in plan if op.action == 'rename']
        self.assertEqual(len(renames), 1)
        self.assertTrue(renames[0].dst.endswith('A - B.flac'))

    def test_no_action_without_fix_flag(self):
        tracks = [track('C:/lib/A-B.flac', title='B', artist='A', album='x', year='2000')]
        result = checker.check_library(tracks, [], check_lyrics=False, check_duplicates=False)
        plan = Plan('fix', dry_run=True)
        checker.plan_fixes(result, plan, review_dir=None, rename_canonical=False)
        self.assertTrue(plan.is_empty)

    def test_filename_without_artist_finding_is_fixable_by_tags(self):
        tracks = [track('C:/lib/晴天.flac', title='晴天', artist='周杰伦',
                        album='叶惠美', year='2003')]
        result = checker.check_library(tracks, [], check_lyrics=False, check_duplicates=False)
        finding = result.by_kind(checker.KIND_FILENAME)[0]
        self.assertTrue(finding.fixable)
        self.assertIn('周杰伦 - 晴天.flac', finding.detail)

    def test_plan_fixes_renames_by_tags_only_when_allowed(self):
        tracks = [track('C:/lib/晴天.flac', title='晴天', artist='周杰伦',
                        album='叶惠美', year='2003')]
        result = checker.check_library(tracks, [], check_lyrics=False, check_duplicates=False)

        conservative = Plan('fix', dry_run=True)
        checker.plan_fixes(result, conservative, review_dir=None, rename_by_tags=False)
        self.assertTrue(conservative.is_empty)

        aggressive = Plan('fix', dry_run=True)
        checker.plan_fixes(result, aggressive, review_dir=None, rename_by_tags=True)
        renames = [op for op in aggressive if op.action == 'rename']
        self.assertEqual(len(renames), 1)
        self.assertTrue(renames[0].dst.endswith('周杰伦 - 晴天.flac'))

    def test_duration_unknown_group_is_not_moved(self):
        """时长读不出来多半是损坏文件，只报告，不自动搬走"""
        tracks = [
            track('C:/lib/A - B.flac', 0, 9000, title='B', artist='A', album='x', year='2000'),
            track('C:/lib/A - B (1).flac', 0, 5000, title='B', artist='A', album='x', year='2000'),
        ]
        result = checker.check_library(tracks, [], check_lyrics=False)
        self.assertEqual(len(result.by_kind(checker.KIND_DUP)), 1)
        self.assertIn('时长未知', result.by_kind(checker.KIND_DUP)[0].detail)

        plan = Plan('fix', dry_run=True)
        checker.plan_fixes(result, plan, review_dir='C:/review', move_bad=True,
                           delete_duplicates=True)
        actions = [op.action for op in plan]
        self.assertNotIn('trash', actions)
        self.assertNotIn('move', actions)


if __name__ == '__main__':
    unittest.main()
