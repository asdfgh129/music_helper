# -*- coding: utf-8 -*-
"""
配置模块 - 只放纯数据，不导入任何业务模块

之所以这样约束：旧版 config.py 承担了「导入中转站」的职责（把 MusicTagger、
FingerprintMatcher 等类从 config 导出），导致
  1) 任一可选依赖缺失就让 `from config import X` 直接崩，主程序起不来；
  2) config 与 Fingerprint 形成循环导入，FPCALC_LENGTH 永远读到默认值。
现在所有可选依赖都在各自模块内部延迟导入。

所有路径都可以用环境变量覆盖，方便换机器 / 换盘符：
    MUSIC_HELPER_MAIN_DIR、MUSIC_HELPER_TEMP_DIR ...
"""

import os

# ==================== 版本信息 ====================
# 手工维护，与仓库根目录的 CHANGELOG.md 对齐；不再用时间戳动态生成
__version__ = '0.4.0'
VERSION = __version__

# ==================== 项目目录 ====================
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(PROJECT_DIR, 'log')
REPORT_DIR = os.path.join(PROJECT_DIR, 'log', 'reports')
JOURNAL_PATH = os.path.join(PROJECT_DIR, 'log', 'journal.jsonl')
TRASH_DIR = os.path.join(PROJECT_DIR, 'log', '_trash')


def _path(env_key, default):
    """路径支持环境变量覆盖"""
    return os.environ.get(env_key, default)


# ==================== 目录配置 ====================
# 主目录（最终音乐库）
MAIN_DIR = _path('MUSIC_HELPER_MAIN_DIR', r'D:\music')

# 流水线工作目录
TEMP_COMPLETED_DIR = _path('MUSIC_HELPER_TEMP_DIR', r'G:\Temp')
TEMP_MOVE_DIR = _path('MUSIC_HELPER_MOVE_DIR', r'G:\Tmp')      # 待处理/不一致文件
TEMP_REVIEW_DIR = _path('MUSIC_HELPER_REVIEW_DIR', r'G:\Tmp\review')

# 网易云音乐
NETEASE_DIR = _path('MUSIC_HELPER_NETEASE_DIR', r'G:\Neteasymusic')
NETEASE_VIP_DIR = os.path.join(NETEASE_DIR, 'VipSOngsDownload')
NETEASE_TMP_DIR = _path('MUSIC_HELPER_NETEASE_TMP', r'G:\NeTmp')

# QQ 音乐
QQ_DIR = _path('MUSIC_HELPER_QQ_DIR', r'G:\QQMusic')
QQ_VIP_DIR = os.path.join(QQ_DIR, 'VipSOngsDownload')
QQ_TMP_DIR = _path('MUSIC_HELPER_QQ_TMP', r'G:\QQTmp')

# ==================== 外部程序 ====================
# 默认指向仓库内已有的二进制位置，避免为了「好看」而搬动 exe 导致原有 bat 失效
UM_EXE = _path('MUSIC_HELPER_UM_EXE', os.path.join(PROJECT_DIR, 'Decrypto', 'um.exe'))
SOUNDALIKE_EXE = _path('MUSIC_HELPER_SOUNDALIKE_EXE',
                       os.path.join(PROJECT_DIR, 'Fingerprint', 'soundalike.exe'))

# 外部程序超时（秒）—— 旧代码没有超时，exe 卡死会拖死整条流水线
SUBPROCESS_TIMEOUT = int(os.environ.get('MUSIC_HELPER_TIMEOUT', '3600'))

# ==================== 扩展名 ====================
MUSIC_EXTENSIONS = {'.flac', '.mp3', '.wav', '.ape', '.ogg', '.mflac', '.mgg', '.ncm'}
AUDIO_EXTENSIONS = {'.flac', '.mp3', '.wav', '.ape', '.ogg'}
VIP_EXTENSIONS = {'.mflac', '.mgg', '.ncm'}
NETEASE_VIP_EXTENSIONS = {'.ncm'}
QQ_VIP_EXTENSIONS = {'.mflac', '.mgg'}

# ==================== 业务参数 ====================
# 指纹长度：MusicBrainz 标准 120 秒，必须与 soundalike 工具一致
FPCALC_LENGTH = 120
# 声纹匹配分数阈值（0-100）
FINGERPRINT_THRESHOLD = 50
# 判定重复时允许的时长误差（秒）
DURATION_TOLERANCE = 3.0
# 封面下载限制（字节）
MAX_COVER_SIZE = 5 * 1024 * 1024
# 解密成功后，加密原文件怎么处理：
#   return（默认）= 搬回 VIP 下载目录（只搬本次解密涉及的文件）
#   trash        = 移入 log/_trash 回收站
#   keep         = 留在临时目录，由后续人工处理
ENCRYPTED_SOURCE_MODE = os.environ.get('MUSIC_HELPER_ENCRYPTED_MODE', 'return')


def validate():
    """返回配置问题列表，空列表表示可用"""
    problems = []
    if not os.path.isdir(MAIN_DIR):
        problems.append(f'主目录不存在: {MAIN_DIR}')
    if not os.path.isdir(TEMP_COMPLETED_DIR):
        problems.append(f'临时目录不存在: {TEMP_COMPLETED_DIR}')
    return problems


def as_dict():
    return {
        '版本': __version__,
        '主目录': MAIN_DIR,
        '临时目录': TEMP_COMPLETED_DIR,
        '待处理目录': TEMP_MOVE_DIR,
        '报告目录': REPORT_DIR,
        '回收站': TRASH_DIR,
    }
