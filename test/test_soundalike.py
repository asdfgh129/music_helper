# -*- coding: utf-8 -*-
"""
单元测试 - 声纹识别模块
"""

import unittest
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from soundalike import run_soundalike_fingerprinting, check_database_consistency
from unittest.mock import patch, MagicMock


class TestSoundalike(unittest.TestCase):
    """声纹识别模块测试"""

    @patch('soundalike.subprocess.run')
    def test_run_soundalike_fingerprinting_success(self, mock_run):
        """测试声纹识别成功"""
        # 模拟subprocess.run返回成功
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Processing complete"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        result = run_soundalike_fingerprinting()
        self.assertTrue(result)
        mock_run.assert_called_once()

    @patch('soundalike.subprocess.run')
    def test_run_soundalike_fingerprinting_failure(self, mock_run):
        """测试声纹识别失败"""
        # 模拟subprocess.run返回失败
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Error occurred"
        mock_run.return_value = mock_result

        result = run_soundalike_fingerprinting()
        self.assertFalse(result)

    @patch('soundalike.subprocess.run')
    def test_run_soundalike_fingerprinting_exception(self, mock_run):
        """测试声纹识别异常"""
        # 模拟subprocess.run抛出异常
        mock_run.side_effect = Exception("Command not found")

        result = run_soundalike_fingerprinting()
        self.assertFalse(result)

    @patch('soundalike.subprocess.run')
    def test_check_database_consistency_success(self, mock_run):
        """测试数据库一致性检查成功"""
        # 模拟subprocess.run返回成功
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Database is consistent"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        result = check_database_consistency()
        self.assertTrue(result)
        mock_run.assert_called_once()

    @patch('soundalike.subprocess.run')
    def test_check_database_consistency_failure(self, mock_run):
        """测试数据库一致性检查失败"""
        # 模拟subprocess.run返回失败
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Database inconsistencies found"
        mock_run.return_value = mock_result

        result = check_database_consistency()
        self.assertFalse(result)

    @patch('soundalike.subprocess.run')
    def test_check_database_consistency_exception(self, mock_run):
        """测试数据库一致性检查异常"""
        # 模拟subprocess.run抛出异常
        mock_run.side_effect = Exception("Command not found")

        result = check_database_consistency()
        self.assertFalse(result)

    def test_functions_exist(self):
        """测试函数是否存在"""
        self.assertTrue(callable(run_soundalike_fingerprinting))
        self.assertTrue(callable(check_database_consistency))


if __name__ == '__main__':
    unittest.main()
