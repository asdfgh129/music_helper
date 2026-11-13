# -*- coding: utf-8 -*-
"""项目根目录的唯一判定：源码模式 / PyInstaller 冻结模式。

源码模式：项目根 = 本文件所在目录（仓库根）。
冻结模式：项目根 = 可执行文件所在目录（打包后的 ``dist/``）。

为什么不能直接用 ``__file__``：PyInstaller 把模块收进 PYZ 后，``__file__``
指向 ``sys._MEIPASS``（onedir 下是 ``_internal/``）里的 ``.pyc`` 路径。
那样 ``config.TOOLS_DIR`` 会指向不存在的 ``_internal/tools``，``config.ini``
与 ``log/`` 也会写进依赖目录，用户找不到配置和日志。

打包时 ``tools/``、``web/``、``config.example.ini``、``log/`` 都放在 exe
旁边，由 ``scripts/build_exe.py`` 负责组装；见根目录 ``build_exe.bat``。
"""

import os
import sys


def project_dir():
    """返回当前运行形态下的项目根目录（绝对路径）。"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))
