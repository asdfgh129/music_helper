# -*- coding: utf-8 -*-
"""
单元测试 - 工具函数模块
"""

import unittest
import sys
import os
import tempfile

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import (
    get_current_month,
    parse_filename,
    split_artist,
    normalize_text,
    check_filename_format,
)


class TestUtils(unittest.TestCase):
    """工具函数模块测试"""

    def test_get_current_month_format(self):
        """测试当前月份格式正确"""
        month = get_current_month()
        self.assertEqual(len(month), 6)
        self.assertTrue(month.isdigit())

    def test_parse_filename_standard(self):
        """测试标准文件名解析"""
        artist, title = parse_filename("Taylor Swift - Love Story.mp3")
        self.assertEqual(artist, "Taylor Swift")
        self.assertEqual(title, "Love Story")

    def test_parse_filename_no_separator(self):
        """测试无分隔符的文件名解析"""
        artist, title = parse_filename("Love Story.mp3")
        self.assertEqual(artist, "")
        self.assertEqual(title, "Love Story")

    def test_parse_filename_multiple_separators(self):
        """测试多个分隔符的文件名解析"""
        artist, title = parse_filename("Coldplay - Viva La Vida - Live.mp3")
        self.assertEqual(artist, "Coldplay")
        self.assertEqual(title, "Viva La Vida - Live")

    def test_split_artist_semicolon(self):
        """测试分号分隔的艺术家"""
        artists = split_artist("周杰伦;林俊杰")
        self.assertIn("周杰伦", artists)
        self.assertIn("林俊杰", artists)
        self.assertEqual(len(artists), 2)

    def test_split_artist_comma(self):
        """测试逗号分隔的艺术家"""
        artists = split_artist("Jay Chou, JJ Lin")
        self.assertIn("Jay Chou", artists)
        self.assertIn("JJ Lin", artists)
        self.assertEqual(len(artists), 2)

    def test_split_artist_chinese_comma(self):
        """测试中文逗号分隔的艺术家"""
        artists = split_artist("周杰伦，林俊杰，陈奕迅")
        self.assertIn("周杰伦", artists)
        self.assertIn("林俊杰", artists)
        self.assertIn("陈奕迅", artists)
        self.assertEqual(len(artists), 3)

    def test_split_artist_ampersand(self):
        """测试&分隔的艺术家"""
        artists = split_artist("Beyoncé & Jay-Z")
        self.assertIn("Beyoncé", artists)
        self.assertIn("Jay-Z", artists)

    def test_split_artist_whitespace(self):
        """测试艺术家名称包含空格"""
        artists = split_artist("Taylor Swift; Ed Sheeran")
        self.assertEqual(artists, ["Taylor Swift", "Ed Sheeran"])

    def test_split_artist_empty(self):
        """测试空字符串"""
        artists = split_artist("")
        self.assertEqual(artists, [])

    def test_normalize_text_spaces(self):
        """测试空格标准化"""
        text = normalize_text("Hello  World")
        self.assertEqual(text, "helloworld")

    def test_normalize_text_case(self):
        """测试大小写标准化"""
        text = normalize_text("Hello World")
        self.assertEqual(text, "helloworld")

    def test_normalize_text_chinese(self):
        """测试中文字符保留"""
        text = normalize_text("你好 世界")
        self.assertEqual(text, "你好世界")

    def test_normalize_text_empty(self):
        """测试空字符串"""
        text = normalize_text("")
        self.assertEqual(text, "")

    def test_check_filename_format_valid(self):
        """测试有效的文件名格式"""
        self.assertTrue(check_filename_format("Artist - Song.mp3"))
        self.assertTrue(check_filename_format("周杰伦 - 青花瓷.flac"))

    def test_check_filename_format_invalid(self):
        """测试无效的文件名格式"""
        self.assertFalse(check_filename_format("Song.mp3"))
        self.assertFalse(check_filename_format("Artist_Song.mp3"))

    def test_check_filename_format_multiple_separators(self):
        """测试多个分隔符的文件名"""
        self.assertTrue(check_filename_format("Artist - Song - Version.mp3"))


if __name__ == '__main__':
    unittest.main()
