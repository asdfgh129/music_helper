# -*- coding: utf-8 -*-
"""
单元测试 - 主程序模块
"""

import unittest
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import validate_month_format


class TestMain(unittest.TestCase):
    """主程序模块测试"""

    def test_validate_month_format_valid_formats(self):
        """测试有效的月份格式"""
        # 测试正常月份
        self.assertTrue(validate_month_format("202401"))
        self.assertTrue(validate_month_format("202312"))
        self.assertTrue(validate_month_format("202406"))
        self.assertTrue(validate_month_format("199901"))
        self.assertTrue(validate_month_format("209912"))

    def test_validate_month_format_invalid_formats(self):
        """测试无效的月份格式"""
        # 长度错误
        self.assertFalse(validate_month_format(""))
        self.assertFalse(validate_month_format("2024"))
        self.assertFalse(validate_month_format("20240607"))

        # 非数字
        self.assertFalse(validate_month_format("2024ab"))
        self.assertFalse(validate_month_format("abcd06"))
        self.assertFalse(validate_month_format("20-406"))

        # 无效月份
        self.assertFalse(validate_month_format("202400"))
        self.assertFalse(validate_month_format("202413"))
        self.assertFalse(validate_month_format("202499"))

        # 无效年份
        self.assertFalse(validate_month_format("189901"))
        self.assertFalse(validate_month_format("210001"))

    def test_validate_month_format_boundary_cases(self):
        """测试边界情况"""
        # 边界年份
        self.assertTrue(validate_month_format("190001"))
        self.assertTrue(validate_month_format("209912"))

        # 边界月份
        self.assertTrue(validate_month_format("202401"))
        self.assertTrue(validate_month_format("202412"))

        # 闰年测试
        self.assertTrue(validate_month_format("202402"))  # 2024是闰年
        self.assertTrue(validate_month_format("202002"))  # 2020是闰年


if __name__ == '__main__':
    unittest.main()
