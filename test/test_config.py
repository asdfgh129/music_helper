# -*- coding: utf-8 -*-
"""
单元测试 - 配置模块
"""

import unittest
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    MAIN_DIR, TEMP_MOVE_DIR, TEMP_COMPLETED_DIR,
    NETEASE_DIR, NETEASE_VIP_DIR, QQ_DIR, QQ_VIP_DIR,
    AUDIO_EXTENSIONS, MUSIC_EXTENSIONS,
    SOUNDALIKE_EXE, UM_EXE,
    mutagen_available,
)


class TestConfig(unittest.TestCase):
    """配置模块测试"""

    def test_directories_defined(self):
        """测试所有目录路径已定义"""
        self.assertIsNotNone(MAIN_DIR)
        self.assertIsNotNone(TEMP_MOVE_DIR)
        self.assertIsNotNone(TEMP_COMPLETED_DIR)
        self.assertIsNotNone(NETEASE_DIR)
        self.assertIsNotNone(NETEASE_VIP_DIR)
        self.assertIsNotNone(QQ_DIR)
        self.assertIsNotNone(QQ_VIP_DIR)

    def test_audio_extensions_defined(self):
        """测试音频扩展名已定义"""
        self.assertIn('.mp3', AUDIO_EXTENSIONS)
        self.assertIn('.flac', AUDIO_EXTENSIONS)
        self.assertIn('.wav', AUDIO_EXTENSIONS)
        self.assertIn('.ogg', AUDIO_EXTENSIONS)

    def test_music_extensions_is_superset(self):
        """测试MUSIC_EXTENSIONS是AUDIO_EXTENSIONS的超集"""
        for ext in AUDIO_EXTENSIONS:
            self.assertIn(ext, MUSIC_EXTENSIONS)

    def test_executables_defined(self):
        """测试可执行文件路径已定义"""
        self.assertIsNotNone(SOUNDALIKE_EXE)
        self.assertIsNotNone(UM_EXE)

    def test_mutagen_available_is_bool(self):
        """测试mutagen_available是布尔值"""
        self.assertIsInstance(mutagen_available, bool)


if __name__ == '__main__':
    unittest.main()
