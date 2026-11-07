# -*- coding: utf-8 -*-
"""utils 的单元测试：日志初始化与月份工具

命名规则、艺术家拆分、标准化等都属 `core.naming`，用例在 `test_naming.py`——
历史上有过半份用例挂在 test_utils 里测 core.naming，与 test_naming 重复，已合并。
"""

import logging
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import utils as utils_mod
from utils import get_current_month, validate_month_format


class TestMonthTools(unittest.TestCase):

    def test_get_current_month_format(self):
        month = get_current_month()
        self.assertEqual(len(month), 6)
        self.assertTrue(month.isdigit())

    def test_validate_month_format_valid(self):
        self.assertTrue(validate_month_format('202406'))
        self.assertTrue(validate_month_format('202001'))
        self.assertTrue(validate_month_format('199912'))

    def test_validate_month_format_invalid(self):
        self.assertFalse(validate_month_format('2024'))       # 长度不够
        self.assertFalse(validate_month_format('20240607'))   # 长度过长
        self.assertFalse(validate_month_format('2024ab'))     # 非数字
        self.assertFalse(validate_month_format('202400'))     # 月份越界
        self.assertFalse(validate_month_format('202413'))     # 月份越界
        self.assertFalse(validate_month_format('189906'))     # 年份太小
        self.assertFalse(validate_month_format('220006'))     # 年份太大
        self.assertFalse(validate_month_format(''))
        self.assertFalse(validate_month_format(None))


