# -*- coding: utf-8 -*-
"""单元测试 - 配置模块"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from core.tags import MUTAGEN_AVAILABLE


class TestConfig(unittest.TestCase):
    def test_directories_defined(self):
        for name in ('MAIN_DIR', 'TEMP_MOVE_DIR', 'TEMP_COMPLETED_DIR',
                     'NETEASE_DIR', 'NETEASE_VIP_DIR', 'QQ_DIR', 'QQ_VIP_DIR'):
            self.assertTrue(getattr(config, name), name)

    def test_audio_extensions_defined(self):
        for ext in ('.mp3', '.flac', '.wav', '.ogg'):
            self.assertIn(ext, config.AUDIO_EXTENSIONS)

    def test_music_extensions_is_superset(self):
        self.assertTrue(config.AUDIO_EXTENSIONS <= config.MUSIC_EXTENSIONS)

    def test_executables_defined(self):
        self.assertTrue(config.SOUNDALIKE_EXE.endswith('.exe'))
        self.assertTrue(config.UM_EXE.endswith('.exe'))

    def test_mutagen_available_is_bool(self):
        self.assertIsInstance(MUTAGEN_AVAILABLE, bool)

    def test_version_is_static(self):
        """版本号不应随运行时间变化"""
        self.assertNotIn('b1', config.__version__)
        self.assertEqual(config.__version__, config.VERSION)

    def test_vip_dir_under_base(self):
        self.assertTrue(config.NETEASE_VIP_DIR.startswith(config.NETEASE_DIR))
        self.assertTrue(config.QQ_VIP_DIR.startswith(config.QQ_DIR))

    def test_validate_returns_list(self):
        self.assertIsInstance(config.validate(), list)


if __name__ == '__main__':
    unittest.main()
