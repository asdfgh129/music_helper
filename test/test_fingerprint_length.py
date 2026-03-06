# -*- coding: utf-8 -*-
"""
测试指纹长度配置
"""
import unittest
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import FPCALC_LENGTH


class TestFingerprintLengthConfig(unittest.TestCase):
    """测试指纹长度配置"""

    def test_fpcalc_length_defined(self):
        """测试 FPCALC_LENGTH 已定义"""
        self.assertIsNotNone(FPCALC_LENGTH)
        self.assertIsInstance(FPCALC_LENGTH, int)

    def test_fpcalc_length_value(self):
        """测试 FPCALC_LENGTH 值为 120"""
        self.assertEqual(FPCALC_LENGTH, 120,
                        "FPCALC_LENGTH 应为 120（MusicBrainz 标准长度）")

    def test_fpcalc_length_positive(self):
        """测试 FPCALC_LENGTH 为正数"""
        self.assertGreater(FPCALC_LENGTH, 0,
                          "FPCALC_LENGTH 应该是正数")


if __name__ == "__main__":
    unittest.main()
