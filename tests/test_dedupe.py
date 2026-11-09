# -*- coding: utf-8 -*-
"""单元测试 - 重复判定与年份归档"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from core.dedupe import (
    find_by_filename,
    find_by_tag,
    find_duplicates,
    fingerprint_candidates,
    fingerprint_similarity,
    match_against,
    pick_keep,
    strip_suffix,
    version_markers_conflict,
)
from core.model import Track
from core.ops import Plan
from core.organize import decade_label, missing_fields, plan_organize, target_path


def track(path, duration=200.0, size=1000, **tags):
    return Track(path=path, tags=dict(tags), duration=duration, size=size)


class TestDedupe(unittest.TestCase):
    def test_strip_suffix(self):
        self.assertEqual(strip_suffix('晴天 (1)'), '晴天')
        self.assertEqual(strip_suffix('晴天（2）'), '晴天')
        self.assertEqual(strip_suffix('晴天'), '晴天')

    def test_strip_underscore_suffix(self):
        """copy_items / Plan 重名时加的是 _1，必须和 (1) 一样能被识别"""
        self.assertEqual(strip_suffix('晴天_1'), '晴天')
        self.assertEqual(strip_suffix('晴天_12'), '晴天')
        self.assertEqual(strip_suffix('Track_1 (Live)'), 'Track_1 (Live)')

    def test_same_tag_and_duration_is_duplicate(self):
        a = track('a.flac', 200, 5000, title='晴天', artist='周杰伦')
        b = track('b.flac', 201, 4000, title='晴天', artist='周杰伦')
        groups = find_by_tag([a, b])
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].keep, b)          # 同格式同音质留更小文件
        self.assertEqual(len(groups[0].drop), 1)

    def test_duration_out_of_tolerance_not_duplicate(self):
        a = track('a.flac', 200, 5000, title='晴天', artist='周杰伦')
        b = track('b.flac', 260, 5000, title='晴天', artist='周杰伦')
        self.assertEqual(find_by_tag([a, b]), [])

    def test_different_artist_not_duplicate(self):
        a = track('a.flac', 200, 5000, title='晴天', artist='周杰伦')
        b = track('b.flac', 200, 5000, title='晴天', artist='罗大佑')
        self.assertEqual(find_by_tag([a, b]), [])

    def test_live_and_studio_not_duplicate(self):
        studio = track('a.flac', 200, 5000, title='晴天', artist='周杰伦')
        live = track('b.flac', 200, 5000, title='晴天 (Live)', artist='周杰伦')
        self.assertEqual(find_by_tag([studio, live]), [])

    def test_same_version_markers_are_duplicate(self):
        a = track('a.flac', 200, 5000, title='晴天 (Live)', artist='周杰伦')
        b = track('b.flac', 201, 4000, title='晴天（现场版）', artist='周杰伦')
        groups = find_by_tag([a, b])
        self.assertEqual(len(groups), 1)

    def test_download_suffix_still_duplicate(self):
        a = track('a.flac', 200, 5000, title='晴天', artist='周杰伦')
        b = track('b.flac', 200, 5000, title='晴天 (1)', artist='周杰伦')
        groups = find_by_tag([a, b])
        self.assertEqual(len(groups), 1)

    def test_pick_keep_prefers_lossless(self):
        mp3 = track('a.mp3', 200, 9000, title='x', artist='y')
        flac = track('b.flac', 200, 5000, title='x', artist='y')
        self.assertEqual(pick_keep([mp3, flac]), flac)

    def test_pick_keep_prefers_smaller_within_same_format(self):
        """格式相同时，同音质下保留更省磁盘的那份"""
        bigger = track('a.flac', 200, 9000, title='x', artist='y')
        smaller = track('b.flac', 200, 5000, title='x', artist='y')
        self.assertEqual(pick_keep([bigger, smaller]), smaller)

    def test_filename_suffix_group(self):
        a = track('晴天.flac', 200, 5000)
        b = track('晴天 (1).flac', 200, 5000)
        groups = find_by_filename([a, b])
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].kind, '文件名')

    def test_filename_dimension_ignores_case_and_spaces(self):
        a = track('C:/lib/a/Artist - Song.flac', 200, 5000)
        b = track('C:/lib/b/artist - song.flac', 200, 5000)
        self.assertEqual(len(find_by_filename([a, b])), 1)

    def test_underscore_suffix_group(self):
        a = track('C:/lib/a/A - B.flac', 200, 5000)
        b = track('C:/lib/a/A - B_1.flac', 200, 5000)
        self.assertEqual(len(find_by_filename([a, b])), 1)

    def test_unnamed_file_only_compared_in_same_dir(self):
        """`Intro.flac` 没有歌手信息，跨目录同名多半是不同曲目，不应判重"""
        a = track('C:/lib/1980/x/Intro.flac', 200, 5000)
        b = track('C:/lib/1990/y/Intro.flac', 200, 5000)
        self.assertEqual(find_by_filename([a, b]), [])

        same_dir = [
            track('C:/lib/x/Intro.flac', 200, 5000),
            track('C:/lib/x/Intro (1).flac', 200, 5000),
        ]
        self.assertEqual(len(find_by_filename(same_dir)), 1)

    def test_canonical_file_compared_across_dirs(self):
        a = track('C:/lib/1980/x/Artist - Song.flac', 200, 5000)
        b = track('C:/lib/1990/y/Artist - Song.flac', 200, 5000)
        self.assertEqual(len(find_by_filename([a, b])), 1)

    def test_find_duplicates_keeps_unclaimed_remainder(self):
        """标签维度认领了一个文件，文件名维度剩下的两个仍应成组，不能整组丢掉"""
        tagged = track('C:/a/S - T.flac', 200, 5000, title='T', artist='S')
        loose_mp3 = track('C:/a/S - T.mp3', 200, 3000)
        loose_ogg = track('C:/a/S - T.ogg', 200, 2000)
        other = track('C:/d/S - T.flac', 200, 5000, title='T', artist='S')

        groups = find_duplicates([tagged, loose_mp3, loose_ogg, other])
        self.assertEqual(len(groups), 2)
        kinds = sorted(group.kind for group in groups)
        self.assertEqual(kinds, ['文件名', '标签'])
        filename_group = next(g for g in groups if g.kind == '文件名')
        self.assertEqual(len(filename_group.drop), 1)
        self.assertEqual(filename_group.keep.ext, '.ogg')

    def test_find_duplicates_merges_strategies(self):
        a = track('晴天.flac', 200, 5000, title='晴天', artist='周杰伦')
        b = track('晴天 (1).flac', 200, 5000, title='晴天', artist='周杰伦')
        groups = find_duplicates([a, b])
        self.assertEqual(len(groups), 1)             # 不应重复计两次
        self.assertEqual(len(groups[0].drop), 1)

    def test_duration_unknown_flagged(self):
        a = track('a.flac', 0, 5000, title='晴天', artist='周杰伦')
        b = track('b.flac', 0, 5000, title='晴天', artist='周杰伦')
        groups = find_by_tag([a, b])
        self.assertTrue(groups[0].duration_unknown)


class TestOrganize(unittest.TestCase):
    def test_decade_label(self):
        self.assertEqual(decade_label(1965), '1950-1979')
        self.assertEqual(decade_label(1979), '1950-1979')
        self.assertEqual(decade_label(1980), '1980-1989')
        self.assertEqual(decade_label(2024), '2020-2029')

    def test_target_path(self):
        item = track('x.flac', 200, 100, title='晴天', artist='周杰伦', year='2003')
        expected = os.path.join('base', '2000-2009', '2003', 'x.flac')
        self.assertEqual(target_path(item, 'base'), expected)

    def test_target_path_none_without_year(self):
        item = track('x.flac', 200, 100, title='晴天', artist='周杰伦')
        self.assertIsNone(target_path(item, 'base'))

    def test_missing_fields(self):
        item = track('x.flac', 0, 0, title='晴天')
        self.assertIn('歌手', missing_fields(item))
        self.assertIn('年份', missing_fields(item))

    def test_plan_organize(self):
        good = track('g.flac', 200, 100, title='晴天', artist='周杰伦', year='2003')
        bad = track('b.flac', 200, 100, title='未知')
        plan = Plan('test', dry_run=True)
        organized, unknown = plan_organize([good, bad], 'base', plan)
        self.assertEqual([t.path for t in organized], ['g.flac'])
        self.assertEqual([t.path for t in unknown], ['b.flac'])
        self.assertEqual(len(plan), 2)                # 一个归档 + 一个 unknown


class TestMatchAgainst(unittest.TestCase):
    """工作区 vs 库目录的跨集合比对（第 6 步查重）

    库那边的 Track 通常只有 size 与从文件名解析出的 artist/title，
    duration 为 0——所以判定不能只依赖时长。
    """

    def _ws(self, name='a.flac', duration=200.0, size=5000, **tags):
        return track('G:/ws/' + name, duration, size, **tags)

    def _lib(self, name='a.flac', duration=0.0, size=5000, **tags):
        return track('D:/lib/2020-2029/2020/' + name, duration, size, **tags)

    def test_new_file_is_unique(self):
        result = match_against([self._ws(title='新歌', artist='A')],
                               [self._lib(title='老歌', artist='B')])
        self.assertEqual(result[0].status, 'unique')
        self.assertEqual(result[0].matched, [])

    def test_same_tag_and_size_is_duplicate(self):
        result = match_against([self._ws(title='晴天', artist='周杰伦')],
                               [self._lib(title='晴天', artist='周杰伦')])
        self.assertEqual(result[0].status, 'duplicate')
        self.assertEqual(result[0].kind, '歌手+歌名')
        self.assertEqual(len(result[0].matched), 1)

    def test_same_tag_size_diff_without_duration_is_unknown(self):
        """库里那份没读时长时，大小不同只能交给人工，不能自动搬走"""
        result = match_against([self._ws(title='晴天', artist='周杰伦', size=5000)],
                               [self._lib('a.mp3', title='晴天', artist='周杰伦', size=4000)])
        self.assertEqual(result[0].status, 'unknown')

    def test_same_tag_duration_close_is_duplicate(self):
        """同格式不同码率转码、大小不同，但时长能对上，也应判重复"""
        result = match_against([self._ws(title='晴天', artist='周杰伦', size=5000)],
                               [self._lib('a.flac', duration=201, size=4000,
                                          title='晴天', artist='周杰伦')])
        self.assertEqual(result[0].status, 'duplicate')

    def test_lossless_replaces_lossy_in_library(self):
        """工作区无损、库里是有损：库里那份该让位，这份才是要入库的"""
        result = match_against([self._ws(title='晴天', artist='周杰伦', size=30000)],
                               [self._lib('a.mp3', duration=200, size=4000,
                                          title='晴天', artist='周杰伦')])
        self.assertEqual(result[0].status, 'upgrade')
        self.assertEqual(result[0].comparisons[0]['relation'], 'better')

    def test_lossy_does_not_replace_lossless(self):
        """工作区是有损、库里是无损：新文件才是多余的，库不能动"""
        result = match_against([self._ws('a.mp3', title='晴天', artist='周杰伦', size=4000)],
                               [self._lib('a.flac', duration=200, size=30000,
                                          title='晴天', artist='周杰伦')])
        self.assertEqual(result[0].status, 'duplicate')
        self.assertEqual(result[0].comparisons[0]['relation'], 'worse')

    def test_upgrade_probe_reads_spec(self):
        """同为无损时比采样率/位深：probe 补上规格才能判出谁更好"""
        def probe(track_obj):
            if track_obj.path.startswith('D:/lib'):
                return {'duration': 200.0, 'sample_rate': 44100, 'bit_depth': 16}
            return {'duration': 200.0, 'sample_rate': 96000, 'bit_depth': 24}

        result = match_against([self._ws(title='晴天', artist='周杰伦', size=30000)],
                               [self._lib('a.flac', title='晴天', artist='周杰伦', size=20000)],
                               probe=probe)
        self.assertEqual(result[0].status, 'upgrade')

    def test_same_spec_is_duplicate_not_upgrade(self):
        """同为 44.1kHz/16bit 的 FLAC，音质相同，没有替换理由"""
        def probe(_track):
            return {'duration': 200.0, 'sample_rate': 44100, 'bit_depth': 16}

        result = match_against([self._ws(title='晴天', artist='周杰伦', size=30000)],
                               [self._lib('a.flac', title='晴天', artist='周杰伦', size=25000)],
                               probe=probe)
        self.assertEqual(result[0].status, 'duplicate')

    def test_unreadable_spec_of_other_format_is_unknown(self):
        """格式不同又读不到规格（连无损/有损都判不了）时不能自动替换"""
        result = match_against([self._ws(title='晴天', artist='周杰伦', size=30000)],
                               [self._lib('a.dff', duration=200, size=4000,
                                          title='晴天', artist='周杰伦')])
        self.assertEqual(result[0].status, 'unknown')

    def test_filename_dimension_when_tags_are_empty(self):
        result = match_against([self._ws('周杰伦 - 晴天.flac')],
                               [self._lib('周杰伦 - 晴天.flac')])
        self.assertEqual(result[0].status, 'duplicate')
        self.assertEqual(result[0].kind, '文件名')

    def test_plain_filename_is_not_matched_across_directories(self):
        """`Intro.flac` 这类没有歌手结构的名字跨目录同名，多半是不同曲目"""
        result = match_against([self._ws('Intro.flac')], [self._lib('Intro.flac')])
        self.assertEqual(result[0].status, 'unique')

    def test_live_version_is_not_duplicate(self):
        result = match_against(
            [self._ws('周杰伦 - 晴天 (Live).flac', title='晴天 (Live)', artist='周杰伦')],
            [self._lib('周杰伦 - 晴天.flac', title='晴天', artist='周杰伦')])
        self.assertEqual(result[0].status, 'unique')

    def test_flac_replaces_wav_at_same_spec(self):
        """同规格的 WAV 与 FLAC 音质一样，但 FLAC 更省磁盘，仍值得替换"""
        def probe(_track):
            return {'duration': 200.0, 'sample_rate': 44100, 'bit_depth': 16}

        result = match_against([self._ws('a.flac', title='晴天', artist='周杰伦', size=20000)],
                               [self._lib('a.wav', title='晴天', artist='周杰伦', size=40000)],
                               probe=probe)
        self.assertEqual(result[0].status, 'upgrade')
        self.assertEqual(result[0].basis, 'format')
        self.assertIn('更占地方', result[0].reason)

    def test_wav_does_not_replace_flac_at_same_spec(self):
        """反过来：库里已经是 FLAC，工作区的 WAV 才是更占地方的那份"""
        def probe(_track):
            return {'duration': 200.0, 'sample_rate': 44100, 'bit_depth': 16}

        result = match_against([self._ws('a.wav', title='晴天', artist='周杰伦', size=40000)],
                               [self._lib('a.flac', title='晴天', artist='周杰伦', size=20000)],
                               probe=probe)
        self.assertEqual(result[0].status, 'duplicate')
        self.assertEqual(result[0].basis, '')

    def test_quality_upgrade_keeps_quality_basis(self):
        def probe(track_obj):
            if track_obj.path.startswith('D:/lib'):
                return {'duration': 200.0, 'sample_rate': 44100, 'bit_depth': 16}
            return {'duration': 200.0, 'sample_rate': 96000, 'bit_depth': 24}

        result = match_against([self._ws(title='晴天', artist='周杰伦', size=30000)],
                               [self._lib('a.flac', title='晴天', artist='周杰伦', size=20000)],
                               probe=probe)
        self.assertEqual(result[0].status, 'upgrade')
        self.assertEqual(result[0].basis, 'quality')

    def test_one_target_matches_several_library_files(self):
        """库里同一首有多份（不同目录 / 不同版本）时全部列出，供逐条确认"""
        pool = [self._lib('a.flac', title='晴天', artist='周杰伦'),
                track('D:/lib/1990-1999/1990/b.flac', 0.0, 5000,
                      title='晴天', artist='周杰伦')]
        result = match_against([self._ws(title='晴天', artist='周杰伦')], pool)
        self.assertEqual(result[0].status, 'duplicate')
        self.assertEqual(len(result[0].matched), 2)
        self.assertEqual(len(result[0].comparisons), 2)

    def test_result_order_follows_targets(self):
        targets = [self._ws('a.flac', title='A', artist='X'),
                   self._ws('b.flac', title='B', artist='Y')]
        result = match_against(targets, [])
        self.assertEqual([item.track.path for item in result],
                         [t.path for t in targets])


class TestFingerprintSignals(unittest.TestCase):
    """声纹是第三条查重信号：不同文件名、不同标签的同一录音也必须命中"""

    def setUp(self):
        patcher = mock.patch.multiple(config, FP_LOOKUP_THRESHOLD=0.25,
                                      FP_MATCH_THRESHOLD=0.95)
        patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def _fp(count=120):
        return tuple((1 + index * 7919) & 0xFFFFFFFF for index in range(count))

    @staticmethod
    def _probe(_track):
        return {'duration': 200.0, 'bitrate': 900,
                'sample_rate': 44100, 'bit_depth': 16}

    def test_identical_fingerprint_scores_one(self):
        fp = self._fp()
        self.assertAlmostEqual(fingerprint_similarity(fp, fp), 1.0)

    def test_unrelated_fingerprint_scores_low(self):
        self.assertLess(fingerprint_similarity((0,) * 120, (0xFFFFFFFF,) * 120), 0.1)

    def test_offset_alignment(self):
        fp = self._fp()
        self.assertGreater(fingerprint_similarity(fp[3:], fp), 0.5)

    def test_candidates_find_pool_entry(self):
        fp = self._fp()
        other = track('D:/lib/a.flac')
        hits = fingerprint_candidates(fp, [(other, fp)])
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0][0].path, other.path)
        self.assertAlmostEqual(hits[0][1], 1.0)

    def test_different_name_and_tags_is_duplicate(self):
        fp = self._fp()
        library = track('D:/lib/1990-1999/1990/别的歌手 - 完全不同的名字.flac',
                        200, 5000, title='完全不同的名字', artist='别的歌手')
        workspace = track('D:/ws/周杰伦 - 晴天.flac', 200, 5000,
                          title='晴天', artist='周杰伦')
        workspace.fingerprint = fp
        result = match_against([workspace], [library], probe=self._probe,
                               fp_pool=[(library, fp)])
        self.assertEqual(result[0].kind, '声纹')
        self.assertEqual(result[0].status, 'duplicate')
        self.assertEqual(result[0].matched[0].path, library.path)

    def test_version_marker_conflict_goes_unknown(self):
        fp = self._fp()
        library = track('D:/lib/1990-1999/1990/周杰伦 - 晴天 (Live).flac',
                        200, 5000, title='晴天 (Live)', artist='周杰伦')
        workspace = track('D:/ws/周杰伦 - 晴天 (Remix).flac', 200, 5000,
                          title='晴天 (Remix)', artist='周杰伦')
        workspace.fingerprint = fp
        result = match_against([workspace], [library], probe=self._probe,
                               fp_pool=[(library, fp)])
        self.assertTrue(version_markers_conflict(workspace, library))
        self.assertEqual(result[0].status, 'unknown')


if __name__ == '__main__':
    unittest.main()
