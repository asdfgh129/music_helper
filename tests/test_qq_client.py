# -*- coding: utf-8 -*-
"""单元测试 - QQ 音乐客户端环境准备（安装检测 / 启动 / 登录确认 / 打补丁）

这些测试一律不启动真实客户端：`find_client`、`is_running`、`start`、`probe_login`
全部替换成桩函数。
"""

import os
import sys
import tempfile
import unittest
import zipfile
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import decrypto.qq_client as qc


def _log():
    return SimpleNamespace(
        error=lambda *a, **k: None, warning=lambda *a, **k: None,
        info=lambda *a, **k: None, debug=lambda *a, **k: None,
    )


class TestFindClient(unittest.TestCase):
    def test_override_wins(self):
        """config.QQ_CLIENT_EXE 手工指定时优先于注册表探测"""
        with tempfile.TemporaryDirectory() as tmp:
            exe = os.path.join(tmp, 'QQMusic.exe')
            open(exe, 'wb').close()
            with patch.object(qc, '_config_value', return_value=exe):
                self.assertEqual(qc.find_windows(), exe)

    def test_registry_install_value(self):
        """注册表 Install 值指向的目录里有 QQMusic.exe 才算装了"""
        class FakeKey:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with tempfile.TemporaryDirectory() as tmp:
            exe = os.path.join(tmp, 'QQMusic.exe')
            open(exe, 'wb').close()
            fake_winreg = SimpleNamespace(
                HKEY_LOCAL_MACHINE=0, HKEY_CURRENT_USER=1,
                OpenKey=lambda *a: FakeKey(),
                QueryValueEx=lambda *a: (tmp, 1),
            )
            with patch.object(qc, '_config_value', return_value=''), \
                    patch.dict(sys.modules, {'winreg': fake_winreg}):
                self.assertEqual(qc.find_windows(), exe)

    def test_uninstalled_returns_none(self):
        with patch.object(qc, '_config_value', return_value=''), \
                patch.object(qc, '_WIN_GUESS', ()), \
                patch.dict(sys.modules, {'winreg': None}):
            self.assertIsNone(qc.find_windows())


class TestProcessDetection(unittest.TestCase):
    def test_tasklist_hit(self):
        out = '"QQMusic.exe","1234","Console","1","100,000 K"'
        with patch.object(qc.subprocess, 'run',
                          return_value=SimpleNamespace(stdout=out)):
            self.assertTrue(qc._process_alive('QQMusic.exe'))

    def test_tasklist_miss(self):
        out = '信息: 没有运行的任务匹配指定标准。'
        with patch.object(qc.subprocess, 'run',
                          return_value=SimpleNamespace(stdout=out)):
            self.assertFalse(qc._process_alive('QQMusic.exe'))


class TestProbeSample(unittest.TestCase):
    def test_skips_mgg_and_tiny_files(self):
        """只认够大的 .mflac：.mgg 在已登录时也可能 Open 失败，会误报"""
        with tempfile.TemporaryDirectory() as tmp:
            for name, size in (('a.mgg', 5_000_000), ('b.mflac', 10),
                               ('c.mflac', 2_000_000)):
                with open(os.path.join(tmp, name), 'wb') as handle:
                    handle.write(b'\0' * size)
            self.assertEqual(os.path.basename(qc.probe_sample([tmp])), 'c.mflac')

    def test_empty_dir_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(qc.probe_sample([tmp]))


class TestProbeLogin(unittest.TestCase):
    def test_not_running_returns_none(self):
        with patch.object(qc.sys, 'platform', 'win32'), \
                patch.object(qc.os, 'name', 'nt'), \
                patch.object(qc, 'probe_sample', return_value='/tmp/x.mflac'), \
                patch.object(qc, 'is_running', return_value=False):
            self.assertIsNone(qc.probe_login())

    def test_missing_frida_returns_none(self):
        with tempfile.NamedTemporaryFile(suffix='.mflac', delete=False) as handle:
            sample = handle.name
            handle.write(b'\0' * 10)
        try:
            with patch.object(qc.sys, 'platform', 'win32'), \
                    patch.object(qc.os, 'name', 'nt'), \
                    patch.object(qc, 'is_running', return_value=True), \
                    patch.dict(sys.modules, {'frida': None}):
                self.assertIsNone(qc.probe_login(sample))
        finally:
            os.unlink(sample)


