# -*- coding: utf-8 -*-
"""在线音乐平台客户端（QQ 音乐 / 网易云）

只保留主流程仍在使用的两个平台：酷狗/酷我/咪咕客户端已删除（上游接口不可用）。

**本文件刻意不做顶层转导出，改用模块级 `__getattr__` 惰性取属性。** 原因：
`netease.py` 依赖 pycryptodomex（Cryptodome）做请求签名，`qqmusic.py` 不需要。
若在包初始化时就 `from .netease import ...`，那么缺 Cryptodome 时连 QQ 音乐
客户端都会导入失败，`tagger.Tagger` 的 try/except 会把两个平台一起降级——
表现为「少装一个只有网易云才用的库，QQ 音乐也跟着废掉」。
惰性取属性可同时兼容下面两种写法，且都不会误触发 netease：

    from tagger.platforms import QQMusicApi
    from tagger.platforms.qqmusic import QQMusicApi
"""

_LAZY = {
    'QQMusicApi': '.qqmusic',
    'NetEaseMusicClient': '.netease',
}

__all__ = ['NetEaseMusicClient', 'QQMusicApi']


def __getattr__(name):
    """按需导入平台客户端（PEP 562），避免包初始化时牵连 Cryptodome"""
    module = _LAZY.get(name)
    if module is None:
        raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
    from importlib import import_module

    return getattr(import_module(module, __name__), name)
