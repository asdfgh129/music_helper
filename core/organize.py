# -*- coding: utf-8 -*-
"""
归档模块 - 合并 file_operations.organize_by_year 与 archive.move_to_dir

规则：按年份建立 <年代>/<年份>/ 两级目录，例如 1980-1989/1985/。
缺少 歌手/歌名/年份 的曲目进入 unknown 目录，等待人工处理。
"""

import os

UNKNOWN_DIRNAME = 'unknown'
REQUIRED_TAG_FIELDS = ('title', 'artist', 'year')


def decade_label(year):
    """年份 -> 年代目录名"""
    if year <= 1979:
        return '1950-1979'
    decade = (year // 10) * 10
    return f'{decade}-{decade + 9}'


def missing_fields(track):
    """返回缺失的必要标签字段（中文名），用于报告"""
    labels = {'title': '歌曲名', 'artist': '歌手', 'year': '年份'}
    return [labels[key] for key in REQUIRED_TAG_FIELDS if not track.tag(key)]


def target_path(track, base_dir):
    """计算出归档目标路径；无法归档返回 None"""
    if missing_fields(track):
        return None
    year = track.year_int
    if not year:
        return None
    return os.path.join(base_dir, decade_label(year), str(year), track.filename)


def unknown_path(track, base_dir):
    return os.path.join(base_dir, UNKNOWN_DIRNAME, track.filename)


def plan_organize(tracks, base_dir, plan, sort_unknown=True):
    """把归档动作写入 plan

    Returns:
        (organized, unknown) 两个 Track 列表
    """
    organized, unknown = [], []
    for track in tracks:
        dst = target_path(track, base_dir)
        if dst is None:
            unknown.append(track)
            if sort_unknown:
                plan.add_move(track.path, unknown_path(track, base_dir),
                              reason=f'标签不全({"/".join(missing_fields(track))})')
            continue
        plan.add_move(track.path, dst, reason=f'按年份归档 {track.year_int}')
        organized.append(track)
    return organized, unknown
