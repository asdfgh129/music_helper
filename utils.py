# -*- coding: utf-8 -*-
"""工具模块 - 日志与月份小函数

日志约定：
1. `setup_logging` 可重复调用，不会叠加 handler；
2. 对外统一通过 `utils.main_logger` 访问，不要 `from utils import main_logger`
   （那样拿到的是旧引用，重新初始化后不会更新）。

文件名解析、艺术家拆分、歌词判断等逻辑统一在 `core.naming` / `core.lyrics`。
本模块历史上有一层「兼容壳」把它们再包一遍，但生产代码零调用、测试只测到壳，
已删除——需要这些函数请直接 `from core.naming import ...`。
"""

import logging
import os
import re
import sys
from datetime import datetime

import config

# 兼容旧引用；日志目录固定，不随 config.reload() 变化
LOG_DIR = config.LOG_DIR

main_logger = logging.getLogger('music_manager')
log_file = None


_WINDOWS_ABS = re.compile(r'^[A-Za-z]:[\\/]')


def ensure_dirs():
    """创建流水线运行所需的目录（幂等，不碰用户已有数据）

    在非 Windows 上跳过 `D:\\...` 这类盘符路径，避免把字面量目录建到当前目录。
    """
    created = []
    for path in config.runtime_dirs():
        if not path or os.path.isdir(path):
            continue
        if os.name != 'nt' and _WINDOWS_ABS.match(path):
            continue
        os.makedirs(path, exist_ok=True)
        created.append(path)
    return created


def _make_handler(kind, path, level, fmt):
    if kind == 'file':
        handler = logging.FileHandler(path, encoding='utf-8')
    else:
        handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(fmt))
    return handler


def setup_logging(debug_mode=False):
    """初始化主日志（可重复调用，不会叠加 handler）"""
    global main_logger, log_file

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    os.makedirs(LOG_DIR, exist_ok=True)
    log_file = os.path.join(LOG_DIR, f'Music-{timestamp}.log')

    level = logging.DEBUG if debug_mode else logging.INFO
    main_logger = logging.getLogger('music_manager')
    main_logger.setLevel(level)

    for handler in main_logger.handlers[:]:
        main_logger.removeHandler(handler)
        handler.close()

    main_logger.addHandler(_make_handler('file', log_file, level,
                                         '%(asctime)s - %(levelname)s - %(message)s'))
    main_logger.addHandler(_make_handler('console', None, level, '%(levelname)s: %(message)s'))

    main_logger.info(f'运行模式: {"调试" if debug_mode else "正常"}')
    main_logger.info(f'日志文件: {log_file}')
    return main_logger


def validate_month_format(month_str):
    """校验 YYYYMM 格式，年份 1900-2099、月份 1-12"""
    if not month_str or len(month_str) != 6 or not month_str.isdigit():
        return False
    year, month = int(month_str[:4]), int(month_str[4:6])
    return 1900 <= year < 2100 and 1 <= month <= 12


def get_current_month():
    """当前月份（YYYYMM）"""
    return datetime.now().strftime('%Y%m')
