# -*- coding: utf-8 -*-
"""生成 docs/index.html：带侧栏、总览看板与状态标记的离线文档站

用法：
    python scripts/build_docs_index.py            # 重新生成索引
    python scripts/build_docs_index.py --check   # CI 用：索引是否过期

约定：
- 只依赖标准库；输出路径固定为 ``docs/index.html``，与当前工作目录无关；
- 页面是纯静态单文件（内联 CSS/JS、内嵌正文，无外部依赖），双击即可离线浏览；
- 索引只收录项目自身维护的 ``.md``；``third_party/`` 下的第三方源码自带文档不纳入
  （正文里指向它们的链接仍会指向原文件），侧栏点击直接在页面内切换文档，无需服务器；
- ``docs/`` 下项目文档按用途再分一层（使用与操作 / 开发与规则 / 排错与运维 / 规划与路线），
  映射唯一来源为 ``DOC_CATEGORIES`` 与 ``DOC_CATEGORY_OF``；新增文档漏配会落进「未分类」并告警；
- 文档状态在生成时计算：生命周期分类 + ``check_docs.py`` 校验结果 + git 最近提交日期；
- 生成时间与「最近更新」日期写入固定标记，``--check`` 比较时忽略，避免浅克隆误报。

本文件是生成器，``docs/index.html`` 是产物，不要手工编辑产物。
"""

import argparse
import html
import importlib.util
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'
OUTPUT = DOCS / 'index.html'
CHECK_DOCS = ROOT / 'scripts' / 'check_docs.py'

SKIP_DIRS = {
    '.git', '.codebuddy', '.workbuddy', '.sisyphus', '.omo', '.venv', 'venv',
    'node_modules', '__pycache__', '.pytest_cache', 'log', 'tmp', 'dist', 'build',
    'third_party',  # 上游源码自带文档不纳入项目文档索引
}
ROOT_FILES = {'README.md', 'AGENTS.md', 'CHANGELOG.md', 'CONTRIBUTING.md'}
COMPANION_FILES = {
    'scripts/README.md', 'tests/README.md',
}
PLANNING_DOCS = {'docs/browser-local-roadmap.md'}
# 与 check_docs.py 的豁免范围保持一致：历史归档与 CHANGELOG 不参与校验
CHECK_SKIP = {'CHANGELOG.md'}

GROUPS = (
    ('root', '项目总览', '根目录惯例文件：先读这些'),
    ('docs', '项目文档', 'docs/ 下当前有效的设计与使用文档'),
    ('history', '历史归档', '只读，描述重构前状态，不再更新'),
    ('companion', '配套说明', '脚本与测试的说明入口'),
)

STATUS = (
    ('current', '现行维护', '当前有效、随代码同步更新'),
    ('planning', '规划中', '下一分支的路线与待决决策，不代表主干现状'),
    ('archived', '历史归档', '只读，描述重构前状态，不再更新'),
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
    'docs/media-player.md': '试听与歌词',
    'docs/web-guide.md': 'Web 操作',
    'docs/troubleshooting.md': '排错',
    'docs/git-proxy.md': '运维',
    'docs/history/cleanup-2026-03.md': '历史',
    'docs/history/debug-mode.md': '历史',
    'docs/history/code-review-2026-02.md': '历史',
    'docs/history/extraction-2026-02.md': '历史',
}

# 项目文档（docs/）按用途再分一层；侧栏二级分组与首页「分类」列共用这份唯一映射
DOC_CATEGORIES = (
    ('usage', '使用与操作', '跑流程、点界面、查参数、改配置'),
    ('dev', '开发与规则', '分层、判定规则、算法与声纹原理'),
    ('ops', '排错与运维', '自检、故障排查与网络代理'),
    ('plan', '规划与路线', '下一个分支的路线与待决决策'),
    ('other', '未分类', '新增项目文档请补 DOC_CATEGORY_OF'),
)
DOC_CATEGORY_OF = {
    'docs/README.md': 'usage',
    'docs/usage.md': 'usage',
    'docs/workflow.md': 'usage',
    'docs/web-guide.md': 'usage',
    'docs/web-wizard.md': 'usage',
    'docs/media-player.md': 'usage',
    'docs/configuration.md': 'usage',
    'docs/architecture.md': 'dev',
    'docs/rules.md': 'dev',
    'docs/algorithms.md': 'dev',
    'docs/fingerprint.md': 'dev',
    'docs/self-check.md': 'ops',
    'docs/troubleshooting.md': 'ops',
    'docs/git-proxy.md': 'ops',
    'docs/browser-local-roadmap.md': 'plan',
}

QUICK_LINKS = (
    ('快速上手', 'README.md'),
    ('端到端流程', 'docs/workflow.md'),
    ('判定规则总表', 'docs/rules.md'),
    ('算法与阈值', 'docs/algorithms.md'),
    ('架构与分层', 'docs/architecture.md'),
    ('命令行手册', 'docs/usage.md'),
    ('Web 操作说明', 'docs/web-guide.md'),
    ('故障排查', 'docs/troubleshooting.md'),
)

# 摘要提取时跳过的行：标题、引用、表格、分隔线、列表标记、代码块围栏
SKIP_LINE_RE = re.compile(r'^\s*(#{1,6}\s|>|\||---+|\*\*\*+|```|!\[|<|$)')
MD_LINK_RE = re.compile(r'\[([^\]]+)\]\([^)]+\)')
MD_MARK_RE = re.compile(r'[`*_~]')

# ---- Markdown 渲染（够用的子集：标题 / 段落 / 列表 / 表格 / 引用 / 代码块 / 行内标记） ----
FENCE_RE = re.compile(r'^\s{0,3}```')
HEAD_RE = re.compile(r'^(#{1,6})\s+(.*)$')
UL_RE = re.compile(r'^(\s*)[-*+]\s+(.*)$')
OL_RE = re.compile(r'^(\s*)\d+[.)]\s+(.*)$')
QUOTE_RE = re.compile(r'^\s{0,3}>\s?(.*)$')
HR_RE = re.compile(r'^\s*(?:-{3,}|\*{3,}|_{3,})\s*$')
SEP_CELL_RE = re.compile(r'^:?-{2,}:?$')
INLINE_CODE_RE = re.compile(r'`([^`\n]+)`')
IMAGE_RE = re.compile(r'!\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)')
LINK_RE = re.compile(r'(?<!!)\[([^\]]+)\]\(([^)\s]+)(?:\s+"[^"]*")?\)')
STASH_RE = re.compile('\x00(\\d+)\x00')


def iter_markdown():
    """遍历项目自身维护的 Markdown，跳过运行期、隐藏目录与第三方源码目录"""
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
    return 'companion'


def status_of(rel, group):
    if group == 'history':
        return 'archived'
    if rel in PLANNING_DOCS:
        return 'planning'
    return 'current'


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
    return title, summary, LABELS.get(rel, '')


def size_text(path):
    size = path.stat().st_size
    return f'{size / 1024:.1f} KB' if size < 1024 * 1024 else f'{size / 1024 / 1024:.1f} MB'


