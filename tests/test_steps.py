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
                  tags={'title': 'A', 'artist': 'X', 'album': 'Al', 'year': '1995'},
                  has_cover=True),
            Track(path=os.path.join(self.workspace, 'b.flac'),
                  tags={'title': 'B', 'artist': 'Y', 'album': 'Al', 'year': '1995'},
                  has_cover=True),
            Track(path=os.path.join(self.workspace, 'c.flac'),
                  tags={'title': 'C', 'artist': 'Z', 'album': 'Al', 'year': '2003'},
                  has_cover=True),
            Track(path=os.path.join(self.workspace, 'd.flac'),
                  tags={'title': 'D', 'artist': 'W', 'album': 'Al'},
                  has_cover=True),
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


class _DedupeRunBase(StepsTestCase):
    """查重执行类用例的公共准备：目录、日志、音频规格 mock

    用例里的「音频」都是文本文件，mutagen 读不出规格，所以 `read_quality`
    用 mock 顶替，按扩展名返回固定规格。
    """

    def setUp(self):
        super().setUp()
        self.duplicate_dir = self._mkdir('duplicates')
        self.trash_dir = self._mkdir('trash')
        self._patch('DUPLICATE_DIR', self.duplicate_dir)
        self._patch('TRASH_DIR', self.trash_dir)
        self._patch('JOURNAL_PATH', os.path.join(self.root, 'journal.jsonl'))
        steps.invalidate_library_cache()
        self.addCleanup(steps.invalidate_library_cache)

        patcher = mock.patch.object(steps.core_tags, 'read_quality',
                                    side_effect=self._quality)
        patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def _quality(path):
        size = os.path.getsize(path)
        ext = os.path.splitext(path)[1].lower()
        if ext == '.mp3':
            return {'ext': '.mp3', 'size': size, 'duration': 200.5,
                    'bitrate': 128000, 'sample_rate': 44100, 'bit_depth': 0}
        if ext == '.wav':
            return {'ext': '.wav', 'size': size, 'duration': 200.0,
                    'bitrate': 0, 'sample_rate': 44100, 'bit_depth': 16}
        return {'ext': ext, 'size': size, 'duration': 200.0,
                'bitrate': 0, 'sample_rate': 44100, 'bit_depth': 16}


class TestDedupeUpgrade(_DedupeRunBase):
    """库里音质更低时：移走的是库里那份，工作区这份留给归档"""

    def _prepare(self):
        self._touch('workspace', '周杰伦 - 晴天.flac', content='a' * 40)
        return self._touch('library', '2020-2029', '2020',
                           '周杰伦 - 晴天.mp3', content='b' * 10)

    def test_preview_marks_upgrade_and_lists_replacement(self):
        self._prepare()
        data = steps.dedupe_preview(refresh=True)
        self.assertEqual(data['upgrade'], 1)
        self.assertEqual(data['duplicate'], 0)
        self.assertEqual(data['replace_count'], 1)
        item = data['items'][0]
        self.assertEqual(item['status_label'], '库中音质更低')
        self.assertEqual([entry['name'] for entry in item['replace']],
                         ['周杰伦 - 晴天.mp3'])
        self.assertIn('无损', item['quality'])
        self.assertIn('有损', item['replace'][0]['quality'])

    def test_run_moves_library_copy_away(self):
        library_file = self._prepare()
        result = steps.run_dedupe(paths=[os.path.join(self.workspace, '周杰伦 - 晴天.flac')],
                                  action='move', refresh=True, statuses=['upgrade'])
        self.assertEqual(result['executed'], 1)
        self.assertEqual(result['library_replaced'], 1)
        self.assertFalse(os.path.exists(library_file), '库里旧版本应已移走')
        self.assertTrue(os.path.exists(
            os.path.join(self.workspace, '周杰伦 - 晴天.flac')), '工作区这份要留给归档')
        self.assertTrue(os.path.exists(
            os.path.join(self.duplicate_dir, '周杰伦 - 晴天.mp3')))

    def test_upgrade_ignores_trash_action(self):
        """动的是库里存量文件，即使选了回收站也只进重复目录"""
        library_file = self._prepare()
        result = steps.run_dedupe(paths=[os.path.join(self.workspace, '周杰伦 - 晴天.flac')],
                                  action='trash', refresh=True, statuses=['upgrade'])
        self.assertEqual(result['library_replaced'], 1)
        self.assertFalse(os.path.exists(library_file))
        self.assertTrue(os.path.exists(
            os.path.join(self.duplicate_dir, '周杰伦 - 晴天.mp3')))
        self.assertEqual(os.listdir(self.trash_dir), [])

    def test_default_status_leaves_library_alone(self):
        """默认只处理 duplicate：不显式要求时绝不动库里的文件"""
        library_file = self._prepare()
        result = steps.run_dedupe(action='move', refresh=True)
        self.assertEqual(result['planned'], 0)
        self.assertTrue(os.path.exists(library_file))

    def test_upgrade_without_paths_is_refused(self):
        """动库的操作不接受全量：必须逐条指定要替换哪些文件"""
        library_file = self._prepare()
        with self.assertRaises(ValueError):
            steps.run_dedupe(action='move', refresh=True, statuses=['upgrade'])
        self.assertTrue(os.path.exists(library_file))


