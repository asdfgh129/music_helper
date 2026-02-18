# -*- coding: utf-8 -*-
"""
工具函数模块 - 日志和通用工具函数
"""

import os
import sys
import re
from datetime import datetime
import logging

from config import MAIN_DIR


# ==================== 日志系统 ====================
main_logger: logging.Logger = logging.getLogger('music_manager_init')
log_file: str | None = None


def setup_logging():
    """设置主日志系统"""
    global main_logger, log_file

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = os.path.join(MAIN_DIR, f'Music-{timestamp}.log')

    # 确保主目录存在
    os.makedirs(MAIN_DIR, exist_ok=True)

    main_logger = logging.getLogger('music_manager')
    main_logger.setLevel(logging.INFO)

    # 文件处理器
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(levelname)s: %(message)s')
    console_handler.setFormatter(console_formatter)

    main_logger.addHandler(file_handler)
    main_logger.addHandler(console_handler)

    main_logger.info(f'日志文件: {log_file}')
    main_logger.info('音乐文件管理系统启动')

    return main_logger


def create_operation_log(operation_name):
    """创建操作专用日志文件"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_filename = f'{operation_name}-{timestamp}.log'
    log_path = os.path.join(MAIN_DIR, log_filename)

    # 创建操作日志记录器
    op_logger = logging.getLogger(f'operation.{operation_name}')
    op_logger.setLevel(logging.INFO)

    # 移除旧处理器
    for handler in op_logger.handlers[:]:
        op_logger.removeHandler(handler)

    # 添加文件处理器
    file_handler = logging.FileHandler(log_path, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    op_logger.addHandler(file_handler)

    return op_logger, log_path


def get_file_modification_month(filepath):
    """获取文件修改时间戳（年月格式：YYYYMM）"""
    try:
        mtime = os.path.getmtime(filepath)
        dt = datetime.fromtimestamp(mtime)
        return dt.strftime('%Y%m')
    except Exception as e:
        if main_logger and main_logger.handlers:
            main_logger.error(f'获取文件修改时间失败 {filepath}: {e}')
        return None


def get_current_month():
    """获取当前月份（YYYYMM格式）"""
    return datetime.now().strftime('%Y%m')


def split_artist(artist):
    """拆分艺术家名称，支持多种分隔符"""
    if not artist:
        return []

    separators = ['；', ';', '，', ',', '&', '/', '、', '•', '·', '|', '｜', '+', '＋']
    result = [artist]
    for sep in separators:
        new_result = []
        for item in result:
            new_result.extend([a.strip() for a in item.split(sep)])
        result = new_result
    return [a for a in result if a]


def normalize_text(text):
    """标准化文本：去除空格、转为小写"""
    if not text:
        return ''
    return re.sub(r'\s+', '', text).lower()


def parse_filename(filename):
    """解析文件名，提取艺术家和歌曲名"""
    # 移除扩展名
    name = os.path.splitext(filename)[0]

    # 检查是否符合 "艺术家 - 歌曲名" 格式
    if ' - ' in name:
        parts = name.split(' - ', 1)
        artist = parts[0].strip()
        title = parts[1].strip()
        return artist, title

    return '', name.strip()


def check_filename_format(filename):
    """检查文件名是否符合 '艺术家 - 歌曲名' 格式"""
    artist, title = parse_filename(filename)
    return bool(artist and title and ' - ' in filename)


def has_lrc_file(music_filepath):
    """检查音乐文件是否有对应的LRC歌词文件"""
    lrc_path = os.path.splitext(music_filepath)[0] + '.lrc'
    return os.path.exists(lrc_path)
