# -*- coding: utf-8 -*-
"""八步向导 Web 路由的 HTTP 层回归测试

用 FastAPI TestClient 走真实路由、请求模型与响应码，业务逻辑用 mock 挡在
`services.steps` 之外，任务提交用假的 `manager.submit` 顶掉——绝不真的启动后台
worker（那会跑流水线、动文件）。所有目录一律指向 tempfile。

覆盖：向导初始状态 / 目录设置 / 目录浏览与新建 / 第 3~8 步 preview 与 run /
单曲编辑 / 任务队列 / 工作区文件 / 旧版只读接口 / 页面。
"""

import os
import shutil
import tempfile
import types
import unittest
from unittest import mock

import config

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover - 未装开发依赖时 unittest discover 仍应能跑
    TestClient = None

_PATCHED_DIRS = (
    'LIBRARY_DIR', 'WORKSPACE_DIR', 'INCOMPLETE_DIR', 'DUPLICATE_DIR',
    'NETEASE_DIR', 'NETEASE_VIP_DIR', 'QQ_DIR', 'QQ_VIP_DIR',
    'DECRYPT_STAGING_DIR', 'LOG_DIR',
)
_PATCHED_FILES = {
    'DB_PATH': 'music.db',
    'JOURNAL_PATH': 'journal.jsonl',
    'TRASH_DIR': '_trash',
    'REPORT_DIR': 'reports',
}


