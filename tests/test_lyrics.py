# -*- coding: utf-8 -*-
"""core.lyrics 的单元测试：缺失/孤立歌词、同名路径、编码探测、LRC 解析与 offset 改写"""

import os
import shutil
import tempfile
import unittest

from core import lyrics
from core.model import Track


class TestLyrics(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='mh_lrc_')
        self.addCleanup(shutil.rmtree, self.root, True)

    def _touch(self, *parts):
        path = os.path.join(self.root, *parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write('x')
        return path

    def test_missing_lrc(self):
        with_lrc = self._touch('a.flac')
        self._touch('a.lrc')
        without = self._touch('b.mp3')

        missing = lyrics.missing_lrc([Track(path=with_lrc), Track(path=without)])
        self.assertEqual([t.path for t in missing], [without])

    def test_orphan_lrc(self):
        self._touch('a.flac')
        self._touch('a.lrc')
        orphan = self._touch('b.lrc')

        self.assertEqual(lyrics.orphan_lrc([self.root]), [orphan])

    def test_orphan_accepts_string(self):
        orphan = self._touch('b.lrc')
        self.assertEqual(lyrics.orphan_lrc(self.root), [orphan])

    def test_all_extensions_count_as_audio(self):
        for ext in ('.flac', '.mp3', '.wav', '.ape', '.ogg'):
            self._touch(f'song{ext}')
            self._touch(f'song{ext}'.replace(ext, '.lrc'))
        self.assertEqual(lyrics.orphan_lrc([self.root]), [])

    def test_nested_directories(self):
        self._touch('sub', 'x.lrc')
        self.assertEqual(len(lyrics.orphan_lrc([self.root])), 1)

    def test_ignores_non_lrc(self):
        self._touch('readme.txt')
        self.assertEqual(lyrics.orphan_lrc([self.root]), [])

    def test_uppercase_lrc_recognized(self):
        """大写扩展名 .LRC 也应被识别，并与小写音频配对不算孤立"""
        self._touch('a.flac')
        self._touch('a.LRC')
        self.assertEqual(lyrics.orphan_lrc([self.root]), [])

    def test_case_insensitive_matching(self):
        """音频文件名大小写不同仍视为配对（优化后用集合判重，需保持语义）"""
        self._touch('Song.FLAC')
        self._touch('song.lrc')
        self.assertEqual(lyrics.orphan_lrc([self.root]), [])

    def test_orphan_with_different_extension_audio(self):
        """同名音频是另一种格式时，.lrc 不算孤立"""
        self._touch('a.mp3')
        self._touch('a.lrc')
        self.assertEqual(lyrics.orphan_lrc([self.root]), [])


class TestLrcPath(unittest.TestCase):
    """同名歌词路径：大小写不敏感，且与 orphan_lrc 的配对口径一致"""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='mh_lrcpath_')
        self.addCleanup(shutil.rmtree, self.root, True)
        lyrics.clear_lrc_cache()
        self.addCleanup(lyrics.clear_lrc_cache)

    def _write(self, name, data=b'x'):
        path = os.path.join(self.root, name)
        with open(path, 'wb') as handle:
            handle.write(data)
        return path

    def test_prefers_exact_lowercase(self):
        audio = self._write('a.flac')
        self._write('a.lrc')
        self.assertEqual(os.path.normcase(lyrics.lrc_path_for(audio)),
                         os.path.normcase(os.path.join(self.root, 'a.lrc')))

    def test_finds_uppercase_extension(self):
        audio = self._write('a.flac')
        self._write('a.LRC')
        path = lyrics.lrc_path_for(audio)
        self.assertTrue(os.path.isfile(path))
        # Windows 文件系统大小写不敏感，此时返回小写的 a.lrc 也能打开同一个文件；
        # macOS 上则必须由目录扫描找出真实的 a.LRC。normcase 让断言跨平台成立。
        self.assertEqual(os.path.normcase(path),
                         os.path.normcase(os.path.join(self.root, 'a.LRC')))

    def test_track_has_lrc_matches_orphan_logic(self):
        audio = self._write('a.flac')
        self._write('a.LRC')
        self.assertTrue(Track(path=audio).has_lrc)
        self.assertEqual(lyrics.orphan_lrc([self.root]), [])

    def test_missing_returns_lowercase_default_for_writing(self):
        audio = self._write('a.mp3')
        self.assertEqual(lyrics.lrc_path_for(audio),
                         os.path.join(self.root, 'a.lrc'))

    def test_cache_refreshes_after_new_lrc(self):
        audio = self._write('a.flac')
        self.assertFalse(os.path.isfile(lyrics.lrc_path_for(audio)))
        self._write('a.LRC')
        lyrics.clear_lrc_cache()
        path = lyrics.lrc_path_for(audio)
        self.assertTrue(os.path.isfile(path))
        self.assertEqual(os.path.normcase(path),
                         os.path.normcase(os.path.join(self.root, 'a.LRC')))


