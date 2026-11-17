# -*- coding: utf-8 -*-
"""单元测试 - 入口默认行为：无参数只启动 Web 服务、打开播放器首页，不跑任何文件流程"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main


class TestEffectiveArgv(unittest.TestCase):
    """无参数才注入 --web；带任意参数时 CLI 语义保持原样"""

    def test_empty_argv_defaults_to_web(self):
        self.assertEqual(main._effective_argv([]), ['--web'])

    def test_explicit_args_are_untouched(self):
        for argv in (['--archive'], ['--check', '--fix'], ['--web', '--no-browser'],
                     ['--version'], ['--dry-run']):
            with self.subTest(argv=argv):
                self.assertEqual(main._effective_argv(argv), argv)

    def test_none_reads_sys_argv(self):
        with patch.object(main.sys, 'argv', ['music_helper.exe']):
            self.assertEqual(main._effective_argv(), ['--web'])
        with patch.object(main.sys, 'argv', ['music_helper.exe', '--archive']):
            self.assertEqual(main._effective_argv(), ['--archive'])


class TestMainEntry(unittest.TestCase):
    """main() 的分派：无参数 → Web；显式参数 → 原有流程"""

    def test_no_args_starts_web_and_opens_browser(self):
        with patch.object(main, 'run_web', return_value=0) as run_web:
            code = main.main([])
        self.assertEqual(code, 0)
        run_web.assert_called_once()
        self.assertTrue(run_web.call_args.kwargs['open_browser'])

    def test_web_no_browser_keeps_flag(self):
        with patch.object(main, 'run_web', return_value=0) as run_web:
            main.main(['--web', '--no-browser'])
        run_web.assert_called_once()
        self.assertFalse(run_web.call_args.kwargs['open_browser'])

    def test_explicit_archive_runs_pipeline_not_web(self):
        with patch.object(main, 'run_web') as run_web, \
                patch.object(main, 'utils'), \
                patch.object(main, 'flow_pipeline', return_value=None) as pipeline:
            code = main.main(['--archive'])
        self.assertEqual(code, 0)
        run_web.assert_not_called()
        pipeline.assert_called_once()


if __name__ == '__main__':
    unittest.main()
