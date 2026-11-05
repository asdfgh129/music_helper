# -*- coding: utf-8 -*-
"""services.settings_store 的单元测试：目录设置的校验与持久化

每个用例都把 `MUSIC_HELPER_CONFIG` 指向临时 ini，避免写坏仓库里的 config.ini。
"""

import os
import shutil
import tempfile
import unittest

import config
from services import settings_store


def base_values(workspace):
    return {
        'library_dir': os.path.join(workspace, 'library'),
        'workspace_dir': os.path.join(workspace, 'workspace'),
        'incomplete_dir': os.path.join(workspace, 'unready'),
        'duplicate_dir': os.path.join(workspace, 'dup'),
        'netease_dir': os.path.join(workspace, 'netease'),
        'netease_vip_dir': '',
        'qq_dir': os.path.join(workspace, 'qq'),
        'qq_vip_dir': '',
    }


class SettingsTestCase(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='mh_cfg_')
        self.addCleanup(shutil.rmtree, self.root, True)
        self.ini = os.path.join(self.root, 'config.ini')
        self._old_env = {key: os.environ.get(key) for key in (
            'MUSIC_HELPER_CONFIG', 'MUSIC_HELPER_LIBRARY_DIR', 'MUSIC_HELPER_WORKSPACE_DIR')}
        os.environ['MUSIC_HELPER_CONFIG'] = self.ini
        for key in ('MUSIC_HELPER_LIBRARY_DIR', 'MUSIC_HELPER_WORKSPACE_DIR'):
            os.environ.pop(key, None)
        config.reload()
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        for key, value in self._old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        config.reload()


class TestValidate(SettingsTestCase):

    def test_accepts_complete_absolute_paths(self):
        problems, values = settings_store.validate(base_values(self.root))
        self.assertEqual(problems, [])
        self.assertTrue(values['library_dir'].endswith('library'))

    def test_requires_library_and_workspace(self):
        values = base_values(self.root)
        values['library_dir'] = ''
        values['workspace_dir'] = ''
        problems, _ = settings_store.validate(values)
        self.assertTrue(any('库目录' in item for item in problems))
        self.assertTrue(any('工作区' in item for item in problems))

    def test_rejects_relative_path(self):
        values = base_values(self.root)
        values['library_dir'] = 'music'
        problems, _ = settings_store.validate(values)
        self.assertTrue(any('绝对路径' in item for item in problems))

    def test_rejects_same_directory_twice(self):
        values = base_values(self.root)
        values['duplicate_dir'] = values['incomplete_dir']
        problems, _ = settings_store.validate(values)
        self.assertTrue(any('同一个目录' in item for item in problems))

    def test_rejects_nested_workspace_inside_library(self):
        values = base_values(self.root)
        values['workspace_dir'] = os.path.join(values['library_dir'], 'temp')
        problems, _ = settings_store.validate(values)
        self.assertTrue(any('不能放在' in item for item in problems))

    def test_vip_dir_defaults_to_parent(self):
        values = base_values(self.root)
        _problems, normalized = settings_store.validate(values)
        self.assertEqual(normalized['netease_vip_dir'], '')
        self.assertEqual(settings_store.vip_default(normalized['netease_dir']),
                         os.path.join(normalized['netease_dir'], 'VipSOngsDownload'))

    def test_accepts_drive_letter_paths_on_windows(self):
        """回归：曾用 `sys.platform != 'nt'` 判平台，而 Windows 上是 'win32'，
        导致「非 Windows 才拦盘符路径」在 Windows 上永远成立，D:/G: 正常路径被拒。
        tmp_path 都在系统盘用户目录下，碰不到这个分支，所以必须单独构造盘符路径。
        """
        if os.name != 'nt':
            self.skipTest('盘符路径只在 Windows 上有意义')
        drive = os.path.splitdrive(self.root)[0] or 'C:'
        values = {
            'library_dir': drive + os.sep + 'mh_library_probe',
            'workspace_dir': drive + os.sep + 'mh_workspace_probe',
            'incomplete_dir': drive + os.sep + 'mh_unready_probe',
            'duplicate_dir': drive + os.sep + 'mh_duplicate_probe',
            'netease_dir': drive + os.sep + 'mh_netease_probe',
            'netease_vip_dir': '',
            'qq_dir': drive + os.sep + 'mh_qq_probe',
            'qq_vip_dir': '',
        }
        problems, _normalized = settings_store.validate(values)
        self.assertEqual(problems, [])

    def test_drive_letter_rejected_on_non_windows(self):
        """非 Windows 上仍应明确提示盘符路径不可用（直接改模块常量，避免依赖真机平台）"""
        values = base_values(self.root)
        values['library_dir'] = 'D:\\music'
        original = settings_store._IS_WINDOWS
        settings_store._IS_WINDOWS = False
        try:
            problems, _normalized = settings_store.validate(values)
        finally:
            settings_store._IS_WINDOWS = original
        self.assertTrue(any('不是 Windows' in item for item in problems))


