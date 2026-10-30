# -*- coding: utf-8 -*-
"""
标签匹配评分模块 - 纯计算，无网络依赖

供 services.tagger 在多个平台候选中择优，也便于单独单测。
"""

from core.naming import split_artist, normalize_text


def match_score(local, online):
    """字符串匹配得分：2 完全相同 / 1 包含 / 0 不匹配"""
    local = normalize_text(local)
    online = normalize_text(online)
    if not local or not online:
        return 0
    if local == online:
        return 2
    if local in online or online in local:
        return 1
    return 0


def match_artist(local, online):
    """多艺术家匹配：取与任一在线艺术家匹配的最高分"""
    online_artists = split_artist(online)
    if not online_artists:
        return match_score(local, online)
    return max(match_score(local, name) for name in online_artists)


def tag_score(tags, query_title, query_artist):
    """标签质量分（0-100）：完整性 40 分 + 匹配度 60 分"""
    score = 0

    for key, weight in (('title', 10), ('artist', 10), ('album', 10), ('year', 5), ('genre', 5)):
        if tags.get(key):
            score += weight

    title_score = match_score(query_title, tags.get('title', ''))
    score += 30 if title_score == 2 else 20 if title_score == 1 else 0

    if query_artist and tags.get('artist'):
        if match_artist(query_artist, tags['artist']) >= 1:
            score += 30

    return score
