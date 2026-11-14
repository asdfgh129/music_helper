# -*- coding: utf-8 -*-
"""services.media 的单元测试：只读媒体层（白名单 / Range / MIME / 歌词 / 封面 / 偏移）

只用 tempfile，不碰真实音乐库、网络、外部程序，也不需要 mutagen 或 Web 框架。
"""

import os
import shutil
import tempfile
import unittest
from unittest import mock

import config
from core import lyrics as lyrics_core
from services import media

_PATCHED_DIRS = (
    'LIBRARY_DIR', 'WORKSPACE_DIR', 'INCOMPLETE_DIR', 'DUPLICATE_DIR',
    'NETEASE_DIR', 'NETEASE_VIP_DIR', 'QQ_DIR', 'QQ_VIP_DIR',
    'DECRYPT_STAGING_DIR',
)


class MediaTestCase(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='mh_media_')
        self.addCleanup(shutil.rmtree, self.root, True)
        self.workspace = self._mkdir('workspace')
        for name in _PATCHED_DIRS:
            value = self.workspace if name == 'WORKSPACE_DIR' else os.path.join(
                self.root, 'unused', name)
            patcher = mock.patch.object(config, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        lyrics_core.clear_lrc_cache()
        self.addCleanup(lyrics_core.clear_lrc_cache)

    def _mkdir(self, *parts):
        path = os.path.join(self.root, *parts)
        os.makedirs(path, exist_ok=True)
        return path

    def _audio(self, *parts, data=b'0123456789'):
        path = os.path.join(self.root, *parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as handle:
            handle.write(data)
        return path


class TestResolveMedia(MediaTestCase):

    def test_accepts_audio_in_allowed_dir_recursively(self):
        path = self._audio('workspace', '2020', '2020', 'a.flac')
        self.assertEqual(media.resolve_media(path), os.path.realpath(path))

    def test_rejects_empty_and_relative_path(self):
        for value in ('', '   ', 'a.flac', 'workspace/a.flac'):
            with self.assertRaises(media.MediaError):
                media.resolve_media(value)

    def test_rejects_non_audio_extension(self):
        path = self._audio('workspace', 'notes.txt')
        with self.assertRaises(media.MediaError):
            media.resolve_media(path)

    def test_rejects_path_outside_whitelist(self):
        path = self._audio('outside', 'a.mp3')
        with self.assertRaises(media.MediaError):
            media.resolve_media(path)

    def test_rejects_sibling_with_same_prefix(self):
        """commonpath 而不是字符串前缀：workspace_evil 不算工作区"""
        path = self._audio('workspace_evil', 'a.mp3')
        with self.assertRaises(media.MediaError):
            media.resolve_media(path)

    def test_rejects_parent_traversal(self):
        outside = self._audio('outside', 'a.mp3')
        traversal = os.path.join(self.workspace, '..', 'outside', 'a.mp3')
        self.assertTrue(os.path.isfile(traversal))
        with self.assertRaises(media.MediaError):
            media.resolve_media(traversal)
        self.assertEqual(os.path.realpath(outside), os.path.realpath(traversal))

    def test_rejects_missing_file(self):
        with self.assertRaises(media.MediaError):
            media.resolve_media(os.path.join(self.workspace, 'nope.flac'))

    def test_whitelist_roots_are_unique_and_real(self):
        roots = media.allowed_roots()
        self.assertEqual(len(roots), len(set(roots)))
        self.assertIn(os.path.realpath(self.workspace), roots)


class TestParseRange(MediaTestCase):

    def test_no_range_returns_full_file(self):
        self.assertEqual(media.parse_range(None, 100), (0, 99, False))
        self.assertEqual(media.parse_range('', 100), (0, 99, False))

    def test_start_end(self):
        self.assertEqual(media.parse_range('bytes=10-19', 100), (10, 19, True))

    def test_open_ended(self):
        self.assertEqual(media.parse_range('bytes=90-', 100), (90, 99, True))

    def test_clamps_end_beyond_size(self):
        self.assertEqual(media.parse_range('bytes=95-999', 100), (95, 99, True))

    def test_suffix_length(self):
        self.assertEqual(media.parse_range('bytes=-5', 100), (95, 99, True))
        self.assertEqual(media.parse_range('bytes=-500', 100), (0, 99, True))

    def test_multipart_takes_first_segment(self):
        self.assertEqual(media.parse_range('bytes=0-9,20-29', 100), (0, 9, True))

    def test_invalid_ranges_raise_416(self):
        for header, size in (('bytes=100-', 100), ('bytes=20-10', 100),
                             ('bytes=-0', 100), ('bytes=-', 100),
                             ('items=0-9', 100), ('bytes=abc', 100),
                             (None, 0)):
            with self.assertRaises(media.RangeError):
                media.parse_range(header, size)


class TestIterChunks(MediaTestCase):

    def test_reads_exact_subrange(self):
        path = self._audio('workspace', 'a.mp3', data=bytes(range(256)) * 20)
        chunks = list(media.iter_chunks(path, 10, 29))
        with open(path, 'rb') as handle:
            expected = handle.read()[10:30]
        self.assertEqual(b''.join(chunks), expected)

    def test_full_file_in_chunks(self):
        data = b'x' * (media.CHUNK_SIZE * 2 + 17)
        path = self._audio('workspace', 'big.flac', data=data)
        chunks = list(media.iter_chunks(path, 0, len(data) - 1))
        self.assertEqual(len(chunks), 3)
        self.assertEqual(chunks[0], b'x' * media.CHUNK_SIZE)
        self.assertEqual(b''.join(chunks), data)


class TestMimeMatrix(MediaTestCase):

    def test_covers_every_audio_extension(self):
        """防止「只加扩展名、漏 MIME」：新格式会被浏览器当二进制下载"""
        self.assertEqual(set(media.MEDIA_MIME), set(config.AUDIO_EXTENSIONS))

    def test_playable_set_is_subset(self):
        self.assertTrue(set(media.BROWSER_PLAYABLE) <= set(media.MEDIA_MIME))
        for ext in ('.ape', '.wma', '.dsf'):
            self.assertNotIn(ext, media.BROWSER_PLAYABLE)
            self.assertTrue(media.NOT_PLAYABLE_REASON[ext])

    def test_unknown_extension(self):
        self.assertEqual(media.mime_for('a.xyz'), 'application/octet-stream')


class TestInfoAndLyric(MediaTestCase):

    def test_info_flags_unplayable_and_lyrics(self):
        path = self._audio('workspace', 'a.ape', data=b'fake')
        with open(os.path.join(self.workspace, 'a.lrc'), 'w', encoding='utf-8') as handle:
            handle.write('[00:01.00]晴天')
        info = media.media_info(path)
        self.assertFalse(info['browser_playable'])
        self.assertTrue(info['playable_reason'])
        self.assertEqual(info['mime'], 'audio/x-ape')
        self.assertEqual(info['size'], 4)
        self.assertTrue(info['has_lrc'])

    def test_lyric_payload_is_structured(self):
        path = self._audio('workspace', 'a.flac')
        with open(os.path.join(self.workspace, 'a.LRC'), 'wb') as handle:
            handle.write('[ti:晴天]\n[00:01.00]故事的小黄花\n'.encode('gb18030'))
        payload = media.lyric_payload(path)
        self.assertTrue(payload['exists'])
        self.assertEqual(payload['encoding'], 'gb18030')
        self.assertTrue(payload['has_timing'])
        self.assertEqual(payload['meta']['ti'], '晴天')
        self.assertIn('故事的小黄花', payload['lines'][0]['text'])

    def test_lyric_payload_without_lrc(self):
        path = self._audio('workspace', 'b.mp3')
        payload = media.lyric_payload(path)
        self.assertFalse(payload['exists'])
        self.assertFalse(payload['has_timing'])
        self.assertEqual(payload['lines'], [])

    def test_lyric_payload_includes_raw_text(self):
        path = self._audio('workspace', 'a.flac')
        with open(os.path.join(self.workspace, 'a.lrc'), 'w', encoding='utf-8') as handle:
            handle.write('[offset:0]\n[00:01.00]晴天\n')
        payload = media.lyric_payload(path)
        self.assertIn('[00:01.00]晴天', payload['raw'])
        self.assertEqual(payload['offset'], 0)

    def test_writable_only_inside_workspace(self):
        workspace_file = self._audio('workspace', 'a.mp3')
        self.assertTrue(media.media_info(workspace_file)['writable'])
        library_dir = os.path.join(self.root, 'unused', 'LIBRARY_DIR')
        os.makedirs(library_dir, exist_ok=True)
        library_file = self._audio('unused', 'LIBRARY_DIR', 'b.mp3')
        self.assertFalse(media.media_info(library_file)['writable'])

    def test_cover_payload_without_embedded_cover(self):
        path = self._audio('workspace', 'a.mp3')
        self.assertEqual(media.cover_payload(path), (None, ''))

    def test_parse_lyric_text_is_pure_and_structured(self):
        payload = media.parse_lyric_text('[00:01.00]晴天\n')
        self.assertTrue(payload['ok'])
        self.assertTrue(payload['has_timing'])
        self.assertEqual(payload['lines'][0]['text'], '晴天')

    def test_lyric_payload_exposes_word_segments(self):
        """P3：逐字字段由 core.lyrics 透传到 GET /api/media/lyric，raw 仍是原文"""
        path = self._audio('workspace', 'a.flac')
        with open(os.path.join(self.workspace, 'a.lrc'), 'w', encoding='utf-8') as handle:
            handle.write('[00:01.00]<00:01.00>晴<00:01.50>天\n')
        payload = media.lyric_payload(path)
        self.assertTrue(payload['word_timing'])
        self.assertEqual(payload['lines'][0]['text'], '晴天')
        self.assertEqual([s['time'] for s in payload['lines'][0]['syllables']],
                         [1.0, 1.5])
        self.assertIn('<00:01.50>天', payload['raw'])

    def test_parse_lyric_text_exposes_word_segments(self):
        payload = media.parse_lyric_text('[00:02.50]<00:02.50>晴<00:03.00>天\n')
        self.assertTrue(payload['word_timing'])
        self.assertEqual(payload['lines'][0]['syllables'],
                         [{'time': 2.5, 'text': '晴'}, {'time': 3.0, 'text': '天'}])

    def test_lyric_with_offset_clamps_and_rewrites(self):
        result = media.lyric_with_offset('[00:01.00]x\n', 999999)
        self.assertEqual(result['offset'], 60000)
        self.assertIn('[offset:60000]', result['text'])
        self.assertIn('[00:01.00]x', result['text'])
        self.assertEqual(media.lyric_with_offset('', -999999)['offset'], -60000)


if __name__ == '__main__':
    unittest.main()
