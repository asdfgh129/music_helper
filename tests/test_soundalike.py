# -*- coding: utf-8 -*-
"""单元测试 - 声纹去重服务"""

import os
import sys
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


if __name__ == '__main__':
    unittest.main()
