# -*- coding: utf-8 -*-
"""单元测试 - 标签读取（一次读取三件事）与封面探测"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import core.tags as tags
from core.model import Track


def _copy_fixture(suffix='.flac'):
    """复制只读 fixture 到临时目录，返回可写路径（测试结束后清理由调用方负责）"""
    dst = os.path.join(tempfile.mkdtemp(prefix='mh_tag_'), 'song' + suffix)
    shutil.copy(FIXTURE, dst)
    return dst


def _make_wav():
    """生成一个最小可用 wav 文件（仅用标准库），用于封面写盘测试

    wav 的封面走 ID3/APIC 通道，与 mp3/dsf 是同一份实现，足以覆盖该写盘路径。
    """
    import wave
    path = os.path.join(tempfile.mkdtemp(prefix='mh_wav_'), 'song.wav')
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b'\x00\x00' * 100)
    return path

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', '1.flac')


class FakeAudio:
    """只实现封面探测用到的那几个属性"""

    def __init__(self, data=None, tag_keys=None, cover_tags=None, pictures=None):
        self._data = data or {}
        self.tags = {key: object() for key in (tag_keys or [])}
        self.tags.update(cover_tags or {})
        self.pictures = pictures or []

    def get(self, key, default=None):
        return self._data.get(key, default)


class TestReadMeta(unittest.TestCase):
    def test_read_meta_matches_individual_readers(self):
        """一次读取的结果必须和分别调用三个函数一致"""
        tags_dict, duration, cover = tags.read_meta(FIXTURE)
        self.assertEqual(tags_dict, tags.read_tags(FIXTURE))
        self.assertEqual(duration, tags.duration(FIXTURE))
        self.assertEqual(cover, tags.has_cover(FIXTURE))

    def test_read_meta_reads_expected_fields(self):
        tags_dict, duration, _cover = tags.read_meta(FIXTURE)
        for key in ('title', 'artist', 'album', 'year'):
            self.assertTrue(tags_dict.get(key), key)
        self.assertGreater(duration, 0)

    def test_read_meta_on_missing_file_is_silent(self):
        self.assertEqual(tags.read_meta('no/such/file.flac'), ({}, 0.0, False))

    def test_read_meta_on_unknown_extension_is_silent(self):
        self.assertEqual(tags.read_meta('notes.txt'), ({}, 0.0, False))


class TestCoverDetection(unittest.TestCase):
    def test_id3_cover(self):
        self.assertTrue(tags._cover_id3(FakeAudio(tag_keys=['APIC:'])))
        self.assertFalse(tags._cover_id3(FakeAudio(tag_keys=['TIT2'])))
        self.assertFalse(tags._cover_id3(FakeAudio()))       # 完全没有标签

    def test_flac_cover(self):
        self.assertTrue(tags._cover_flac(FakeAudio(pictures=[object()])))
        self.assertFalse(tags._cover_flac(FakeAudio()))

    def test_vorbis_cover(self):
        """ogg / opus 的封面存在 Vorbis 注释里"""
        self.assertTrue(tags._cover_vorbis(FakeAudio({'metadata_block_picture': ['aGVsbG8=']})))
        self.assertFalse(tags._cover_vorbis(FakeAudio()))

    def test_ape_cover(self):
        self.assertTrue(tags._cover_ape(FakeAudio(tag_keys=['Cover Art (Front)'])))
        self.assertFalse(tags._cover_ape(FakeAudio(tag_keys=['Title'])))

    def test_mp4_cover(self):
        self.assertTrue(tags._cover_mp4(FakeAudio(cover_tags={'covr': [object()]})))
        self.assertFalse(tags._cover_mp4(FakeAudio()))

    def test_asf_cover(self):
        self.assertTrue(tags._cover_asf(FakeAudio(cover_tags={'WM/Picture': object()})))
        self.assertFalse(tags._cover_asf(FakeAudio()))

    def test_has_cover_on_unknown_extension(self):
        self.assertFalse(tags.has_cover('x.txt'))


class TestFormatRegistry(unittest.TestCase):
    def test_every_audio_extension_has_a_reader(self):
        """能被扫描到的格式必须有读取器，否则整类文件会被判成「缺标签」"""
        for ext in config.AUDIO_EXTENSIONS:
            self.assertIn(ext, tags._READERS, f'{ext} 缺少读取器')
            self.assertIn(ext, tags._COVER_READERS, f'{ext} 缺少封面探测')

    def test_new_formats_registered(self):
        for ext in ('.opus', '.m4a', '.wma', '.dsf'):
            self.assertIn(ext, tags._READERS, ext)
            self.assertIn(ext, config.AUDIO_EXTENSIONS, ext)


class TestMissingTagFields(unittest.TestCase):
    def _track(self, **kwargs):
        base = {'title': 'T', 'artist': 'A', 'album': 'X', 'year': '2000'}
        base.update(kwargs.pop('tags', {}))
        return Track(path=kwargs.pop('path', 'no/such/file.flac'), tags=base, **kwargs)

    def test_cached_cover_true_suppresses_warning(self):
        self.assertNotIn('封面', tags.missing_tag_fields(self._track(has_cover=True)))

    def test_cached_cover_false_reports_warning(self):
        self.assertIn('封面', tags.missing_tag_fields(self._track(has_cover=False)))

    def test_unknown_cover_falls_back_to_probe(self):
        """缓存为 None 时才现场探测；文件不存在 -> 判为缺封面"""
        self.assertIn('封面', tags.missing_tag_fields(self._track(has_cover=None)))

    def test_missing_core_fields(self):
        track = Track(path='no/such/file.flac', tags={'title': 'T'}, has_cover=True)
        missing = tags.missing_tag_fields(track)
        for label in ('歌手', '专辑', '年份'):
            self.assertIn(label, missing)
        self.assertNotIn('封面', missing)


class TestNormalizeYear(unittest.TestCase):
    def test_full_date_extracts_four_digit_year(self):
        self.assertEqual(tags._normalize_year({'year': '2003-07-31'})['year'], '2003')

    def test_already_four_digit(self):
        self.assertEqual(tags._normalize_year({'year': '2003'})['year'], '2003')

    def test_no_digits_leaves_empty(self):
        self.assertEqual(tags._normalize_year({'year': 'unknown'})['year'], '')

    def test_missing_key_untouched(self):
        self.assertEqual(tags._normalize_year({}), {})

    def test_read_meta_normalizes_year(self):
        """read_meta 读出的 year 也应当是四位年，而非完整日期串"""
        import shutil
        import tempfile
        path = _copy_fixture()
        try:
            tags.write_tags(path, {'title': 'T', 'artist': 'A', 'album': 'X',
                                   'year': '2003-07-31', 'genre': 'Pop'})
            got, _, _ = tags.read_meta(path)
            self.assertEqual(got['year'], '2003')
        finally:
            shutil.rmtree(os.path.dirname(path), True)


class TestWriteTags(unittest.TestCase):
    def setUp(self):
        self.path = _copy_fixture()

    def tearDown(self):
        shutil.rmtree(os.path.dirname(self.path), True)

    def test_write_then_read_roundtrip(self):
        ok = tags.write_tags(self.path, {'title': 'A', 'artist': 'B', 'album': 'C',
                                         'year': '2022', 'genre': 'Rock'})
        self.assertTrue(ok)
        got = tags.read_tags(self.path)
        self.assertEqual(got['title'], 'A')
        self.assertEqual(got['artist'], 'B')
        self.assertEqual(got['album'], 'C')
        self.assertEqual(got['year'], '2022')
        self.assertEqual(got['genre'], 'Rock')

    def test_write_preserves_other_tags(self):
        """写盘只覆盖传入字段，不应清空其它既有标签"""
        from mutagen.flac import FLAC
        audio = FLAC(self.path)
        audio['custom'] = 'keep'
        audio.save()
        tags.write_tags(self.path, {'title': 'New'})
        self.assertEqual(FLAC(self.path)['custom'], ['keep'])

    def test_write_empty_is_noop(self):
        self.assertFalse(tags.write_tags(self.path, {}))

    def test_write_unknown_extension_fails(self):
        self.assertFalse(tags.write_tags('x.txt', {'title': 'X'}))


class TestWriteCover(unittest.TestCase):
    def setUp(self):
        self.path = _copy_fixture()

    def tearDown(self):
        shutil.rmtree(os.path.dirname(self.path), True)

    def test_flac_roundtrip(self):
        self.assertFalse(tags.has_cover(self.path))
        self.assertTrue(tags.write_cover(self.path, b'\x89PNG\r\n\x1a\n' + b'\x00' * 20))
        self.assertTrue(tags.has_cover(self.path))

    def test_wav_roundtrip(self):
        wav = _make_wav()
        try:
            self.assertFalse(tags.has_cover(wav))
            self.assertTrue(tags.write_cover(wav, b'\xff\xd8\xff' + b'\x00' * 20))
            self.assertTrue(tags.has_cover(wav))
        finally:
            shutil.rmtree(os.path.dirname(wav), True)

    def test_no_data_is_noop(self):
        self.assertFalse(tags.write_cover(self.path, b''))

    def test_guess_mime(self):
        self.assertEqual(tags._guess_mime(b'\x89PNG\r\n\x1a\n'), 'image/png')
        self.assertEqual(tags._guess_mime(b'\xff\xd8\xff'), 'image/jpeg')


class TestDownloadCover(unittest.TestCase):
    """download_cover 的下载/体积拦截逻辑（用 mock 替代真实网络）"""

    def _fake_response(self, status=200, content=b'img', content_length=None):
        resp = unittest.mock.MagicMock()
        resp.status_code = status
        resp.content = content
        resp.headers = {'Content-Length': str(content_length)} if content_length else {}
        resp.close = unittest.mock.MagicMock()
        return resp

    def test_oversized_declared_is_rejected(self):
        import tagger
        big = 10 * 1024 * 1024  # 超过 MAX_COVER_SIZE(5MiB)
        resp = self._fake_response(content=b'x' * 100, content_length=big)
        with unittest.mock.patch('requests.get', return_value=resp):
            self.assertIsNone(tagger.download_cover('http://example/cover.jpg'))

    def test_non_200_is_rejected(self):
        import tagger
        resp = self._fake_response(status=404, content=b'')
        with unittest.mock.patch('requests.get', return_value=resp):
            self.assertIsNone(tagger.download_cover('http://example/cover.jpg'))

    def test_ok_returns_bytes(self):
        import tagger
        resp = self._fake_response(content=b'imagedata')
        with unittest.mock.patch('requests.get', return_value=resp):
            self.assertEqual(tagger.download_cover('http://example/cover.jpg'), b'imagedata')

    def test_empty_body_rejected(self):
        import tagger
        resp = self._fake_response(content=b'')
        with unittest.mock.patch('requests.get', return_value=resp):
            self.assertIsNone(tagger.download_cover('http://example/cover.jpg'))


if __name__ == '__main__':
    unittest.main()
