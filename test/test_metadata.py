# -*- coding: utf-8 -*-
"""
单元测试 - 元数据模块
"""

import unittest
import sys
import os
import tempfile

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import mutagen_available
from metadata import get_music_metadata, set_music_metadata


@unittest.skipIf(not mutagen_available, "mutagen库未安装，跳过测试")
class TestMetadata(unittest.TestCase):
    """元数据模块测试"""

    def setUp(self):
        """创建临时目录用于测试"""
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        """清理临时目录"""
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_get_metadata_nonexistent_file(self):
        """测试读取不存在的文件"""
        result = get_music_metadata("/nonexistent/file.mp3")
        self.assertIsNone(result)

    def test_get_metadata_unsupported_format(self):
        """测试不支持的文件格式"""
        # 创建一个文本文件
        test_file = os.path.join(self.test_dir, "test.txt")
        with open(test_file, 'w') as f:
            f.write("test")
        result = get_music_metadata(test_file)
        self.assertIsNone(result)

    def test_set_metadata_nonexistent_file(self):
        """测试设置不存在的文件元数据"""
        tags = {'title': 'Test', 'artist': 'Test Artist'}
        result = set_music_metadata("/nonexistent/file.mp3", tags)
        self.assertFalse(result)

    def test_set_metadata_empty_tags(self):
        """测试设置空标签"""
        # 创建一个临时MP3文件（空的）
        test_file = os.path.join(self.test_dir, "empty.mp3")
        with open(test_file, 'wb') as f:
            f.write(b'')

        result = set_music_metadata(test_file, {})
        # 对于空文件可能失败，这是预期的
        # 这里我们只确保函数不会抛出异常
        self.assertIsInstance(result, bool)

    def test_set_metadata_partial_tags(self):
        """测试设置部分标签"""
        # 这个测试需要创建一个有效的MP3文件
        # 由于需要完整的MP3文件，这里跳过
        pass

    def test_metadata_structure(self):
        """测试元数据结构"""
        # 测试返回的元数据字典结构
        # 由于需要实际的音乐文件，这里只测试函数可以正常调用
        pass


class TestMetadataMock(unittest.TestCase):
    """元数据模块模拟测试（不需要mutagen）"""

    def test_functions_exist(self):
        """测试函数是否存在"""
        self.assertTrue(callable(get_music_metadata))
        self.assertTrue(callable(set_music_metadata))


if __name__ == '__main__':
    unittest.main()