class TestDedupeFormatAndSides(_DedupeRunBase):
    """同音质换格式省磁盘 + 一个工作区文件对上库里多份"""

    def test_wav_replaced_by_same_spec_flac(self):
        """WAV 与 FLAC 同规格时音质一样，但 FLAC 只有一半体积，值得替换"""
        self._touch('workspace', '周杰伦 - 晴天.flac', content='a' * 40)
        library_file = self._touch('library', '2020-2029', '2020',
                                  '周杰伦 - 晴天.wav', content='b' * 80)
        data = steps.dedupe_preview(refresh=True)
        self.assertEqual(data['upgrade'], 1)
        self.assertEqual(data['upgrade_format'], 1)
        self.assertEqual(data['upgrade_quality'], 0)
        item = data['items'][0]
        self.assertEqual(item['basis'], 'format')
        self.assertEqual(item['basis_label'], '同音质更省磁盘')

        result = steps.run_dedupe(paths=[os.path.join(self.workspace,
                                                      '周杰伦 - 晴天.flac')],
                                  action='trash', refresh=True, statuses=['upgrade'])
        self.assertEqual(result['library_replaced'], 1)
        self.assertFalse(os.path.exists(library_file))
        # 动的是库里的文件，即使网页上选「删除」也只进重复目录
        self.assertTrue(os.path.exists(
            os.path.join(self.duplicate_dir, '周杰伦 - 晴天.wav')))
        self.assertEqual(os.listdir(self.trash_dir), [])

    def _two_library_copies(self):
        self._touch('workspace', '周杰伦 - 晴天.flac', content='a' * 40)
        first = self._touch('library', '2020-2029', '2020',
                            '周杰伦 - 晴天.mp3', content='b' * 10)
        second = self._touch('library', '1990-1999', '1999',
                             '周杰伦 - 晴天.mp3', content='c' * 10)
        return first, second

    def test_preview_lists_every_library_copy(self):
        """同一首在库里有两份，两栏比对时要全部列出来，不能只显示第一条"""
        self._two_library_copies()
        data = steps.dedupe_preview(refresh=True)
        item = data['items'][0]
        self.assertEqual(item['status'], 'upgrade')
        self.assertEqual(len(item['matched']), 2)
        self.assertEqual(len(item['replace']), 2)
        self.assertEqual(item['matched_total'], 2)
        self.assertFalse(item['matched_truncated'])
        self.assertEqual(data['replace_count'], 2)

    def test_replaces_moves_only_selected_copy(self):
        """用户只勾了其中一份：另一份必须原样留在库里"""
        first, second = self._two_library_copies()
        workspace_file = os.path.join(self.workspace, '周杰伦 - 晴天.flac')
        result = steps.run_dedupe(paths=[workspace_file], action='move',
                                  refresh=True, statuses=['upgrade'],
                                  replaces={workspace_file: [first]})
        self.assertEqual(result['library_replaced'], 1)
        self.assertFalse(os.path.exists(first))
        self.assertTrue(os.path.exists(second))

    def test_replaces_rejects_path_outside_preview(self):
        """不在可替换清单里的路径必须拒绝，防止借接口删库里的任意文件"""
        self._two_library_copies()
        stray = self._touch('library', '2020-2029', '2020', '别的 - 歌.mp3',
                            content='z')
        workspace_file = os.path.join(self.workspace, '周杰伦 - 晴天.flac')
        with self.assertRaises(ValueError):
            steps.run_dedupe(paths=[workspace_file], action='move', refresh=True,
                             statuses=['upgrade'],
                             replaces={workspace_file: [stray]})
        self.assertTrue(os.path.exists(stray))

    def test_replaces_with_empty_selection_does_nothing(self):
        """全部取消勾选等于不处理：库里和工作区都保持原样"""
        first, second = self._two_library_copies()
        workspace_file = os.path.join(self.workspace, '周杰伦 - 晴天.flac')
        result = steps.run_dedupe(paths=[workspace_file], action='move',
                                  refresh=True, statuses=['upgrade'],
                                  replaces={workspace_file: []})
        self.assertEqual(result['planned'], 0)
        self.assertEqual(result['skipped'], 1)
        self.assertTrue(os.path.exists(first))
        self.assertTrue(os.path.exists(second))
        self.assertTrue(os.path.exists(workspace_file))


