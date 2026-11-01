# -*- coding: utf-8 -*-
"""单元测试 - 配置模块"""

import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from core.tags import MUTAGEN_AVAILABLE


class TestConfig(unittest.TestCase):
    def test_directories_defined(self):
        for name in ('LIBRARY_DIR', 'WORKSPACE_DIR', 'INCOMPLETE_DIR', 'DUPLICATE_DIR',
                     'NETEASE_STAGING_DIR', 'QQ_STAGING_DIR',
                     'NETEASE_DIR', 'NETEASE_VIP_DIR', 'QQ_DIR', 'QQ_VIP_DIR', 'DB_PATH'):
            self.assertTrue(getattr(config, name), name)

    def test_audio_extensions_defined(self):
        for ext in ('.mp3', '.flac', '.wav', '.ogg'):
            self.assertIn(ext, config.AUDIO_EXTENSIONS)

    def test_music_extensions_is_superset(self):
        self.assertTrue(config.AUDIO_EXTENSIONS <= config.MUSIC_EXTENSIONS)

    def test_executables_defined(self):
        """外部程序按平台取名：Windows 是 .exe，macOS 是按架构命名的二进制"""
        if os.name == 'nt':
            self.assertTrue(config.SOUNDALIKE_EXE.endswith('.exe'), config.SOUNDALIKE_EXE)
            self.assertTrue(config.UM_EXE.endswith('.exe'), config.UM_EXE)
        elif sys.platform == 'darwin':
            self.assertIn('soundalike-darwin-', config.SOUNDALIKE_EXE)
            self.assertIn('um-darwin-', config.UM_EXE)

    def test_default_um_picks_arch_on_macos(self):
        """um 是纯 Go 程序，macOS 上按架构挑 tools/um-darwin-<arch>"""
        with patch.object(config.sys, 'platform', 'darwin'), \
                patch.object(config.platform, 'machine', return_value='arm64'):
            self.assertTrue(config._default_um().endswith('um-darwin-arm64'))
        with patch.object(config.sys, 'platform', 'darwin'), \
                patch.object(config.platform, 'machine', return_value='x86_64'):
            self.assertTrue(config._default_um().endswith('um-darwin-amd64'))

    def test_fpcalc_defined(self):
        """fpcalc 路径来自 config，缺文件时调用方回退到 PATH"""
        self.assertTrue(config.FPCALC_EXE)
        self.assertEqual(config.FPCALC_EXE,
                         os.path.normpath(os.path.join(config.TOOLS_DIR,
                                                       'fpcalc.exe' if os.name == 'nt' else 'fpcalc')))

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


class TestConfigIni(unittest.TestCase):
    """config.ini 与环境变量的优先级"""

    ENV_KEYS = ('MUSIC_HELPER_CONFIG', 'MUSIC_HELPER_LIBRARY_DIR', 'MUSIC_HELPER_WORKSPACE_DIR',
                'MUSIC_HELPER_INCOMPLETE_DIR', 'MUSIC_HELPER_DUPLICATE_DIR', 'MUSIC_HELPER_DB')

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='mh_config_')
        self.ini = os.path.join(self.root, 'config.ini')
        with open(self.ini, 'w', encoding='utf-8') as handle:
            handle.write(
                '[paths]\n'
                f'library_dir = {os.path.join(self.root, "library")}\n'
                f'workspace_dir = {os.path.join(self.root, "workspace")}\n'
                f'incomplete_dir = {os.path.join(self.root, "incomplete")}\n'
                f'duplicate_dir = {os.path.join(self.root, "duplicate")}\n'
                'db_path = local.db\n'
            )
        self._saved = {key: os.environ.get(key) for key in self.ENV_KEYS}
        for key in self.ENV_KEYS[1:]:
            os.environ.pop(key, None)
        os.environ['MUSIC_HELPER_CONFIG'] = self.ini
        config.reload()

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        config.reload()
        shutil.rmtree(self.root, ignore_errors=True)

    def test_ini_used_when_env_absent(self):
        self.assertEqual(config.LIBRARY_DIR, os.path.normpath(os.path.join(self.root, 'library')))
        self.assertEqual(config.WORKSPACE_DIR, os.path.normpath(os.path.join(self.root, 'workspace')))
        self.assertEqual(config.INCOMPLETE_DIR, os.path.normpath(os.path.join(self.root, 'incomplete')))
        self.assertEqual(config.DUPLICATE_DIR, os.path.normpath(os.path.join(self.root, 'duplicate')))

    def test_relative_path_resolved_against_project(self):
        self.assertEqual(config.DB_PATH, os.path.join(config.PROJECT_DIR, 'local.db'))

    def test_env_overrides_ini(self):
        env_library = os.path.join(self.root, 'from-env')
        os.environ['MUSIC_HELPER_LIBRARY_DIR'] = env_library
        config.reload()
        self.assertEqual(config.LIBRARY_DIR, os.path.normpath(env_library))


if __name__ == '__main__':
    unittest.main()
