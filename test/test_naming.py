# -*- coding: utf-8 -*-
"""单元测试 - 命名规则与匹配评分"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.naming import (
    canonicalize,
    format_filename,
    is_audio,
    is_canonical,
    normalize_key,
    normalize_text,
    parse_filename,
    sanitize_component,
    split_artist,
)
from core.scoring import match_artist, match_score, tag_score


class TestNaming(unittest.TestCase):
    def test_parse_standard(self):
        self.assertEqual(parse_filename('Taylor Swift - Love Story.mp3'),
                         ('Taylor Swift', 'Love Story'))

    def test_parse_single_dash(self):
        self.assertEqual(parse_filename('周杰伦-晴天.flac'), ('周杰伦', '晴天'))

    def test_parse_no_separator(self):
        self.assertEqual(parse_filename('Love Story.mp3'), ('', 'Love Story'))

    def test_parse_keeps_dash_in_title(self):
        artist, title = parse_filename('A - B - C.mp3')
        self.assertEqual(artist, 'A')
        self.assertEqual(title, 'B - C')

    def test_is_canonical(self):
        self.assertTrue(is_canonical('A - B.mp3'))
        self.assertFalse(is_canonical('A-B.mp3'))
        self.assertFalse(is_canonical('B.mp3'))

    def test_canonicalize_single_dash(self):
        self.assertEqual(canonicalize('周杰伦-晴天.flac'), '周杰伦 - 晴天.flac')

    def test_canonicalize_skips_multiple_dash(self):
        self.assertIsNone(canonicalize('AC-DC - Back.mp3'))
        self.assertIsNone(canonicalize('A-B-C.mp3'))

    def test_canonicalize_skips_already_canonical(self):
        self.assertIsNone(canonicalize('A - B.mp3'))

    def test_format_filename(self):
        self.assertEqual(format_filename('周杰伦', '晴天', '.flac'), '周杰伦 - 晴天.flac')
        self.assertEqual(format_filename('', '晴天', '.mp3'), '晴天.mp3')

    def test_format_filename_sanitizes(self):
        self.assertNotIn('/', format_filename('A/B', 'C:D', '.mp3'))

    def test_sanitize_component(self):
        self.assertEqual(sanitize_component('a?b*c'), 'a_b_c')

    def test_split_artist(self):
        self.assertEqual(split_artist('A&B/C'), ['A', 'B', 'C'])
        self.assertEqual(split_artist('A，B；C'), ['A', 'B', 'C'])
        self.assertEqual(split_artist(''), [])

    def test_normalize_text(self):
        self.assertEqual(normalize_text('Hello  World'), 'helloworld')

    def test_normalize_key_strips_noise(self):
        self.assertEqual(normalize_key('晴天 (Live)'), '晴天')

    def test_is_audio(self):
        self.assertTrue(is_audio('a.FLAC'))
        self.assertFalse(is_audio('a.txt'))


class TestScoring(unittest.TestCase):
    def test_match_score(self):
        self.assertEqual(match_score('晴天', '晴天'), 2)
        self.assertEqual(match_score('晴天', '晴天 (Live)'), 1)
        self.assertEqual(match_score('晴天', '下雨天'), 0)
        self.assertEqual(match_score('', 'x'), 0)

    def test_match_artist_multi(self):
        self.assertEqual(match_artist('周杰伦', '周杰伦/费玉清'), 2)
        self.assertEqual(match_artist('费玉清', '周杰伦, 费玉清'), 2)

    def test_tag_score_completeness(self):
        full = {'title': '晴天', 'artist': '周杰伦', 'album': '叶惠美', 'year': '2003', 'genre': 'Pop'}
        self.assertEqual(tag_score(full, '晴天', '周杰伦'), 100)

    def test_tag_score_partial(self):
        self.assertLess(tag_score({'title': '晴天'}, '晴天', '周杰伦'), 100)


if __name__ == '__main__':
    unittest.main()
