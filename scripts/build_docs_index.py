# -*- coding: utf-8 -*-
"""生成 docs/index.html：覆盖仓库内全部 Markdown 文档的可浏览索引

用法：
    python scripts/build_docs_index.py            # 重新生成索引
    python scripts/build_docs_index.py --check   # CI 用：索引是否过期

约定：
- 只依赖标准库；输出路径固定为 ``docs/index.html``，与当前工作目录无关；
- 页面是纯静态单文件（内联 CSS/JS，无外部依赖），可直接用浏览器打开；
- 索引覆盖仓库内所有 ``.md``，第三方源码自带文档单独分组并标注「只读」；
- 生成时间写在 HTML 注释里，``--check`` 比较时会忽略它。
"""

import argparse
import html
import os
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'
OUTPUT = DOCS / 'index.html'

SKIP_DIRS = {
    '.git', '.codebuddy', '.workbuddy', '.sisyphus', '.omo', '.venv', 'venv',
    'node_modules', '__pycache__', '.pytest_cache', 'log', 'tmp', 'dist', 'build',
}
ROOT_FILES = {'README.md', 'AGENTS.md', 'CHANGELOG.md', 'CONTRIBUTING.md'}
COMPANION_FILES = {
    'scripts/README.md', 'tests/README.md', 'third_party/README.md',
}

GROUPS = (
    ('root', '项目总览', '根目录惯例文件：先读这些'),
    ('docs', '项目文档', 'docs/ 下当前有效的设计与使用文档'),
    ('history', '历史归档', '只读，描述重构前状态，不再更新'),
    ('companion', '配套说明', '脚本、测试、第三方源码的说明入口'),
    ('thirdparty', '第三方源码自带文档', '只读，非本项目维护，仅供查阅'),
)

LABELS = {
    'README.md': '入口',
    'AGENTS.md': '代理速查',
    'CHANGELOG.md': '变更记录',
    'CONTRIBUTING.md': '贡献指南',
    'docs/README.md': '文档索引',
    'docs/browser-local-roadmap.md': '分支路线',
    'docs/architecture.md': '架构',
    'docs/rules.md': '判定规则',
    'docs/algorithms.md': '算法',
    'docs/workflow.md': '流程',
    'docs/configuration.md': '配置',
    'docs/usage.md': 'CLI 参数',
    'docs/fingerprint.md': '声纹',
    'docs/self-check.md': '自检',
    'docs/web-wizard.md': 'Web 向导',
    'docs/web-guide.md': 'Web 操作',
    'docs/troubleshooting.md': '排错',
    'docs/git-proxy.md': '运维',
    'docs/history/cleanup-2026-03.md': '历史',
    'docs/history/debug-mode.md': '历史',
    'docs/history/code-review-2026-02.md': '历史',
    'docs/history/extraction-2026-02.md': '历史',
}

# 摘要提取时跳过的行：标题、引用、表格、分隔线、列表标记、代码块围栏
SKIP_LINE_RE = re.compile(r'^\s*(#{1,6}\s|>|\||---+|\*\*\*+|```|!\[|<|$)')
MD_LINK_RE = re.compile(r'\[([^\]]+)\]\([^)]+\)')
MD_MARK_RE = re.compile(r'[`*_~]')


def iter_markdown():
    """遍历仓库内所有 Markdown，跳过运行期与第三方构建目录"""
    for root, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]
        for name in files:
            if name.lower().endswith('.md'):
                yield Path(root) / name


def group_of(rel):
    if rel in ROOT_FILES:
        return 'root'
    if rel.startswith('docs/history/'):
        return 'history'
    if rel.startswith('docs/'):
        return 'docs'
    if rel in COMPANION_FILES:
        return 'companion'
    return 'thirdparty'


def plain_text(line):
    text = MD_LINK_RE.sub(r'\1', line.strip())
    text = MD_MARK_RE.sub('', text)
    return re.sub(r'\s+', ' ', text).strip()


