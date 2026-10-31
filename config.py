# -*- coding: utf-8 -*-
"""
配置模块 - 只放纯数据，不导入任何业务模块

读取顺序（优先级从高到低）：
    1. 环境变量（MUSIC_HELPER_*）
    2. 项目根目录的 config.ini（路径可用 MUSIC_HELPER_CONFIG 指向别处）
    3. 本文件里的默认值

之所以这样约束：旧版 config.py 承担了「导入中转站」的职责，导致任一可选依赖缺失
就让主程序起不来，还与 fingerprint 形成循环导入。现在所有可选依赖都在各自模块内部
延迟导入，本文件只依赖标准库。

目录语义（从下载到入库）：
    LIBRARY_DIR       最终音乐库
    WORKSPACE_DIR     流水线工作区；标签完整的文件处理完后仍留在这里
    INCOMPLETE_DIR    标签不全 / 文件名矛盾，等待人工处理
    DUPLICATE_DIR     重复文件
    TOOLS_DIR         外部程序（um.exe、soundalike.exe、Frida hook）
"""

import configparser
import os
import re

# ==================== 版本信息 ====================
# 手工维护，与仓库根目录的 CHANGELOG.md 对齐；不再用时间戳动态生成
__version__ = '0.7.0'
VERSION = __version__

# ==================== 项目目录 ====================
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
TOOLS_DIR = os.path.join(PROJECT_DIR, 'tools')
LOG_DIR = os.path.join(PROJECT_DIR, 'log')
REPORT_DIR = os.path.join(PROJECT_DIR, 'log', 'reports')
JOURNAL_PATH = os.path.join(PROJECT_DIR, 'log', 'journal.jsonl')
TRASH_DIR = os.path.join(PROJECT_DIR, 'log', '_trash')

DEFAULT_CONFIG_PATH = os.path.join(PROJECT_DIR, 'config.ini')
_ENV_CONFIG_PATH = 'MUSIC_HELPER_CONFIG'

_WINDOWS_ABS = re.compile(r'^(?:[A-Za-z]:[\\/]|\\\\)')


def _is_absolute(value):
    """跨平台判断绝对路径（在 macOS 上也要能识别 D:\\music）"""
    return bool(_WINDOWS_ABS.match(value)) or os.path.isabs(value)


def _ini_path():
    return os.environ.get(_ENV_CONFIG_PATH) or DEFAULT_CONFIG_PATH


def _load_ini():
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(_ini_path(), encoding='utf-8')
    except (configparser.Error, OSError):
        # 配置写坏了不能阻止程序启动，退回默认值即可
        return configparser.ConfigParser()
    return parser


def _raw(env_key, section, key, default):
    if env_key and os.environ.get(env_key):
        return os.environ[env_key]
    if _INI.has_option(section, key):
        value = _INI.get(section, key).strip()
        if value:
            return value
    return default


def _path(env_key, section, key, default):
    """路径配置：支持 env / ini / 默认值，相对路径按项目根解析"""
    value = str(_raw(env_key, section, key, default)).strip()
    if not value:
        return value
    value = os.path.expanduser(value)
    if _is_absolute(value):
        return os.path.normpath(value)
    return os.path.normpath(os.path.join(PROJECT_DIR, value))


def _int(env_key, section, key, default):
    try:
        return int(_raw(env_key, section, key, default))
    except (TypeError, ValueError):
        return default


def _float(env_key, section, key, default):
    try:
        return float(_raw(env_key, section, key, default))
    except (TypeError, ValueError):
        return default