@unittest.skipIf(TestClient is None, 'fastapi/httpx 未安装（pip install -r requirements-dev.txt）')
class TestWizardApi(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='mh_wizard_api_')
        self.addCleanup(shutil.rmtree, self.root, True)
        self.workspace = os.path.join(self.root, 'workspace')
        self.library = os.path.join(self.root, 'library')
        os.makedirs(self.workspace)
        os.makedirs(self.library)

        for name in _PATCHED_DIRS:
            if name == 'WORKSPACE_DIR':
                value = self.workspace
            elif name == 'LIBRARY_DIR':
                value = self.library
            elif name == 'LOG_DIR':
                value = os.path.join(self.root, 'log')
            else:
                value = os.path.join(self.root, 'unused', name)
            patcher = mock.patch.object(config, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        for name, leaf in _PATCHED_FILES.items():
            patcher = mock.patch.object(config, name, os.path.join(self.root, 'log', leaf))
            patcher.start()
            self.addCleanup(patcher.stop)
        # validate() 只读真实配置；这里固定成空列表，测试只关心路由怎么组装响应
        patcher = mock.patch.object(config, 'validate', return_value=[])
        patcher.start()
        self.addCleanup(patcher.stop)

        # 模块级 app 只创建一次；导入发生在目录被 patch 之后
        from services import steps
        from web.api import app
        from web.tasks import manager

        self.steps = steps
        self.manager = manager
        self.client = TestClient(app)

        # 挡住后台任务：不许真的把流水线塞进 worker 线程
        patcher = mock.patch.object(manager, 'submit')
        self.submit = patcher.start()
        self.addCleanup(patcher.stop)
        self.submit.side_effect = lambda kind, opts=None: types.SimpleNamespace(
            id='task-test', kind=kind, label=f'任务:{kind}', status='queued',
        )
        for method, value in (('busy', False), ('list', [])):
            patcher = mock.patch.object(manager, method, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(manager, 'get', return_value=None)
        self.get = patcher.start()
        self.addCleanup(patcher.stop)

    # ---------------- 第 1、2 步：状态与目录 ----------------

    def test_wizard_state_returns_full_snapshot(self):
        with mock.patch.object(self.steps, 'directories',
                               return_value={'items': [{'key': 'library_dir'}]}), \
                mock.patch.object(self.steps, 'library_status',
                                  return_value={'ready': True, 'actions': []}):
            resp = self.client.get('/api/wizard/state')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        for key in ('ok', 'version', 'dirs', 'library', 'platform', 'problems',
                    'month', 'months', 'busy', 'ini_path'):
            self.assertIn(key, data)
        self.assertEqual(data['version'], config.__version__)
        self.assertEqual(data['dirs']['items'][0]['key'], 'library_dir')
        self.assertTrue(data['library']['ready'])
        self.assertTrue(data['platform']['ok'])
        self.assertEqual(len(data['months']), 120)
        self.assertEqual(data['problems'], [])
        self.assertFalse(data['busy'])

    def test_wizard_dirs_success_and_validation(self):
        values = {'library_dir': self.library}
        with mock.patch.object(self.steps, 'save_directories',
                               return_value=([], {'items': []})) as save, \
                mock.patch.object(self.steps, 'library_status',
                                  return_value={'ready': True, 'actions': []}):
            ok = self.client.post('/api/wizard/dirs', json={'values': values})
        self.assertEqual(ok.status_code, 200)
        self.assertTrue(ok.json()['ok'])
        self.assertEqual(ok.json()['library']['ready'], True)
        save.assert_called_once_with(values)

        with mock.patch.object(self.steps, 'save_directories',
                               return_value=(['路径非法'], {'items': []})):
            bad = self.client.post('/api/wizard/dirs',
                                   json={'values': {'library_dir': 'x'}})
        self.assertEqual(bad.status_code, 400)
        self.assertFalse(bad.json()['ok'])
        self.assertEqual(bad.json()['problems'], ['路径非法'])

    def test_wizard_dirs_rejected_while_busy(self):
        with mock.patch.object(self.manager, 'busy', return_value=True):
            resp = self.client.post('/api/wizard/dirs', json={'values': {}})
        self.assertEqual(resp.status_code, 409)
        self.assertIn('任务', resp.json()['detail'])
        self.submit.assert_not_called()

    def test_fs_list_and_mkdir(self):
        child = os.path.join(self.root, 'child')
        os.makedirs(child)
        listed = self.client.get('/api/fs/list', params={'path': self.root})
        self.assertEqual(listed.status_code, 200)
        data = listed.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['path'], os.path.abspath(self.root))
        self.assertIn(child, [item['path'] for item in data['dirs']])
        self.assertEqual(self.client.get(
            '/api/fs/list', params={'path': os.path.join(self.root, 'nope')}
        ).status_code, 404)

        self.assertEqual(self.client.post(
            '/api/fs/mkdir', json={'path': 'relative/dir'}).status_code, 400)
        new_dir = os.path.join(self.root, 'newdir')
        created = self.client.post('/api/fs/mkdir', json={'path': new_dir})
        self.assertEqual(created.status_code, 200)
        self.assertTrue(created.json()['ok'])
        self.assertTrue(os.path.isdir(new_dir))

    def test_library_status_and_init(self):
        with mock.patch.object(self.steps, 'library_status',
                               return_value={'ready': True, 'actions': []}):
            status = self.client.get('/api/library/status')
        self.assertEqual(status.status_code, 200)
        self.assertTrue(status.json()['library']['ready'])

        init = self.client.post('/api/library/init', json={'make_db': False})
        self.assertEqual(init.status_code, 200)
        self.assertEqual(init.json()['kind'], 'init')
        self.assertEqual(init.json()['task_id'], 'task-test')
        self.assertEqual(self.submit.call_args.args, ('init', {'make_db': False}))

    # ---------------- 第 3~8 步：预览 ----------------

    def test_all_step_previews_pass_params_and_merge_payload(self):
        cases = (
            ('/api/copy/preview', 'copy_candidates',
             {'month': '202611'}, {'month': '202611', 'month_from': None, 'month_to': None}),
            ('/api/decrypt/preview', 'decrypt_candidates',
             {'month_from': '202601', 'month_to': '202611'},
             {'month_from': '202601', 'month_to': '202611'}),
            ('/api/tags/preview', 'tag_candidates', {}, {}),
            ('/api/dedupe/preview', 'dedupe_preview', {'refresh': 'true'}, {'refresh': True}),
            ('/api/selfcheck/preview', 'workspace_check', {}, {}),
            ('/api/archive/preview', 'archive_preview',
             {'into_library': 'false'}, {'into_library': False}),
        )
        for path, func_name, params, expected in cases:
            with self.subTest(path=path):
                with mock.patch.object(self.steps, func_name,
                                       return_value={'marker': func_name}) as fn:
                    resp = self.client.get(path, params=params)
                self.assertEqual(resp.status_code, 200)
                self.assertTrue(resp.json()['ok'])
                self.assertEqual(resp.json()['marker'], func_name)
                fn.assert_called_once_with(**expected)

    def test_selfcheck_preview_requires_existing_workspace(self):
        with mock.patch.object(config, 'WORKSPACE_DIR', os.path.join(self.root, 'gone')):
            resp = self.client.get('/api/selfcheck/preview')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('工作区目录不存在', resp.json()['detail'])

    # ---------------- 第 3~8 步：执行（只验任务入参，不真跑） ----------------

    def test_all_step_runs_submit_with_expected_opts(self):
        cases = (
            ('/api/copy/run', {'paths': ['a.mp3'], 'month': '202611'}, 'copy',
             {'paths': ['a.mp3'], 'month': '202611', 'month_from': '', 'month_to': ''}),
            ('/api/decrypt/run',
             {'paths': ['a.ncm'], 'month_from': '202601', 'month_to': '202611'},
             'decrypt-direct',
             {'paths': ['a.ncm'], 'month_from': '202601', 'month_to': '202611'}),
            ('/api/tags/run',
             {'paths': [], 'with_fingerprint': False, 'write_cover': False,
              'write_lyrics': False, 'fields': ['title']},
             'tags',
             {'paths': [], 'with_fingerprint': False, 'write_cover': False,
              'write_lyrics': False, 'fields': ['title']}),
            ('/api/dedupe/run',
             {'paths': ['a.mp3'], 'action': 'move', 'refresh': False,
              'statuses': ['duplicate'], 'replaces': {}},
             'dedupe-cross',
             {'paths': ['a.mp3'], 'action': 'move', 'refresh': False,
              'statuses': ['duplicate'], 'replaces': {}}),
            ('/api/selfcheck/run', None, 'selfcheck', {}),
            ('/api/archive/run',
             {'into_library': False, 'move_incomplete': False, 'write_fingerprints': False},
             'archive',
             {'into_library': False, 'move_incomplete': False, 'write_fingerprints': False}),
        )
        for path, body, kind, expected in cases:
            with self.subTest(path=path):
                resp = (self.client.post(path) if body is None
                        else self.client.post(path, json=body))
                self.assertEqual(resp.status_code, 200)
                self.assertTrue(resp.json()['ok'])
                self.assertEqual(resp.json()['kind'], kind)
                self.assertEqual(resp.json()['status'], 'queued')
                self.assertEqual(self.submit.call_args.args, (kind, expected))

    def test_run_routes_validate_request_models(self):
        self.assertEqual(self.client.post(
            '/api/copy/run', json={'paths': 'not-a-list'}).status_code, 422)
        self.assertEqual(self.client.post(
            '/api/tags/run', json={'write_cover': 'maybe'}).status_code, 422)
        # 注意 pydantic 会把 'yes'/'true' 宽松解析成 bool，必须用真正非法的值
        self.assertEqual(self.client.post(
            '/api/archive/run', json={'into_library': 'not-a-bool'}).status_code, 422)
        self.submit.assert_not_called()

    def test_dedupe_run_validation_blocks_task(self):
        bodies = (
            {'action': 'delete'},
            {'statuses': ['duplicate', 'unknown']},
            {'statuses': []},
            {'statuses': ['upgrade'], 'paths': []},
            {'statuses': ['duplicate'], 'paths': ['a.mp3'],
             'replaces': {'b.mp3': ['old.mp3']}},
            {'statuses': ['duplicate'], 'paths': ['a.mp3'],
             'replaces': {'a.mp3': 'not-a-list'}},
        )
        for body in bodies:
            with self.subTest(body=body):
                self.assertEqual(
                    self.client.post('/api/dedupe/run', json=body).status_code, 400)
        self.submit.assert_not_called()

    # ---------------- 第 5 步：单曲编辑 ----------------

    def test_track_routes_delegate_to_steps(self):
        with mock.patch.object(self.steps, 'track_detail',
                               return_value={'path': 'a.mp3', 'tags': {}}):
            detail = self.client.get('/api/track', params={'path': 'a.mp3'})
        self.assertEqual(detail.status_code, 200)
        self.assertTrue(detail.json()['ok'])
        self.assertEqual(detail.json()['path'], 'a.mp3')

        with mock.patch.object(self.steps, 'save_track',
                               return_value={'ok': True, 'saved': ['title']}) as save:
            saved = self.client.post('/api/track/save', json={
                'path': 'a.mp3', 'tags': {'title': '晴天'}, 'lyric': None})
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()['saved'], ['title'])
        save.assert_called_once_with('a.mp3', tags={'title': '晴天'}, lyric=None)

        with mock.patch.object(self.steps, 'fetch_track_online',
                               return_value={'ok': True, 'found': {}}) as fetch:
            fetched = self.client.post('/api/track/fetch',
                                       json={'path': 'a.mp3', 'fields': ['title']})
        self.assertEqual(fetched.status_code, 200)
        fetch.assert_called_once_with('a.mp3', fields=['title'])

    def test_track_routes_map_value_error_to_400(self):
        checks = (
            ('get', '/api/track', 'track_detail', {'params': {'path': '../x'}}),
            ('post', '/api/track/save', 'save_track', {'json': {'path': '../x'}}),
            ('post', '/api/track/fetch', 'fetch_track_online', {'json': {'path': '../x'}}),
        )
        for method, path, func_name, kwargs in checks:
            with self.subTest(path=path):
                with mock.patch.object(self.steps, func_name,
                                       side_effect=ValueError('非法路径')):
                    resp = getattr(self.client, method)(path, **kwargs)
                self.assertEqual(resp.status_code, 400)
                self.assertIn('非法路径', resp.json()['detail'])

    # ---------------- 任务队列与旧版只读接口 ----------------

    def test_task_queue_endpoints(self):
        listed = self.client.get('/api/tasks')
        self.assertEqual(listed.status_code, 200)
        self.assertTrue(listed.json()['ok'])
        self.assertEqual(listed.json()['tasks'], [])
        self.assertIn('archive', [item['kind'] for item in listed.json()['supported']])

        self.assertEqual(self.client.post(
            '/api/tasks', json={'kind': 'not-a-kind', 'opts': {}}).status_code, 400)
        ok = self.client.post('/api/tasks',
                              json={'kind': 'check', 'opts': {'dry_run': True}})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()['kind'], 'check')
        self.assertEqual(self.submit.call_args.args, ('check', {'dry_run': True}))

        self.assertEqual(self.client.get('/api/tasks/nope').status_code, 404)
        self.get.return_value = types.SimpleNamespace(
            to_dict=lambda **kwargs: {'id': 'task-test', 'status': 'done'})
        found = self.client.get('/api/tasks/task-test')
        self.assertEqual(found.status_code, 200)
        self.assertEqual(found.json()['status'], 'done')

    def test_workspace_files_and_readonly_legacy_endpoints(self):
        empty = self.client.get('/api/workspace/files')
        self.assertEqual(empty.status_code, 200)
        self.assertTrue(empty.json()['exists'])
        self.assertEqual(empty.json()['files'], [])

        song = os.path.join(self.workspace, 'song.mp3')
        with open(song, 'wb') as handle:
            handle.write(b'x')
        filled = self.client.get('/api/workspace/files').json()
        self.assertEqual(filled['total'], 1)
        self.assertEqual(filled['files'][0]['name'], 'song.mp3')
        self.assertEqual(filled['bytes'], 1)

        for path in ('/api/config', '/api/platform', '/api/scan', '/api/reports'):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)
        scan = self.client.get('/api/scan').json()
        self.assertEqual(scan['count'], 1)
        self.assertEqual(self.client.get('/api/reports').json()['reports'], [])

    def test_pages_and_unknown_route(self):
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertEqual(self.client.get('/legacy').status_code, 200)
        self.assertEqual(self.client.get('/api/does-not-exist').status_code, 404)


if __name__ == '__main__':
    unittest.main()
