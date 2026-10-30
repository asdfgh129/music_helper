# -*- coding: utf-8 -*-
"""music_tagger 内部工具（避免依赖包外的 utils）

该包原本写的是 `from ..utils import split_artist`，越出了顶层包范围，
导致 `import music_tagger` 直接 ImportError。这里补一个包内实现。
"""


def split_artist(artist):
    """拆分多艺术家字符串"""
    if not artist:
        return []
    separators = ['；', ';', '，', ',', '&', '/', '、', '•', '·', '|', '｜', '+', '＋']
    result = [str(artist)]
    for sep in separators:
        new_result = []
        for item in result:
            new_result.extend([part.strip() for part in item.split(sep)])
        result = new_result
    return [part for part in result if part]
