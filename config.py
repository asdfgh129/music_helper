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
    TOOLS_DIR         外部程序（um.exe、soundalike、fpcalc、Frida hook）
"""

import configparser
import os
import platform
import re
import sys

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

# macOS 的架构名映射到 Go 交叉编译产物的后缀（tools/soundalike-darwin-<arch>）
_MACOS_ARCH = {'arm64': 'arm64', 'aarch64': 'arm64', 'x86_64': 'amd64', 'amd64': 'amd64'}


def _default_soundalike():
    """声纹工具默认路径：Windows 用 .exe，macOS 用按架构命名的二进制

    以前只有 soundalike.exe，macOS 上直接 Exec format error。现在 tools/ 里
    同时放 soundalike-darwin-arm64 / -amd64，按平台挑一个，仍然允许被
    config.ini / 环境变量覆盖。
    """
    if os.name == 'nt':
        return os.path.join(TOOLS_DIR, 'soundalike.exe')
    if sys.platform == 'darwin':
        arch = _MACOS_ARCH.get(platform.machine().lower())
        if arch:
            return os.path.join(TOOLS_DIR, f'soundalike-darwin-{arch}')
    return os.path.join(TOOLS_DIR, 'soundalike')


def _default_fpcalc():
    """fpcalc 默认路径：优先用随仓库分发的 tools/fpcalc，找不到再靠 PATH"""
    name = 'fpcalc.exe' if os.name == 'nt' else 'fpcalc'
    return os.path.join(TOOLS_DIR, name)


def _default_um():
    """网易云/QQ 文件解密用的 um 默认路径

    um 是纯 Go 程序（unlock-music CLI），tools/ 里同时放了 Windows 的 um.exe 与
    macOS 的 um-darwin-<arch>，按平台挑一个；仍然允许 config.ini / 环境变量覆盖。
    """
    if sys.platform == 'darwin':
        arch = _MACOS_ARCH.get(platform.machine().lower())
        if arch:
            return os.path.join(TOOLS_DIR, f'um-darwin-{arch}')
    if os.name == 'nt':
        return os.path.join(TOOLS_DIR, 'um.exe')
    return os.path.join(TOOLS_DIR, 'um')



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
    global DB_PATH, UM_EXE, SOUNDALIKE_EXE, FPCALC_EXE, QQ_HOOK_JS
    global QQ_CLIENT_EXE, QQ_INSTALLER, QQ_UPDATE_PATCH, QQ_MAC_DMG, QQ_MAC_PATCH
    global QQ_LOGIN_TIMEOUT
    global QMC_MMKV, QMC_MMKV_KEY
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
    UM_EXE = _path('MUSIC_HELPER_UM_EXE', 'tools', 'um_exe', _default_um())
    SOUNDALIKE_EXE = _path('MUSIC_HELPER_SOUNDALIKE_EXE', 'tools', 'soundalike_exe',
                           _default_soundalike())
    FPCALC_EXE = _path('MUSIC_HELPER_FPCALC_EXE', 'tools', 'fpcalc_exe', _default_fpcalc())
    QQ_HOOK_JS = _path('MUSIC_HELPER_QQ_HOOK', 'tools', 'qq_hook',
                       os.path.join(TOOLS_DIR, 'hook_qq_music.js'))
    # QQ 音乐客户端（解密前置条件）：留空则按平台自动探测——Windows 查注册表
    # Install 值 + 常见安装路径，macOS 查 /Applications/QQMusic.app。
    # 未安装时用下面两个安装包自动装旧版，再打屏蔽更新补丁（升级会让导出符号变化）。
    QQ_CLIENT_EXE = _path('MUSIC_HELPER_QQ_CLIENT', 'tools', 'qq_client_exe', '')
    QQ_INSTALLER = _path('MUSIC_HELPER_QQ_INSTALLER', 'tools', 'qq_installer',
                         os.path.join(TOOLS_DIR, 'QQMusic_Setup_1951.exe'))
    QQ_UPDATE_PATCH = _path('MUSIC_HELPER_QQ_PATCH', 'tools', 'qq_update_patch',
                            os.path.join(TOOLS_DIR, 'Q音屏蔽更新.zip'))
    QQ_MAC_DMG = _path('MUSIC_HELPER_QQ_MAC_DMG', 'tools', 'qq_mac_dmg',
                       os.path.join(TOOLS_DIR, 'QQMusicMac_Mgr_8.8.0_20230903.dmg'))
    QQ_MAC_PATCH = _path('MUSIC_HELPER_QQ_MAC_PATCH', 'tools', 'qq_mac_patch',
                         os.path.join(TOOLS_DIR, 'QQ 音乐 Mac 屏蔽升级.tar.gz'))
    # 解密前等待用户登录的秒数（0 表示不等待）
    QQ_LOGIN_TIMEOUT = _int('MUSIC_HELPER_QQ_LOGIN_TIMEOUT', 'tools', 'qq_login_timeout', 300)
    # 新版 qmc（.mflac/.mgg 的 qmc2、mflac1）离线解密凭据：留空则自动在 QQ 音乐
    # 数据目录里找 mmkv；密钥只能手工填（随账号下发，不落在文件里）
    QMC_MMKV = _path('MUSIC_HELPER_QMC_MMKV', 'tools', 'qmc_mmkv', '')
    QMC_MMKV_KEY = str(_raw('MUSIC_HELPER_QMC_KEY', 'tools', 'qmc_mmkv_key', '')).strip()

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
MUSIC_EXTENSIONS = {'.flac', '.mp3', '.wav', '.ape', '.ogg', '.opus', '.m4a', '.wma', '.dsf',
                    '.mflac', '.mgg', '.ncm'}
# 可播放的本地音频；裸 .aac(ADTS) 不在内：它没有统一的容器标签，读不出歌手/歌名，
# 纳入扫描只会让整个库突然"缺标签"
AUDIO_EXTENSIONS = {'.flac', '.mp3', '.wav', '.ape', '.ogg', '.opus', '.m4a', '.wma', '.dsf'}
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