def load_check_file():
    """复用 check_docs.py 的唯一实现，不在本文件另写一套校验规则"""
    spec = importlib.util.spec_from_file_location('_docs_checker', CHECK_DOCS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.check_file


def git_dates():
    """一次 git log 取出每个文件最近一次提交日期；浅克隆 / 无 git 时返回空表"""
    try:
        result = subprocess.run(
            ['git', 'log', '--format=%cs', '--name-only'],
            cwd=str(ROOT), capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=30,
        )
        if result.returncode != 0:
            return {}
    except (OSError, subprocess.SubprocessError):
        return {}
    dates = {}
    current = ''
    for raw in result.stdout.splitlines():
        line = raw.strip()
        if not line:
            continue
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', line):
            current = line
        elif current and line.lower().endswith('.md') and line not in dates:
            dates[line] = current
    return dates


def split_row(line):
    return [cell.strip() for cell in line.strip().strip('|').split('|')]


def is_table_sep(line):
    if '|' not in line or '-' not in line:
        return False
    cells = split_row(line)
    return bool(cells) and all(SEP_CELL_RE.fullmatch(cell) for cell in cells)


def rewrite_href(target, rel, doc_rels):
    """把文档内相对链接改写成相对 docs/index.html 的路径或站内 hash 路由"""
    raw = target.strip()
    pathpart = raw.split('#', 1)[0].split('?', 1)[0]
    if raw.startswith('#'):
        return f'#/doc/{rel}'
    if pathpart.startswith(('http://', 'https://', 'mailto:', 'tel:', 'data:', '//')):
        return raw
    if not pathpart:
        return raw
    base = os.path.dirname(os.path.join(str(ROOT), rel))
    absolute = os.path.normpath(os.path.join(base, pathpart.replace('/', os.sep)))
    try:
        rel_target = os.path.relpath(absolute, str(ROOT)).replace(os.sep, '/')
    except ValueError:
        rel_target = os.path.relpath(absolute, str(DOCS)).replace(os.sep, '/')
    if rel_target in doc_rels and rel_target.lower().endswith('.md'):
        return f'#/doc/{rel_target}'
    try:
        href = os.path.relpath(absolute, str(DOCS)).replace(os.sep, '/')
    except ValueError:
        href = rel_target
    fragment = raw.split('#', 1)[1] if '#' in raw else ''
    return href + (f'#{fragment}' if fragment else '')


def inline(text, rel, doc_rels):
    """行内标记：代码 / 图片 / 链接 / 粗斜体 / 删除线；生成的标签用占位符保护"""
    stash = []

    def keep(markup):
        stash.append(markup)
        return f'\x00{len(stash) - 1}\x00'

    def code(match):
        return keep('<code>' + html.escape(match.group(1)) + '</code>')

    text = INLINE_CODE_RE.sub(code, text)
    text = html.escape(text, quote=False)

    def image(match):
        alt = match.group(1)
        src = html.escape(rewrite_href(match.group(2), rel, doc_rels), quote=True)
        return keep(f'<img src="{src}" alt="{alt}" loading="lazy">')

    text = IMAGE_RE.sub(image, text)

    def link(match):
        label = match.group(1)
        href = html.escape(rewrite_href(match.group(2), rel, doc_rels), quote=True)
        # 站内路由留在本页；未收录的 .md（第三方源码自带说明）与外链另开标签
        offsite = (href.startswith(('http://', 'https://')) or
                   (not href.startswith('#/') and href.split('#', 1)[0].lower().endswith('.md')))
        extra = ' target="_blank" rel="noopener"' if offsite else ''
        return keep(f'<a href="{href}"{extra}>{label}</a>')

    text = LINK_RE.sub(link, text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'(?<!\*)\*([^*\n]+)\*(?!\*)', r'<em>\1</em>', text)
    text = re.sub(r'~~([^~]+)~~', r'<del>\1</del>', text)
    text = text.replace('\n', '<br>')
    # 链接文字里可能还带行内代码（嵌套占位符），多轮展开直至收敛
    for _ in range(8):
        expanded = STASH_RE.sub(lambda m: stash[int(m.group(1))], text)
        if expanded == text:
            break
        text = expanded
    return text


def render_list(lines, rel, doc_rels):
    """按缩进生成一层嵌套的 ul/ol；同一层内 ul↔ol 切换时自动闭合重开"""
    out = []
    stack = []
    for indent, ordered, text in lines:
        tag = 'ol' if ordered else 'ul'
        depth = 2 if len(indent) >= 2 else 1
        while len(stack) > depth:
            out.append(f'</{stack.pop()}>')
        while len(stack) < depth:
            out.append(f'<{tag}>')
            stack.append(tag)
        if stack[-1] != tag:
            out.append(f'</{stack.pop()}>')
            out.append(f'<{tag}>')
            stack.append(tag)
        out.append(f'<li>{inline(text, rel, doc_rels)}</li>')
    while stack:
        out.append(f'</{stack.pop()}>')
    return ''.join(out)


def render_table(header, rows, sep, rel, doc_rels):
    aligns = []
    for cell in split_row(sep):
        left, right = cell.startswith(':'), cell.endswith(':')
        aligns.append(' style="text-align:center"' if left and right
                      else (' style="text-align:right"' if right else ''))
    parts = ['<div class="table-wrap"><table><thead><tr>']
    for index, cell in enumerate(header):
        parts.append(f'<th{aligns[index] if index < len(aligns) else ""}>'
                     f'{inline(cell, rel, doc_rels)}</th>')
    parts.append('</tr></thead><tbody>')
    for row in rows:
        parts.append('<tr>')
        for index, cell in enumerate(row):
            parts.append(f'<td{aligns[index] if index < len(aligns) else ""}>'
                         f'{inline(cell, rel, doc_rels)}</td>')
        parts.append('</tr>')
    parts.append('</tbody></table></div>')
    return ''.join(parts)


def block_start(line):
    return bool(FENCE_RE.match(line) or HEAD_RE.match(line) or HR_RE.match(line)
                or UL_RE.match(line) or OL_RE.match(line) or QUOTE_RE.match(line)
                or line.lstrip().startswith('|'))


def join_paragraph(parts):
    """中文软换行直接拼接，英文之间补空格，行尾两空格转成 <br> 标记"""
    result = ''
    for part in parts:
        if not result:
            result = part
        elif result.endswith('  '):
            result = result.rstrip() + '\n' + part
        elif re.search(r'[A-Za-z0-9)\]]$', result) and re.match(r'^[A-Za-z0-9(\[]', part):
            result += ' ' + part
        else:
            result += part
    return result


def render_markdown(text, rel, doc_rels, prefix):
    """把 Markdown 转成 HTML 片段，同时收集 h2/h3 目录"""
    lines = text.splitlines()
    out = []
    toc = []
    index = 0
    first_h1_skipped = False
    total = len(lines)

    while index < total:
        line = lines[index]
        if not line.strip():
            index += 1
            continue

        if FENCE_RE.match(line):
            index += 1
            buffer = []
            while index < total and not FENCE_RE.match(lines[index]):
                buffer.append(lines[index])
                index += 1
            index += 1
            out.append('<pre><code>' + html.escape('\n'.join(buffer)) + '</code></pre>')
            continue

        heading = HEAD_RE.match(line)
        if heading:
            level = len(heading.group(1))
            raw = heading.group(2).strip()
            if level == 1 and not first_h1_skipped:
                first_h1_skipped = True
                index += 1
                continue
            anchor = f'{prefix}-h{len(toc) + 1}'
            if level in (2, 3):
                toc.append((level, plain_text(raw), anchor))
            out.append(f'<h{level} id="{anchor}">{inline(raw, rel, doc_rels)}</h{level}>')
            index += 1
            continue

        if HR_RE.match(line):
            out.append('<hr>')
            index += 1
            continue

        if line.lstrip().startswith('|') and index + 1 < total and is_table_sep(lines[index + 1]):
            header = split_row(line)
            sep = lines[index + 1]
            index += 2
            rows = []
            while index < total and lines[index].lstrip().startswith('|') and lines[index].strip():
                rows.append(split_row(lines[index]))
                index += 1
            out.append(render_table(header, rows, sep, rel, doc_rels))
            continue

        list_match = UL_RE.match(line) or OL_RE.match(line)
        if list_match:
            items = []
            while index < total:
                candidate = UL_RE.match(lines[index]) or OL_RE.match(lines[index])
                if not candidate:
                    break
                items.append((candidate.group(1), bool(OL_RE.match(lines[index])),
                              candidate.group(2)))
                index += 1
            out.append(render_list(items, rel, doc_rels))
            continue

        if QUOTE_RE.match(line):
            buffer = []
            while index < total and QUOTE_RE.match(lines[index]):
                buffer.append(QUOTE_RE.match(lines[index]).group(1))
                index += 1
            out.append('<blockquote>' + inline(join_paragraph(buffer), rel, doc_rels) + '</blockquote>')
            continue

        buffer = [line]
        index += 1
        while index < total and lines[index].strip() and not block_start(lines[index]):
            buffer.append(lines[index])
            index += 1
        out.append('<p>' + inline(join_paragraph(buffer), rel, doc_rels) + '</p>')

    return '\n'.join(out), toc


def collect():
    """收集全部文档、状态、校验结果、最近更新与渲染后的正文"""
    paths = sorted(iter_markdown(), key=lambda p: p.relative_to(ROOT).as_posix())
    rels = [p.relative_to(ROOT).as_posix() for p in paths]
    doc_rels = set(rels)
    check_file = load_check_file()
    dates = git_dates()

    entries = {key: [] for key, _title, _desc in GROUPS}
    for position, (path, rel) in enumerate(zip(paths, rels)):
        group = group_of(rel)
        status = status_of(rel, group)
        title, summary, label = read_meta(path, rel)
        text = path.read_text(encoding='utf-8', errors='replace')
        body, toc = render_markdown(text, rel, doc_rels, f'sec-{position}')

        if group == 'history' or rel in CHECK_SKIP:
            problems = []
            check_state = 'skip'
        else:
            problems = check_file(path)
            check_state = 'issues' if problems else 'pass'

        updated = dates.get(rel) or datetime.fromtimestamp(path.stat().st_mtime).strftime('%Y-%m-%d')
        entries[group].append({
            'rel': rel,
            'href': os.path.relpath(path, DOCS).replace(os.sep, '/'),
            'title': title,
            'summary': summary,
            'label': label,
            'size': size_text(path),
            'group': group,
            'category': DOC_CATEGORY_OF.get(rel, 'other') if group == 'docs' else '',
            'status': status,
            'check': check_state,
            'issues': [detail for _source, detail in problems],
            'updated': updated,
            'body': body,
            'toc': toc,
            'sections': len(toc),
        })

    priority = {'docs/README.md': 0, 'docs/browser-local-roadmap.md': 1}
    for items in entries.values():
        items.sort(key=lambda item: (priority.get(item['rel'], 9), item['rel']))
    return entries


def badge(status):
    text = dict((key, title) for key, title, _desc in STATUS)[status]
    return f'<span class="badge st-{status}"><i></i>{html.escape(text)}</span>'


def esc(value):
    return html.escape(str(value), quote=True)


def nav_link(item):
    return (
        f'<a href="#/doc/{esc(item["rel"])}" data-doc="{esc(item["rel"])}" '
        f'data-text="{esc((item["title"] + " " + item["rel"] + " " + item["label"]).lower())}" '
        f'title="{esc(item["rel"])}">'
        f'<i class="dot dot-{item["status"]}"></i>'
        f'<span>{html.escape(item["title"])}</span></a>'
    )


def category_title(key):
    if not key:
        return '—'
    return dict((k, title) for k, title, _desc in DOC_CATEGORIES).get(key, '未分类')


def render_nav(entries):
    parts = ['<a class="nav-home" href="#/overview" data-view="overview">'
             '<span class="nav-ico">▦</span>总览<em>Overview</em></a>']
    for key, title, _desc in GROUPS:
        items = entries[key]
        parts.append(f'<div class="nav-group" data-group="{key}">')
        parts.append('<button type="button" class="nav-group-head" data-toggle>'
                     f'<span class="chev">▾</span>{html.escape(title)}'
                     f'<span class="nav-count">{len(items)}</span></button>')
        if key == 'docs':
            # 项目文档按用途再分一层；未配置分类的落到「未分类」，生成时会告警
            for cat_key, cat_title, cat_desc in DOC_CATEGORIES:
                members = [item for item in items if item['category'] == cat_key]
                if not members:
                    continue
                parts.append(f'<div class="nav-sub" data-category="{cat_key}">')
                parts.append('<button type="button" class="nav-subhead" data-toggle '
                             f'title="{esc(cat_desc)}"><span class="chev">▾</span>'
                             f'{html.escape(cat_title)}'
                             f'<span class="nav-count">{len(members)}</span></button>')
                parts.append('<div class="nav-items">'
                             + '\n'.join(nav_link(item) for item in members)
                             + '</div></div>')
        else:
            parts.append('<div class="nav-items">'
                         + '\n'.join(nav_link(item) for item in items)
                         + '</div>')
        parts.append('</div>')
    return '\n'.join(parts)


def render_overview(entries, generated_at):
    items = [item for group in entries.values() for item in group]
    total = len(items)
    counts = {key: sum(1 for item in items if item['status'] == key) for key, _t, _d in STATUS}
    passed = sum(1 for item in items if item['check'] == 'pass')
    issues = sum(1 for item in items if item['check'] == 'issues')
    skipped = sum(1 for item in items if item['check'] == 'skip')
    issue_files = [item for item in items if item['check'] == 'issues']
    docs_items = [item for item in items if item['group'] == 'docs']
    category_counts = {
        key: sum(1 for item in docs_items if item['category'] == key)
        for key, _title, _desc in DOC_CATEGORIES
    }
    cat_buttons = '\n'.join(
        f'<button type="button" class="cf" data-cf="{key}">{html.escape(title)} '
        f'{category_counts[key]}</button>'
        for key, title, _desc in DOC_CATEGORIES if category_counts[key]
    )

    cards = [
        ('文档总数', total, f'覆盖 {len(GROUPS)} 个分组 · 仅项目自身文档', 'plain'),
        ('现行维护', counts['current'], '随代码同步更新的有效文档', 'ok'),
        ('规划中', counts['planning'], '下一分支路线，不代表主干现状', 'plan'),
        ('历史归档', counts['archived'], '只读，描述重构前状态，不再更新', 'muted'),
    ]
    stat_html = '\n'.join(
        f'<div class="stat stat-{tone}"><div class="stat-num">{value}</div>'
        f'<div class="stat-label">{html.escape(label)}</div>'
        f'<div class="stat-note">{html.escape(note)}</div></div>'
        for label, value, note, tone in cards
    )

    check_cards = (
        f'<div class="check-line"><span class="badge ck-pass">校验通过</span>'
        f'<b>{passed}</b> 篇链接 / 路径 / 命令均有效</div>'
        f'<div class="check-line"><span class="badge ck-issues">待处理</span>'
        f'<b>{issues}</b> 篇发现问题'
        + ('<span class="issue-names">'
           + '、'.join(html.escape(i['rel']) for i in issue_files[:4])
           + ('…' if len(issue_files) > 4 else '') + '</span>' if issue_files else '')
        + f'</div>'
        f'<div class="check-line"><span class="badge ck-skip">免校验</span>'
        f'<b>{skipped}</b> 篇历史归档 / 变更记录按约定不参与校验；'
        f'现行文档以校验结果为准</div>'
    )

    bar_parts = []
    for key, title, _desc in STATUS:
        percent = counts[key] / total * 100 if total else 0
        bar_parts.append(
            f'<div class="bar-row"><span class="bar-label">{html.escape(title)}</span>'
            f'<div class="bar-track"><div class="bar-fill bar-{key}" style="width:{percent:.1f}%"></div></div>'
            f'<span class="bar-num">{counts[key]}</span></div>'
        )

    recent = sorted(items, key=lambda item: (item['updated'], item['rel']), reverse=True)[:8]
    recent_html = '\n'.join(
        f'<li><a href="#/doc/{esc(item["rel"])}">{html.escape(item["title"])}</a>'
        f'<span><time class="upd">{item["updated"]}</time></span></li>'
        for item in recent
    )

    quick_html = '\n'.join(
        f'<a class="quick" href="#/doc/{esc(rel)}"><span>{html.escape(title)}</span>'
        f'<small>{esc(rel)}</small></a>'
        for title, rel in QUICK_LINKS
    )

    legend = '\n'.join(
        f'<span class="legend-item"><i class="dot dot-{key}"></i>{html.escape(title)}'
        f'<small>{html.escape(desc)}</small></span>'
        for key, title, desc in STATUS
    )

    rows = []
    for item in items:
        check_badge = {
            'pass': '<span class="badge ck-pass">通过</span>',
            'issues': f'<span class="badge ck-issues">{len(item["issues"])} 处问题</span>',
            'skip': '<span class="badge ck-skip">免校验</span>',
        }[item['check']]
        group_title = dict((key, title) for key, title, _desc in GROUPS)[item['group']]
        cat = item['category']
        rows.append(
            f'<tr data-status="{item["status"]}" data-check="{item["check"]}" '
            f'data-category="{cat}" '
            f'data-text="{esc((item["title"] + " " + item["rel"] + " " + group_title + " " + category_title(cat)).lower())}">'
            f'<td>{badge(item["status"])}</td>'
            f'<td><a href="#/doc/{esc(item["rel"])}">{html.escape(item["title"])}</a>'
            f'<small>{esc(item["rel"])}</small></td>'
            f'<td>{html.escape(group_title)}</td>'
            f'<td>{html.escape(category_title(cat))}</td>'
            f'<td>{check_badge}</td>'
            f'<td><time class="upd">{item["updated"]}</time></td>'
            f'<td>{esc(item["size"])}</td></tr>'
        )

    return f'''<div class="hero">
  <div class="eyebrow">MUSIC HELPER / DOCUMENTATION</div>
  <h1>文档中心</h1>
  <p>项目自身文档的离线索引与阅读器。左侧点选即可切换文档，项目文档再按「使用与操作 / 开发与规则 / 排错与运维 / 规划与路线」分类；首页汇总每篇文档的维护状态、校验结果与最近更新。<code>third_party/</code> 下的上游源码自带文档不收录。</p>
  <div class="hero-meta"><span class="pill">共 {total} 篇</span>
    <span class="pill">不含第三方源码文档</span>
    <span class="pill">生成于 {generated_at}</span>
    <span class="pill">纯静态 · 无外部依赖</span></div>
</div>
<div class="stat-grid">{stat_html}</div>

<section class="panel">
  <div class="panel-head"><div><h2>校验概况</h2>
    <p>复用 <code>scripts/check_docs.py</code> 的唯一实现，在生成时逐篇检查相对链接、反引号路径与代码块命令。</p></div>
    <a class="text-link" href="#/doc/docs/README.md">文档约定 ↗</a></div>
  <div class="check-grid">{check_cards}</div>
</section>

<section class="panel">
  <div class="panel-head"><div><h2>文档状态一览</h2>
    <p>状态 = 生命周期分类 + 校验结果 + git 最近提交日期；点击任意一行直接打开该文档。</p></div>
    <input id="table-q" type="search" placeholder="筛选标题或路径…" autocomplete="off"></div>
  <div class="legend">{legend}</div>
  <div class="table-filter">
    <button type="button" class="sf active" data-sf="all">全部 {total}</button>
    <button type="button" class="sf" data-sf="current">现行 {counts['current']}</button>
    <button type="button" class="sf" data-sf="planning">规划中 {counts['planning']}</button>
    <button type="button" class="sf" data-sf="archived">历史归档 {counts['archived']}</button>
    <button type="button" class="sf" data-sf="issues">有校验问题 {issues}</button>
  </div>
  <div class="cat-filter"><span class="cat-label">项目文档分类</span>
    <button type="button" class="cf active" data-cf="all">全部 {len(docs_items)}</button>
    {cat_buttons}
    <small>按分类筛选时只显示项目文档</small>
  </div>
  <div class="table-wrap"><table class="status-table">
    <thead><tr><th>状态</th><th>文档</th><th>分组</th><th>分类</th><th>校验</th><th>最近更新</th><th>大小</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table></div>
  <p class="table-empty" id="table-empty">没有匹配的文档。</p>
</section>

<div class="two-col">
  <section class="panel"><div class="panel-head"><div><h2>状态分布</h2>
    <p>按生命周期分类统计</p></div></div><div class="bars">{''.join(bar_parts)}</div></section>
  <section class="panel"><div class="panel-head"><div><h2>最近更新</h2>
    <p>按最近一次提交日期排序</p></div></div><ul class="recent">{recent_html}</ul></section>
</div>

<section class="panel"><div class="panel-head"><div><h2>快速入口</h2>
  <p>按问题找文档，摘自 <a href="#/doc/docs/README.md">docs/README.md</a></p></div></div>
  <div class="quick-grid">{quick_html}</div></section>

<footer class="page-foot">
  <p>本页由 <code>scripts/build_docs_index.py</code> 生成，请勿手工编辑；新增或移动文档后执行
    <code>python scripts/build_docs_index.py</code> 重新生成，再运行 <code>python scripts/check_docs.py</code> 校验链接。</p>
  <p><code>--check</code> 会忽略生成时间与最近更新日期，避免浅克隆环境误报索引过期。</p>
</footer>'''


def render_article(item):
    group_title = dict((key, title) for key, title, _desc in GROUPS)[item['group']]
    cat = item['category']
    crumb = (html.escape(group_title)
             + (f' <span>/</span> {html.escape(category_title(cat))}' if cat else '')
             + f' <span>/</span> {esc(item["rel"])}')
    check_badge = {
        'pass': '<span class="badge ck-pass">校验通过</span>',
        'issues': f'<span class="badge ck-issues">{len(item["issues"])} 处问题</span>',
        'skip': '<span class="badge ck-skip">免校验</span>',
    }[item['check']]
    issue_html = ''
    if item['issues']:
        issue_html = ('<div class="issue-box"><b>校验发现的问题：</b><ul>'
                      + ''.join(f'<li>{html.escape(detail)}</li>' for detail in item['issues'])
                      + '</ul></div>')
    toc = ''
    if item['toc']:
        toc = ('<aside class="doc-toc"><div class="toc-title">本页目录</div><ul>'
               + ''.join(
                   f'<li class="lv{level}"><a href="#/doc/{esc(item["rel"])}::{anchor}">'
                   f'{html.escape(text)}</a></li>'
                   for level, text, anchor in item['toc']
               )
               + '</ul></aside>')

    return f'''<article class="doc" data-doc="{esc(item["rel"])}" hidden>
  <div class="doc-head">
    <div class="crumb">{crumb}</div>
    <h1>{html.escape(item["title"])}</h1>
    <p class="doc-summary">{html.escape(item["summary"])}</p>
    <div class="doc-meta">{badge(item["status"])}{check_badge}
      <span>最近更新 <time class="upd">{item["updated"]}</time></span>
      <span>{esc(item["size"])}</span><span>{item["sections"]} 个小节</span>
      <a class="raw" href="{esc(item["href"])}" target="_blank" rel="noopener">打开原始 Markdown ↗</a>
    </div>
  </div>{issue_html}
  <div class="doc-layout"><div class="doc-body">{item["body"]}</div>{toc}</div>
  <div class="doc-foot"><a href="#/overview">← 返回总览</a>
    <a href="{esc(item["href"])}" target="_blank" rel="noopener">查看源文件 {esc(item["rel"])} ↗</a></div>
</article>'''


def render(entries, generated_at):
    total = sum(len(items) for items in entries.values())
    nav = render_nav(entries)
    overview = render_overview(entries, generated_at)
    articles = '\n'.join(
        render_article(item) for group in entries.values() for item in group
    )
    return (TEMPLATE.replace('__GENERATED_AT__', generated_at)
                    .replace('__TOTAL__', str(total))
                    .replace('__NAV__', nav)
                    .replace('__OVERVIEW__', overview)
                    .replace('__ARTICLES__', articles))


TEMPLATE = r'''<!DOCTYPE html>
<!-- generated-at: __GENERATED_AT__ -->
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Music Helper 文档中心</title>
<style>
:root { color-scheme: light;
  --bg:#f5f7fa; --panel:#fff; --panel-2:#f9fafc; --text:#1b2028; --muted:#6b7684;
  --line:#e2e7ee; --accent:#2563eb; --soft:#eaf0ff; --code:#f2f4f8;
  --ok:#12805c; --ok-soft:#e4f5ee; --warn:#b45309; --warn-soft:#fff2dc;
  --plan:#6d4bd8; --plan-soft:#f0eaff; --ro:#6b7684; --ro-soft:#edf0f4;
  --shadow:0 1px 2px rgba(20,30,50,.05),0 8px 24px rgba(20,30,50,.04); }
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) { color-scheme: dark;
    --bg:#11151b; --panel:#1a2029; --panel-2:#1f2631; --text:#e7ecf3; --muted:#9aa6b6;
    --line:#2c3542; --accent:#7ea6ff; --soft:#22304c; --code:#151b24;
    --ok:#4ed6a4; --ok-soft:#16382d; --warn:#f0b45c; --warn-soft:#402f18;
    --plan:#b79bff; --plan-soft:#302549; --ro:#9aa6b6; --ro-soft:#252d38;
    --shadow:none; }
}
:root[data-theme="dark"] { color-scheme: dark;
  --bg:#11151b; --panel:#1a2029; --panel-2:#1f2631; --text:#e7ecf3; --muted:#9aa6b6;
  --line:#2c3542; --accent:#7ea6ff; --soft:#22304c; --code:#151b24;
  --ok:#4ed6a4; --ok-soft:#16382d; --warn:#f0b45c; --warn-soft:#402f18;
  --plan:#b79bff; --plan-soft:#302549; --ro:#9aa6b6; --ro-soft:#252d38;
  --shadow:none; }
* { box-sizing:border-box; }
[hidden] { display:none !important; }
html { scroll-behavior:smooth; }
body { margin:0; background:var(--bg); color:var(--text);
  font:15px/1.75 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; }
a { color:var(--accent); text-decoration:none; }
a:hover { text-decoration:underline; }
code { font:13px/1.6 ui-monospace,SFMono-Regular,Consolas,"Liberation Mono",monospace;
  background:var(--code); border:1px solid var(--line); border-radius:5px; padding:1px 5px; }
pre code { display:block; background:none; border:0; padding:0; }

/* 侧栏 */
#sidebar { position:fixed; inset:0 auto 0 0; width:288px; z-index:20;
  background:var(--panel); border-right:1px solid var(--line);
  display:flex; flex-direction:column; }
.brand { padding:22px 20px 14px; border-bottom:1px solid var(--line); }
.brand-title { font-size:18px; font-weight:700; letter-spacing:.2px; }
.brand-sub { color:var(--muted); font-size:12px; margin-top:2px; letter-spacing:.4px; }
.side-search { padding:14px 16px 10px; }
#q { width:100%; padding:9px 12px; font-size:13px; border:1px solid var(--line);
  border-radius:9px; background:var(--panel-2); color:var(--text); outline:none; }
#q:focus { border-color:var(--accent); box-shadow:0 0 0 3px var(--soft); }
#nav { flex:1; overflow-y:auto; padding:4px 10px 18px; scrollbar-width:thin; }
.nav-home { display:flex; align-items:center; gap:9px; padding:9px 12px; margin:2px 0 10px;
  border-radius:9px; color:var(--text); font-weight:650; }
.nav-home em { margin-left:auto; font-style:normal; font-size:11px; color:var(--muted); font-weight:400; }
.nav-home .nav-ico { color:var(--accent); }
.nav-home:hover, .nav-home.active { background:var(--soft); color:var(--accent); text-decoration:none; }
.nav-group { margin-bottom:4px; }
.nav-group-head { width:100%; display:flex; align-items:center; gap:7px; cursor:pointer;
  background:none; border:0; color:var(--muted); font:inherit; font-size:12px; font-weight:700;
  letter-spacing:.6px; text-transform:uppercase; padding:11px 12px 6px; text-align:left; }
.nav-group-head:hover { color:var(--accent); }
.chev { font-size:11px; transition:transform .15s ease; }
.nav-group.collapsed .chev { transform:rotate(-90deg); }
.nav-group.collapsed .nav-items { display:none; }
.nav-count { margin-left:auto; background:var(--panel-2); border:1px solid var(--line);
  border-radius:999px; padding:0 7px; font-size:11px; letter-spacing:0; }
.nav-items a { display:flex; align-items:center; gap:9px; padding:6px 12px; border-radius:8px;
  color:var(--text); font-size:13px; line-height:1.5; }
.nav-items a span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.nav-items a:hover { background:var(--panel-2); text-decoration:none; }
.nav-items a.active { background:var(--soft); color:var(--accent); font-weight:650; }
.nav-sub { margin:2px 0 6px 8px; border-left:1px solid var(--line); padding-left:6px; }
.nav-subhead { width:100%; display:flex; align-items:center; gap:6px; cursor:pointer;
  background:none; border:0; color:var(--muted); font:inherit; font-size:12px; font-weight:650;
  padding:5px 8px; text-align:left; }
.nav-subhead:hover { color:var(--accent); }
.nav-subhead .chev { font-size:10px; }
.nav-sub.collapsed .nav-subhead .chev { transform:rotate(-90deg); }
.nav-sub.collapsed .nav-items { display:none; }
.nav-sub .nav-items a { font-size:12.5px; padding:5px 10px; }
.dot { display:inline-block; width:7px; height:7px; border-radius:50%; flex:none; }
.dot-current { background:var(--ok); } .dot-planning { background:var(--plan); }
.dot-archived { background:var(--ro); }
.side-foot { padding:12px 16px 16px; border-top:1px solid var(--line);
  display:flex; align-items:center; justify-content:space-between; gap:8px; }
.side-foot span { color:var(--muted); font-size:11px; }
#theme, #menu { cursor:pointer; background:var(--panel-2); color:var(--muted);
  border:1px solid var(--line); border-radius:8px; padding:5px 10px; font-size:12px; }
#theme:hover, #menu:hover { color:var(--accent); border-color:var(--accent); }
#menu { display:none; position:fixed; top:12px; left:12px; z-index:30; font-size:16px; padding:4px 11px; }
#side-mask { display:none; }

/* 主区 */
#main { margin-left:288px; min-height:100vh; }
.view, .doc { max-width:1120px; margin:0 auto; padding:34px 40px 80px; }
.hero { padding:18px 0 26px; border-bottom:1px solid var(--line); }
.eyebrow { font-size:11px; letter-spacing:2px; color:var(--accent); font-weight:700; }
.hero h1 { font-size:34px; margin:10px 0 8px; letter-spacing:.5px; }
.hero p { color:var(--muted); margin:0; max-width:760px; }
.hero-meta { display:flex; gap:8px; flex-wrap:wrap; margin-top:16px; }
.pill { font-size:12px; color:var(--accent); background:var(--soft);
  border-radius:999px; padding:3px 11px; font-weight:600; }
.stat-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin:24px 0 6px; }
.stat { background:var(--panel); border:1px solid var(--line); border-radius:14px;
  padding:16px 18px; box-shadow:var(--shadow); border-top:3px solid var(--line); }
.stat-ok { border-top-color:var(--ok); } .stat-plan { border-top-color:var(--plan); }
.stat-muted { border-top-color:var(--ro); } .stat-plain { border-top-color:var(--accent); }
.stat-num { font-size:30px; font-weight:750; line-height:1.2; }
.stat-label { font-weight:650; margin-top:2px; }
.stat-note { color:var(--muted); font-size:12px; margin-top:4px; }
.panel { background:var(--panel); border:1px solid var(--line); border-radius:14px;
  padding:20px 22px; margin-top:20px; box-shadow:var(--shadow); }
.panel-head { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; }
.panel h2 { font-size:18px; margin:0 0 3px; }
.panel-head p { color:var(--muted); font-size:13px; margin:0; }
.text-link { font-size:13px; white-space:nowrap; }
.check-grid { margin-top:16px; display:grid; grid-template-columns:1fr; gap:0; }
.check-line { display:flex; align-items:center; gap:9px; font-size:13px; color:var(--muted);
  border-top:1px solid var(--line); padding:10px 0; }
.check-line b { color:var(--text); font-size:15px; }
.issue-names { color:var(--warn); font-size:12px; }
.badge { display:inline-flex; align-items:center; gap:6px; white-space:nowrap;
  border-radius:999px; padding:2px 10px; font-size:11px; font-weight:650; }
.badge i { width:6px; height:6px; border-radius:50%; background:currentColor; }
.st-current { color:var(--ok); background:var(--ok-soft); }
.st-planning { color:var(--plan); background:var(--plan-soft); }
.st-archived { color:var(--ro); background:var(--ro-soft); }
.ck-pass { color:var(--ok); background:var(--ok-soft); }
.ck-issues { color:var(--warn); background:var(--warn-soft); }
.ck-skip { color:var(--ro); background:var(--ro-soft); }
.legend { display:flex; flex-wrap:wrap; gap:8px 22px; margin:18px 0 14px; }
.legend-item { display:flex; align-items:center; gap:7px; font-size:12px; font-weight:600; }
.legend-item small { color:var(--muted); font-weight:400; }
.table-filter { display:flex; gap:7px; flex-wrap:wrap; margin-bottom:12px; }
.sf, .cf, #table-q { cursor:pointer; border:1px solid var(--line); background:var(--panel-2);
  color:var(--muted); border-radius:999px; padding:5px 12px; font-size:12px; }
.sf:hover, .cf:hover, .sf.active, .cf.active { color:var(--accent);
  border-color:var(--accent); background:var(--soft); }
#table-q { border-radius:8px; cursor:text; min-width:190px; outline:none; }
#table-q:focus { border-color:var(--accent); }
.cat-filter { display:flex; align-items:center; gap:7px; flex-wrap:wrap;
  margin:0 0 12px; padding-top:11px; border-top:1px solid var(--line); }
.cat-label { font-size:12px; font-weight:650; color:var(--muted); margin-right:2px; }
.cat-filter small { color:var(--muted); font-size:11px; margin-left:4px; }
.table-wrap { overflow-x:auto; }
table { width:100%; border-collapse:collapse; font-size:13px; }
th, td { text-align:left; padding:9px 12px; border-bottom:1px solid var(--line); vertical-align:middle; }
th { color:var(--muted); font-size:12px; font-weight:650; background:var(--panel-2); }
tbody tr:hover { background:var(--panel-2); }
.status-table { min-width:900px; }
.status-table td:nth-child(2) a { font-weight:600; }
.status-table td:nth-child(2) small { display:block; color:var(--muted);
  font:11px/1.4 ui-monospace,SFMono-Regular,Consolas,monospace; }
.status-table td:nth-child(6), .status-table td:nth-child(7) { white-space:nowrap; }
.status-table tbody tr:last-child td { border-bottom:0; }
.table-empty { display:none; color:var(--muted); text-align:center; padding:26px 0 4px; font-size:13px; }
.two-col { display:grid; grid-template-columns:1fr 1fr; gap:20px; }
.two-col .panel { margin-top:20px; }
.bars { margin-top:18px; }
.bar-row { display:flex; align-items:center; gap:10px; margin:10px 0; font-size:12px; }
.bar-label { width:72px; color:var(--muted); flex:none; }
.bar-track { flex:1; height:9px; background:var(--panel-2); border-radius:999px; overflow:hidden; }
.bar-fill { height:100%; border-radius:999px; }
.bar-current { background:var(--ok); } .bar-planning { background:var(--plan); }
.bar-archived { background:var(--ro); }
.bar-num { width:28px; text-align:right; font-weight:650; }
.recent { list-style:none; margin:16px 0 0; padding:0; }
.recent li { display:flex; justify-content:space-between; gap:12px; padding:7px 0;
  border-bottom:1px solid var(--line); font-size:13px; }
.recent li:last-child { border-bottom:0; }
.recent span { color:var(--muted); font-size:12px; white-space:nowrap; }
.quick-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin-top:16px; }
.quick { display:block; padding:11px 13px; border:1px solid var(--line); border-radius:10px;
  background:var(--panel-2); }
.quick:hover { border-color:var(--accent); background:var(--soft); text-decoration:none; }
.quick span { display:block; font-weight:650; font-size:13px; }
.quick small { display:block; color:var(--muted); font-size:11px; margin-top:2px;
  font-family:ui-monospace,SFMono-Regular,Consolas,monospace; overflow:hidden;
  text-overflow:ellipsis; white-space:nowrap; }
.page-foot { color:var(--muted); font-size:12px; margin-top:28px; padding-top:16px;
  border-top:1px solid var(--line); }
.page-foot p { margin:5px 0; }

/* 文档正文 */
.doc-head { padding-bottom:18px; border-bottom:1px solid var(--line); }
.crumb { font-size:12px; color:var(--muted); font-family:ui-monospace,SFMono-Regular,Consolas,monospace; }
.crumb span { margin:0 5px; opacity:.6; }
.doc-head h1 { font-size:30px; margin:10px 0 4px; line-height:1.35; }
.doc-summary { color:var(--muted); margin:0 0 14px; font-size:14px; }
.doc-meta { display:flex; align-items:center; gap:10px; flex-wrap:wrap;
  font-size:12px; color:var(--muted); }
.doc-meta .raw { margin-left:auto; border:1px solid var(--line); border-radius:8px;
  padding:4px 10px; background:var(--panel-2); white-space:nowrap; }
.issue-box { margin-top:16px; background:var(--warn-soft); color:var(--warn);
  border-radius:10px; padding:12px 16px; font-size:13px; }
.issue-box ul { margin:6px 0 0; padding-left:20px; }
.doc-layout { display:grid; grid-template-columns:minmax(0,1fr) 190px; gap:36px; margin-top:26px; }
.doc-body { min-width:0; font-size:14.5px; }
.doc-body h1, .doc-body h2, .doc-body h3, .doc-body h4 { line-height:1.4; scroll-margin-top:20px; }
.doc-body h1 { font-size:25px; margin:30px 0 12px; }
.doc-body h2 { font-size:21px; margin:32px 0 12px; padding-bottom:7px; border-bottom:1px solid var(--line); }
.doc-body h3 { font-size:17px; margin:24px 0 8px; }
.doc-body h4 { font-size:15px; margin:18px 0 6px; }
.doc-body p { margin:10px 0; }
.doc-body ul, .doc-body ol { padding-left:24px; margin:10px 0; }
.doc-body li { margin:3px 0; }
.doc-body blockquote { margin:12px 0; padding:8px 16px; border-left:3px solid var(--accent);
  background:var(--panel-2); color:var(--muted); border-radius:0 8px 8px 0; }
.doc-body pre { background:var(--code); border:1px solid var(--line); border-radius:10px;
  padding:14px 16px; overflow-x:auto; font-size:12.5px; line-height:1.6; }
.doc-body hr { border:0; border-top:1px solid var(--line); margin:26px 0; }
.doc-body img { max-width:100%; border-radius:8px; border:1px solid var(--line); }
.doc-body table { margin:14px 0; font-size:13px; }
.doc-body th, .doc-body td { border:1px solid var(--line); }
.doc-body thead th { background:var(--panel-2); }
.doc-body a { text-decoration:underline; text-underline-offset:2px; }
.doc-toc { position:sticky; top:24px; align-self:start; font-size:12px;
  border-left:1px solid var(--line); padding-left:14px; max-height:calc(100vh - 60px); overflow-y:auto; }
.toc-title { color:var(--muted); font-weight:700; letter-spacing:.6px; margin-bottom:8px; }
.doc-toc ul { list-style:none; margin:0; padding:0; }
.doc-toc li { margin:5px 0; }
.doc-toc li.lv3 { padding-left:12px; opacity:.85; }
.doc-toc a { color:var(--muted); display:block; line-height:1.45; }
.doc-toc a:hover { color:var(--accent); }
.doc-foot { display:flex; justify-content:space-between; gap:12px; margin-top:44px;
  padding-top:16px; border-top:1px solid var(--line); font-size:13px; }

@media (max-width:1100px) { .doc-layout { grid-template-columns:1fr; } .doc-toc { display:none; }
  .quick-grid { grid-template-columns:repeat(2,1fr); } }
@media (max-width:900px) {
  #menu { display:block; }
  #sidebar { transform:translateX(-100%); transition:transform .2s ease; box-shadow:var(--shadow); }
  body.nav-open #sidebar { transform:translateX(0); }
  body.nav-open #side-mask { display:block; position:fixed; inset:0; z-index:15;
    background:rgba(0,0,0,.35); }
  #main { margin-left:0; padding-top:44px; }
  .view, .doc { padding:24px 20px 60px; }
  .stat-grid, .two-col { grid-template-columns:1fr 1fr; }
}
@media (max-width:600px) {
  .stat-grid, .two-col, .quick-grid { grid-template-columns:1fr; }
  .hero h1 { font-size:27px; }
  .panel { padding:16px; }
}
</style>
</head>
<body>
<button id="menu" type="button" aria-label="打开目录">☰</button>
<div id="side-mask"></div>
<aside id="sidebar">
  <div class="brand"><div class="brand-title">Music Helper</div>
    <div class="brand-sub">文档中心 · 共 __TOTAL__ 篇</div></div>
  <div class="side-search"><input id="q" type="search"
    placeholder="搜索文档…（按 / 聚焦）" autocomplete="off"></div>
  <nav id="nav">
__NAV__
  </nav>
  <div class="side-foot"><span>生成于 __GENERATED_AT__</span>
    <button id="theme" type="button" title="切换明暗主题">◐ 主题</button></div>
</aside>
<main id="main">
  <section id="view-overview" class="view">
__OVERVIEW__
  </section>
__ARTICLES__
</main>
<script>
(function () {
  var overview = document.getElementById('view-overview');
  var articles = Array.prototype.slice.call(document.querySelectorAll('article.doc'));
  var links = Array.prototype.slice.call(document.querySelectorAll('.nav-items a[data-doc]'));
  var home = document.querySelector('.nav-home');
  var search = document.getElementById('q');
  var navGroups = Array.prototype.slice.call(document.querySelectorAll('.nav-group'));
  var body = document.body;

  function route() {
    var hash = location.hash || '#/overview';
    var anchor = '';
    if (hash.indexOf('::') >= 0) {
      var pieces = hash.split('::');
      hash = pieces[0];
      anchor = pieces[1];
    }
    var rel = hash.indexOf('#/doc/') === 0 ? decodeURIComponent(hash.slice(6)) : '';
    overview.hidden = !!rel;
    var currentTitle = 'Music Helper 文档中心';
    articles.forEach(function (article) {
      var match = article.getAttribute('data-doc') === rel;
      article.hidden = !match;
      if (match) { currentTitle = article.querySelector('h1').textContent + ' · 文档中心'; }
    });
    links.forEach(function (link) {
      link.classList.toggle('active', link.getAttribute('data-doc') === rel);
    });
    home.classList.toggle('active', !rel);
    document.title = currentTitle;
    body.classList.remove('nav-open');
    if (anchor) {
      requestAnimationFrame(function () {
        var target = document.getElementById(anchor);
        if (target) { target.scrollIntoView({ block: 'start' }); }
      });
    } else {
      window.scrollTo(0, 0);
    }
  }
  window.addEventListener('hashchange', route);

  document.querySelectorAll('[data-toggle]').forEach(function (button) {
    button.addEventListener('click', function () {
      button.parentNode.classList.toggle('collapsed');
    });
  });

  search.addEventListener('input', function () {
    var q = search.value.trim().toLowerCase();
    document.querySelectorAll('.nav-sub').forEach(function (sub) {
      // 搜索时展开二级分类，否则命中的文档会被折叠遮住
      if (q) { sub.classList.remove('collapsed'); }
    });
    navGroups.forEach(function (group) {
      var shown = 0;
      group.querySelectorAll('.nav-items a').forEach(function (link) {
        var ok = !q || link.getAttribute('data-text').indexOf(q) >= 0;
        link.hidden = !ok;
        if (ok) { shown++; }
      });
      group.hidden = shown === 0;
      if (q) { group.classList.remove('collapsed'); }
    });
  });

  var filters = Array.prototype.slice.call(document.querySelectorAll('.sf'));
  var catFilters = Array.prototype.slice.call(document.querySelectorAll('.cf'));
  var tableQuery = document.getElementById('table-q');
  var rows = Array.prototype.slice.call(document.querySelectorAll('.status-table tbody tr'));
  var activeFilter = 'all';
  var activeCategory = 'all';
  function filterTable() {
    var q = tableQuery.value.trim().toLowerCase();
    var shown = 0;
    rows.forEach(function (row) {
      var status = row.getAttribute('data-status');
      var okFilter = activeFilter === 'all' ||
        (activeFilter === 'issues' && row.getAttribute('data-check') === 'issues') ||
        (activeFilter === status);
      var okCategory = activeCategory === 'all' ||
        row.getAttribute('data-category') === activeCategory;
      var ok = okFilter && okCategory &&
        (!q || row.getAttribute('data-text').indexOf(q) >= 0);
      row.hidden = !ok;
      if (ok) { shown++; }
    });
    document.getElementById('table-empty').style.display = shown ? 'none' : 'block';
  }
  filters.forEach(function (button) {
    button.addEventListener('click', function () {
      activeFilter = button.getAttribute('data-sf');
      filters.forEach(function (b) { b.classList.toggle('active', b === button); });
      filterTable();
    });
  });
  catFilters.forEach(function (button) {
    button.addEventListener('click', function () {
      activeCategory = button.getAttribute('data-cf');
      catFilters.forEach(function (b) { b.classList.toggle('active', b === button); });
      filterTable();
    });
  });
  tableQuery.addEventListener('input', filterTable);

  var menu = document.getElementById('menu');
  menu.addEventListener('click', function () { body.classList.toggle('nav-open'); });
  document.getElementById('side-mask').addEventListener('click', function () {
    body.classList.remove('nav-open');
  });

  var themeButton = document.getElementById('theme');
  try {
    var saved = localStorage.getItem('mh-docs-theme');
    if (saved) { document.documentElement.setAttribute('data-theme', saved); }
  } catch (e) { /* file:// 下可能不可用 */ }
  themeButton.addEventListener('click', function () {
    var dark = document.documentElement.getAttribute('data-theme') === 'dark' ||
      (!document.documentElement.getAttribute('data-theme') &&
       window.matchMedia('(prefers-color-scheme: dark)').matches);
    var next = dark ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    try { localStorage.setItem('mh-docs-theme', next); } catch (e) { /* 忽略 */ }
  });

  document.addEventListener('keydown', function (event) {
    if (event.key === '/' && document.activeElement !== search &&
        document.activeElement !== tableQuery) {
      event.preventDefault(); search.focus();
    }
    if (event.key === 'Escape') {
      if (document.activeElement === search) { search.value = ''; search.dispatchEvent(new Event('input')); }
      body.classList.remove('nav-open');
    }
  });

  filterTable();
  route();
})();
</script>
</body>
</html>
'''


GEN_AT_RE = re.compile(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}')
UPDATED_RE = re.compile(r'(<time class="upd">)\d{4}-\d{2}-\d{2}(</time>)')
RECENT_RE = re.compile(r'(<ul class="recent">).*?(</ul>)', re.S)
SIZE_RE = re.compile(r'\d+(?:\.\d+)?\s?(?:KB|MB)')


def strip_generated(text):
    """比较时忽略与文档内容无关的易变字段

    - 生成时间；
    - git 最近更新日期：浅克隆（CI 默认 fetch-depth=1）里会整体变成同一天，
      且「最近更新」列表的顺序也会随之改变；
    - 字节数：Windows 与 Linux checkout 的换行符不同，同一篇文档 stat 大小不同。
    正文、状态、校验结果与文档清单仍然逐字比较，所以内容变更不会被漏掉。
    """
    text = RECENT_RE.sub(r'\1<recent>\2', text)
    text = UPDATED_RE.sub(r'\1<date>\2', text)
    text = SIZE_RE.sub('<size>', text)
    return GEN_AT_RE.sub('<time>', text)


def main(argv=None):
    parser = argparse.ArgumentParser(description='生成 docs/index.html')
    parser.add_argument('--check', action='store_true', help='只检查索引是否过期，不写文件')
    args = parser.parse_args(argv)

    entries = collect()
    uncategorized = [item['rel'] for item in entries['docs'] if item['category'] == 'other']
    if uncategorized:
        print('警告：以下项目文档未配置分类，请补 scripts/build_docs_index.py 的 '
              'DOC_CATEGORY_OF：' + '、'.join(uncategorized), file=sys.stderr)
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
