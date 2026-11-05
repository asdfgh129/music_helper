# -*- coding: utf-8 -*-
"""库目录状态判定 - 「库是否已初始化」的唯一判据

在本项目里，一个可用的音乐库只需要两件事：

1. **目录结构可用**：库目录存在，能按 `<年代>/<年份>/` 归档（见 `core.organize`）；
2. **声纹库存在**：`music.db` 是去重与「库是否已有这首」的比对基准。

本模块只做只读判定并给出建议动作，真正创建目录 / 建库由 `services.steps` 执行
（`core/` 不写盘）。判定规则集中在这里，`web/` 与 CLI 都从这里取，避免两边各判一套。
"""

import os
import re
from datetime import datetime

DECADE_RE = re.compile(r'^(\d{4})-(\d{4})$')
YEAR_RE = re.compile(r'^(19|20)\d{2}$')
UNKNOWN_DIRNAME = 'unknown'

# 统计音频文件时的扫描上限：两万首足够判断「库是不是空的」，
# 再大的库没必要为了一个状态徽标把整个目录走完。
AUDIO_COUNT_LIMIT = 20000


def decade_dirs(directory):
    """列出 `<年代>/<年份>` 结构，返回 [{name, years: [...]}]"""
    result = []
    try:
        entries = sorted(os.listdir(directory))
    except OSError:
        return result
    for name in entries:
        path = os.path.join(directory, name)
        if not os.path.isdir(path) or not DECADE_RE.match(name):
            continue
        years = []
        try:
            for child in sorted(os.listdir(path)):
                if YEAR_RE.match(child) and os.path.isdir(os.path.join(path, child)):
                    years.append(child)
        except OSError:
            pass
        result.append({'name': name, 'years': years})
    return result


def count_audio(directory, limit=AUDIO_COUNT_LIMIT):
    """统计音频文件数量（带上限，返回 (count, truncated)）"""
    from core.naming import is_audio
    from core.scan import SKIP_DIRS

    count = 0
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]
        for name in files:
            if is_audio(name):
                count += 1
                if count >= limit:
                    return count, True
    return count, False


def db_info(db_path):
    """声纹库现状"""
    info = {'path': db_path, 'exists': False, 'size': 0, 'mtime_str': ''}
    try:
        stat = os.stat(db_path)
    except OSError:
        return info
    info['exists'] = True
    info['size'] = stat.st_size
    info['mtime_str'] = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M')
    return info


def status(library_dir, db_path=''):
    """库目录是否已初始化

    「已初始化」= 目录存在，且（已有 `<年代>/<年份>` 结构 或 至少有音频文件）。
    声纹库缺失不算未初始化——它是可单独补建的，会作为建议列在 `problems` 里。
    """
    directory = str(library_dir or '')
    info = {
        'dir': directory,
        'exists': False,
        'is_dir': False,
        'audio_count': 0,
        'count_truncated': False,
        'decades': [],
        'year_count': 0,
        'has_year_layout': False,
        'has_unknown': False,
        'db': db_info(db_path) if db_path else db_info(''),
        'initialized': False,
        'problems': [],
        'suggestions': [],
    }

    if not directory:
        info['problems'].append('库目录未配置')
        return info

    info['exists'] = os.path.exists(directory)
    info['is_dir'] = os.path.isdir(directory)
    if not info['is_dir']:
        info['problems'].append(
            f'库目录不存在：{directory}' if not info['exists']
            else f'该路径不是目录：{directory}')
        return info

    info['decades'] = decade_dirs(directory)
    info['year_count'] = sum(len(item['years']) for item in info['decades'])
    info['has_year_layout'] = bool(info['decades'])
    info['has_unknown'] = os.path.isdir(os.path.join(directory, UNKNOWN_DIRNAME))
    info['audio_count'], info['count_truncated'] = count_audio(directory)

    info['initialized'] = bool(info['has_year_layout'] or info['audio_count'])

    if not info['initialized']:
        info['problems'].append('库目录是空的：既没有音频文件，也没有 <年代>/<年份> 结构')
        info['suggestions'].append('执行「初始化」创建目录结构，并按需建立声纹库')
    elif not info['has_year_layout']:
        info['suggestions'].append('库里还没有 <年代>/<年份> 结构，归档后会自动生成')
    if not info['db']['exists']:
        info['suggestions'].append('声纹库不存在：初始化或「归档 → 入库」前建议先建库')
    return info


def init_actions(status_info):
    """根据状态给出初始化动作清单（供界面展示「将要做什么」）"""
    actions = []
    if not status_info.get('is_dir'):
        actions.append({'key': 'mkdir', 'label': '创建库目录',
                        'detail': status_info.get('dir', '')})
    if not status_info.get('has_year_layout'):
        actions.append({'key': 'layout', 'label': '建立归档结构',
                        'detail': f'{UNKNOWN_DIRNAME}/ 与流水线所需的工作/暂存目录'})
    if not status_info.get('db', {}).get('exists'):
        actions.append({'key': 'db', 'label': '建立声纹库',
                        'detail': '扫描库目录写入指纹，供去重比对'})
    else:
        actions.append({'key': 'db-refresh', 'label': '刷新声纹库',
                        'detail': '补充库里新增的文件（已有指纹不重算）'})
    return actions
