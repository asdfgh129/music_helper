# -*- coding: utf-8 -*-
"""guess_song_url 是解密后的附赠信息，任何网络问题都必须 fail-soft，
不能让已经解出来的文件被判成失败。"""
import unittest
from unittest.mock import patch

from decrypto import source_finder


class TestGuessSongUrlFailSoft(unittest.TestCase):
    def test_returns_none_when_network_fails(self):
        with patch.object(source_finder.urllib.request, 'urlopen',
                          side_effect=OSError('网络不通')):
            self.assertIsNone(
                source_finder.guess_song_url('周杰伦 - 晴天.mflac'))

    def test_returns_none_on_bad_json(self):
        fake = unittest.mock.MagicMock()
        fake.__enter__.return_value.read.return_value = b'{not json'
        with patch.object(source_finder.urllib.request, 'urlopen',
                          return_value=fake):
            self.assertIsNone(source_finder.guess_song_url('x - y.mflac'))

    def test_returns_none_on_empty_query(self):
        self.assertIsNone(source_finder.guess_song_url('.mflac'))


if __name__ == '__main__':
    unittest.main()
