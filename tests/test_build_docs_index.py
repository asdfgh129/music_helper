# -*- coding: utf-8 -*-
"""单元测试 - 文档索引生成器（状态、Markdown 渲染、离线索引新鲜度）

这些用例只测纯函数与仓库内文件，不触碰音乐库、网络或外部程序。
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts import build_docs_index as idx


class TestStatus(unittest.TestCase):
    def test_lifecycle_status_by_group(self):
        self.assertEqual(idx.status_of('README.md', 'root'), 'current')
        self.assertEqual(idx.status_of('scripts/README.md', 'companion'), 'current')
        self.assertEqual(idx.status_of('docs/history/debug-mode.md', 'history'), 'archived')

    def test_roadmap_is_planning_not_current(self):
        self.assertEqual(idx.status_of('docs/browser-local-roadmap.md', 'docs'), 'planning')


class TestScope(unittest.TestCase):
    """第三方源码自带文档不进索引：整个 third_party/ 目录都被跳过"""

    def test_iter_markdown_skips_third_party(self):
        rels = [path.relative_to(idx.ROOT).as_posix() for path in idx.iter_markdown()]
        self.assertFalse([rel for rel in rels if rel.startswith('third_party/')])

    def test_collected_entries_exclude_third_party(self):
        entries = idx.collect()
        self.assertEqual(set(entries), {'root', 'docs', 'history', 'companion'})
        rels = [item['rel'] for group in entries.values() for item in group]
        self.assertFalse([rel for rel in rels if rel.startswith('third_party/')])
        self.assertGreater(len(rels), 20)


class TestCategories(unittest.TestCase):
    """项目文档按用途分类，映射必须覆盖全部 docs/ 文档"""

    def test_every_project_doc_has_a_real_category(self):
        docs = idx.collect()['docs']
        keys = {key for key, _title, _desc in idx.DOC_CATEGORIES} - {'other'}
        for item in docs:
            self.assertIn(item['category'], keys, item['rel'])
        for key in ('usage', 'dev', 'ops', 'plan'):
            self.assertTrue(any(item['category'] == key for item in docs), key)

    def test_nav_and_overview_expose_categories(self):
        entries = idx.collect()
        nav = idx.render_nav(entries)
        overview = idx.render_overview(entries, '2026-11-09 20:00')
        for key in ('usage', 'dev', 'ops', 'plan'):
            self.assertIn(f'data-category="{key}"', nav)
            self.assertIn(f'data-cf="{key}"', overview)
        self.assertIn('<th>分类</th>', overview)


class TestMarkdownRendering(unittest.TestCase):
    def test_nested_inline_code_in_link_leaves_no_placeholder(self):
        out = idx.inline('[见 `core/naming.py`](../core/naming.py) 与 **重点**',
                         'docs/rules.md', {'docs/rules.md'})
        self.assertNotIn('\x00', out)
        self.assertIn('<code>core/naming.py</code>', out)
        self.assertIn('<strong>重点</strong>', out)

    def test_markdown_link_becomes_in_site_route(self):
        out = idx.inline('[规则](rules.md)', 'docs/README.md', {'docs/rules.md'})
        self.assertIn('href="#/doc/docs/rules.md"', out)

    def test_link_to_unlisted_markdown_opens_original_file(self):
        out = idx.inline('[上游说明](../third_party/README.md)',
                         'docs/README.md', {'docs/README.md'})
        self.assertIn('href="../third_party/README.md"', out)
        self.assertIn('target="_blank"', out)

    def test_relative_asset_is_rebased_to_docs_dir(self):
        from_docs = idx.inline('![流程](images/flow.svg)', 'docs/workflow.md', set())
        from_root = idx.inline('![流程](docs/images/flow.svg)', 'README.md', set())
        self.assertIn('src="images/flow.svg"', from_docs)
        self.assertIn('src="images/flow.svg"', from_root)

    def test_blocks_table_list_code_and_toc(self):
        text = ('# 标题\n\n## 小节\n\n| 左 | 右 |\n| --- | --- |\n| 1 | 2 |\n\n'
                '- 甲\n- 乙\n\n```python\nprint(1)\n```\n')
        body, toc = idx.render_markdown(text, 'docs/x.md', {'docs/x.md'}, 'sec-0')
        self.assertEqual(toc, [(2, '小节', 'sec-0-h1')])
        self.assertIn('<h2 id="sec-0-h1">小节</h2>', body)
        self.assertIn('<table>', body)
        self.assertIn('<li>甲</li>', body)
        self.assertIn('<pre><code>print(1)</code></pre>', body)
        self.assertNotIn('# 标题', body)  # 首个 H1 由文档头部展示，正文不重复

    def test_code_block_content_is_escaped(self):
        body, _toc = idx.render_markdown('```\n<script>alert(1)</script>\n```',
                                         'docs/x.md', set(), 'sec-0')
        self.assertIn('&lt;script&gt;', body)
        self.assertNotIn('<script>', body)


class TestFreshness(unittest.TestCase):
    def test_strip_generated_ignores_time_date_and_size(self):
        left = ('生成于 2026-11-09 09:51 <time class="upd">2026-11-09</time> 28.4 KB '
                '<ul class="recent"><li>甲</li></ul>')
        right = ('生成于 2026-12-01 23:59 <time class="upd">2026-12-01</time> 30.1 KB '
                 '<ul class="recent"><li>乙</li></ul>')
        self.assertEqual(idx.strip_generated(left), idx.strip_generated(right))

    def test_strip_generated_keeps_document_content(self):
        self.assertNotEqual(idx.strip_generated('<p>规则 A</p>'),
                            idx.strip_generated('<p>规则 B</p>'))

    def test_collected_entries_have_status_and_rendered_body(self):
        entries = idx.collect()
        items = [item for group in entries.values() for item in group]
        self.assertGreater(len(items), 20)
        for item in items:
            self.assertIn(item['status'], {'current', 'planning', 'archived'})
            self.assertIn(item['check'], {'pass', 'issues', 'skip'})
            self.assertTrue(item['body'])
            self.assertRegex(item['updated'], r'^\d{4}-\d{2}-\d{2}$')

    def test_committed_index_is_up_to_date(self):
        self.assertEqual(idx.main(['--check']), 0)


if __name__ == '__main__':
    unittest.main()