def read_meta(path, rel):
    """取 H1 作标题，取第一段正文作摘要"""
    title = ''
    summary = ''
    try:
        lines = path.read_text(encoding='utf-8', errors='replace').splitlines()[:80]
    except OSError:
        lines = []
    for line in lines:
        if line.startswith('# ') and not title:
            title = plain_text(line[2:])
            break
    if not title:
        title = path.stem
    for line in lines:
        if line.startswith('# '):
            continue
        if SKIP_LINE_RE.match(line):
            continue
        candidate = plain_text(line)
        if len(candidate) < 8:
            continue
        summary = candidate[:140] + ('…' if len(candidate) > 140 else '')
        break
    if not summary:
        summary = '（无摘要）'
    label = LABELS.get(rel, '')
    return title, summary, label


def size_text(path):
    size = path.stat().st_size
    return f'{size / 1024:.1f} KB' if size < 1024 * 1024 else f'{size / 1024 / 1024:.1f} MB'


def collect():
    entries = {key: [] for key, _title, _desc in GROUPS}
    for path in iter_markdown():
        rel = path.relative_to(ROOT).as_posix()
        group = group_of(rel)
        title, summary, label = read_meta(path, rel)
        href = os.path.relpath(path, DOCS).replace(os.sep, '/')
        entries[group].append({
            'rel': rel,
            'href': href,
            'title': title,
            'summary': summary,
            'label': label,
            'size': size_text(path),
        })

    # 索引与路线文档排在项目文档最前面，其余按路径排序
    priority = {'docs/README.md': 0, 'docs/browser-local-roadmap.md': 1}
    for items in entries.values():
        items.sort(key=lambda item: (priority.get(item['rel'], 9), item['rel']))
    return entries


def render_card(item, group):
    esc = html.escape
    label = (f'<span class="tag">{esc(item["label"])}</span>' if item['label'] else '')
    readonly = '<span class="tag muted">只读</span>' if group in ('history', 'thirdparty') else ''
    searchable = esc(' '.join((item['title'], item['rel'], item['summary'],
                               item['label'])).lower(), quote=True)
    return (
        f'<a class="card" href="{esc(item["href"], quote=True)}" '
        f'data-group="{group}" data-text="{searchable}">'
        f'<div class="card-top"><span class="card-title">{esc(item["title"])}</span>{label}{readonly}</div>'
        f'<div class="card-path">{esc(item["rel"])}</div>'
        f'<div class="card-summary">{esc(item["summary"])}</div>'
        f'<div class="card-foot">{esc(item["size"])}</div>'
        f'</a>'
    )


def render(entries, generated_at):
    total = sum(len(items) for items in entries.values())
    sections = []
    for key, title, desc in GROUPS:
        items = entries[key]
        cards = '\n'.join(render_card(item, key) for item in items)
        sections.append(
            f'<section class="group" data-group="{key}">'
            f'<div class="group-head"><h2>{html.escape(title)}'
            f'<span class="count">{len(items)}</span></h2>'
            f'<p>{html.escape(desc)}</p></div>'
            f'<div class="grid">{cards}</div></section>'
        )
    buttons = '\n'.join(
        f'<button type="button" class="filter" data-filter="{key}">{html.escape(title)}</button>'
        for key, title, _desc in GROUPS
    )
    return TEMPLATE.replace('__GENERATED_AT__', generated_at) \
                   .replace('__TOTAL__', str(total)) \
                   .replace('__BUTTONS__', buttons) \
                   .replace('__SECTIONS__', '\n'.join(sections))


