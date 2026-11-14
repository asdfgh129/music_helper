# -*- coding: utf-8 -*-
"""Web 只读媒体接口的 HTTP 回归测试

用 FastAPI TestClient 走真实路由与真实响应头，但只用 tempfile 里的假音频，
不碰音乐库、网络、外部播放器。依赖 requirements-dev.txt 的 fastapi / httpx。
"""

import os
import shutil
import tempfile
import unittest
from unittest import mock

import config
from core import lyrics as lyrics_core

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover - 未装开发依赖时 unittest discover 仍应能跑
    TestClient = None

_PATCHED_DIRS = (
    'LIBRARY_DIR', 'WORKSPACE_DIR', 'INCOMPLETE_DIR', 'DUPLICATE_DIR',
    'NETEASE_DIR', 'NETEASE_VIP_DIR', 'QQ_DIR', 'QQ_VIP_DIR',
    'DECRYPT_STAGING_DIR', 'LOG_DIR',
)


@unittest.skipIf(TestClient is None, 'fastapi/httpx 未安装（pip install -r requirements-dev.txt）')
class TestMediaApi(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='mh_media_api_')
        self.addCleanup(shutil.rmtree, self.root, True)
        self.workspace = os.path.join(self.root, 'workspace')
        self.library = os.path.join(self.root, 'library')
        os.makedirs(self.workspace)
        os.makedirs(self.library)
        for name in _PATCHED_DIRS:
            if name == 'WORKSPACE_DIR':
                value = self.workspace
            elif name == 'LIBRARY_DIR':
                value = self.library
            elif name == 'LOG_DIR':
                value = os.path.join(self.root, 'log')
            else:
                value = os.path.join(self.root, 'unused', name)
            patcher = mock.patch.object(config, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        lyrics_core.clear_lrc_cache()
        self.addCleanup(lyrics_core.clear_lrc_cache)
        from services import transcode
        transcode.clear_jobs()
        self.addCleanup(transcode.clear_jobs)

        # 模块级 app 只创建一次；导入发生在目录被 patch 之后
        from web.api import app

        self.client = TestClient(app)
        self.audio = os.path.join(self.workspace, 'a.mp3')
        with open(self.audio, 'wb') as handle:
            handle.write(bytes(range(100)))
        with open(os.path.join(self.workspace, 'a.lrc'), 'w', encoding='utf-8') as handle:
            handle.write('[ti:测试]\n[offset:0]\n[00:01.00]歌词第一行\n')

    def test_info(self):
        resp = self.client.get('/api/media/info', params={'path': self.audio})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['ok'])
        self.assertTrue(data['browser_playable'])
        self.assertEqual(data['mime'], 'audio/mpeg')
        self.assertEqual(data['size'], 100)
        self.assertTrue(data['has_lrc'])
        self.assertTrue(data['writable'])

    def test_info_library_file_is_read_only(self):
        path = os.path.join(self.library, 'b.mp3')
        with open(path, 'wb') as handle:
            handle.write(b'x')
        data = self.client.get('/api/media/info', params={'path': path}).json()
        self.assertFalse(data['writable'])

    def test_stream_head_full_and_ranges(self):
        head = self.client.head('/api/media/stream', params={'path': self.audio})
        self.assertEqual(head.status_code, 200)
        self.assertEqual(head.headers['accept-ranges'], 'bytes')
        self.assertEqual(head.headers['content-length'], '100')
        self.assertEqual(head.content, b'')

        full = self.client.get('/api/media/stream', params={'path': self.audio})
        self.assertEqual(full.status_code, 200)
        self.assertEqual(full.content, bytes(range(100)))

        part = self.client.get('/api/media/stream', params={'path': self.audio},
                               headers={'Range': 'bytes=10-19'})
        self.assertEqual(part.status_code, 206)
        self.assertEqual(part.headers['content-range'], 'bytes 10-19/100')
        self.assertEqual(part.content, bytes(range(10, 20)))

        suffix = self.client.get('/api/media/stream', params={'path': self.audio},
                                 headers={'Range': 'bytes=-5'})
        self.assertEqual(suffix.content, bytes(range(95, 100)))

        bad = self.client.get('/api/media/stream', params={'path': self.audio},
                              headers={'Range': 'bytes=200-'})
        self.assertEqual(bad.status_code, 416)
        self.assertEqual(bad.headers['content-range'], 'bytes */100')

    def test_lyric_is_structured(self):
        data = self.client.get('/api/media/lyric', params={'path': self.audio}).json()
        self.assertTrue(data['exists'])
        self.assertEqual(data['meta']['ti'], '测试')
        self.assertEqual(data['lines'][0]['text'], '歌词第一行')
        self.assertIn('[00:01.00]歌词第一行', data['raw'])

    def test_cover_404_when_missing(self):
        resp = self.client.get('/api/media/cover', params={'path': self.audio})
        self.assertEqual(resp.status_code, 404)

    def test_cover_returns_bytes_and_mime(self):
        from services import media as media_service

        png = b'\x89PNG\r\n\x1a\n' + b'\x00' * 8
        with mock.patch.object(media_service, 'cover_payload', return_value=(png, 'image/png')):
            resp = self.client.get('/api/media/cover', params={'path': self.audio})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, png)
        self.assertEqual(resp.headers['content-type'], 'image/png')
        self.assertEqual(resp.headers['cache-control'], 'no-store')

    def test_cover_roundtrip_with_real_wav(self):
        """真写一张内嵌封面再经 HTTP 读回，覆盖 read_cover 与路由的串联"""
        import wave

        import core.tags as tags_reader

        if not tags_reader.MUTAGEN_AVAILABLE:
            self.skipTest('mutagen 未安装')
        wav = os.path.join(self.workspace, 'with-cover.wav')
        with wave.open(wav, 'wb') as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(8000)
            handle.writeframes(b'\x00\x00' * 100)
        png = b'\x89PNG\r\n\x1a\n' + b'\x00' * 16
        self.assertTrue(tags_reader.write_cover(wav, png))
        resp = self.client.get('/api/media/cover', params={'path': wav})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, png)
        self.assertEqual(resp.headers['content-type'], 'image/png')

    def test_lyric_parse_and_offset_are_pure(self):
        parsed = self.client.post('/api/media/lyric/parse',
                                  json={'text': '[00:02.50]第二行\n'}).json()
        self.assertTrue(parsed['has_timing'])
        self.assertEqual(parsed['lines'][0]['time'], 2.5)

        shifted = self.client.post('/api/media/lyric/offset', json={
            'text': '[offset:0]\n[00:01.00]歌词第一行\n', 'offset': 500,
        }).json()
        self.assertEqual(shifted['offset'], 500)
        self.assertIn('[offset:500]', shifted['text'])
        self.assertIn('[00:01.00]歌词第一行', shifted['text'])
        self.assertEqual(len(shifted['text'].splitlines()), 2)
        # 纯计算：不因调用接口而改写磁盘上的 .lrc
        with open(os.path.join(self.workspace, 'a.lrc'), encoding='utf-8') as handle:
            self.assertIn('[offset:0]', handle.read())

    def test_whitelist_rejects_outside_and_non_audio(self):
        outside = os.path.join(self.root, 'outside.mp3')
        with open(outside, 'wb') as handle:
            handle.write(b'x')
        self.assertEqual(
            self.client.get('/api/media/info', params={'path': outside}).status_code, 400)
        text = os.path.join(self.workspace, 'notes.txt')
        with open(text, 'w', encoding='utf-8') as handle:
            handle.write('x')
        self.assertEqual(
            self.client.get('/api/media/info', params={'path': text}).status_code, 400)

    def test_open_uses_validated_path_only(self):
        with mock.patch('utils.open_with_default_app') as opener:
            resp = self.client.post('/api/media/open', json={'path': self.audio})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['launched'])
        opener.assert_called_once_with(os.path.realpath(self.audio))

    def test_info_marks_unplayable_formats(self):
        wma = os.path.join(self.workspace, 'a.wma')
        with open(wma, 'wb') as handle:
            handle.write(b'fake')
        data = self.client.get('/api/media/info', params={'path': wma}).json()
        self.assertFalse(data['browser_playable'])
        self.assertTrue(data['needs_transcode'])
        self.assertFalse(self.client.get('/api/media/info',
                                         params={'path': self.audio}).json()['needs_transcode'])

    def test_transcode_stream_rejects_playable_and_unready(self):
        self.assertEqual(self.client.get(
            '/api/media/stream', params={'path': self.audio, 'transcode': 1}).status_code, 400)
        wma = os.path.join(self.workspace, 'a.wma')
        with open(wma, 'wb') as handle:
            handle.write(b'fake')
        with mock.patch('services.transcode.ffmpeg_exe', return_value=''):
            resp = self.client.get('/api/media/stream',
                                   params={'path': wma, 'transcode': 1})
        self.assertEqual(resp.status_code, 409)
        self.assertIn('transcode', resp.json())
        self.assertEqual(resp.json()['transcode']['status'], 'unavailable')

    def test_transcode_stream_reuses_range_from_cache(self):
        """伪造一份派生 MP3，验证 stream?transcode=1 仍走同一套 Range 与白名单"""
        from services import transcode

        wma = os.path.join(self.workspace, 'a.wma')
        with open(wma, 'wb') as handle:
            handle.write(b'fake')
        cached = os.path.join(transcode.cache_dir(), transcode.cache_key(wma) + '.mp3')
        with open(cached, 'wb') as handle:
            handle.write(bytes(range(100)))

        full = self.client.get('/api/media/stream',
                               params={'path': wma, 'transcode': 1})
        self.assertEqual(full.status_code, 200)
        self.assertEqual(full.headers['content-type'], 'audio/mpeg')
        self.assertEqual(full.content, bytes(range(100)))

        part = self.client.get('/api/media/stream',
                               params={'path': wma, 'transcode': 1},
                               headers={'Range': 'bytes=20-29'})
        self.assertEqual(part.status_code, 206)
        self.assertEqual(part.headers['content-range'], 'bytes 20-29/100')
        self.assertEqual(part.content, bytes(range(20, 30)))
        # 派生文件只读，原文件一字节未动
        with open(wma, 'rb') as handle:
            self.assertEqual(handle.read(), b'fake')

    def test_transcode_status_is_pure_query(self):
        from services import transcode

        wma = os.path.join(self.workspace, 'a.wma')
        with open(wma, 'wb') as handle:
            handle.write(b'fake')
        with mock.patch('services.transcode.ffmpeg_exe', return_value=''):
            data = self.client.get('/api/media/transcode',
                                   params={'path': wma}).json()
        self.assertTrue(data['ok'])
        self.assertFalse(data['available'])
        self.assertEqual(data['status'], 'unavailable')
        self.assertIn('FFmpeg', data['hint'])
        self.assertEqual(transcode.status(self.audio)['status'], 'not_needed')


if __name__ == '__main__':
    unittest.main()
