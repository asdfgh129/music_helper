# -*- coding: utf-8 -*-
"""
单元测试 - 标签获取模块
"""

import unittest
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 初始化日志系统，避免main_logger为None
from utils import setup_logging
setup_logging()


class TestTagFetcher(unittest.TestCase):
    """标签获取模块测试"""

    def test_parse_musicbrainz_recording_full(self):
        """测试解析完整的MusicBrainz记录"""
        # 导入函数单独测试
        from tag_fetcher import parse_musicbrainz_recording

        recording = {
            'title': 'Test Song',
            'artist-credit': [
                {'artist': {'name': 'Artist 1'}},
                {'artist': {'name': 'Artist 2'}}
            ],
            'releases': [
                {
                    'title': 'Test Album',
                    'date': '2023-01-15'
                }
            ],
            'genre': 'Pop'
        }

        tags = parse_musicbrainz_recording(recording)
        self.assertIsNotNone(tags)
        self.assertEqual(tags['title'], 'Test Song')
        self.assertEqual(tags['artist'], 'Artist 1; Artist 2')
        self.assertEqual(tags['album'], 'Test Album')
        self.assertEqual(tags['year'], '2023')

    def test_parse_musicbrainz_recording_minimal(self):
        """测试解析最小MusicBrainz记录"""
        from tag_fetcher import parse_musicbrainz_recording

        recording = {
            'title': 'Test Song'
        }

        tags = parse_musicbrainz_recording(recording)
        self.assertIsNotNone(tags)
        self.assertEqual(tags['title'], 'Test Song')

    def test_parse_musicbrainz_recording_empty(self):
        """测试解析空记录"""
        from tag_fetcher import parse_musicbrainz_recording

        recording = {}

        tags = parse_musicbrainz_recording(recording)
        self.assertIsNone(tags)

    def test_parse_musicbrainz_recording_date_variations(self):
        """测试不同日期格式"""
        from tag_fetcher import parse_musicbrainz_recording

        test_cases = [
            ('2023-01-15', '2023'),
            ('2023', '2023'),
            ('2023/01/15', '2023'),
            ('15-01-2023', '2023'),
        ]

        for date, expected_year in test_cases:
            recording = {
                'title': 'Test Song',
                'releases': [{'date': date}]
            }
            tags = parse_musicbrainz_recording(recording)
            self.assertEqual(tags.get('year'), expected_year, f"Failed for date: {date}")

    def test_fetch_qq_music_tags_no_api(self):
        """测试没有QQ API时的行为"""
        from tag_fetcher import fetch_qq_music_tags

        tags = fetch_qq_music_tags(None, "Test Song", "Test Artist")
        self.assertIsNone(tags)

    def test_fetch_qq_music_tags_empty_title(self):
        """测试空标题"""
        from tag_fetcher import fetch_qq_music_tags

        tags = fetch_qq_music_tags(None, "", "Test Artist")
        self.assertIsNone(tags)

    def test_fetch_netease_tags_no_api(self):
        """测试没有网易云API时的行为"""
        from tag_fetcher import fetch_netease_tags

        tags = fetch_netease_tags(None, "Test Song", "Test Artist")
        self.assertIsNone(tags)

    def test_fetch_netease_tags_empty_title(self):
        """测试空标题"""
        from tag_fetcher import fetch_netease_tags

        tags = fetch_netease_tags(None, "", "Test Artist")
        self.assertIsNone(tags)

    def test_fetch_album_cover_no_apis(self):
        """测试没有API时的行为"""
        from tag_fetcher import fetch_album_cover

        cover_url = fetch_album_cover(None, None, "Test Song", "Test Artist")
        self.assertIsNone(cover_url)


if __name__ == '__main__':
    unittest.main()