class TestWaitLogin(unittest.TestCase):
    def test_timeout_returns_false(self):
        """一直探测未登录 -> 超时返回 False"""
        with patch.object(qc, 'probe_login', return_value=False):
            self.assertFalse(qc.wait_login(_log(), timeout=0, interval=0))

    def test_login_appears_later(self):
        """轮询中途变成已登录 -> True"""
        seen = {'n': 0}

        def fake_probe(sample=None, logger=None):
            seen['n'] += 1
            return seen['n'] > 2

        with patch.object(qc, 'probe_login', side_effect=fake_probe):
            self.assertTrue(qc.wait_login(_log(), timeout=30, interval=0))

    def test_undetectable_returns_none(self):
        with patch.object(qc, 'probe_login', return_value=None):
            self.assertIsNone(qc.wait_login(_log(), timeout=0))


class TestEnsureReady(unittest.TestCase):
    def _run(self, installed, running, login, expect, installs=0):
        state = {'n': 0}

        def fake_find():
            return 'C:/QQMusic.exe' if installed or state['n'] > installs else None

        def fake_install(_log):
            state['n'] += 1
            return True

        with patch.object(qc, 'find_client', side_effect=fake_find), \
                patch.object(qc, 'is_running', return_value=running), \
                patch.object(qc, 'start', return_value=True), \
                patch.object(qc, 'install_client', side_effect=fake_install), \
                patch.object(qc, 'probe_login', return_value=login), \
                patch.object(qc, 'supports_frida', return_value=True), \
                patch.object(qc, '_config_value',
                             side_effect=lambda k, d=None: 0 if k == 'QQ_LOGIN_TIMEOUT' else d):
            return qc.ensure_ready(_log())

    def test_ready_when_logged_in(self):
        self.assertTrue(self._run(True, True, True, True))

    def test_missing_client_is_installed(self):
        self.assertTrue(self._run(False, True, True, True))

    def test_not_logged_in_gives_up(self):
        self.assertFalse(self._run(True, True, False, False))

    def test_macos_skips_frida_path(self):
        """macOS 没有可注入的符号，走 um，不因登录态而阻断"""
        with patch.object(qc, 'find_client', return_value='/Applications/QQMusic.app'), \
                patch.object(qc, 'supports_frida', return_value=False), \
                patch.object(qc, 'is_running', return_value=False):
            self.assertTrue(qc.ensure_ready(_log()))


class TestApplyPatch(unittest.TestCase):
    def test_overwrites_updater(self):
        """补丁就是把假 QQMusicUp.exe 覆盖进安装目录"""
        with tempfile.TemporaryDirectory() as tmp:
            install = os.path.join(tmp, 'install')
            os.makedirs(install)
            exe = os.path.join(install, 'QQMusic.exe')
            open(exe, 'wb').close()
            archive = os.path.join(tmp, 'patch.zip')
            with zipfile.ZipFile(archive, 'w') as zf:
                zf.writestr('QQMusicUp.exe', b'MZ-fake-updater')

            with patch.object(qc, 'find_windows', return_value=exe), \
                    patch.object(qc, 'patch_path', return_value=archive):
                self.assertTrue(qc.apply_patch_windows(_log()))

            target = os.path.join(install, 'QQMusicUp.exe')
            with open(target, 'rb') as handle:
                self.assertEqual(handle.read(), b'MZ-fake-updater')

    def test_missing_patch_reports_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = os.path.join(tmp, 'QQMusic.exe')
            open(exe, 'wb').close()
            with patch.object(qc, 'find_windows', return_value=exe), \
                    patch.object(qc, 'patch_path', return_value=os.path.join(tmp, 'nope.zip')):
                self.assertFalse(qc.apply_patch_windows(_log()))


class TestInstallLayout(unittest.TestCase):
    def test_installer_and_patch_paths_exist(self):
        """仓库自带的安装包与补丁必须存在，否则「未安装时自动装」是空承诺"""
        self.assertTrue(os.path.exists(qc.installer_path()), qc.installer_path())
        self.assertTrue(os.path.exists(qc.patch_path()), qc.patch_path())

    def test_install_dir(self):
        self.assertEqual(qc.install_dir(r'C:\a\b\QQMusic.exe'), r'C:\a\b')
        self.assertEqual(qc.install_dir(''), '')


if __name__ == '__main__':
    unittest.main()
