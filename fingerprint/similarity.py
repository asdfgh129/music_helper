# -*- coding: utf-8 -*-
"""相似度打分（移植自 MusicBrainz Picard）

纯函数，不做 IO、不依赖包内其他模块，因此可以单独测、单独调参。
`acoustid._find_best_match()` 把这些分数按权重线性组合成「候选录音与本地文件的
匹配度」，权重表也在那里维护——本模块只回答「这两样东西有多像」。

两处容易看错的地方：

1. `similarity2` 是**词袋式**匹配，不是纯编辑距离：按 `\\W+` 切词后逐个找最佳配对，
   高相似（>0.6）的配对会被消耗掉，最后除以 `alen + len(blist) * 0.4`——分母里
   剩下的词按 0.4 折算，所以「多出来的词」只扣 40%，比漏词轻。
2. `length_score` 的阈值写死在函数内（30 秒），超出后线性归零，不是超出即 0。
"""

import re
from datetime import datetime
from typing import List, Optional, Tuple

_split_words_re = re.compile(r'\W+', re.UNICODE)


def normalize(orig_string: str) -> str:
    """标准化字符串：转小写并去掉非字母数字字符；全被去掉时回退原文"""
    string = re.sub(r'[^a-zA-Z0-9]', '', orig_string.lower())
    if not string:
        string = orig_string
    return string


def _string_similarity(a: str, b: str) -> float:
    """两个词的相似度（Levenshtein 距离归一化到 0-1）"""
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0

    len_a, len_b = len(a), len(b)
    if len_a == 0 or len_b == 0:
        return 0.0

    dp = [[0] * (len_b + 1) for _ in range(len_a + 1)]
    for i in range(len_a + 1):
        dp[i][0] = i
    for j in range(len_b + 1):
        dp[0][j] = j

    for i in range(1, len_a + 1):
        for j in range(1, len_b + 1):
            if a[i - 1] == b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1]) + 1

    max_len = max(len_a, len_b)
    return 1.0 - (dp[len_a][len_b] / max_len)


def similarity2(a: str, b: str) -> float:
    """多词字符串的相似度（0.0-1.0），按词袋配对而非整串编辑距离"""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0

    alist = list(filter(bool, _split_words_re.split(a.lower())))
    blist = list(filter(bool, _split_words_re.split(b.lower())))

    alen, blen = len(alist), len(blist)
    if not alen or not blen:
        return 0.0
    if alen > blen:
        alist, blist = blist, alist
        alen, blen = blen, alen

    score = 0.0
    for av in alist:
        ms = 0.0
        mp = None
        for position, bv in enumerate(blist):
            s = _string_similarity(av, bv)
            if s > ms:
                ms = s
                mp = position
        if mp is not None:
            score += ms
            if ms > 0.6:
                del blist[mp]

    return score / (alen + len(blist) * 0.4)


def length_score(a: int, b: int) -> float:
    """时长相似度（毫秒）：30 秒内线性递减，超出归零"""
    if a is None or b is None:
        return 0.0
    LENGTH_SCORE_THRES_MS = 30000
    return 1.0 - min(abs(a - b), LENGTH_SCORE_THRES_MS) / float(LENGTH_SCORE_THRES_MS)


def trackcount_score(actual: int, expected: int) -> float:
    """曲目数相似度：实际多于候选得 0（不可能），少于得 0.3，相同得 1.0"""
    if actual > expected:
        return 0.0
    elif actual < expected:
        return 0.3
    else:
        return 1.0


def extract_year_from_date(dt: str) -> Optional[int]:
    """从各种日期写法里取年份，解析不了返回 None"""
    try:
        if isinstance(dt, str):
            dt = dt.strip()
            date_formats = [
                "%Y",
                "%Y-%m",
                "%Y-%m-%d",
                "%Y.%m",
                "%Y.%m.%d",
                "%Y/%m/%d",
                "%d.%m.%Y",
                "%m/%d/%Y",
                "%m.%d.%Y",
                "%d/%m/%Y",
            ]
            for fmt in date_formats:
                try:
                    parsed_date = datetime.strptime(dt, fmt)
                    return parsed_date.year
                except ValueError:
                    continue
        return None
    except (ValueError, TypeError):
        return None


def linear_combination_of_weights(parts: List[Tuple[float, int]]) -> float:
    """加权平均；value 必须在 0-1，权重必须非负"""
    total = 0.0
    sum_of_products = 0.0
    for value, weight in parts:
        if value < 0.0:
            raise ValueError("Value must be greater than or equal to 0.0")
        if value > 1.0:
            raise ValueError("Value must be lesser than or equal to 1.0")
        if weight < 0:
            raise ValueError("Weight must be greater than or equal to 0.0")
        total += weight
        sum_of_products += value * weight
    if total == 0.0:
        return 0.0
    return sum_of_products / total


def get_score(track: dict) -> float:
    """录音的搜索分数归一到 0-1；缺省 1.0"""
    return track.get('score', 1.0) / 100.0 if track.get('score') else 1.0


def artist_credit_from_node(artist_credits: List[dict]) -> Tuple[str, List[str]]:
    """从 artist-credit 节点拼出「艺术家串 + 名称列表」"""
    artists = []
    names = []
    for artist_credit in artist_credits:
        artist = artist_credit.get('artist', {})
        name = artist.get('name', '')
        artists.append(name)
        names.append(name)
        if 'joinphrase' in artist_credit:
            artists[-1] += artist_credit['joinphrase']
    return (' '.join(artists), names)