class TestReadLrcText(unittest.TestCase):
    """编码探测：BOM / utf-8 / gb18030 / 兜底"""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='mh_lrctext_')
        self.addCleanup(shutil.rmtree, self.root, True)

    def _write(self, data):
        path = os.path.join(self.root, 'a.lrc')
        with open(path, 'wb') as handle:
            handle.write(data)
        return path

    def test_utf8(self):
        text, enc = lyrics.read_lrc_text(self._write('[00:01]晴天'.encode('utf-8')))
        self.assertEqual(enc, 'utf-8')
        self.assertIn('晴天', text)

    def test_utf8_bom(self):
        text, enc = lyrics.read_lrc_text(self._write(b'\xef\xbb\xbf[00:01]\xe6\x99\xb4\xe5\xa4\xa9'))
        self.assertEqual(enc, 'utf-8-sig')
        self.assertIn('晴天', text)
        self.assertFalse(text.startswith('\ufeff'))

    def test_gbk_no_longer_mojibake(self):
        text, enc = lyrics.read_lrc_text(self._write('[00:01]周杰伦 晴天'.encode('gb18030')))
        self.assertEqual(enc, 'gb18030')
        self.assertIn('晴天', text)
        self.assertNotIn('\ufffd', text)

    def test_missing_file(self):
        self.assertEqual(lyrics.read_lrc_text(os.path.join(self.root, 'nope.lrc')), ('', ''))


class TestParseLrc(unittest.TestCase):
    """结构化解析：Web 试听与歌词同步的唯一口径"""

    def test_metadata_offset_and_multiple_timestamps(self):
        raw = ('[ti:晴天]\n[ar:周杰伦]\n[al:叶惠美]\n[by:mh]\n[offset:-500]\n'
               '[00:01.00][00:31.00]故事的小黄花\n[00:03.50]从出生那年就飘着\n')
        data = lyrics.parse_lrc(raw)
        self.assertEqual(data['meta'], {'ti': '晴天', 'ar': '周杰伦',
                                        'al': '叶惠美', 'by': 'mh'})
        self.assertEqual(data['offset'], -500)
        self.assertTrue(data['has_timing'])
        self.assertEqual([line['time'] for line in data['lines']], [1.0, 3.5, 31.0])
        self.assertEqual(data['lines'][2]['text'], '故事的小黄花')
        self.assertIn('故事的小黄花', data['plain'])

    def test_same_timestamp_second_line_is_translation(self):
        data = lyrics.parse_lrc('[00:01.00]晴天\n[00:01.00]Sunny day\n')
        self.assertEqual(len(data['lines']), 1)
        self.assertEqual(data['lines'][0]['text'], '晴天')
        self.assertEqual(data['lines'][0]['translation'], 'Sunny day')

    def test_translation_section_merges_by_time(self):
        raw = ('[00:01.00]晴天\n[00:02.00]刮风\n\n[翻译]\n'
               '[00:01.00]Sunny day\n[00:02.00]Windy day\n')
        data = lyrics.parse_lrc(raw)
        self.assertEqual(len(data['lines']), 2)
        self.assertEqual(data['lines'][0]['translation'], 'Sunny day')
        self.assertEqual(data['lines'][1]['translation'], 'Windy day')

    def test_out_of_order_sorted_and_deduplicated(self):
        raw = '[00:09.00]晚\n[00:01.00]早\n[00:01.00]早\n'
        data = lyrics.parse_lrc(raw)
        self.assertEqual([line['text'] for line in data['lines']], ['早', '晚'])

    def test_centisecond_and_millisecond_forms(self):
        data = lyrics.parse_lrc('[01:02.25]a\n[01:03:250]b\n')
        self.assertEqual([line['time'] for line in data['lines']], [62.25, 63.25])

    def test_plain_text_without_timestamps(self):
        data = lyrics.parse_lrc('没有时间轴的歌词\n第二行\n')
        self.assertFalse(data['has_timing'])
        self.assertEqual(data['lines'], [])
        self.assertEqual(data['plain'], '没有时间轴的歌词\n第二行')

    def test_empty_text(self):
        data = lyrics.parse_lrc('')
        self.assertFalse(data['has_timing'])
        self.assertEqual(data['lines'], [])
        self.assertEqual(data['plain'], '')


