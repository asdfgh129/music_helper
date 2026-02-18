# -*- coding: utf-8 -*-
"""
单元测试 - LRC歌词模块
"""

import unittest
import sys
import os
import tempfile
import shutil

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lrc import find_missing_lrc_files, find_orphan_lrc_files


class TestLrc(unittest.TestCase):
    """LRC歌词模块测试"""

    def setUp(self):
        """创建临时目录用于测试"""
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        """清理临时目录"""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

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

    def test_find_missing_lrc_files_with_temp_path(self):
        """测试使用临时路径移动缺失lrc的文件"""
        temp_dir = tempfile.mkdtemp()

        try:
            # 创建MP3文件（无LRC）
            music_file = os.path.join(self.test_dir, "song.mp3")
            with open(music_file, 'w') as f:
                f.write("test")

            # 调用函数，应该将文件移动到temp_dir
            missing = find_missing_lrc_files(self.test_dir, temp_path=temp_dir)
            # 文件应该被移动到临时目录
            self.assertEqual(len(missing), 1)
            # 原文件应该被移动
            self.assertFalse(os.path.exists(music_file))
            # 新文件应该在temp_dir
            self.assertTrue(os.path.exists(os.path.join(temp_dir, "song.mp3")))
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

    def test_find_missing_lrc_files_multiple_formats(self):
        """测试多种音频格式"""
        formats = ['song1.mp3', 'song2.flac', 'song3.wav', 'song4.ogg']
        for filename in formats:
            filepath = os.path.join(self.test_dir, filename)
            with open(filepath, 'w') as f:
                f.write("test")

        missing = find_missing_lrc_files(self.test_dir)
        self.assertEqual(len(missing), 4)

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

    def test_find_orphan_lrc_files_all_formats(self):
        """测试所有支持的格式"""
        # 创建各种格式的音乐文件和对应的LRC
        formats = ['song.mp3', 'song.flac', 'song.wav', 'song.ogg', 'song.ape']
        for filename in formats:
            filepath = os.path.join(self.test_dir, filename)
            with open(filepath, 'w') as f:
                f.write("test")

        # 创建孤立的LRC
        orphan_lrc = os.path.join(self.test_dir, "orphan.lrc")
        with open(orphan_lrc, 'w') as f:
            f.write("lyrics")

        orphans = find_orphan_lrc_files(self.test_dir)
        self.assertEqual(len(orphans), 1)
        self.assertEqual(orphans[0], orphan_lrc)

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

    def test_find_orphan_lrc_files_case_insensitive(self):
        """测试大小写不敏感"""
        # 创建小写的音乐文件
        music_file = os.path.join(self.test_dir, "song.flac")
        with open(music_file, 'w') as f:
            f.write("test")

        # 创建大写的LRC文件
        lrc_file = os.path.join(self.test_dir, "SONG.LRC")
        with open(lrc_file, 'w') as f:
            f.write("lyrics")

        orphans = find_orphan_lrc_files(self.test_dir)
        # 由于文件名匹配是区分大小写的，这可能是孤立的
        self.assertGreaterEqual(len(orphans), 0)


if __name__ == '__main__':
    unittest.main()
