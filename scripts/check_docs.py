# -*- coding: utf-8 -*-
"""文档校验 - 确认文档没跟代码脱节

三类检查：
1. **相对链接**是否指向真实文件（重构最容易留下的死链）；
2. **正文里 `core/check.py` 这类反引号路径**是否还存在（模块搬家/改名后最常见的漂移）；
3. **代码块里的 `python xxx.py` 命令**，脚本是否还在。

用法：
    python scripts/check_docs.py            # 检查全仓
    python scripts/check_docs.py docs       # 只检查指定目录

豁免：
- `docs/history/` 与 `CHANGELOG.md` 记录的是历史状态，按约定不校验；
- 「别的仓库 / 运行期产物」路径（见 EXTERNAL_PREFIXES）不校验。
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {'.git', '.workbuddy', '.sisyphus', '__pycache__', '.pytest_cache', 'log', 'node_modules', 'history'}
# 允许指向「将来会生成」的路径（运行产物）
IGNORE_PREFIXES = ('log/', 'music.db')

# 记录历史状态的文档不参与存在性校验（CHANGELOG 里写的是当时有什么）
SKIP_FILES = {'CHANGELOG.md'}
# 引用的是别的仓库或运行期产物，本仓库里本来就没有
EXTERNAL_PREFIXES = ('log/', 'nodes/', 'runtime/', '.workbuddy/', 'src/', '~/',
                     'available_', 'pool_', 'conversion_log.csv',
                     'Doc/')  # 历史归档里记录的「原文件名」
CHECK_EXTS = {'.py', '.md', '.yml', '.yaml', '.toml', '.txt', '.json',
              '.bat', '.exe', '.js', '.flac', '.cfg', '.ini'}

LINK_RE = re.compile(r'!?\[[^\]]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)')
FENCE_RE = re.compile(r'```.*?```', re.S)
FENCE_BLOCK_RE = re.compile(r'```[^\n]*\n(.*?)```', re.S)
# 反引号里的「带斜杠的仓库内路径」，如 `core/check.py`、`docs/git-proxy.md`
CODE_PATH_RE = re.compile(r'`([A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)+\.[A-Za-z0-9]+)`')
# 代码块里的 python 调用
CMD_RE = re.compile(r'\bpython3?\s+([A-Za-z0-9_./\-]+\.py)')


def iter_markdown(base):
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]
        for name in files:
            if name.lower().endswith('.md'):
                yield os.path.join(root, name)


def strip_fences(text):
    return FENCE_RE.sub('', text)


def _exists_anywhere(ref, doc_path):
    """仓库根或文档同级目录能解析到就算存在。"""
    candidates = (
        os.path.join(ROOT, ref.replace('/', os.sep)),
        os.path.join(os.path.dirname(doc_path), ref.replace('/', os.sep)),
    )
    return any(os.path.exists(path) for path in candidates)


def _skip_ref(ref):
    return ref.startswith(EXTERNAL_PREFIXES) or 'YYYY' in ref or '\\' in ref


def check_links(path, text):
    problems = []
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
            problems.append((path, f'链接失效 -> {target}'))
    return problems


def check_code_paths(path, text):
    """反引号里的仓库内路径是否存在。"""
    problems = []
    for ref in CODE_PATH_RE.findall(strip_fences(text)):
        if os.path.splitext(ref)[1].lower() not in CHECK_EXTS:
            continue
        if _skip_ref(ref) or _exists_anywhere(ref, path):
            continue
        problems.append((path, f'路径不存在 -> {ref}'))
    return problems


def check_commands(path, text):
    """代码块里 `python xxx.py` 的脚本是否存在。"""
    problems = []
    for block in FENCE_BLOCK_RE.findall(text):
        for script in CMD_RE.findall(block):
            if script.startswith(('.', '/')) or _skip_ref(script):
                continue
            if not _exists_anywhere(script, path):
                problems.append((path, f'命令里的脚本不存在 -> {script}'))
    return problems


def check_file(path):
    with open(path, encoding='utf-8', errors='replace') as handle:
        text = handle.read()
    problems = check_links(path, text)
    problems += check_code_paths(path, text)
    problems += check_commands(path, text)
    return problems


def main(argv):
    target = os.path.join(ROOT, argv[1]) if len(argv) > 1 else ROOT
    failures = []
    count = 0
    for path in iter_markdown(target):
        if os.path.basename(path) in SKIP_FILES:
            continue
        count += 1
        for source, detail in check_file(path):
            failures.append(f'{os.path.relpath(source, ROOT)}: {detail}')

    if failures:
        print(f'发现 {len(failures)} 处问题（共检查 {count} 个文件）：')
        for item in failures:
            print('  ' + item)
        return 1

    print(f'文档校验通过（{count} 个 Markdown 文件：链接 + 路径 + 命令）')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
