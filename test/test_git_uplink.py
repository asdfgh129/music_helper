# -*- coding: utf-8 -*-
"""scripts.git_uplink 的单元测试：配置解析、单节点配置生成、环境变量注入

不碰网络与真实内核（起代理那段只能手测），只测纯逻辑部分。
"""

import importlib.util
import json
import os
import socket
import tempfile
import unittest

_SPEC = importlib.util.spec_from_file_location(
    'git_uplink', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               'scripts', 'git_uplink.py'))
uplink = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(uplink)


def _write(tmpdir, payload):
    path = os.path.join(tmpdir, 'clash.yaml')
    with open(path, 'w', encoding='utf-8') as handle:
        if isinstance(payload, str):
            handle.write(payload)
        else:
            json.dump(payload, handle, ensure_ascii=False)
    return path


class TestLoadProxies(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='mh_up_')
        self.addCleanup(lambda: __import__('shutil').rmtree(self.dir, True))

    def test_keeps_valid_and_drops_incomplete(self):
        path = _write(self.dir, {'proxies': [
            {'name': 'a', 'type': 'ss', 'server': '1.1.1.1', 'port': 443},
            {'name': 'b', 'type': 'ss', 'server': '1.1.1.1'},          # 缺 port
            {'name': 'c', 'server': '2.2.2.2', 'port': 443},           # 缺 type
            'not-a-dict',
        ]})
        got = uplink.load_proxies(path)
        self.assertEqual([p['name'] for p in got], ['a'])

    def test_rejects_empty_proxies(self):
        path = _write(self.dir, {'proxies': []})
        with self.assertRaises(SystemExit):
            uplink.load_proxies(path)

    def test_rejects_non_mapping(self):
        path = _write(self.dir, '[1, 2, 3]')
        with self.assertRaises(SystemExit):
            uplink.load_proxies(path)

    def test_missing_file(self):
        with self.assertRaises(SystemExit):
            uplink.load_proxies(os.path.join(self.dir, 'nope.yaml'))


class TestBuildConfig(unittest.TestCase):

    def test_single_proxy_global_mode(self):
        cfg = uplink.build_config({'name': 'n1', 'type': 'ss',
                                   'server': '1.1.1.1', 'port': 8443}, 26001)
        self.assertEqual(cfg['mixed-port'], 26001)
        self.assertEqual(cfg['mode'], 'global')
        self.assertFalse(cfg['allow-lan'])
        self.assertEqual(len(cfg['proxies']), 1)
        self.assertEqual(cfg['proxy-groups'][0]['name'], 'GLOBAL')
        self.assertEqual(cfg['proxy-groups'][0]['proxies'], ['n1'])
        self.assertEqual(cfg['rules'], ['MATCH,GLOBAL'])

    def test_generates_name_when_missing(self):
        cfg = uplink.build_config({'type': 'trojan', 'server': '9.9.9.9', 'port': 443}, 26002)
        self.assertEqual(cfg['proxies'][0]['name'], 'trojan-9.9.9.9:443')

    def test_does_not_mutate_input(self):
        source = {'name': 'n', 'type': 'ss', 'server': '1.1.1.1', 'port': 80}
        uplink.build_config(source, 26003)
        self.assertEqual(source, {'name': 'n', 'type': 'ss', 'server': '1.1.1.1', 'port': 80})


class TestFindConfig(unittest.TestCase):

    def test_explicit_existing(self):
        handle, path = tempfile.mkstemp(suffix='.yaml')
        os.close(handle)
        self.addCleanup(os.remove, path)
        self.assertEqual(uplink.find_config(path), path)

    def test_explicit_missing_raises(self):
        with self.assertRaises(SystemExit):
            uplink.find_config('C:/definitely/not/here.yaml')


class TestPortAndEnv(unittest.TestCase):

    def test_free_port_is_bindable(self):
        port = uplink._free_port(26100)
        self.assertTrue(26100 <= port < 26600)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(('127.0.0.1', port))

    def test_proxy_env_sets_all_keys(self):
        env = uplink.proxy_env('http://127.0.0.1:26000')
        for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY'):
            self.assertEqual(env[key], 'http://127.0.0.1:26000')

    def test_proxy_env_clears_when_empty(self):
        env = uplink.proxy_env('')
        for key in uplink.PROXY_KEYS:
            self.assertNotIn(key, env)
        # 只改副本，不污染当前进程环境
        before = os.environ.get('HTTP_PROXY')
        uplink.proxy_env('http://127.0.0.1:26001')
        self.assertEqual(os.environ.get('HTTP_PROXY'), before)


class TestParser(unittest.TestCase):

    def setUp(self):
        self.parser = uplink.build_parser()

    def test_push_collects_git_args(self):
        args = self.parser.parse_args(['push', 'origin', 'master'])
        self.assertEqual(args.action, 'push')
        self.assertEqual(args.git_args, ['origin', 'master'])

    def test_run_remainder_keeps_dashdash(self):
        args = self.parser.parse_args(['run', '--', 'git', 'fetch'])
        self.assertEqual(args.command[:2], ['--', 'git'])

    def test_defaults(self):
        args = self.parser.parse_args(['status'])
        self.assertEqual(args.probe, 'https://github.com/')
        self.assertEqual(args.max_tries, 12)
        self.assertTrue(args.allow_direct)

    def test_no_direct_flag(self):
        args = self.parser.parse_args(['pull', '--no-direct'])
        self.assertFalse(args.allow_direct)


if __name__ == '__main__':
    unittest.main()