def reload():
    """重新读取 config.ini 与环境变量

    模块导入时自动调用一次；测试或多环境切换时可手动调用。
    """
    global _INI
    global LIBRARY_DIR, WORKSPACE_DIR, INCOMPLETE_DIR, DUPLICATE_DIR
    global NETEASE_DIR, NETEASE_VIP_DIR
    global QQ_DIR, QQ_VIP_DIR
    global DECRYPT_STAGING_DIR, NETEASE_STAGING_DIR, QQ_STAGING_DIR
    global DB_PATH, UM_EXE, SOUNDALIKE_EXE, QQ_HOOK_JS
    global SUBPROCESS_TIMEOUT, FPCALC_LENGTH, FINGERPRINT_THRESHOLD
    global DURATION_TOLERANCE, MAX_COVER_SIZE, ENCRYPTED_SOURCE_MODE
    # 旧名兼容别名（下游脚本可能还在用；新代码请用上面的语义名）
    global MAIN_DIR, TEMP_COMPLETED_DIR, TEMP_MOVE_DIR, TEMP_REVIEW_DIR
    global NETEASE_TMP_DIR, QQ_TMP_DIR

    _INI = _load_ini()

    # ==================== 目录配置 ====================
    LIBRARY_DIR = _path('MUSIC_HELPER_LIBRARY_DIR', 'paths', 'library_dir', r'D:\music')
    WORKSPACE_DIR = _path('MUSIC_HELPER_WORKSPACE_DIR', 'paths', 'workspace_dir', r'G:\Temp')

    # 两个结果目录默认与 WORKSPACE_DIR 平级，避免被声纹工具当成待扫描的临时文件
    INCOMPLETE_DIR = _path('MUSIC_HELPER_INCOMPLETE_DIR', 'paths', 'incomplete_dir', r'G:\Unready')
    DUPLICATE_DIR = _path('MUSIC_HELPER_DUPLICATE_DIR', 'paths', 'duplicate_dir', r'G:\Tmp')

    # 下载目录
    NETEASE_DIR = _path('MUSIC_HELPER_NETEASE_DIR', 'paths', 'netease_dir', r'G:\Neteasymusic')
    NETEASE_VIP_DIR = os.path.join(NETEASE_DIR, 'VipSOngsDownload')
    QQ_DIR = _path('MUSIC_HELPER_QQ_DIR', 'paths', 'qq_dir', r'G:\QQMusic')
    QQ_VIP_DIR = os.path.join(QQ_DIR, 'VipSOngsDownload')

    # 解密暂存区：仍然在 WORKSPACE_DIR 内，按平台分开，避免两类加密文件互相干扰
    DECRYPT_STAGING_DIR = _path('MUSIC_HELPER_DECRYPT_DIR', 'paths', 'decrypt_dir',
                                os.path.join(WORKSPACE_DIR, '_decrypt'))
    NETEASE_STAGING_DIR = os.path.join(DECRYPT_STAGING_DIR, 'netease')
    QQ_STAGING_DIR = os.path.join(DECRYPT_STAGING_DIR, 'qq')

    # ==================== 声纹库 ====================
    DB_PATH = _path('MUSIC_HELPER_DB', 'paths', 'db_path', 'music.db')

    # ==================== 外部程序 ====================
    UM_EXE = _path('MUSIC_HELPER_UM_EXE', 'tools', 'um_exe',
                   os.path.join(TOOLS_DIR, 'um.exe'))
    SOUNDALIKE_EXE = _path('MUSIC_HELPER_SOUNDALIKE_EXE', 'tools', 'soundalike_exe',
                           os.path.join(TOOLS_DIR, 'soundalike.exe'))
    QQ_HOOK_JS = _path('MUSIC_HELPER_QQ_HOOK', 'tools', 'qq_hook',
                       os.path.join(TOOLS_DIR, 'hook_qq_music.js'))

    # ==================== 业务参数 ====================
    SUBPROCESS_TIMEOUT = _int('MUSIC_HELPER_TIMEOUT', 'settings', 'subprocess_timeout', 3600)
    FPCALC_LENGTH = _int('MUSIC_HELPER_FPCALC_LENGTH', 'settings', 'fpcalc_length', 120)
    FINGERPRINT_THRESHOLD = _int('MUSIC_HELPER_FP_THRESHOLD', 'settings', 'fingerprint_threshold', 50)
    DURATION_TOLERANCE = _float('MUSIC_HELPER_DURATION_TOLERANCE', 'settings',
                                'duration_tolerance', 3.0)
    MAX_COVER_SIZE = _int('MUSIC_HELPER_MAX_COVER_SIZE', 'settings', 'max_cover_size',
                          5 * 1024 * 1024)
    ENCRYPTED_SOURCE_MODE = str(_raw('MUSIC_HELPER_ENCRYPTED_MODE', 'settings',
                                     'encrypted_source_mode', 'return')).lower()

    # ==================== 兼容别名 ====================
    MAIN_DIR = LIBRARY_DIR
    TEMP_COMPLETED_DIR = WORKSPACE_DIR
    TEMP_MOVE_DIR = DUPLICATE_DIR
    TEMP_REVIEW_DIR = INCOMPLETE_DIR
    NETEASE_TMP_DIR = NETEASE_STAGING_DIR
    QQ_TMP_DIR = QQ_STAGING_DIR


# ==================== 扩展名 ====================
MUSIC_EXTENSIONS = {'.flac', '.mp3', '.wav', '.ape', '.ogg', '.mflac', '.mgg', '.ncm'}
AUDIO_EXTENSIONS = {'.flac', '.mp3', '.wav', '.ape', '.ogg'}
VIP_EXTENSIONS = {'.mflac', '.mgg', '.ncm'}
NETEASE_VIP_EXTENSIONS = {'.ncm'}
QQ_VIP_EXTENSIONS = {'.mflac', '.mgg'}


def runtime_dirs():
    """运行时需要存在的目录（由 utils.ensure_dirs() 创建）"""
    return [
        WORKSPACE_DIR,
        INCOMPLETE_DIR,
        DUPLICATE_DIR,
        NETEASE_STAGING_DIR,
        QQ_STAGING_DIR,
        os.path.dirname(DB_PATH) or PROJECT_DIR,
        REPORT_DIR,
        TRASH_DIR,
    ]


def validate():
    """返回配置问题列表，空列表表示可用"""
    problems = []
    if not os.path.isdir(LIBRARY_DIR):
        problems.append(f'音乐库不存在: {LIBRARY_DIR}')
    if not os.path.isdir(WORKSPACE_DIR):
        problems.append(f'工作区不存在: {WORKSPACE_DIR}')
    return problems


def as_dict():
    return {
        '版本': __version__,
        '音乐库': LIBRARY_DIR,
        '工作区': WORKSPACE_DIR,
        '待补全': INCOMPLETE_DIR,
        '重复文件': DUPLICATE_DIR,
        '声纹库': DB_PATH,
        '报告目录': REPORT_DIR,
        '回收站': TRASH_DIR,
    }


reload()
