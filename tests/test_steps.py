# -*- coding: utf-8 -*-
"""services.steps 的单元测试：八步向导的预览数据（不碰真实音乐库）

这些用例只覆盖「把哪些文件算进来、分到哪一组」，真实拷贝/解密/归档的副作用
由 test_ops / test_decrypt 覆盖，这里一律用 tempfile 造目录。
"""

import os
import shutil
import tempfile
import unittest
from unittest import mock

import config
import core.scan as scanner
from core.model import Track
from services import steps


class StepsTestCase(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='mh_steps_')
        self.addCleanup(shutil.rmtree, self.root, True)
        self.workspace = self._mkdir('workspace')
        self.library = self._mkdir('library')
        self._patch('WORKSPACE_DIR', self.workspace)
        self._patch('LIBRARY_DIR', self.library)
        self._patch('INCOMPLETE_DIR', self._mkdir('unready'))

    def _mkdir(self, *parts):
        path = os.path.join(self.root, *parts)
        os.makedirs(path, exist_ok=True)
        return path

    def _touch(self, *parts, content='x'):
        path = os.path.join(self.root, *parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(content)
        return path

    def _patch(self, name, value):
        patcher = mock.patch.object(config, name, value)
        patcher.start()
        self.addCleanup(patcher.stop)


class TestCopyCandidates(StepsTestCase):

    def setUp(self):
        super().setUp()
        self.netease = self._mkdir('netease')
        self.qq = self._mkdir('qq')
        self._patch('NETEASE_DIR', self.netease)
        self._patch('NETEASE_VIP_DIR', os.path.join(self.netease, 'VipSOngsDownload'))
        self._patch('QQ_DIR', self.qq)
        self._patch('QQ_VIP_DIR', os.path.join(self.qq, 'VipSOngsDownload'))
        self._touch('netease', 'a.mp3')
        self._touch('netease', 'sub', 'b.flac')
        self._touch('netease', 'VipSOngsDownload', 'secret.ncm')
        self._touch('qq', 'c.ogg')
        self._touch('qq', 'VipSOngsDownload', 'vip.mflac')

    def test_excludes_vip_subdirectory(self):
        data = steps.copy_candidates()
        names = [item['name'] for group in data['groups'] for item in group['files']]
        self.assertEqual(sorted(names), ['a.mp3', 'b.flac', 'c.ogg'])
        self.assertEqual(data['total'], 3)

    def test_targets_workspace(self):
        data = steps.copy_candidates()
        for group in data['groups']:
            for item in group['files']:
                self.assertEqual(item['target'], os.path.join(self.workspace, item['name']))

    def test_grouped_by_source_directory(self):
        data = steps.copy_candidates()
        roots = {group['root'] for group in data['groups'] if group['files']}
        self.assertIn(self.netease, roots)
        self.assertIn(os.path.join(self.netease, 'sub'), roots)
        self.assertIn(self.qq, roots)

    def test_missing_source_reported(self):
        self._patch('QQ_DIR', os.path.join(self.root, 'nope'))
        data = steps.copy_candidates()
        missing = [group for group in data['groups'] if group.get('missing')]
        self.assertEqual(len(missing), 1)

    def test_pairs_match_candidates(self):
        pairs = steps.copy_pairs()
        self.assertEqual(len(pairs), steps.copy_candidates()['total'])
        self.assertTrue(all(os.path.isabs(src) and os.path.isabs(dst) for src, dst in pairs))

    def test_marked_existing_when_workspace_has_same_name(self):
        self._touch('workspace', 'a.mp3')
        data = steps.copy_candidates()
        flags = {item['name']: item['existing']
                 for group in data['groups'] for item in group['files']}
        self.assertTrue(flags['a.mp3'])
        self.assertFalse(flags['c.ogg'])


class TestDecryptCandidates(StepsTestCase):

    def setUp(self):
        super().setUp()
        self.n_vip = self._mkdir('netease', 'VipSOngsDownload')
        self.q_vip = self._mkdir('qq', 'VipSOngsDownload')
        self._patch('NETEASE_VIP_DIR', self.n_vip)
        self._patch('QQ_VIP_DIR', self.q_vip)
        self._touch('netease', 'VipSOngsDownload', 'x.ncm')
        self._touch('qq', 'VipSOngsDownload', 'y.mflac')
        self._touch('qq', 'VipSOngsDownload', 'z.mgg')

    def test_groups_both_sources(self):
        data = steps.decrypt_candidates()
        labels = [group['label'] for group in data['groups']]
        self.assertEqual(labels, ['网易云', 'QQ音乐'])
        self.assertEqual(data['total'], 3)

    def test_expected_names(self):
        data = steps.decrypt_candidates()
        expects = {item['name']: item['expect']
                   for group in data['groups'] for item in group['files']}
        self.assertEqual(expects['y.mflac'], 'y.flac')
        self.assertEqual(expects['z.mgg'], 'z.ogg')
        self.assertIn('扩展名由内容决定', expects['x.ncm'])

    def test_existing_output_detected(self):
        self._touch('workspace', 'y.flac')
        data = steps.decrypt_candidates()
        flags = {item['name']: item['existing']
                 for group in data['groups'] for item in group['files']}
        self.assertTrue(flags['y.mflac'])

    def test_missing_vip_dir_is_not_fatal(self):
        self._patch('QQ_VIP_DIR', os.path.join(self.root, 'nope'))
        data = steps.decrypt_candidates()
        self.assertEqual(data['total'], 1)
        self.assertTrue(any(group['missing'] for group in data['groups']))


class TestArchivePreview(StepsTestCase):

    def _tracks(self):
        return [
            Track(path=os.path.join(self.workspace, 'a.flac'),
                  tags={'title': 'A', 'artist': 'X', 'album': 'Al', 'year': '1995'}),
            Track(path=os.path.join(self.workspace, 'b.flac'),
                  tags={'title': 'B', 'artist': 'Y', 'album': 'Al', 'year': '1995'}),
            Track(path=os.path.join(self.workspace, 'c.flac'),
                  tags={'title': 'C', 'artist': 'Z', 'album': 'Al', 'year': '2003'}),
            Track(path=os.path.join(self.workspace, 'd.flac'),
                  tags={'title': 'D', 'artist': 'W', 'album': 'Al'}),
        ]

    def test_groups_by_decade_and_year(self):
        with mock.patch.object(scanner, 'scan', return_value=self._tracks()):
            data = steps.archive_preview(into_library=True)
        self.assertEqual(data['total'], 3)
        self.assertEqual(len(data['groups']), 2)
        self.assertEqual(data['groups'][0]['decade'], '1990-1999')
        self.assertEqual(data['groups'][0]['count'], 2)
        self.assertEqual(data['groups'][1]['year'], '2003')

    def test_incomplete_listed_separately(self):
        with mock.patch.object(scanner, 'scan', return_value=self._tracks()):
            data = steps.archive_preview()
        self.assertEqual(len(data['incomplete']), 1)
        self.assertIn('缺少年份', data['incomplete'][0]['problems'])

    def test_target_switches_between_library_and_workspace(self):
        with mock.patch.object(scanner, 'scan', return_value=self._tracks()):
            into = steps.archive_preview(into_library=True)
            local = steps.archive_preview(into_library=False)
        self.assertEqual(into['base_dir'], self.library)
        self.assertEqual(local['base_dir'], self.workspace)
        self.assertEqual(into['groups'][0]['dir'],
                         os.path.join(self.library, '1990-1999', '1995'))


class TestTagCandidates(StepsTestCase):

    def test_empty_workspace(self):
        data = steps.tag_candidates()
        self.assertEqual(data['total'], 0)
        self.assertEqual(data['ready'], 0)

    def test_reports_missing_lyrics(self):
        self._touch('workspace', 'a.flac')
        data = steps.tag_candidates()
        self.assertEqual(data['total'], 1)
        self.assertEqual(data['missing_lrc'], 1)
        self.assertFalse(data['items'][0]['has_lrc'])


class TestDirectories(StepsTestCase):

    def test_eight_entries_with_status(self):
        data = steps.directories()
        self.assertEqual(len(data['items']), 8)
        self.assertIn('fields', data)
        for item in data['items']:
            self.assertIn('exists', item)
            self.assertIn('source', item)


class TestDedupePreview(StepsTestCase):
    """第 6 步：工作区 vs 库目录

    库索引只 stat + 解析文件名，不读标签，所以这些用例用假音频（文本文件）
    也能覆盖判定链路。
    """

    def test_duplicate_by_filename_and_size(self):
        self._touch('workspace', '周杰伦 - 晴天.flac', content='abcd')
        self._touch('library', '2020-2029', '2020', '周杰伦 - 晴天.flac', content='abcd')
        data = steps.dedupe_preview(refresh=True)
        self.assertEqual(data['total'], 1)
        self.assertEqual(data['duplicate'], 1)
        self.assertEqual(data['items'][0]['status'], 'duplicate')
        self.assertEqual(data['items'][0]['matched'][0]['name'], '周杰伦 - 晴天.flac')

    def test_size_differs_without_duration_is_unknown(self):
        self._touch('workspace', '周杰伦 - 晴天.flac', content='abcd')
        self._touch('library', '2020-2029', '2020', '周杰伦 - 晴天.flac', content='abcdefgh')
        data = steps.dedupe_preview(refresh=True)
        self.assertEqual(data['unknown'], 1)
        self.assertEqual(data['duplicate'], 0)

    def test_new_file_is_unique(self):
        self._touch('workspace', '新歌 - 某某.flac', content='abcd')
        self._touch('library', '2020-2029', '2020', '老歌 - 别人.flac', content='abcd')
        data = steps.dedupe_preview(refresh=True)
        self.assertEqual(data['unique'], 1)
        self.assertEqual(data['duplicate'], 0)

    def test_empty_library_makes_everything_unique(self):
        self._touch('workspace', 'a.flac', content='x')
        data = steps.dedupe_preview(refresh=True)
        self.assertEqual(data['library_count'], 0)
        self.assertEqual(data['unique'], 1)

    def test_unready_file_is_not_ready_to_archive(self):
        """查重通过不等于可入库：文本文件读不出标签，仍不算 archive_ok"""
        self._touch('workspace', '周杰伦 - 晴天.flac', content='abcd')
        data = steps.dedupe_preview(refresh=True)
        self.assertEqual(data['items'][0]['status'], 'unique')
        self.assertFalse(data['items'][0]['ready'])
        self.assertEqual(data['ready_to_archive'], 0)


class TestWorkspaceCheck(StepsTestCase):
    """第 7 步：工作区自检（只读）"""

    def test_reports_consistency_details(self):
        self._touch('workspace', '周杰伦 - 晴天.flac')
        data = steps.workspace_check()
        self.assertEqual(data['total'], 1)
        item = data['items'][0]
        self.assertEqual(item['consistency']['file']['artist'], '周杰伦')
        self.assertEqual(item['consistency']['file']['title'], '晴天')
        # 文本文件读不出标签 -> 不可入库，但歌手维度是 skipped 而不是矛盾
        self.assertFalse(item['ready'])
        self.assertEqual(data['mismatch'], 0)
        self.assertEqual(item['consistency']['items'][0]['state'], 'skipped')

    def test_empty_workspace(self):
        data = steps.workspace_check()
        self.assertEqual(data['total'], 0)
        self.assertEqual(data['findings'], [])
        self.assertEqual(data['ready'], 0)
        self.assertEqual(data['counts'], {})

    def test_findings_are_serialized(self):
        self._touch('workspace', '晴天.flac')
        data = steps.workspace_check()
        kinds = {item['kind'] for item in data['findings']}
        self.assertIn('标签不完整', kinds)
        self.assertIn('文件名格式', kinds)
        for finding in data['findings']:
            self.assertEqual(finding['name'], os.path.basename(finding['path']))


class TestTrackAccess(StepsTestCase):
    """单曲编辑接口的越权防护"""

    def test_rejects_path_outside_workspace(self):
        outside = self._touch('library', 'a.flac')
        with self.assertRaises(ValueError):
            steps.track_detail(outside)

    def test_rejects_missing_file(self):
        with self.assertRaises(ValueError):
            steps.track_detail(os.path.join(self.workspace, 'nope.flac'))

    def test_rejects_non_audio(self):
        path = self._touch('workspace', 'note.txt')
        with self.assertRaises(ValueError):
            steps.track_detail(path)

    def test_detail_includes_lyric_and_consistency(self):
        self._touch('workspace', '周杰伦 - 晴天.flac')
        self._touch('workspace', '周杰伦 - 晴天.lrc', content='[00:01]晴天')
        data = steps.track_detail(os.path.join(self.workspace, '周杰伦 - 晴天.flac'))
        self.assertTrue(data['has_lrc'])
        self.assertIn('晴天', data['lyric'])
        self.assertEqual(data['consistency']['file']['artist'], '周杰伦')


if __name__ == '__main__':
    unittest.main()
