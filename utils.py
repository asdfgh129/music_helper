# -*- coding: utf-8 -*-
"""
工具函数模块 - 日志和通用工具函数
"""

import os
import sys
import re
from datetime import datetime
import logging

from config import LOG_DIR


# ==================== 日志系统 ====================
# 声明全局变量以便其他模块导入，初始化在 setup_logging 中完成
main_logger: logging.Logger = logging.getLogger('music_manager')
log_file: str | None = None


def setup_logging(debug_mode=False):
    """设置主日志系统"""
    global main_logger, log_file

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = os.path.join(LOG_DIR, f'Music-{timestamp}.log')

    # 确保日志目录存在
    os.makedirs(LOG_DIR, exist_ok=True)

    main_logger = logging.getLogger('music_manager')

    # 根据 debug 模式设置日志级别
    if debug_mode:
        main_logger.setLevel(logging.DEBUG)
    else:
        main_logger.setLevel(logging.INFO)

    # 文件处理器
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG if debug_mode else logging.INFO)
    file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if debug_mode else logging.INFO)
    console_formatter = logging.Formatter('%(levelname)s: %(message)s')
    console_handler.setFormatter(console_formatter)

    main_logger.addHandler(file_handler)
    main_logger.addHandler(console_handler)

    mode_str = "调试" if debug_mode else "正常"
    main_logger.info(f'运行模式: {mode_str}')
    main_logger.info(f'日志文件: {log_file}')
    main_logger.info('音乐文件管理系统启动')

    return main_logger


def create_operation_log(operation_name):
    """创建操作专用日志文件"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_filename = f'{operation_name}-{timestamp}.log'
    log_path = os.path.join(LOG_DIR, log_filename)

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

    # 添加控制台处理器（warning级别）
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.WARNING)
    console_formatter = logging.Formatter('WARNING: %(message)s')
    console_handler.setFormatter(console_formatter)
    op_logger.addHandler(console_handler)

    return op_logger, log_path


def get_file_modification_month(filepath):
    """获取文件修改时间戳（年月格式：YYYYMM）"""
    try:
        mtime = os.path.getmtime(filepath)
        dt = datetime.fromtimestamp(mtime)
        return dt.strftime('%Y%m')
    except Exception as e:
        if main_logger is not None and main_logger.handlers:
            main_logger.error(f'获取文件修改时间失败 {filepath}: {e}')
        return None


def validate_month_format(month_str):
    """验证月份格式是否正确（YYYYMM）"""
    if not month_str or len(month_str) != 6:
        return False
    if not month_str.isdigit():
        return False
    year = int(month_str[:4])
    month = int(month_str[4:6])
    return 1900 <= year < 2100 and 1 <= month <= 12


def get_current_month():
    """获取当前月份（YYYYMM格式）"""
    return datetime.now().strftime('%Y%m')


def split_artist(artist):
    """
    拆分艺术家名称，支持多种分隔符
    
    支持的分隔符：
    - 英文逗号: ,
    - 英文分号: ;
    - 中文逗号: ，
    - 中文分号: ；
    - & 符号: &
    - 斜杠: /
    - 中文顿号: 、
    - 中点: • ·
    - 竖线: | ｜
    - 加号: + ＋
    
    Args:
        artist: 艺术家字符串，可能包含多个艺术家
    
    Returns:
        list: 拆分后的艺术家列表，去除空字符串
    """
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

def detect_language(lyrics):
    chinese_pattern = re.compile(r'[\u4e00-\u9fa5]')
    english_pattern = re.compile(r'[a-zA-Z]')
    japanese_pattern = re.compile(r'[\u0800-\u4e00]')
    korean_pattern = re.compile(r'[\uac00-\ud7a3]')
    thai_pattern = re.compile(r'[\u0e00-\u0e7f]')

    chinese_count = len(re.findall(chinese_pattern, lyrics))
    english_count = len(re.findall(english_pattern, lyrics))
    japanese_count = len(re.findall(japanese_pattern, lyrics))
    korean_count = len(re.findall(korean_pattern, lyrics))
    thai_count = len(re.findall(thai_pattern, lyrics))
    if chinese_count > english_count and chinese_count > japanese_count and chinese_count > korean_count \
            and chinese_count > thai_count:
        return '中文'
    elif english_count > chinese_count and english_count > japanese_count and english_count > korean_count \
            and english_count > thai_count:
        return '英文'
    elif japanese_count > chinese_count and japanese_count > english_count and japanese_count > korean_count \
            and japanese_count > thai_count:
        return '日文'
    elif korean_count > chinese_count and korean_count > english_count and korean_count > japanese_count \
            and korean_count > thai_count:
        return '韩文'
    elif thai_count > chinese_count and thai_count > english_count and thai_count > japanese_count \
            and thai_count > korean_count:
        return '泰文'
    else:
        return '未知'
