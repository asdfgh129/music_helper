# -*- coding: utf-8 -*-
"""单元测试 - WORKSPACE_DIR 只移出未达入库标准的文件"""

import os
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import main
from core.model import Track


class TestSplitIncomplete(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='mh_split_')
        self.workspace_dir = os.path.join(self.root, 'workspace')
        self.incomplete_dir = os.path.join(self.root, 'incomplete')
        os.makedirs(self.workspace_dir)

        self.complete = os.path.join(self.workspace_dir, 'Artist - Title.flac')
        self.incomplete = os.path.join(self.workspace_dir, 'Other - Song.flac')
        for path in (self.complete, self.incomplete):
            with open(path, 'wb') as handle:
                handle.write(b'audio')

        self.tracks = [
            Track(path=self.complete, tags={'title': 'Title', 'artist': 'Artist',
                                            'album': 'Album', 'year': '2000'}),
            Track(path=self.incomplete, tags={'title': 'Song', 'artist': 'Other'}),
        ]
        self.args = SimpleNamespace(dry_run=False, limit=0)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _run(self, dry_run=False):
        self.args.dry_run = dry_run
        with patch.object(main.scanner, 'scan', return_value=self.tracks), \
                patch.object(config, 'WORKSPACE_DIR', self.workspace_dir), \
                patch.object(config, 'INCOMPLETE_DIR', self.incomplete_dir), \
                patch.object(config, 'JOURNAL_PATH', os.path.join(self.root, 'journal.jsonl')), \
                patch.object(config, 'TRASH_DIR', os.path.join(self.root, 'trash')):
            return main._split_incomplete(self.args)

    def test_complete_stays_in_workspace_incomplete_moves_out(self):
        kept, moved = self._run()

        self.assertEqual((kept, moved), (1, 1))
        self.assertTrue(os.path.exists(self.complete))
        self.assertFalse(os.path.exists(os.path.join(self.workspace_dir, 'Other - Song.flac')))
        self.assertTrue(os.path.exists(os.path.join(self.incomplete_dir, 'Other - Song.flac')))

    def test_dry_run_reports_without_moving(self):
        kept, moved = self._run(dry_run=True)

        self.assertEqual((kept, moved), (1, 1))
        self.assertTrue(os.path.exists(self.complete))
        self.assertTrue(os.path.exists(self.incomplete))
        self.assertFalse(os.path.exists(self.incomplete_dir))


class TestCheckEntry(unittest.TestCase):
    """检查入口必须拒绝不存在的目录，否则「零问题」会被误读成「库很健康」"""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='mh_check_')
        self.missing = os.path.join(self.root, 'no-such-library')
        self.args = SimpleNamespace(dry_run=True, fix=False, no_move=False,
                                    trash_dup=False, report_dir=None, limit=0)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_flow_check_returns_none_when_library_missing(self):
        with patch.object(config, 'LIBRARY_DIR', self.missing):
            self.assertIsNone(main.flow_check(self.args))

    def test_require_dir_rejects_missing(self):
        self.assertFalse(main._require_dir(self.missing, '音乐库'))
        self.assertTrue(main._require_dir(self.root, '音乐库'))

    def test_only_check_file_name_returns_error_code(self):
        with patch.object(config, 'LIBRARY_DIR', self.missing):
            self.assertEqual(main.main(['--only-check-file-name', 'master']), 1)


class TestManualArchive(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='mh_archive_')
        self.workspace_dir = os.path.join(self.root, 'workspace')
        self.library_dir = os.path.join(self.root, 'library')
        self.incomplete_dir = os.path.join(self.root, 'incomplete')
        os.makedirs(self.workspace_dir)

        self.complete = os.path.join(self.workspace_dir, 'Artist - Title.flac')
        self.incomplete = os.path.join(self.workspace_dir, 'Other - Song.flac')
        for path in (self.complete, self.incomplete):
            with open(path, 'wb') as handle:
                handle.write(b'audio')

        self.tracks = [
            Track(path=self.complete, tags={'title': 'Title', 'artist': 'Artist',
                                            'album': 'Album', 'year': '2000'}),
            Track(path=self.incomplete, tags={'title': 'Song', 'artist': 'Other'}),
        ]
        self.args = SimpleNamespace(dry_run=False, limit=0)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _scan(self, paths, **kwargs):
        return self.tracks if os.path.abspath(list(paths)[0]) == os.path.abspath(self.workspace_dir) else []

    def test_complete_goes_to_library_incomplete_goes_to_incomplete(self):
        with patch.object(main.scanner, 'scan', side_effect=self._scan), \
                patch.object(main, '_update_tags', return_value=(2, 0)), \
                patch.object(main, '_save'), \
                patch.object(config, 'WORKSPACE_DIR', self.workspace_dir), \
                patch.object(config, 'LIBRARY_DIR', self.library_dir), \
                patch.object(config, 'INCOMPLETE_DIR', self.incomplete_dir), \
                patch.object(config, 'JOURNAL_PATH', os.path.join(self.root, 'journal.jsonl')), \
                patch.object(config, 'TRASH_DIR', os.path.join(self.root, 'trash')):
            main.flow_manual_archive(self.args)

        self.assertTrue(os.path.exists(
            os.path.join(self.library_dir, '2000-2009', '2000', 'Artist - Title.flac')))
        self.assertFalse(os.path.exists(self.complete))
        self.assertTrue(os.path.exists(os.path.join(self.incomplete_dir, 'Other - Song.flac')))


if __name__ == '__main__':
    unittest.main()
