# -*- coding: utf-8 -*-
"""
工具模块 - 日志与通用小函数

日志相关修复：
1. create_operation_log 统一返回 logging.Logger（旧版返回 tuple，导致 5 处调用方全部 AttributeError）；
2. setup_logging 重复调用不会叠加 handler；
3. 对外统一通过 utils.main_logger 访问，避免 `from utils import main_logger` 拿到旧引用。
"""

import logging
import os
import re
import sys
from datetime import datetime

from config import LOG_DIR
import core.naming as naming

main_logger = logging.getLogger('music_manager')
log_file = None
_last_operation_log = None


def _make_handler(kind, path, level, fmt):
    if kind == 'file':
        handler = logging.FileHandler(path, encoding='utf-8')
    else:
        handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(fmt))
    return handler


def setup_logging(debug_mode=False):
    """初始化主日志（可重复调用）"""
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


def create_operation_log(operation_name, debug_mode=False):
    """创建操作专用日志，返回 Logger 本身"""
    global _last_operation_log

    os.makedirs(LOG_DIR, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_path = os.path.join(LOG_DIR, f'{operation_name}-{timestamp}.log')
    _last_operation_log = log_path

    level = logging.DEBUG if debug_mode else logging.INFO
    logger = logging.getLogger(f'operation.{operation_name}')
    logger.setLevel(level)
    logger.propagate = False

    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()

    logger.addHandler(_make_handler('file', log_path, level,
                                    '%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(_make_handler('console', None,
                                    logging.DEBUG if debug_mode else logging.WARNING,
                                    '%(levelname)s: %(message)s'))
    return logger


# ---------------- 兼容旧接口的小函数（实现统一收敛到 core.naming） ----------------

def get_file_modification_month(filepath):
    try:
        return datetime.fromtimestamp(os.path.getmtime(filepath)).strftime('%Y%m')
    except Exception as exc:  # noqa: BLE001
        if main_logger.handlers:
            main_logger.error(f'获取文件修改时间失败 {filepath}: {exc}')
        return None


def validate_month_format(month_str):
    if not month_str or len(month_str) != 6 or not month_str.isdigit():
        return False
    year, month = int(month_str[:4]), int(month_str[4:6])
    return 1900 <= year < 2100 and 1 <= month <= 12


def get_current_month():
    return datetime.now().strftime('%Y%m')


def split_artist(artist):
    return naming.split_artist(artist)


def normalize_text(text):
    return naming.normalize_text(text)


def parse_filename(filename):
    return naming.parse_filename(filename)


def check_filename_format(filename):
    return naming.is_canonical(filename)


def has_lrc_file(music_filepath):
    return os.path.exists(os.path.splitext(music_filepath)[0] + '.lrc')


def detect_language(lyrics):
    if not lyrics:
        return '未知'
    patterns = {
        '中文': r'[\u4e00-\u9fa5]',
        '英文': r'[a-zA-Z]',
        '日文': r'[\u3040-\u30ff]',
        '韩文': r'[\uac00-\ud7a3]',
        '泰文': r'[\u0e00-\u0e7f]',
    }
    counts = {name: len(re.findall(pattern, lyrics)) for name, pattern in patterns.items()}
    top = max(counts, key=counts.get)
    return top if counts[top] > 0 else '未知'
