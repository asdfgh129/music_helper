# -*- coding: utf-8 -*-
"""core.quality 单测：音质比较（决定库里旧版本要不要让位）"""

import unittest

from core.quality import compare, describe, is_lossless


def spec(ext='.flac', **kwargs):
    info = {'ext': ext, 'size': 0, 'duration': 0.0,
            'bitrate': 0, 'sample_rate': 0, 'bit_depth': 0}
    info.update(kwargs)
    return info


class TestIsLossless(unittest.TestCase):

    def test_lossless_formats(self):
        for ext in ('.flac', '.ape', '.wav', '.dsf', '.aiff', '.ALAC'):
            self.assertTrue(is_lossless(ext), ext)

    def test_lossy_formats(self):
        for ext in ('.mp3', '.ogg', '.opus', '.m4a', '.wma', ''):
            self.assertFalse(is_lossless(ext), ext)


class TestCompareFormats(unittest.TestCase):

    def test_lossless_beats_lossy(self):
        self.assertEqual(compare(spec('.flac'), spec('.mp3')), 'better')
        self.assertEqual(compare(spec('.mp3'), spec('.flac')), 'worse')

    def test_wav_and_flac_are_both_lossless(self):
        """WAV 体积更大但音质等同，不能因为体积就判 WAV 更好"""
        left = spec('.wav', size=30_000_000, sample_rate=44100, bit_depth=16)
        right = spec('.flac', size=10_000_000, sample_rate=44100, bit_depth=16)
        self.assertEqual(compare(left, right), 'same')

    def test_hires_flac_beats_cd_flac(self):
        left = spec('.flac', sample_rate=96000, bit_depth=24)
        right = spec('.flac', sample_rate=44100, bit_depth=16)
        self.assertEqual(compare(left, right), 'better')
        self.assertEqual(compare(right, left), 'worse')

    def test_lossless_without_spec_is_unknown(self):
        self.assertEqual(compare(spec('.flac'), spec('.flac')), 'unknown')

    def test_same_depth_different_rate(self):
        left = spec('.flac', sample_rate=48000, bit_depth=24)
        right = spec('.flac', sample_rate=96000, bit_depth=24)
        self.assertEqual(compare(left, right), 'worse')


class TestCompareBitrate(unittest.TestCase):

    def test_higher_bitrate_wins(self):
        self.assertEqual(compare(spec('.mp3', bitrate=320000),
                                 spec('.mp3', bitrate=128000)), 'better')

    def test_close_bitrate_is_same(self):
        """码率差在 10% 以内视为同一水平，避免同一次转码互相替换"""
        self.assertEqual(compare(spec('.mp3', bitrate=320000),
                                 spec('.mp3', bitrate=300000)), 'same')

    def test_bitrate_estimated_from_size(self):
        """容器不报码率时用 大小 ÷ 时长 估算"""
        left = spec('.mp3', size=4_800_000, duration=120.0)     # 320kbps
        right = spec('.mp3', size=1_920_000, duration=120.0)    # 128kbps
        self.assertEqual(compare(left, right), 'better')

    def test_missing_bitrate_is_unknown(self):
        self.assertEqual(compare(spec('.mp3', size=100), spec('.mp3', size=200)),
                         'unknown')

    def test_empty_inputs(self):
        self.assertEqual(compare(None, spec('.flac')), 'unknown')
        self.assertEqual(compare(spec('.flac'), {}), 'unknown')


class TestDescribe(unittest.TestCase):

    def test_lossless_description(self):
        text = describe(spec('.flac', sample_rate=44100, bit_depth=16))
        self.assertIn('FLAC', text)
        self.assertIn('无损', text)
        self.assertIn('44.1kHz', text)
        self.assertIn('16bit', text)

    def test_lossy_description(self):
        text = describe(spec('.mp3', bitrate=320000))
        self.assertIn('MP3', text)
        self.assertIn('有损', text)
        self.assertIn('320kbps', text)

    def test_lossless_without_spec(self):
        self.assertEqual(describe(spec('.flac')), 'FLAC 无损')

    def test_empty(self):
        self.assertEqual(describe(None), '—')
        self.assertEqual(describe({}), '—')


if __name__ == '__main__':
    unittest.main()
