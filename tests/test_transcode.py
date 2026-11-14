# -*- coding: utf-8 -*-
"""services.transcode 的单元测试与真实解码端到端

纯函数 / 状态机测试不依赖 FFmpeg；末尾的端到端用例只在探测到 FFmpeg 时运行
（本机可用 imageio-ffmpeg / 系统 PATH / config 指定三种来源之一），
样本用 tempfile 现场生成，不碰真实音乐库。APE 没有可用的编码器，样本只覆盖
WMA 与 DSF；三种格式共用同一条命令，解码器覆盖由构建配方保证。
"""

import os
import shutil
import struct
import subprocess
import tempfile
import time
import unittest
from unittest import mock

import config
from services import media, transcode

_PATCHED_DIRS = (
    'LIBRARY_DIR', 'WORKSPACE_DIR', 'INCOMPLETE_DIR', 'DUPLICATE_DIR',
    'NETEASE_DIR', 'NETEASE_VIP_DIR', 'QQ_DIR', 'QQ_VIP_DIR',
    'DECRYPT_STAGING_DIR', 'LOG_DIR',
)


def _make_dsf(path, seconds=1):
    """手写最小 DSF（DSD64 / 单声道 / 1bit 静音），只用于验证解码链路"""
    rate, channels, block = 2822400, 1, 4096
    per_ch = ((rate // 8) * seconds + block - 1) // block * block
    data = bytes([0x69]) * (per_ch * channels)
    fmt_payload = struct.pack('<IIIIIIQII', 1, 0, 1, channels, rate, 1,
                              per_ch * 8, block, 0)
    fmt = b'fmt ' + struct.pack('<Q', 52) + fmt_payload
    data_hdr = b'data' + struct.pack('<Q', 12 + len(data))
    total = 28 + len(fmt) + len(data_hdr) + len(data)
    dsd = b'DSD ' + struct.pack('<Q', 28) + struct.pack('<QQ', total, 0)
    with open(path, 'wb') as handle:
        handle.write(dsd + fmt + data_hdr + data)


class TestTranscodeContract(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='mh_transcode_')
        self.addCleanup(shutil.rmtree, self.root, True)
        self.workspace = os.path.join(self.root, 'workspace')
        os.makedirs(self.workspace)
        for name in _PATCHED_DIRS:
            if name == 'WORKSPACE_DIR':
                value = self.workspace
            elif name == 'LOG_DIR':
                value = os.path.join(self.root, 'log')
            else:
                value = os.path.join(self.root, 'unused', name)
            patcher = mock.patch.object(config, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        transcode.clear_jobs()
        self.addCleanup(transcode.clear_jobs)

    def _audio(self, name, payload=b'fake'):
        path = os.path.join(self.workspace, name)
        with open(path, 'wb') as handle:
            handle.write(payload)
        return path

    def test_format_matrix_stays_aligned(self):
        self.assertEqual(transcode.NEEDS_TRANSCODE,
                         frozenset(media.NOT_PLAYABLE_REASON))
        self.assertEqual(transcode.NEEDS_TRANSCODE, {'.ape', '.wma', '.dsf'})

    def test_build_command_is_uniform_and_safe(self):
        cmd = transcode.build_command('/bin/ffmpeg', '/src/song.ape', '/cache/x.part')
        self.assertEqual(cmd[0], '/bin/ffmpeg')
        self.assertEqual(cmd[cmd.index('-i') + 1], '/src/song.ape')
        self.assertEqual(cmd[-1], '/cache/x.part')
        for flag in ('-nostdin', '-vn', '-sn', '-dn', '-map_metadata',
                     '-progress', '-f', 'mp3', 'libmp3lame'):
            self.assertIn(flag, cmd)
        self.assertIn('-1', cmd)  # 不带源文件的元数据
        self.assertEqual(cmd[cmd.index('-f') + 1], 'mp3')

    def test_parse_progress(self):
        self.assertEqual(transcode.parse_progress('out_time_us=1010000'), 1.01)
        # out_time_ms 名字带 ms，实际仍是微秒；两个字段同值不能让进度跳到 1000 倍
        self.assertEqual(transcode.parse_progress('out_time_ms=1010000', 1.01), 1.01)
        self.assertEqual(transcode.parse_progress('out_time_ms=2500000', 1.0), 2.5)
        self.assertEqual(transcode.parse_progress('out_time=00:01:02.500'), 62.5)
        self.assertEqual(transcode.parse_progress('out_time_us=500000', 1.0), 1.0)
        self.assertEqual(transcode.parse_progress('frame=12', 3.0), 3.0)
        self.assertEqual(transcode.parse_progress('some error text', 3.0), 3.0)
        self.assertEqual(transcode.parse_progress('out_time_us=N/A', 2.0), 2.0)
        self.assertEqual(transcode.parse_progress('out_time=bad', 2.0), 2.0)

    def test_failure_hint(self):
        self.assertIn('DRM', transcode._failure_hint('DRM protected stream'))
        self.assertIn('损坏', transcode._failure_hint('Invalid data found'))
        self.assertIn('重新解码', transcode._failure_hint('boom'))

    def test_missing_hint_lists_three_sources(self):
        hint = transcode.missing_hint()
        for keyword in ('imageio-ffmpeg', 'PATH', 'tools/', '系统播放器'):
            self.assertIn(keyword, hint)

    def test_cache_key_invalidates_when_source_changes(self):
        path = self._audio('song.ape', b'a' * 10)
        first = transcode.cache_key(path)
        with open(path, 'ab') as handle:
            handle.write(b'more')
        self.assertNotEqual(transcode.cache_key(path), first)
        other = self._audio('other.ape', b'a' * 14)
        self.assertNotEqual(transcode.cache_key(other), transcode.cache_key(path))
        self.assertEqual(len(first), 32)

    def test_ready_path_requires_nonempty_mp3_and_current_key(self):
        path = self._audio('song.wma')
        self.assertIsNone(transcode.ready_path(path))
        cached = os.path.join(transcode.cache_dir(), transcode.cache_key(path) + '.mp3')
        with open(cached, 'wb') as handle:
            handle.write(b'')
        self.assertIsNone(transcode.ready_path(path))
        with open(cached, 'wb') as handle:
            handle.write(b'ID3')
        self.assertEqual(transcode.ready_path(path), cached)
        with open(path, 'ab') as handle:
            handle.write(b'x')
        self.assertIsNone(transcode.ready_path(path))

    def test_prune_cache_only_touches_own_files(self):
        root = transcode.cache_dir()
        for index in range(15):
            with open(os.path.join(root, f'{index:032x}.mp3'), 'wb') as handle:
                handle.write(b'x')
        outsider = os.path.join(root, 'keep-me.txt')
        with open(outsider, 'wb') as handle:
            handle.write(b'keep')
        transcode.prune_cache()
        self.assertTrue(os.path.isfile(outsider))
        remaining = [name for name in os.listdir(root)
                     if transcode._CACHE_NAME_RE.match(name)]
        self.assertLessEqual(len(remaining), transcode.MAX_CACHE_FILES)

    def test_status_not_needed_and_missing_source(self):
        self.assertEqual(transcode.status(self._audio('a.mp3'))['status'], 'not_needed')
        missing = transcode.status(os.path.join(self.workspace, 'gone.wma'))
        self.assertEqual(missing['status'], 'failed')
        self.assertIn('不存在', missing['error'])

    def test_status_unavailable_when_no_ffmpeg(self):
        path = self._audio('a.wma')
        with mock.patch.object(transcode, 'ffmpeg_exe', return_value=''):
            data = transcode.status(path, start=True)
        self.assertFalse(data['available'])
        self.assertEqual(data['status'], 'unavailable')
        self.assertIn('FFmpeg', data['hint'])

    def test_status_idle_is_a_pure_query(self):
        path = self._audio('a.wma')
        with mock.patch.object(transcode, 'ffmpeg_exe', return_value='/bin/ffmpeg'):
            data = transcode.status(path)
        self.assertEqual(data['status'], 'idle')
        self.assertEqual(transcode._JOBS, {})

    def test_failed_worker_keeps_reason_and_cleans_part(self):
        class FakeProc:
            returncode = 1
            stdout = iter(('frame=1', 'Error while decoding', ''))

            def wait(self):
                return self.returncode

            def poll(self):
                return self.returncode

            def kill(self):
                pass

        path = self._audio('a.wma')
        key = transcode.cache_key(path)
        part = os.path.join(transcode.cache_dir(), key + '.part')
        with open(part, 'wb') as handle:
            handle.write(b'half')
        job = {'status': 'running', 'error': '', 'hint': '',
               'decoded': 0.0, 'size': 0, 'started_at': time.time()}
        with mock.patch.object(transcode.subprocess, 'Popen', return_value=FakeProc()):
            transcode._worker(path, key, '/bin/ffmpeg', job)
        self.assertEqual(job['status'], 'failed')
        self.assertIn('解码失败', job['error'])
        self.assertIn('Error while decoding', job['error'])
        self.assertFalse(os.path.exists(part))


@unittest.skipUnless(transcode.ffmpeg_exe(), 'FFmpeg 不可用（imageio-ffmpeg / PATH / tools 三处都没有）')
class TestRealTranscode(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='mh_transcode_real_')
        self.addCleanup(shutil.rmtree, self.root, True)
        self.workspace = os.path.join(self.root, 'workspace')
        os.makedirs(self.workspace)
        for name in _PATCHED_DIRS:
            if name == 'WORKSPACE_DIR':
                value = self.workspace
            elif name == 'LOG_DIR':
                value = os.path.join(self.root, 'log')
            else:
                value = os.path.join(self.root, 'unused', name)
            patcher = mock.patch.object(config, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        transcode.clear_jobs()
        self.addCleanup(transcode.clear_jobs)

    def _samples(self):
        exe = transcode.ffmpeg_exe()
        wma = os.path.join(self.workspace, 'tone.wma')
        proc = subprocess.run(
            [exe, '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
             '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1:sample_rate=44100',
             '-c:a', 'wmav2', '-b:a', '128k', '-f', 'asf', wma],
            capture_output=True, text=True)
        if proc.returncode != 0 or not os.path.isfile(wma):
            self.skipTest('本机 FFmpeg 无法生成 WMA 样本：' + proc.stderr.strip()[:120])
        dsf = os.path.join(self.workspace, 'tone.dsf')
        _make_dsf(dsf)
        return wma, dsf

    def _wait(self, path):
        deadline = time.time() + 90
        data = transcode.status(path)
        while time.time() < deadline:
            data = transcode.status(path)
            if data['status'] in ('done', 'failed'):
                return data
            time.sleep(0.1)
        return data

    def test_wma_and_dsf_decode_to_mp3_without_touching_source(self):
        for path in self._samples():
            with self.subTest(sample=os.path.basename(path)):
                with open(path, 'rb') as handle:
                    before = handle.read()
                started = transcode.status(path, start=True)
                self.assertIn(started['status'], ('running', 'done'))
                result = self._wait(path)
                self.assertEqual(result['status'], 'done', result['error'])
                # 1 秒样本：防 out_time_ms 被按毫秒换算成 1000 倍的显示错误
                self.assertGreater(result['decoded'], 0.5)
                self.assertLess(result['decoded'], 10)
                cached = transcode.ready_path(path)
                self.assertTrue(cached and os.path.getsize(cached) > 0)
                with open(cached, 'rb') as handle:
                    head = handle.read(3)
                self.assertTrue(head == b'ID3' or head[0] == 0xFF, head)
                with open(path, 'rb') as handle:
                    self.assertEqual(handle.read(), before)

    def test_decoded_stream_is_range_readable(self):
        path = self._samples()[0]
        transcode.status(path, start=True)
        result = self._wait(path)
        self.assertEqual(result['status'], 'done', result['error'])
        cached = transcode.ready_path(path)
        size = os.path.getsize(cached)
        start, end, partial = media.parse_range('bytes=10-19', size)
        self.assertTrue(partial)
        with open(cached, 'rb') as handle:
            expected = handle.read()[10:20]
        self.assertEqual(b''.join(media.iter_chunks(cached, start, end)), expected)


if __name__ == '__main__':
    unittest.main()
