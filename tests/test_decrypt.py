# -*- coding: utf-8 -*-
"""单元测试 - 解密流程的加密原文件处理（归还 VIP 目录 / 回收站 / 保留）"""

import os
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import services.decrypt as decrypt


class TestEncryptedSourceHandling(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='mh_decrypt_')
        self.vip_dir = os.path.join(self.root, 'vip')
        self.tmp_dir = os.path.join(self.root, 'tmp')
        self.out_dir = os.path.join(self.root, 'out')
        self.trash_dir = os.path.join(self.root, 'trash')
        for path in (self.vip_dir, self.tmp_dir, self.out_dir):
            os.makedirs(path)

        # 解密模块内部读的是 config 的这几个全局值，测试时指向临时目录
        self._saved = {key: getattr(config, key) for key in
                       ('WORKSPACE_DIR', 'JOURNAL_PATH', 'TRASH_DIR', 'ENCRYPTED_SOURCE_MODE')}
        config.WORKSPACE_DIR = self.out_dir
        config.JOURNAL_PATH = os.path.join(self.root, 'journal.jsonl')
        config.TRASH_DIR = self.trash_dir

    def tearDown(self):
        for key, value in self._saved.items():
            setattr(config, key, value)
        shutil.rmtree(self.root, ignore_errors=True)

    def _encrypted(self, name='song.ncm'):
        path = os.path.join(self.vip_dir, name)
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write('encrypted')
        return path

    def _runner(self, produced_name='song.flac'):
        """模拟外部解密程序：往产出目录写一个解密后的文件"""
        def run():
            with open(os.path.join(self.out_dir, produced_name), 'w', encoding='utf-8') as handle:
                handle.write('audio')
            return SimpleNamespace(returncode=0), ''
        return run

    def _decrypt(self):
        return decrypt._decrypt(
            name='测试',
            vip_dir=self.vip_dir,
            tmp_dir=self.tmp_dir,
            vip_exts={'.ncm'},
            month=None,
            dry_run=False,
            logger=None,
            runner=self._runner(),
        )

    def test_original_returns_to_vip_dir_by_default(self):
        """默认行为：加密原文件搬回 VIP 下载目录，解密产物保留在产出目录"""
        config.ENCRYPTED_SOURCE_MODE = 'return'
        source = self._encrypted()
        result = self._decrypt()

        self.assertTrue(result.ok)
        self.assertTrue(os.path.exists(source), '加密原文件应回到 VIP 目录')
        self.assertFalse(os.path.exists(os.path.join(self.tmp_dir, 'song.ncm')))
        self.assertTrue(os.path.exists(os.path.join(self.out_dir, 'song.flac')))
        self.assertIn('归还', result.message)

    def test_trash_mode_moves_original_to_recycle_bin(self):
        config.ENCRYPTED_SOURCE_MODE = 'trash'
        self._encrypted()
        result = self._decrypt()

        self.assertTrue(result.ok)
        self.assertFalse(os.path.exists(os.path.join(self.vip_dir, 'song.ncm')))
        self.assertFalse(os.path.exists(os.path.join(self.tmp_dir, 'song.ncm')))
        self.assertTrue(os.path.isdir(self.trash_dir))
        self.assertTrue(os.listdir(self.trash_dir), '回收站里应有加密原文件')

    def test_keep_mode_leaves_original_in_temp_dir(self):
        config.ENCRYPTED_SOURCE_MODE = 'keep'
        self._encrypted()
        result = self._decrypt()

        self.assertTrue(result.ok)
        self.assertFalse(os.path.exists(os.path.join(self.vip_dir, 'song.ncm')))
        self.assertTrue(os.path.exists(os.path.join(self.tmp_dir, 'song.ncm')))

    def test_only_touched_files_are_moved(self):
        """VIP 目录里的其他文件、产出目录里的无关文件都不应被搬动"""
        config.ENCRYPTED_SOURCE_MODE = 'return'
        self._encrypted('song.ncm')
        unrelated = os.path.join(self.vip_dir, 'other.mp3')
        with open(unrelated, 'w', encoding='utf-8') as handle:
            handle.write('keep me')
        stray = os.path.join(self.out_dir, 'stray.flac')
        with open(stray, 'w', encoding='utf-8') as handle:
            handle.write('copied by pipeline')

        self._decrypt()

        self.assertTrue(os.path.exists(unrelated))
        self.assertTrue(os.path.exists(stray))
        self.assertTrue(os.path.exists(os.path.join(self.vip_dir, 'song.ncm')))

    def test_dry_run_touches_nothing(self):
        config.ENCRYPTED_SOURCE_MODE = 'return'
        source = self._encrypted()
        result = decrypt._decrypt(
            name='测试', vip_dir=self.vip_dir, tmp_dir=self.tmp_dir, vip_exts={'.ncm'},
            month=None, dry_run=True, logger=None, runner=self._runner(),
        )

        self.assertTrue(result.ok)
        self.assertTrue(os.path.exists(source))
        self.assertFalse(os.path.exists(os.path.join(self.tmp_dir, 'song.ncm')))
        self.assertFalse(os.listdir(self.out_dir))


if __name__ == '__main__':
    unittest.main()
