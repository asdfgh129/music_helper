# -*- coding: utf-8 -*-
"""core.library 的单元测试：库「是否已初始化」的判据"""

import os
import shutil
import tempfile
import unittest

import config
import core.library as library


class TestDecadeDirs(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='mh_lib_')
        self.addCleanup(shutil.rmtree, self.root, True)

    def _mkdir(self, *parts):
        path = os.path.join(self.root, *parts)
        os.makedirs(path, exist_ok=True)
        return path

    def test_reads_two_level_layout(self):
        self._mkdir('1980-1989', '1985')
        self._mkdir('1990-1999', '1995')
        self._mkdir('1990-1999', 'not-a-year')
        result = library.decade_dirs(self.root)
        names = [item['name'] for item in result]
        self.assertEqual(names, ['1980-1989', '1990-1999'])
        self.assertEqual(result[0]['years'], ['1985'])
        self.assertEqual(result[1]['years'], ['1995'])

    def test_ignores_plain_directories(self):
        self._mkdir('unknown')
        self._mkdir('VipSOngsDownload')
        self.assertEqual(library.decade_dirs(self.root), [])

    def test_missing_directory_is_empty(self):
        self.assertEqual(library.decade_dirs(os.path.join(self.root, 'nope')), [])


class TestStatus(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='mh_lib_')
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_missing_dir_is_not_initialized(self):
        status = library.status(os.path.join(self.root, 'nope'), '')
        self.assertFalse(status['initialized'])
        self.assertTrue(status['problems'])

    def test_empty_dir_is_not_initialized(self):
        status = library.status(self.root, '')
        self.assertFalse(status['initialized'])
        self.assertFalse(status['has_year_layout'])
        self.assertIn('空', status['problems'][0])

    def test_year_layout_means_initialized(self):
        os.makedirs(os.path.join(self.root, '1990-1999', '1995'))
        status = library.status(self.root, '')
        self.assertTrue(status['initialized'])
        self.assertTrue(status['has_year_layout'])
        self.assertEqual(status['year_count'], 1)

    def test_audio_without_layout_is_initialized(self):
        """库里有歌但还没归档，也算初始化过——初始化不该重复做"""
        with open(os.path.join(self.root, 'a.flac'), 'w', encoding='utf-8') as handle:
            handle.write('x')
        status = library.status(self.root, '')
        self.assertTrue(status['initialized'])
        self.assertFalse(status['has_year_layout'])
        self.assertEqual(status['audio_count'], 1)
        self.assertTrue(status['suggestions'])

    def test_missing_db_is_a_suggestion_not_a_blocker(self):
        os.makedirs(os.path.join(self.root, '1990-1999', '1995'))
        status = library.status(self.root, os.path.join(self.root, 'music.db'))
        self.assertTrue(status['initialized'])
        self.assertFalse(status['db']['exists'])
        self.assertTrue(any('声纹库' in text for text in status['suggestions']))

    def test_file_instead_of_dir(self):
        path = os.path.join(self.root, 'file.txt')
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write('x')
        status = library.status(path, '')
        self.assertFalse(status['initialized'])
        self.assertFalse(status['is_dir'])

    def test_blank_dir_is_reported(self):
        status = library.status('', '')
        self.assertFalse(status['initialized'])
        self.assertEqual(status['problems'], ['库目录未配置'])


class TestInitActions(unittest.TestCase):

    def test_actions_cover_layout_and_db(self):
        status = {'is_dir': False, 'has_year_layout': False, 'dir': 'D:\\music',
                  'db': {'exists': False}}
        keys = [item['key'] for item in library.init_actions(status)]
        self.assertEqual(keys, ['mkdir', 'layout', 'db'])

    def test_existing_db_means_refresh(self):
        status = {'is_dir': True, 'has_year_layout': True, 'dir': 'D:\\music',
                  'db': {'exists': True}}
        keys = [item['key'] for item in library.init_actions(status)]
        self.assertEqual(keys, ['db-refresh'])


class TestDefaultLibraryIsUsable(unittest.TestCase):

    def test_default_config_status_shape(self):
        """真实配置也应当能算出结构完整的状态（不要求库非空）"""
        status = library.status(config.LIBRARY_DIR, config.DB_PATH)
        for key in ('dir', 'initialized', 'problems', 'suggestions', 'db', 'decades'):
            self.assertIn(key, status)


if __name__ == '__main__':
    unittest.main()
