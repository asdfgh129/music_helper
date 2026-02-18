# -*- coding: utf-8 -*-
"""
单元测试 - 归档模块
"""

import unittest
import sys
import os
import tempfile
import shutil

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from archive import (
    split_artist,
    find_missing_lrc_files,
    find_orphan_lrc_files,
)


class TestArchive(unittest.TestCase):
    """归档模块测试"""

    def setUp(self):
        """创建临时目录用于测试"""
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        """清理临时目录"""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_split_artist_semicolon(self):
        """测试分号分隔的艺术家"""
        artists = split_artist("周杰伦;林俊杰")
        self.assertIn("周杰伦", artists)
        self.assertIn("林俊杰", artists)

    def test_split_artist_comma(self):
        """测试逗号分隔的艺术家"""
        artists = split_artist("Artist1, Artist2, Artist3")
        self.assertEqual(len(artists), 3)
        self.assertIn("artist1", artists)
        self.assertIn("artist2", artists)
        self.assertIn("artist3", artists)

    def test_split_artist_multiple_separators(self):
        """测试多种分隔符"""
        artists = split_artist("Artist1; Artist2, Artist3 & Artist4")
        self.assertEqual(len(artists), 4)

    def test_split_artist_whitespace(self):
        """测试空格处理"""
        artists = split_artist("  Artist1  ;  Artist2  ")
        self.assertIn("artist1", artists)
        self.assertIn("artist2", artists)
        self.assertNotIn("  Artist1  ", artists)

    def test_find_missing_lrc_files_none(self):
        """测试没有缺失lrc的文件"""
        # 创建MP3文件和对应的LRC文件
        music_file = os.path.join(self.test_dir, "song.mp3")
        lrc_file = os.path.join(self.test_dir, "song.lrc")

        with open(music_file, 'w') as f:
            f.write("test")
        with open(lrc_file, 'w') as f:
            f.write("lyrics")

        missing = find_missing_lrc_files(self.test_dir)
        self.assertEqual(len(missing), 0)

    def test_find_missing_lrc_files_with_missing(self):
        """测试有缺失lrc的文件"""
        # 只创建MP3文件
        music_file = os.path.join(self.test_dir, "song.mp3")
        with open(music_file, 'w') as f:
            f.write("test")

        missing = find_missing_lrc_files(self.test_dir)
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0][0], "song.mp3")

    def test_find_missing_lrc_files_multiple_files(self):
        """测试多个文件"""
        # 创建3个MP3文件，只有1个有LRC
        files = ["song1.mp3", "song2.mp3", "song3.mp3"]
        for filename in files:
            filepath = os.path.join(self.test_dir, filename)
            with open(filepath, 'w') as f:
                f.write("test")

        # 为song2创建LRC
        with open(os.path.join(self.test_dir, "song2.lrc"), 'w') as f:
            f.write("lyrics")

        missing = find_missing_lrc_files(self.test_dir)
        self.assertEqual(len(missing), 2)

    def test_find_orphan_lrc_files_none(self):
        """测试没有孤立的lrc文件"""
        # 创建MP3文件和对应的LRC文件
        music_file = os.path.join(self.test_dir, "song.mp3")
        lrc_file = os.path.join(self.test_dir, "song.lrc")

        with open(music_file, 'w') as f:
            f.write("test")
        with open(lrc_file, 'w') as f:
            f.write("lyrics")

        orphans = find_orphan_lrc_files(self.test_dir)
        self.assertEqual(len(orphans), 0)

    def test_find_orphan_lrc_files_with_orphan(self):
        """测试有孤立的lrc文件"""
        # 只创建LRC文件
        lrc_file = os.path.join(self.test_dir, "song.lrc")
        with open(lrc_file, 'w') as f:
            f.write("lyrics")

        orphans = find_orphan_lrc_files(self.test_dir)
        self.assertEqual(len(orphans), 1)
        self.assertEqual(orphans[0], lrc_file)

    def test_find_orphan_lrc_files_flac(self):
        """测试FLAC文件对应的LRC"""
        # 创建FLAC和LRC文件
        music_file = os.path.join(self.test_dir, "song.flac")
        lrc_file = os.path.join(self.test_dir, "song.lrc")

        with open(music_file, 'w') as f:
            f.write("test")
        with open(lrc_file, 'w') as f:
            f.write("lyrics")

        orphans = find_orphan_lrc_files(self.test_dir)
        self.assertEqual(len(orphans), 0)

    def test_find_orphan_lrc_files_ogg(self):
        """测试OGG文件对应的LRC"""
        # 创建OGG和LRC文件
        music_file = os.path.join(self.test_dir, "song.ogg")
        lrc_file = os.path.join(self.test_dir, "song.lrc")

        with open(music_file, 'w') as f:
            f.write("test")
        with open(lrc_file, 'w') as f:
            f.write("lyrics")

        orphans = find_orphan_lrc_files(self.test_dir)
        self.assertEqual(len(orphans), 0)

    def test_find_orphan_lrc_files_subdirectory(self):
        """测试子目录中的文件"""
        # 创建子目录
        subdir = os.path.join(self.test_dir, "subdir")
        os.makedirs(subdir)

        # 在子目录中创建孤立的LRC
        lrc_file = os.path.join(subdir, "song.lrc")
        with open(lrc_file, 'w') as f:
            f.write("lyrics")

        orphans = find_orphan_lrc_files(self.test_dir)
        self.assertEqual(len(orphans), 1)
        self.assertEqual(orphans[0], lrc_file)


if __name__ == '__main__':
    unittest.main()
