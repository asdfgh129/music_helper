# -*- coding: utf-8 -*-
"""core.lyrics 的单元测试：缺失歌词与孤立歌词"""

import os
import shutil
import tempfile
import unittest

from core import lyrics
from core.model import Track


class TestLyrics(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='mh_lrc_')
        self.addCleanup(shutil.rmtree, self.root, True)

    def _touch(self, *parts):
        path = os.path.join(self.root, *parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write('x')
        return path

    def test_missing_lrc(self):
        with_lrc = self._touch('a.flac')
        self._touch('a.lrc')
        without = self._touch('b.mp3')

        missing = lyrics.missing_lrc([Track(path=with_lrc), Track(path=without)])
        self.assertEqual([t.path for t in missing], [without])

    def test_orphan_lrc(self):
        self._touch('a.flac')
        self._touch('a.lrc')
        orphan = self._touch('b.lrc')

        self.assertEqual(lyrics.orphan_lrc([self.root]), [orphan])

    def test_orphan_accepts_string(self):
        orphan = self._touch('b.lrc')
        self.assertEqual(lyrics.orphan_lrc(self.root), [orphan])

    def test_all_extensions_count_as_audio(self):
        for ext in ('.flac', '.mp3', '.wav', '.ape', '.ogg'):
            self._touch(f'song{ext}')
            self._touch(f'song{ext}'.replace(ext, '.lrc'))
        self.assertEqual(lyrics.orphan_lrc([self.root]), [])

    def test_nested_directories(self):
        self._touch('sub', 'x.lrc')
        self.assertEqual(len(lyrics.orphan_lrc([self.root])), 1)

    def test_ignores_non_lrc(self):
        self._touch('readme.txt')
        self.assertEqual(lyrics.orphan_lrc([self.root]), [])

    def test_uppercase_lrc_recognized(self):
        """大写扩展名 .LRC 也应被识别，并与小写音频配对不算孤立"""
        self._touch('a.flac')
        self._touch('a.LRC')
        self.assertEqual(lyrics.orphan_lrc([self.root]), [])

    def test_case_insensitive_matching(self):
        """音频文件名大小写不同仍视为配对（优化后用集合判重，需保持语义）"""
        self._touch('Song.FLAC')
        self._touch('song.lrc')
        self.assertEqual(lyrics.orphan_lrc([self.root]), [])

    def test_orphan_with_different_extension_audio(self):
        """同名音频是另一种格式时，.lrc 不算孤立"""
        self._touch('a.mp3')
        self._touch('a.lrc')
        self.assertEqual(lyrics.orphan_lrc([self.root]), [])


if __name__ == '__main__':
    unittest.main()
