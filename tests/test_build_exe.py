# -*- coding: utf-8 -*-
"""单元测试 - 免 Python 绿色版打包脚本（只测纯函数，不真正调用 PyInstaller）"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts import build_exe as build


class TestVersion(unittest.TestCase):
    def test_version_comes_from_config(self):
        import config

        self.assertEqual(build._version(), config.__version__)


class TestToolLists(unittest.TestCase):
    def test_every_listed_tool_exists(self):
        for name in build.TOOLS_COMMON + build.TOOLS_WINDOWS + build.TOOLS_MACOS:
            with self.subTest(tool=name):
                self.assertTrue((build.ROOT / 'tools' / name).is_file(), name)

    def test_windows_bundle_covers_decrypt_dedupe_and_hook(self):
        names = build.TOOLS_COMMON + build.TOOLS_WINDOWS
        for name in ('um.exe', 'soundalike.exe', 'fpcalc.exe', 'hook_qq_music.js',
                     'QQMusic_Setup_1951.exe', 'Q音屏蔽更新.zip'):
            self.assertIn(name, names)


class TestPyInstallerArgs(unittest.TestCase):
    def test_entry_and_dynamic_imports_are_collected(self):
        args = build.pyinstaller_args()
        self.assertIn(str(build.ROOT / 'main.py'), args)
        self.assertIn('--onedir', args)
        self.assertIn('--paths', args)
        self.assertIn('frida', args)
        self.assertIn('certifi', args)
        # 每次构建用全新目录，PyInstaller 才不会去删旧输出目录
        self.assertIn('runs', build.PYI_DIST.parts)
        self.assertIn(str(build.RUN_DIR / 'dist'), args)
        # 惰性 __getattr__ 与 uvicorn 的动态导入静态扫不到，必须显式声明
        for module in ('tagger.platforms.qqmusic', 'tagger.platforms.netease',
                       'uvicorn.protocols.http.auto', 'uvicorn.loops.auto'):
            self.assertIn(module, args)


class TestResetDist(unittest.TestCase):
    def test_rebuild_overwrites_files_but_keeps_user_data_and_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp) / 'dist'
            dist.mkdir()
            (dist / 'config.ini').write_text('[paths]\n', encoding='utf-8')
            (dist / 'log').mkdir()
            (dist / 'log' / 'Music-test.log').write_text('x', encoding='utf-8')
            (dist / 'notes.txt').write_text('keep', encoding='utf-8')
            (dist / build.EXE_NAME).write_bytes(b'old exe')
            (dist / '_internal').mkdir()
            (dist / '_internal' / 'old.dll').write_bytes(b'x')
            with mock.patch.object(build, 'DIST', dist):
                build.reset_dist()
            # 用户数据与非本脚本生成的文件都保留
            self.assertTrue((dist / 'config.ini').is_file())
            self.assertTrue((dist / 'log' / 'Music-test.log').is_file())
            self.assertTrue((dist / 'notes.txt').is_file())
            # 旧的顶层单文件清掉，目录留着由 copytree 覆盖写入
            self.assertFalse((dist / build.EXE_NAME).exists())
            self.assertTrue((dist / '_internal').is_dir())
            self.assertTrue((dist / '_internal' / 'old.dll').is_file())


class TestGeneratedDocs(unittest.TestCase):
    def test_doc_check_skips_packaging_outputs(self):
        from scripts import check_docs

        self.assertIn('dist', check_docs.SKIP_DIRS)
        self.assertIn('build', check_docs.SKIP_DIRS)

    def test_third_party_readme_is_pruned_but_data_is_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp) / 'dist'
            internal = dist / '_internal' / 'opencc'
            internal.mkdir(parents=True)
            (internal / 'README.md').write_text('x', encoding='utf-8')
            (internal / 'dictionary.txt').write_text('x', encoding='utf-8')
            with mock.patch.object(build, 'DIST', dist):
                build.prune_third_party_docs()
            self.assertFalse((internal / 'README.md').exists())
            self.assertTrue((internal / 'dictionary.txt').is_file())


class TestHelpers(unittest.TestCase):
    def test_human_readable_size(self):
        self.assertEqual(build.human(512), '512 B')
        self.assertTrue(build.human(2048).endswith('KB'))

    def test_dir_size_of_tools(self):
        self.assertGreater(build.dir_size(build.ROOT / 'tools'), 1024 * 1024)