class TestWordTiming(unittest.TestCase):
    """P3 增强 LRC：行内逐字时间戳（<mm:ss.xx> 或正文里的 [mm:ss.xx]）"""

    def test_angle_brackets(self):
        raw = ('[ti:晴天]\n'
               '[00:12.00]<00:12.00>晴<00:12.40>天<00:12.80>的'
               '<00:13.20>小<00:13.60>黄<00:14.00>花\n')
        data = lyrics.parse_lrc(raw)
        self.assertTrue(data['word_timing'])
        self.assertEqual(len(data['lines']), 1)
        row = data['lines'][0]
        self.assertEqual(row['time'], 12.0)
        self.assertEqual(row['text'], '晴天的小黄花')
        self.assertEqual([seg['time'] for seg in row['syllables']],
                         [12.0, 12.4, 12.8, 13.2, 13.6, 14.0])
        self.assertEqual([seg['text'] for seg in row['syllables']],
                         list('晴天的小黄花'))
        # 前端只渲染片段，就不能丢字
        self.assertEqual(''.join(seg['text'] for seg in row['syllables']), row['text'])
        self.assertEqual(data['plain'], '晴天的小黄花')
        self.assertNotIn('<00:', data['plain'])

    def test_inline_square_brackets_in_body(self):
        """正文里的方括号时间戳是逐字标记，不能被当成行首时间戳吃掉正文"""
        data = lyrics.parse_lrc('[00:12.00]晴[00:12.40]天[00:12.80]好\n')
        row = data['lines'][0]
        self.assertEqual(len(data['lines']), 1)
        self.assertEqual(row['text'], '晴天好')
        self.assertEqual([seg['time'] for seg in row['syllables']],
                         [12.0, 12.4, 12.8])
        self.assertEqual(data['plain'], '晴天好')

    def test_chorus_shares_word_axis_with_offset(self):
        """[00:01.00][00:31.00] 复用同一段逐字时间轴时，第二行整体平移"""
        data = lyrics.parse_lrc('[00:01.00][00:31.00]<00:01.00>晴<00:01.50>天\n')
        self.assertEqual([row['time'] for row in data['lines']], [1.0, 31.0])
        self.assertEqual([seg['time'] for seg in data['lines'][0]['syllables']],
                         [1.0, 1.5])
        self.assertEqual([seg['time'] for seg in data['lines'][1]['syllables']],
                         [31.0, 31.5])
        self.assertEqual(data['plain'], '晴天')   # 叠句只记一次

    def test_trailing_marker_adds_no_empty_segment(self):
        data = lyrics.parse_lrc('[00:12.00]<00:12.00>晴<00:12.40>天<00:12.80>\n')
        row = data['lines'][0]
        self.assertEqual(row['text'], '晴天')
        self.assertEqual(len(row['syllables']), 2)

    def test_word_line_without_leading_timestamp(self):
        data = lyrics.parse_lrc('<00:05.00>只<00:05.50>有<00:06.00>逐字\n')
        self.assertTrue(data['word_timing'])
        self.assertEqual(data['lines'][0]['time'], 5.0)
        self.assertEqual(data['lines'][0]['text'], '只有逐字')

    def test_plain_lrc_has_no_syllables(self):
        data = lyrics.parse_lrc('[00:01.00]故事的小黄花\n[00:03.50]从出生那年就飘着\n')
        self.assertFalse(data['word_timing'])
        for row in data['lines']:
            self.assertEqual(row['syllables'], [])

    def test_single_segment_is_not_word_timing(self):
        data = lyrics.parse_lrc('[00:01.00]<00:01.00>一整句\n')
        self.assertFalse(data['word_timing'])
        self.assertEqual(data['lines'][0]['text'], '一整句')
        self.assertEqual(len(data['lines'][0]['syllables']), 1)

    def test_word_times_never_go_backwards(self):
        data = lyrics.parse_lrc('[00:12.00]<00:12.00>晴<00:11.50>天<00:12.80>好\n')
        moments = [seg['time'] for seg in data['lines'][0]['syllables']]
        self.assertEqual(moments, sorted(moments))
        self.assertTrue(data['word_timing'])

    def test_translation_section_keeps_plain_text(self):
        raw = ('[00:01.00]<00:01.00>晴<00:01.50>天\n\n[翻译]\n'
               '[00:01.00]<00:01.00>Sun<00:01.50>ny\n')
        data = lyrics.parse_lrc(raw)
        self.assertTrue(data['word_timing'])
        self.assertEqual(data['lines'][0]['text'], '晴天')
        self.assertEqual(data['lines'][0]['translation'], 'Sunny')

    def test_untimed_text_unchanged(self):
        data = lyrics.parse_lrc('没有时间轴的歌词\n第二行\n')
        self.assertFalse(data['word_timing'])
        self.assertEqual(data['plain'], '没有时间轴的歌词\n第二行')

    def test_offset_rewrite_keeps_word_tags(self):
        raw = '[00:12.00]<00:12.00>晴<00:12.40>天\n'
        shifted = lyrics.set_offset(raw, 500)
        self.assertIn('<00:12.40>天', shifted)
        data = lyrics.parse_lrc(shifted)
        self.assertEqual(data['offset'], 500)
        self.assertTrue(data['word_timing'])
        self.assertEqual(data['lines'][0]['text'], '晴天')