TEMPLATE = r'''<!DOCTYPE html>
<!-- generated-at: __GENERATED_AT__ -->
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Music Helper 文档索引</title>
<style>
:root { color-scheme: light dark;
  --bg:#f6f7f9; --panel:#fff; --text:#1c2026; --muted:#6b7280;
  --line:#e3e7ec; --accent:#2563eb; --chip:#eef2ff; --shadow:0 1px 3px rgba(0,0,0,.06); }
@media (prefers-color-scheme: dark) {
  :root { --bg:#14171c; --panel:#1d222a; --text:#e8ebf0; --muted:#9aa4b2;
    --line:#303743; --accent:#7aa2ff; --chip:#26324a; --shadow:none; }
}
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--text);
  font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; }
.wrap { max-width:1180px; margin:0 auto; padding:32px 20px 64px; }
header h1 { margin:0 0 6px; font-size:28px; letter-spacing:.3px; }
header p { margin:0; color:var(--muted); }
.badges { margin:14px 0 22px; display:flex; gap:10px; flex-wrap:wrap; }
.badge { background:var(--chip); color:var(--accent); border-radius:999px;
  padding:4px 12px; font-size:13px; font-weight:600; }
.toolbar { position:sticky; top:0; z-index:2; background:var(--bg);
  padding:12px 0; border-bottom:1px solid var(--line); margin-bottom:8px; }
#q { width:100%; padding:11px 14px; font-size:15px; border:1px solid var(--line);
  border-radius:10px; background:var(--panel); color:var(--text); outline:none; }
#q:focus { border-color:var(--accent); box-shadow:0 0 0 3px var(--chip); }
.filters { display:flex; gap:8px; flex-wrap:wrap; margin-top:10px; }
.filter { cursor:pointer; border:1px solid var(--line); background:var(--panel);
  color:var(--muted); border-radius:999px; padding:5px 13px; font-size:13px; }
.filter:hover, .filter.active { color:var(--accent); border-color:var(--accent); background:var(--chip); }
#status { color:var(--muted); font-size:13px; margin:14px 0 0; }
.group { margin-top:30px; }
.group[hidden], .card[hidden] { display:none !important; }
.group-head h2 { font-size:19px; margin:0 0 2px; display:flex; align-items:center; gap:9px; }
.count { font-size:12px; font-weight:600; color:var(--accent); background:var(--chip);
  border-radius:999px; padding:2px 9px; }
.group-head p { margin:0 0 14px; color:var(--muted); font-size:13px; }
.grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(290px,1fr)); gap:12px; }
.card { display:block; text-decoration:none; color:inherit; background:var(--panel);
  border:1px solid var(--line); border-radius:12px; padding:14px 16px; box-shadow:var(--shadow);
  transition:transform .12s ease, border-color .12s ease; }
.card:hover { transform:translateY(-2px); border-color:var(--accent); }
.card-top { display:flex; align-items:center; gap:7px; flex-wrap:wrap; }
.card-title { font-weight:650; font-size:15px; }
.tag { font-size:11px; color:var(--accent); background:var(--chip); border-radius:5px; padding:1px 6px; }
.tag.muted { color:var(--muted); background:transparent; border:1px solid var(--line); }
.card-path { font:12px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace;
  color:var(--muted); margin-top:5px; word-break:break-all; }
.card-summary { font-size:13px; color:var(--muted); margin-top:8px; min-height:2.9em; }
.card-foot { font-size:11px; color:var(--muted); margin-top:8px; }
#empty { display:none; text-align:center; color:var(--muted); padding:48px 0; }
footer { margin-top:44px; padding-top:18px; border-top:1px solid var(--line);
  color:var(--muted); font-size:13px; }
code { background:var(--chip); padding:1px 5px; border-radius:4px; }
@media (max-width:600px) { .wrap { padding:20px 14px 48px; } .grid { grid-template-columns:1fr; } }
</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>Music Helper 文档索引</h1>
  <p>仓库内全部 Markdown 文档的可浏览入口；点击卡片直接打开原文。</p>
  <div class="badges">
    <span class="badge">共 __TOTAL__ 篇</span>
    <span class="badge">生成于 __GENERATED_AT__</span>
    <span class="badge">纯静态 · 无外部依赖</span>
  </div>
</header>
<div class="toolbar">
  <input id="q" type="search" placeholder="搜索标题、路径或摘要…（按 / 聚焦，Esc 清空）" autocomplete="off">
  <div class="filters">
    <button type="button" class="filter active" data-filter="all">全部</button>
    __BUTTONS__
  </div>
</div>
<p id="status"></p>
<main>
__SECTIONS__
</main>
<div id="empty">没有匹配的文档，换个关键词试试。</div>
<footer>
  <p>本文件由 <code>scripts/build_docs_index.py</code> 生成，请勿手工编辑；
     新增或移动文档后执行 <code>python scripts/build_docs_index.py</code> 重新生成，
     再运行 <code>python scripts/check_docs.py</code> 校验链接。</p>
  <p>文档边界与写法约定见 <a href="README.md">docs/README.md</a>；
     历史归档与第三方源码自带文档仅供追溯，不参与文档校验。</p>
</footer>
</div>
<script>
(function () {
  var input = document.getElementById('q');
  var status = document.getElementById('status');
  var cards = Array.prototype.slice.call(document.querySelectorAll('.card'));
  var sections = Array.prototype.slice.call(document.querySelectorAll('.group'));
  var buttons = Array.prototype.slice.call(document.querySelectorAll('.filter'));
  var active = 'all';

  function apply() {
    var q = input.value.trim().toLowerCase();
    var shown = 0;
    cards.forEach(function (card) {
      var ok = (active === 'all' || card.getAttribute('data-group') === active) &&
               (!q || card.getAttribute('data-text').indexOf(q) >= 0);
      card.hidden = !ok;
      if (ok) shown++;
    });
    sections.forEach(function (section) {
      var group = section.getAttribute('data-group');
      var visible = section.querySelectorAll('.card:not([hidden])').length;
      section.hidden = (active !== 'all' && active !== group) || visible === 0;
    });
    document.getElementById('empty').style.display = shown ? 'none' : 'block';
    status.textContent = q || active !== 'all' ? ('匹配 ' + shown + ' / ' + cards.length + ' 篇') : '';
  }

  input.addEventListener('input', apply);
  buttons.forEach(function (button) {
    button.addEventListener('click', function () {
      active = button.getAttribute('data-filter');
      buttons.forEach(function (b) { b.classList.toggle('active', b === button); });
      apply();
    });
  });
  document.addEventListener('keydown', function (event) {
    if (event.key === '/' && document.activeElement !== input) {
      event.preventDefault(); input.focus();
    }
    if (event.key === 'Escape' && document.activeElement === input) {
      input.value = ''; apply(); input.blur();
    }
  });
  apply();
})();
</script>
</body>
</html>
'''


GEN_AT_RE = re.compile(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}')


def strip_generated(text):
    """比较时忽略生成时间，只比较文档清单是否变化"""
    return GEN_AT_RE.sub('<time>', text)


def main(argv=None):
    parser = argparse.ArgumentParser(description='生成 docs/index.html')
    parser.add_argument('--check', action='store_true', help='只检查索引是否过期，不写文件')
    args = parser.parse_args(argv)

    entries = collect()
    generated_at = datetime.now().strftime('%Y-%m-%d %H:%M')
    content = render(entries, generated_at)

    if args.check:
        if not OUTPUT.exists():
            print('索引缺失：' + str(OUTPUT.relative_to(ROOT)))
            return 1
        current = OUTPUT.read_text(encoding='utf-8')
        if strip_generated(current) != strip_generated(content):
            print('索引已过期，请运行 python scripts/build_docs_index.py')
            return 1
        print('文档索引是最新的')
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(content, encoding='utf-8')
    total = sum(len(items) for items in entries.values())
    print(f'已生成 {OUTPUT.relative_to(ROOT)}：{total} 篇文档，{len(GROUPS)} 个分组')
    return 0


if __name__ == '__main__':
    sys.exit(main())