class TestSave(SettingsTestCase):

    def test_save_writes_ini_and_reloads_config(self):
        values = base_values(self.root)
        problems, items = settings_store.save(values)
        self.assertEqual(problems, [])
        self.assertTrue(os.path.isfile(self.ini))
        self.assertEqual(config.LIBRARY_DIR, values['library_dir'])
        self.assertEqual(config.WORKSPACE_DIR, values['workspace_dir'])
        # VIP 目录没单独填，就跟随下载目录
        self.assertEqual(config.QQ_VIP_DIR,
                         os.path.join(values['qq_dir'], 'VipSOngsDownload'))
        self.assertTrue(any(item['key'] == 'library_dir' for item in items))

    def test_save_rejects_and_keeps_old_file(self):
        problems, _items = settings_store.save(base_values(self.root))
        self.assertEqual(problems, [])
        before = open(self.ini, encoding='utf-8').read()
        broken = base_values(self.root)
        broken['library_dir'] = 'relative/path'
        problems, _items = settings_store.save(broken)
        self.assertTrue(problems)
        self.assertEqual(open(self.ini, encoding='utf-8').read(), before)

    def test_vip_dir_written_when_saved(self):
        values = base_values(self.root)
        custom = os.path.join(self.root, 'vip-only')
        values['qq_vip_dir'] = custom
        problems, _items = settings_store.save(values)
        self.assertEqual(problems, [])
        self.assertEqual(config.QQ_VIP_DIR, custom)

    def test_vip_dir_removed_when_back_to_default(self):
        values = base_values(self.root)
        values['qq_vip_dir'] = os.path.join(self.root, 'vip-only')
        settings_store.save(values)
        values['qq_vip_dir'] = ''
        settings_store.save(values)
        text = open(self.ini, encoding='utf-8').read()
        self.assertNotIn('qq_vip_dir', text)
        self.assertEqual(config.QQ_VIP_DIR,
                         os.path.join(values['qq_dir'], 'VipSOngsDownload'))

    def test_other_sections_preserved(self):
        os.makedirs(os.path.dirname(self.ini), exist_ok=True)
        with open(self.ini, 'w', encoding='utf-8') as handle:
            handle.write('[paths]\nlibrary_dir = D:\\\\old\n\n[settings]\nfpcalc_length = 60\n')
        config.reload()
        settings_store.save(base_values(self.root))
        text = open(self.ini, encoding='utf-8').read()
        self.assertIn('[settings]', text)
        self.assertIn('fpcalc_length = 60', text)
        self.assertEqual(config.FPCALC_LENGTH, 60)

    def test_env_override_is_reported(self):
        values = base_values(self.root)
        settings_store.save(values)
        os.environ['MUSIC_HELPER_LIBRARY_DIR'] = os.path.join(self.root, 'from-env')
        config.reload()
        sources = {item['key']: item['source'] for item in settings_store.current()}
        self.assertEqual(sources['library_dir'], 'env')
        self.assertEqual(config.LIBRARY_DIR, os.path.join(self.root, 'from-env'))


class TestCurrent(SettingsTestCase):

    def test_lists_all_wizard_dirs(self):
        keys = [item['key'] for item in settings_store.current()]
        self.assertEqual(keys, ['library_dir', 'workspace_dir', 'incomplete_dir',
                                'duplicate_dir', 'netease_dir', 'netease_vip_dir',
                                'qq_dir', 'qq_vip_dir'])

    def test_probe_flags_missing_dir(self):
        missing = os.path.join(self.root, 'not-there')
        info = settings_store._probe(missing)
        self.assertFalse(info['exists'])
        self.assertTrue(info['error'])


if __name__ == '__main__':
    unittest.main()
