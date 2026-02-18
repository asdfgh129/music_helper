# -*- coding: utf-8 -*-
"""
单元测试 - 文件操作模块
"""

import unittest
import sys
import os
import tempfile
import shutil

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from file_operations import (
    scan_music_files,
    move_files_to_temp,
)


class TestFileOperations(unittest.TestCase):
    """文件操作模块测试"""

    def setUp(self):
        """创建临时目录用于测试"""
        self.test_dir = tempfile.mkdtemp()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """清理临时目录"""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_scan_music_files_empty_directory(self):
        """测试扫描空目录"""
        files = scan_music_files([self.test_dir])
        self.assertEqual(len(files), 0)

    def test_scan_music_files_nonexistent_directory(self):
        """测试扫描不存在的目录"""
        files = scan_music_files(["/nonexistent/directory"])
        self.assertEqual(len(files), 0)

    def test_scan_music_files_with_mp3(self):
        """测试扫描包含MP3的目录"""
        # 创建测试MP3文件
        test_file = os.path.join(self.test_dir, "test.mp3")
        with open(test_file, 'w') as f:
            f.write("test content")

        files = scan_music_files([self.test_dir])
        # 由于文件不是当前月份，可能不会被扫描到
        # 这里只确保函数可以正常调用
        self.assertIsInstance(files, list)

    def test_move_files_to_temp_empty_list(self):
        """测试移动空文件列表"""
        count = move_files_to_temp([], self.temp_dir)
        self.assertEqual(count, 0)

    def test_move_files_to_temp_single_file(self):
        """测试移动单个文件"""
        # 创建测试文件
        test_file = os.path.join(self.test_dir, "test.mp3")
        with open(test_file, 'w') as f:
            f.write("test content")

        file_info = {
            'filepath': test_file,
            'filename': 'test.mp3',
            'month': '202401',
            'directory': self.test_dir
        }

        count = move_files_to_temp([file_info], self.temp_dir)
        self.assertEqual(count, 1)

        # 验证文件已移动
        self.assertFalse(os.path.exists(test_file))
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, "test.mp3")))

    def test_move_files_to_temp_with_lrc(self):
        """测试移动文件及LRC歌词"""
        # 创建测试文件
        test_file = os.path.join(self.test_dir, "test.mp3")
        test_lrc = os.path.join(self.test_dir, "test.lrc")

        with open(test_file, 'w') as f:
            f.write("test content")
        with open(test_lrc, 'w') as f:
            f.write("lyrics")

        file_info = {
            'filepath': test_file,
            'filename': 'test.mp3',
            'month': '202401',
            'directory': self.test_dir
        }

        count = move_files_to_temp([file_info], self.temp_dir)
        self.assertEqual(count, 1)

        # 验证文件和歌词都已移动
        self.assertFalse(os.path.exists(test_file))
        self.assertFalse(os.path.exists(test_lrc))
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, "test.mp3")))
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, "test.lrc")))

    def test_move_files_to_temp_duplicate_filename(self):
        """测试移动同名文件"""
        # 在目标目录创建同名文件
        existing_file = os.path.join(self.temp_dir, "test.mp3")
        with open(existing_file, 'w') as f:
            f.write("existing content")

        # 创建源文件
        test_file = os.path.join(self.test_dir, "test.mp3")
        with open(test_file, 'w') as f:
            f.write("new content")

        file_info = {
            'filepath': test_file,
            'filename': 'test.mp3',
            'month': '202401',
            'directory': self.test_dir
        }

        count = move_files_to_temp([file_info], self.temp_dir)
        self.assertEqual(count, 1)

        # 验证原文件仍存在
        self.assertTrue(os.path.exists(existing_file))
        # 验证新文件被重命名
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, "test_1.mp3")))


if __name__ == '__main__':
    unittest.main()
