# -*- coding: utf-8 -*-
"""core.scan 的单元测试：遍历规则、月份过滤、扩展名过滤"""

import os
import shutil
import tempfile
import unittest

import core.scan as scanner


class TestScan(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='mh_scan_')
        self.addCleanup(shutil.rmtree, self.root, True)

    def _touch(self, *parts, content='x'):
        path = os.path.join(self.root, *parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(content)
        return path

    def test_finds_only_audio(self):
        self._touch('a.flac')
        self._touch('b.mp3')
        self._touch('note.txt')
        found = scanner.scan([self.root], with_tags=False)
        self.assertEqual(sorted(os.path.basename(t.path) for t in found), ['a.flac', 'b.mp3'])

    def test_recursive_by_default(self):
        self._touch('sub', 'deep', 'c.ogg')
        self.assertEqual(len(scanner.scan([self.root], with_tags=False)), 1)

    def test_non_recursive(self):
        self._touch('a.flac')
        self._touch('sub', 'c.ogg')
        found = scanner.scan([self.root], with_tags=False, recursive=False)
        self.assertEqual([os.path.basename(t.path) for t in found], ['a.flac'])

    def test_skip_dirs(self):
        self._touch('_trash', 'old.flac')
        self._touch('unknown', 'u.flac')
        self._touch('.hidden', 'h.flac')
        self.assertEqual(scanner.scan([self.root], with_tags=False), [])

    def test_month_filter(self):
        path = self._touch('a.flac')
        actual = scanner.month_of(path)
        self.assertEqual(len(scanner.scan([self.root], month=actual, with_tags=False)), 1)
        wrong = '190001' if actual != '190001' else '190002'
        self.assertEqual(scanner.scan([self.root], month=wrong, with_tags=False), [])

    def test_custom_extensions(self):
        self._touch('song.ncm')
        self._touch('a.flac')
        found = scanner.scan([self.root], with_tags=False, extensions={'.ncm'})
        self.assertEqual([os.path.basename(t.path) for t in found], ['song.ncm'])

    def test_duplicate_paths_deduped(self):
        self._touch('a.flac')
        found = scanner.scan([self.root, self.root], with_tags=False)
        self.assertEqual(len(found), 1)

    def test_missing_directory_is_silent(self):
        self.assertEqual(scanner.scan([os.path.join(self.root, 'nope')], with_tags=False), [])

    def test_sorted_by_path(self):
        self._touch('b.flac')
        self._touch('a.flac')
        paths = [t.path for t in scanner.scan([self.root], with_tags=False)]
        self.assertEqual(paths, sorted(paths))

    def test_track_fields_filled(self):
        self._touch('a.flac', content='12345')
        track = scanner.scan([self.root], with_tags=False)[0]
        self.assertEqual(track.size, 5)
        self.assertGreater(track.mtime, 0)
        self.assertEqual(track.ext, '.flac')


if __name__ == '__main__':
    unittest.main()