class TestDedupeActions(_DedupeRunBase):
    """网页上的「删除」与命令行的「移入重复目录」"""

    def _prepare_duplicate(self):
        self._touch('workspace', '周杰伦 - 晴天.flac', content='abcd')
        self._touch('library', '2020-2029', '2020', '周杰伦 - 晴天.flac',
                    content='abcd')
        return os.path.join(self.workspace, '周杰伦 - 晴天.flac')

    def test_trash_action_goes_to_trash(self):
        workspace_file = self._prepare_duplicate()
        result = steps.run_dedupe(paths=[workspace_file], action='trash',
                                  refresh=True, statuses=['duplicate'])
        self.assertEqual(result['executed'], 1)
        self.assertFalse(os.path.exists(workspace_file))
        self.assertEqual(os.listdir(self.duplicate_dir), [])
        self.assertEqual(os.listdir(self.trash_dir), ['周杰伦 - 晴天.flac'])

    def test_move_action_goes_to_duplicate_dir(self):
        workspace_file = self._prepare_duplicate()
        steps.run_dedupe(paths=[workspace_file], action='move', refresh=True,
                         statuses=['duplicate'])
        self.assertFalse(os.path.exists(workspace_file))
        self.assertEqual(os.listdir(self.duplicate_dir), ['周杰伦 - 晴天.flac'])
        self.assertEqual(os.listdir(self.trash_dir), [])


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

    def test_detail_reads_gbk_lyric_without_mojibake(self):
        """旧 _read_lrc 固定 utf-8 errors=replace，GBK 中文歌词会整篇乱码"""
        from core import lyrics as lyrics_core

        audio = self._touch('workspace', '周杰伦 - 晴天.flac')
        lrc = os.path.join(self.workspace, '周杰伦 - 晴天.lrc')
        with open(lrc, 'wb') as handle:
            handle.write('[00:01.00]故事的小黄花'.encode('gb18030'))
        lyrics_core.clear_lrc_cache()
        data = steps.track_detail(audio)
        self.assertIn('故事的小黄花', data['lyric'])
        self.assertNotIn('\ufffd', data['lyric'])

    def test_detail_and_save_use_uppercase_lrc(self):
        from core import lyrics as lyrics_core

        audio = self._touch('workspace', '周杰伦 - 晴天.flac')
        self._touch('workspace', '周杰伦 - 晴天.LRC', content='[00:01]晴天')
        lyrics_core.clear_lrc_cache()
        self.assertTrue(steps.track_detail(audio)['has_lrc'])
        steps.save_track(audio, lyric='[00:02]新歌词')
        # 写回必须沿用已有的大写文件名，不许再造出第二个同名歌词
        lrc_files = [name for name in os.listdir(self.workspace)
                     if os.path.splitext(name)[1].lower() == '.lrc']
        self.assertEqual(len(lrc_files), 1)
        with open(os.path.join(self.workspace, lrc_files[0]), encoding='utf-8') as handle:
            self.assertIn('新歌词', handle.read())


