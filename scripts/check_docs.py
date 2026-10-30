# -*- coding: utf-8 -*-
"""文档链接检查 - 校验 Markdown 中的相对链接是否指向真实文件

用法：
    python scripts/check_docs.py            # 检查全仓
    python scripts/check_docs.py docs       # 只检查指定目录

CI 里跑这个可以避免文档整合后留下死链（重构最容易犯的错）。
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {'.git', '.workbuddy', '.sisyphus', '__pycache__', '.pytest_cache', 'log', 'node_modules'}
# 允许指向「将来会生成」的路径（运行产物）
IGNORE_PREFIXES = ('log/', 'music.db')

LINK_RE = re.compile(r'!?\[[^\]]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)')
FENCE_RE = re.compile(r'```.*?```', re.S)


def iter_markdown(base):
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]
        for name in files:
            if name.lower().endswith('.md'):
                yield os.path.join(root, name)


def strip_fences(text):
    return FENCE_RE.sub('', text)


def check_file(path):
    problems = []
    with open(path, encoding='utf-8', errors='replace') as handle:
        text = strip_fences(handle.read())

    for match in LINK_RE.finditer(text):
        target = match.group(1).strip()
        if not target or target.startswith(('#', 'http://', 'https://', 'mailto:', 'tel:', 'data:')):
            continue
        if target.startswith(IGNORE_PREFIXES):
            continue
        cleaned = target.split('#', 1)[0].split('?', 1)[0]
        if not cleaned:
            continue
        resolved = os.path.normpath(os.path.join(os.path.dirname(path), cleaned.replace('/', os.sep)))
        if not os.path.exists(resolved):
            problems.append((path, target))
    return problems


def main(argv):
    target = os.path.join(ROOT, argv[1]) if len(argv) > 1 else ROOT
    failures = []
    count = 0
    for path in iter_markdown(target):
        count += 1
        for source, link in check_file(path):
            failures.append(f'{os.path.relpath(source, ROOT)} -> {link}')

    if failures:
        print(f'发现 {len(failures)} 个失效链接（共检查 {count} 个文件）：')
        for item in failures:
            print('  ' + item)
        return 1

    print(f'文档链接检查通过（{count} 个 Markdown 文件）')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
