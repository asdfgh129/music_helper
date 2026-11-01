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
import shutil
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


# ==================== 外部程序（跨平台） ====================
# tools/ 里的程序是「同一个程序的多个平台产物」（soundalike.exe / soundalike-darwin-arm64、
# um.exe / um-darwin-arm64）。config.py 负责按平台挑默认路径，这里负责在真正执行前
# 校验「这份产物在本机能跑」——三种典型故障：文件没随仓库带过来、从 Windows 克隆后
# 缺可执行位、拿错了平台的文件（Mach-O 丢给 Windows / PE 丢给 macOS）。

_MACHO_MAGIC = (b'\xfe\xed\xfa\xce', b'\xfe\xed\xfa\xcf',
                b'\xce\xfa\xed\xfe', b'\xcf\xfa\xed\xfe',
                b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca')
_BINARY_NAMES = {'windows': 'Windows PE', 'macho': 'Mach-O', 'elf': 'ELF', 'script': '脚本'}


def platform_label():
    """当前平台的可读名称（日志/报错用）"""
    if sys.platform == 'darwin':
        return 'macOS'
    if os.name == 'nt':
        return 'Windows'
    return sys.platform


def native_binary_kind():
    """当前平台期望的可执行文件格式"""
    if os.name == 'nt':
        return 'windows'
    return 'macho' if sys.platform == 'darwin' else 'elf'


def binary_kind(path):
    """按文件头判断可执行文件格式：windows / macho / elf / script，认不出返回 None"""
    try:
        with open(path, 'rb') as handle:
            head = handle.read(4)
    except OSError:
        return None
    if head[:2] == b'MZ':
        return 'windows'
    if head in _MACHO_MAGIC:
        return 'macho'
    if head == b'\x7fELF':
        return 'elf'
    if head[:2] == b'#!':
        return 'script'
    return None


def tool_problem(path, label='外部程序'):
    """检查外部程序能否在本机执行；可用返回空串，否则返回能照着做的提示"""
    if not path:
        return f'未配置{label}的路径'
    if not os.path.exists(path):
        return (f'找不到{label}: {path}（当前平台 {platform_label()}，'
                f'确认 tools/ 里带了该平台的产物，或用环境变量指向别处）')
    kind = binary_kind(path)
    native = native_binary_kind()
    if kind and kind not in (native, 'script'):
        return (f'{label}与当前平台不匹配: {path} 是 {_BINARY_NAMES[kind]}，'
                f'而本机是 {platform_label()}，执行会报 Exec format error')
    if os.name != 'nt' and not os.access(path, os.X_OK):
        return f'{label}缺少可执行权限: {path}（运行 chmod +x "{path}"）'
    return ''


def resolve_tool(path, name=''):
    """配置里的路径优先；文件不存在时在 PATH 里找同名程序（brew/系统包的场景）

    返回实际要执行的路径——找不到时仍是原路径，让调用方拿它拼报错信息。
    """
    if path and os.path.exists(path):
        return path
    candidate = name or (os.path.basename(path) if path else '')
    if candidate and os.name != 'nt' and candidate.endswith('.exe'):
        candidate = candidate[:-4]
    if candidate:
        found = shutil.which(candidate)
        if found:
            return found
    return path


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
