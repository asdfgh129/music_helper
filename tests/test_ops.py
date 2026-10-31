# -*- coding: utf-8 -*-
"""单元测试 - 操作计划（移动/改名/回收站/日志/拷贝）"""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.ops import Plan, copy_items


class TestPlan(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='mh_plan_')
        self.src_dir = os.path.join(self.root, 'src')
        self.dst_dir = os.path.join(self.root, 'dst')
        self.trash_dir = os.path.join(self.root, 'trash')
        self.journal = os.path.join(self.root, 'journal.jsonl')
        os.makedirs(self.src_dir)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _file(self, name, content='x'):
        path = os.path.join(self.src_dir, name)
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(content)
        return path

    def _plan(self, dry_run=False):
        return Plan('test', dry_run=dry_run, journal_path=self.journal, trash_dir=self.trash_dir)

    def test_dry_run_touches_nothing(self):
        path = self._file('a.flac')
        plan = self._plan(dry_run=True)
        plan.add_move(path, os.path.join(self.dst_dir, 'a.flac'))
        result = plan.execute()
        self.assertTrue(os.path.exists(path))
        self.assertEqual(len(result.skipped), 1)
        self.assertFalse(os.path.exists(self.dst_dir))

    def test_move_creates_dirs_and_journals(self):
        path = self._file('a.flac')
        dst = os.path.join(self.dst_dir, '2019', 'a.flac')
        plan = self._plan()
        plan.add_move(path, dst)
        result = plan.execute()

        self.assertEqual(len(result.done), 1)
        self.assertTrue(os.path.exists(dst))
        self.assertFalse(os.path.exists(path))

        with open(self.journal, encoding='utf-8') as handle:
            records = [json.loads(line) for line in handle if line.strip()]
        self.assertEqual(records[-1]['action'], 'move')
        self.assertTrue(records[-1]['ok'])

    def test_move_companion_lrc(self):
        path = self._file('a.flac')
        self._file('a.lrc')
        dst = os.path.join(self.dst_dir, 'a.flac')
        plan = self._plan()
        plan.add_move(path, dst)
        plan.execute()
        self.assertTrue(os.path.exists(os.path.join(self.dst_dir, 'a.lrc')))

    def test_rename(self):
        path = self._file('A-B.flac')
        plan = self._plan()
        plan.add_rename(path, 'A - B.flac')
        plan.execute()
        self.assertTrue(os.path.exists(os.path.join(self.src_dir, 'A - B.flac')))
        self.assertFalse(os.path.exists(path))

    def test_name_collision_gets_suffix(self):
        os.makedirs(self.dst_dir, exist_ok=True)
        with open(os.path.join(self.dst_dir, 'a.flac'), 'w', encoding='utf-8') as handle:
            handle.write('old')
        new = self._file('b.flac', 'new')
        dst = os.path.join(self.dst_dir, 'a.flac')
        plan = self._plan()
        plan.add_move(new, dst)
        plan.execute()
        self.assertTrue(os.path.exists(os.path.join(self.dst_dir, 'a_1.flac')))

    def test_trash_instead_of_delete(self):
        path = self._file('bad.flac')
        plan = self._plan()
        plan.add_trash(path, '重复')
        plan.execute()
        self.assertFalse(os.path.exists(path))
        self.assertTrue(os.path.exists(os.path.join(self.trash_dir, 'bad.flac')))

    def test_trash_without_dir_raises_into_failed(self):
        path = self._file('bad.flac')
        plan = Plan('test', journal_path=self.journal)
        plan.add_trash(path, '重复')
        result = plan.execute()
        self.assertEqual(len(result.failed), 1)
        self.assertTrue(os.path.exists(path))       # 失败时原文件仍在

    def test_missing_source_skipped(self):
        plan = self._plan()
        plan.add_move(os.path.join(self.src_dir, 'ghost.flac'), os.path.join(self.dst_dir, 'g.flac'))
        result = plan.execute()
        self.assertEqual(len(result.skipped), 1)

    def test_same_path_not_added(self):
        path = self._file('a.flac')
        plan = self._plan()
        plan.add_move(path, path)
        self.assertTrue(plan.is_empty)

    def test_copy_items(self):
        path = self._file('a.flac')
        self._file('a.lrc')
        copied = copy_items([(path, os.path.join(self.dst_dir, 'a.flac'))])
        self.assertEqual(copied, 1)
        self.assertTrue(os.path.exists(os.path.join(self.dst_dir, 'a.flac')))
        self.assertTrue(os.path.exists(os.path.join(self.dst_dir, 'a.lrc')))
        self.assertTrue(os.path.exists(path))       # 拷贝不动源文件


if __name__ == '__main__':
    unittest.main()