class TestFingerprintGate(StepsTestCase):
    """声纹库是入库必要前置：缺库/空库拦截、跨名称标签命中、归档后补录"""

    @staticmethod
    def _ready_pool(pool=()):
        return list(pool), {'status': 'ready', 'count': len(pool), 'reason': ''}

    def _use_isolated_db(self):
        self._patch('DB_PATH', os.path.join(self.root, 'missing.db'))
        steps.invalidate_library_cache()
        self.addCleanup(steps.invalidate_library_cache)

    def test_missing_db_blocks_archive(self):
        self._use_isolated_db()
        self._touch('workspace', '周杰伦 - 晴天.flac', content='abcd')
        data = steps.dedupe_preview(refresh=True)
        self.assertEqual(data['fingerprint']['status'], 'missing')
        self.assertFalse(data['fingerprint_ready'])
        self.assertEqual(data['ready_to_archive'], 0)
        self.assertTrue(all(item['blocked_reason'] for item in data['items']))

    def test_empty_pool_with_library_files_is_stale(self):
        self._touch('workspace', '甲 - 歌A.flac', content='abcd')
        self._touch('library', '2020-2029', '2020', '乙 - 歌B.flac', content='abcd')
        with mock.patch.object(steps, '_fingerprint_pool',
                               return_value=self._ready_pool()), \
             mock.patch.object(steps.soundalike, 'fingerprint_of',
                               return_value=((), 0.0)):
            data = steps.dedupe_preview(refresh=True)
        self.assertEqual(data['fingerprint']['status'], 'stale')
        self.assertEqual(data['ready_to_archive'], 0)

    def test_same_recording_different_names_is_duplicate(self):
        self._touch('workspace', '甲 - 歌A.flac', content='abcd')
        other_path = self._touch('library', '2020-2029', '2020',
                                 '乙 - 歌B.flac', content='abcd')
        fp = tuple(range(1, 121))
        other = Track(path=other_path, tags={}, size=4, duration=200.0)
        specs = {'duration': 200.0, 'bitrate': 900,
                 'sample_rate': 44100, 'bit_depth': 16}
        with mock.patch.object(steps, '_fingerprint_pool',
                               return_value=self._ready_pool([(other, fp)])), \
             mock.patch.object(steps.soundalike, 'fingerprint_of',
                               return_value=(fp, 200.0)), \
             mock.patch.object(steps.core_tags, 'read_quality', return_value=specs):
            data = steps.dedupe_preview(refresh=True)
        self.assertTrue(data['fingerprint_ready'])
        self.assertEqual(data['items'][0]['status'], 'duplicate')
        self.assertEqual(data['items'][0]['kind'], '声纹')

    def test_archive_rejects_when_fingerprint_db_missing(self):
        self._touch('workspace', '甲 - 歌A.flac', content='abcd')
        self._use_isolated_db()
        with self.assertRaises(ValueError) as ctx:
            steps.run_archive(into_library=True)
        self.assertIn('声纹库未就绪', str(ctx.exception))

    def test_archive_refreshes_fingerprint_db(self):
        path = self._touch('workspace', '甲 - 歌A.flac', content='abcd')
        complete = Track(path=path, tags={'title': '歌A', 'artist': '甲',
                                          'album': '专辑', 'year': '2020'},
                         size=4, duration=200.0, has_cover=True)
        gate = {'fingerprint_ready': True,
                'fingerprint': {'status': 'ready', 'count': 1, 'reason': ''},
                'items': [{'path': path, 'status': 'unique',
                           'archive_ok': True, 'reason': ''}]}
        refreshed = mock.Mock(ok=True)
        refreshed.summary.return_value = '成功'
        with mock.patch.object(steps.scanner, 'scan', return_value=[complete]), \
             mock.patch.object(steps.checker, 'readiness_problems', return_value=[]), \
             mock.patch.object(steps, 'dedupe_preview', return_value=gate), \
             mock.patch.object(steps.soundalike, 'refresh_db',
                               return_value=refreshed) as refresh:
            data = steps.run_archive(into_library=True)
        refresh.assert_called_once()
        self.assertTrue(data['fingerprint_db']['attempted'])
        self.assertEqual(data['fingerprint_db']['message'], '成功')

    def test_archive_dry_run_does_not_write_db(self):
        path = self._touch('workspace', '甲 - 歌A.flac', content='abcd')
        complete = Track(path=path, tags={'title': '歌A', 'artist': '甲',
                                          'album': '专辑', 'year': '2020'},
                         size=4, duration=200.0, has_cover=True)
        gate = {'fingerprint_ready': True,
                'fingerprint': {'status': 'ready', 'count': 1, 'reason': ''},
                'items': []}
        with mock.patch.object(steps.scanner, 'scan', return_value=[complete]), \
             mock.patch.object(steps.checker, 'readiness_problems', return_value=[]), \
             mock.patch.object(steps, 'dedupe_preview', return_value=gate), \
             mock.patch.object(steps.soundalike, 'refresh_db') as refresh:
            data = steps.run_archive(into_library=True, dry_run=True)
        refresh.assert_not_called()
        self.assertFalse(data['fingerprint_db']['attempted'])


    def test_unconfirmed_upgrade_is_blocked(self):
        path = self._touch('workspace', '甲 - 歌A.flac', content='abcd')
        complete = Track(path=path, tags={'title': '歌A', 'artist': '甲',
                                          'album': '专辑', 'year': '2020'},
                         size=4, duration=200.0, has_cover=True)
        gate = {'fingerprint_ready': True,
                'fingerprint': {'status': 'ready', 'count': 1, 'reason': ''},
                'items': [{'path': path, 'status': 'upgrade',
                           'archive_ok': True, 'reason': '音质更好'}]}
        with mock.patch.object(steps.scanner, 'scan', return_value=[complete]), \
             mock.patch.object(steps.checker, 'readiness_problems', return_value=[]), \
             mock.patch.object(steps, 'dedupe_preview', return_value=gate), \
             mock.patch.object(steps.soundalike, 'refresh_db') as refresh:
            data = steps.run_archive(into_library=True)
        self.assertEqual(len(data['blocked']), 1)
        self.assertEqual(data['blocked'][0]['status'], 'upgrade')
        self.assertTrue(os.path.isfile(path))
        refresh.assert_not_called()


if __name__ == '__main__':
    unittest.main()