class TestSetOffset(unittest.TestCase):
    """P1 偏移微调：只做纯文本变换，不读写文件"""

    def test_replaces_existing_offset_in_place(self):
        raw = '[ti:晴天]\n[offset:-200]\n[00:01.00]故事的小黄花\n'
        result = lyrics.set_offset(raw, 500)
        self.assertEqual(result, '[ti:晴天]\n[offset:500]\n[00:01.00]故事的小黄花\n')
        self.assertEqual(lyrics.parse_lrc(result)['offset'], 500)

    def test_inserts_after_metadata_before_first_lyric(self):
        raw = '[ti:A]\n[ar:B]\n[00:01.00]x\n[00:02.00]y\n'
        self.assertEqual(lyrics.set_offset(raw, -500),
                         '[ti:A]\n[ar:B]\n[offset:-500]\n[00:01.00]x\n[00:02.00]y\n')

    def test_inserts_at_top_without_metadata(self):
        raw = '[00:01.00]x\n'
        self.assertEqual(lyrics.set_offset(raw, 0), '[offset:0]\n[00:01.00]x\n')

    def test_empty_text_and_idempotent(self):
        self.assertEqual(lyrics.set_offset('', 0), '[offset:0]\n')
        once = lyrics.set_offset('[00:01.00]x\n', 250)
        self.assertEqual(lyrics.set_offset(once, 250), once)

    def test_preserves_untimed_text(self):
        raw = '纯文本歌词\n第二行\n'
        result = lyrics.set_offset(raw, 100)
        self.assertIn('纯文本歌词', result)
        self.assertEqual(lyrics.parse_lrc(result)['plain'], '纯文本歌词\n第二行')


if __name__ == '__main__':
    unittest.main()