class TestSetupLogging(unittest.TestCase):
    """日志初始化：handler 挂根 logger，子模块日志必须能落盘"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='mh_log_')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.addCleanup(self._reset_handlers)

    def _reset_handlers(self):
        """把本模块装的 handler 全关掉，否则 Windows 上临时目录删不掉。"""
        root = logging.getLogger()
        for handler in utils_mod._log_handlers:
            root.removeHandler(handler)
            handler.close()
        utils_mod._log_handlers = []

    def _read_log(self):
        for handler in utils_mod._log_handlers:
            handler.flush()
        with open(utils_mod.log_file, encoding='utf-8') as handle:
            return handle.read()

    def test_creates_log_file_and_two_handlers(self):
        with mock.patch.object(utils_mod, 'LOG_DIR', self.tmp):
            utils_mod.setup_logging()
            root = logging.getLogger()
            self.assertEqual(len(utils_mod._log_handlers), 2)   # 文件 + 控制台
            for handler in utils_mod._log_handlers:
                self.assertIn(handler, root.handlers)
            self.assertTrue(os.path.exists(utils_mod.log_file))
            self.assertTrue(utils_mod.log_file.startswith(self.tmp))

    def test_repeated_call_does_not_stack_handlers(self):
        with mock.patch.object(utils_mod, 'LOG_DIR', self.tmp):
            first = utils_mod.setup_logging()
            count = len(utils_mod._log_handlers)
            second = utils_mod.setup_logging()
            self.assertIs(first, second)
            self.assertEqual(len(utils_mod._log_handlers), count)
            self.assertEqual(sum(1 for h in logging.getLogger().handlers
                                 if h in utils_mod._log_handlers), count)

    def test_debug_mode_sets_debug_level(self):
        with mock.patch.object(utils_mod, 'LOG_DIR', self.tmp):
            logger = utils_mod.setup_logging(debug_mode=True)
            self.assertEqual(logger.level, logging.DEBUG)
            normal = utils_mod.setup_logging(debug_mode=False)
            self.assertEqual(normal.level, logging.INFO)

    def test_child_logger_writes_into_same_file(self):
        """回归：fingerprint.* 这类子模块日志曾因 handler 挂错位置而只进 stderr"""
        with mock.patch.object(utils_mod, 'LOG_DIR', self.tmp):
            utils_mod.setup_logging()
            logging.getLogger('fingerprint.fpcalc').info('CHILD-INFO-LINE')
            self.assertIn('CHILD-INFO-LINE', self._read_log())

    def test_child_debug_only_in_debug_mode(self):
        with mock.patch.object(utils_mod, 'LOG_DIR', self.tmp):
            utils_mod.setup_logging()
            logging.getLogger('fingerprint.fpcalc').debug('CHILD-DEBUG-LINE')
            self.assertNotIn('CHILD-DEBUG-LINE', self._read_log())

        with mock.patch.object(utils_mod, 'LOG_DIR', self.tmp):
            utils_mod.setup_logging(debug_mode=True)
            logging.getLogger('fingerprint.fpcalc').debug('CHILD-DEBUG-LINE')
            self.assertIn('CHILD-DEBUG-LINE', self._read_log())


class TestPlatformTools(unittest.TestCase):
    """外部程序的跨平台校验：缺文件 / 拿错平台 / 缺可执行位"""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='mh_tools_')
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def _write(self, name, head):
        path = os.path.join(self.root, name)
        with open(path, 'wb') as handle:
            handle.write(head + b'\x00' * 32)
        return path

    def test_binary_kind_reads_magic(self):
        self.assertEqual(utils_mod.binary_kind(self._write('a.exe', b'MZ')), 'windows')
        self.assertEqual(utils_mod.binary_kind(self._write('a.macho', b'\xcf\xfa\xed\xfe')), 'macho')
        self.assertEqual(utils_mod.binary_kind(self._write('a.elf', b'\x7fELF')), 'elf')
        self.assertEqual(utils_mod.binary_kind(self._write('a.sh', b'#!/bin/sh')), 'script')
        self.assertIsNone(utils_mod.binary_kind(self._write('a.bin', b'\x00\x01\x02\x03')))

    def test_missing_file_explains_platform(self):
        problem = utils_mod.tool_problem(os.path.join(self.root, 'nope.exe'), '声纹工具')
        self.assertIn('找不到', problem)
        self.assertIn(utils_mod.platform_label(), problem)

    def test_wrong_platform_binary_is_rejected(self):
        """把 Windows PE 丢给 macOS 会报 Exec format error，提前拦住"""
        pe = self._write('soundalike', b'MZ')
        with mock.patch.object(utils_mod.os, 'name', 'posix'), \
                mock.patch.object(utils_mod.sys, 'platform', 'darwin'):
            problem = utils_mod.tool_problem(pe, '声纹工具')
        self.assertIn('Exec format error', problem)
        self.assertIn('Windows PE', problem)

    @unittest.skipIf(os.name == 'nt', 'Windows 没有可执行位，chmod 只改只读标志')
    def test_matching_binary_passes(self):
        macho = self._write('soundalike', b'\xcf\xfa\xed\xfe')
        os.chmod(macho, 0o755)
        with mock.patch.object(utils_mod.os, 'name', 'posix'), \
                mock.patch.object(utils_mod.sys, 'platform', 'darwin'):
            self.assertEqual(utils_mod.tool_problem(macho, '声纹工具'), '')

    @unittest.skipIf(os.name == 'nt', 'Windows 没有可执行位，chmod 只改只读标志')
    def test_missing_exec_bit_hints_chmod(self):
        macho = self._write('soundalike', b'\xcf\xfa\xed\xfe')
        os.chmod(macho, 0o644)
        with mock.patch.object(utils_mod.os, 'name', 'posix'), \
                mock.patch.object(utils_mod.sys, 'platform', 'darwin'):
            problem = utils_mod.tool_problem(macho, '声纹工具')
        self.assertIn('chmod +x', problem)

    def test_platform_label(self):
        with mock.patch.object(utils_mod.sys, 'platform', 'darwin'):
            self.assertEqual(utils_mod.platform_label(), 'macOS')
        with mock.patch.object(utils_mod.os, 'name', 'nt'), \
                mock.patch.object(utils_mod.sys, 'platform', 'win32'):
            self.assertEqual(utils_mod.platform_label(), 'Windows')

    def test_resolve_tool_prefers_existing_path(self):
        path = self._write('um', b'\x7fELF')
        self.assertEqual(utils_mod.resolve_tool(path, 'um'), path)

    def test_resolve_tool_falls_back_to_path(self):
        missing = os.path.join(self.root, 'nope', 'nothing-here-xyz')
        self.assertEqual(utils_mod.resolve_tool(missing, 'nothing-here-xyz'), missing)


if __name__ == '__main__':
    unittest.main()
