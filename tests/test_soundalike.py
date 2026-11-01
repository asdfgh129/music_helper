# -*- coding: utf-8 -*-
"""单元测试 - 声纹去重服务"""

import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from services import soundalike


def _completed(returncode):
    result = MagicMock()
    result.returncode = returncode
    result.stdout = ''
    result.stderr = ''
    return result


class TestSoundalike(unittest.TestCase):
    @patch('services.soundalike.subprocess.run')
    def test_run_success(self, mock_run):
        mock_run.return_value = _completed(0)
        result = soundalike.run()
        self.assertTrue(result.ok)
        self.assertEqual(result.returncode, 0)
        mock_run.assert_called_once()

    @patch('services.soundalike.subprocess.run')
    def test_run_failure(self, mock_run):
        mock_run.return_value = _completed(1)
        self.assertFalse(soundalike.run().ok)

    @patch('services.soundalike.subprocess.run')
    def test_run_with_temp_adds_flag(self, mock_run):
        mock_run.return_value = _completed(0)
        soundalike.run(with_temp=True, debug=True)
        cmd = mock_run.call_args[0][0]
        self.assertIn('-temp', cmd)
        self.assertIn(config.WORKSPACE_DIR, cmd)
        self.assertIn('-log-sec=1', cmd)

    @patch('services.soundalike.subprocess.run')
    def test_run_uses_db_and_dup_dir(self, mock_run):
        mock_run.return_value = _completed(0)
        soundalike.run(with_temp=False)
        cmd = mock_run.call_args[0][0]
        self.assertIn('-db', cmd)
        self.assertIn(config.DB_PATH, cmd)
        self.assertIn('-move-interactive', cmd)
        self.assertIn(config.DUPLICATE_DIR, cmd)
        self.assertNotIn('-temp', cmd)
        self.assertEqual(mock_run.call_args.kwargs['cwd'], os.path.dirname(os.path.abspath(config.DB_PATH)))

    @patch('services.soundalike.subprocess.run')
    def test_check_requires_db(self, mock_run):
        mock_run.return_value = _completed(0)
        soundalike.check()
        cmd = mock_run.call_args[0][0]
        self.assertIn('-check', cmd)
        self.assertIn('-db', cmd)
        self.assertIn(config.DB_PATH, cmd)

    @patch('services.soundalike.subprocess.run')
    def test_timeout_returns_failure(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired('soundalike', 1)
        result = soundalike.run()
        self.assertFalse(result.ok)
        self.assertIn('超时', result.message)

    def test_missing_executable(self):
        with patch.object(config, 'SOUNDALIKE_EXE', os.path.join('Z:', 'nope', 'soundalike.exe')):
            result = soundalike.check()
        self.assertFalse(result.ok)
        self.assertIn('找不到', result.message)

    @patch('services.soundalike.subprocess.run')
    def test_check_success(self, mock_run):
        mock_run.return_value = _completed(0)
        self.assertTrue(soundalike.check().ok)

    @patch('services.soundalike.subprocess.run')
    def test_fpcalc_length_follows_config(self, mock_run):
        """指纹长度必须与 config 一致，否则声纹库会因 Settings 不符拒绝打开"""
        mock_run.return_value = _completed(0)
        soundalike.run()
        cmd = mock_run.call_args[0][0]
        self.assertIn('-fpcalc-length', cmd)
        self.assertEqual(cmd[cmd.index('-fpcalc-length') + 1], str(config.FPCALC_LENGTH))

    @patch('services.soundalike.subprocess.run')
    def test_tools_dir_prepended_to_path(self, mock_run):
        """soundalike 只按 PATH 找 fpcalc，必须把 tools/ 注入进去"""
        mock_run.return_value = _completed(0)
        soundalike.run()
        env = mock_run.call_args.kwargs['env']
        self.assertTrue(env['PATH'].split(os.pathsep)[0] == config.TOOLS_DIR, env['PATH'])

    @patch('services.soundalike.subprocess.run')
    def test_report_is_read_only(self, mock_run):
        """只列候选必须连库都不写：写进去就会让下一轮正式运行「查不出重复」"""
        mock_run.return_value = _completed(0)
        self.assertTrue(soundalike.report(with_temp=True).ok)
        cmd = mock_run.call_args[0][0]
        self.assertIn('-dry-run', cmd)
        self.assertIn('-temp', cmd)
        self.assertIn(config.LIBRARY_DIR, cmd)

    def test_file_regexp_covers_dsd_and_config(self):
        """soundalike 内置正则不含 dsf；不显式传就会漏掉整个 DSD 类文件"""
        import re
        pattern = soundalike.file_regexp()
        compiled = re.compile(pattern)
        for name in ('a.flac', 'a.mp3', 'a.dsf', 'a.dff', 'a.wav'):
            self.assertTrue(compiled.search(name), f'{name} 应参与声纹扫描: {pattern}')
        self.assertFalse(compiled.search('a.txt'))
        for ext in config.AUDIO_EXTENSIONS:
            self.assertIn(ext.lstrip('.'), pattern)

    @patch('services.soundalike.subprocess.run')
    def test_file_regexp_passed_to_tool(self, mock_run):
        mock_run.return_value = _completed(0)
        soundalike.run()
        cmd = mock_run.call_args[0][0]
        self.assertIn('-file-regexp', cmd)
        self.assertEqual(cmd[cmd.index('-file-regexp') + 1], soundalike.file_regexp())

    @patch('services.soundalike.subprocess.run')
    def test_dry_run_adds_flag_and_prints_plan(self, mock_run):
        """--dry-run 走 soundalike 自己的试运行：只打印，不动文件"""
        completed = _completed(0)
        completed.stdout = '[试运行] 将移动 a.mp3 -> dup\\a.mp3\n'
        mock_run.return_value = completed
        result = soundalike.run(dry_run=True)
        self.assertTrue(result.ok)
        cmd = mock_run.call_args[0][0]
        self.assertIn('-dry-run', cmd)
        self.assertIn('-move-interactive', cmd)
        # 试运行不等人输入，输出要收起来再打（否则捕不到日志）
        self.assertTrue(mock_run.call_args.kwargs['capture_output'])

    @patch('services.soundalike.subprocess.run')
    def test_not_dry_run_by_default(self, mock_run):
        mock_run.return_value = _completed(0)
        soundalike.run()
        self.assertNotIn('-dry-run', mock_run.call_args[0][0])

    def test_temp_supported_compares_volumes(self):
        with patch.object(config, 'WORKSPACE_DIR', r'G:\Temp'), \
                patch.object(config, 'LIBRARY_DIR', r'D:\music'):
            self.assertEqual(soundalike.temp_supported(), os.name != 'nt')
        with patch.object(config, 'WORKSPACE_DIR', r'G:\Temp'), \
                patch.object(config, 'LIBRARY_DIR', r'G:\music'):
            self.assertTrue(soundalike.temp_supported())


class TestDbSettings(unittest.TestCase):
    """声纹库 Settings 与 fpcalc_length 的一致性检查"""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='mh_db_')
        self.db = os.path.join(self.root, 'music.db')
        self._saved = config.DB_PATH
        config.DB_PATH = self.db

    def tearDown(self):
        config.DB_PATH = self._saved
        shutil.rmtree(self.root, ignore_errors=True)

    def _make_db(self, desc):
        with sqlite3.connect(self.db) as connection:
            connection.execute('CREATE TABLE Settings (Desc STRING PRIMARY KEY NOT NULL)')
            connection.execute('INSERT INTO Settings VALUES(?)', (desc,))

    def test_missing_db_is_not_an_error(self):
        self.assertIsNone(soundalike.db_fpcalc_length())
        self.assertEqual(soundalike.settings_problem(), '')

    def test_reads_recorded_length(self):
        self._make_db('length=15.000,chunk=0.000,algorithm=2,overlap=false')
        self.assertEqual(soundalike.db_fpcalc_length(), 15.0)

    def test_mismatch_explains_how_to_fix(self):
        self._make_db('length=15.000,chunk=0.000,algorithm=2,overlap=false')
        problem = soundalike.settings_problem()
        self.assertIn('15', problem)
        self.assertIn('--init', problem)

    def test_same_length_passes(self):
        self._make_db(f'length={float(config.FPCALC_LENGTH):.3f},chunk=0.000,algorithm=2,overlap=false')
        self.assertEqual(soundalike.settings_problem(), '')

    def test_broken_db_is_ignored(self):
        with open(self.db, 'wb') as handle:
            handle.write(b'not a sqlite file')
        self.assertIsNone(soundalike.db_fpcalc_length())


if __name__ == '__main__':
    unittest.main()
