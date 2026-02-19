# -*- coding: utf-8 -*-
"""
配置模块 - 音乐文件管理系统配置
"""

from typing import Any
from datetime import datetime

# ==================== 版本信息 ====================
__version__ = "0.1-b{}".format(int(datetime.now().timestamp()))
VERSION = __version__

# ==================== mutagen 导入 ====================
mutagen_available = False
_flac: Any = None
_mp3: Any = None
_wave: Any = None
_apev2file: Any = None
_oggvorbis: Any = None
_tit2: Any = None
_tpe1: Any = None
_talb: Any = None
_tdrc: Any = None
_tcon: Any = None

try:
    from mutagen.flac import FLAC as _flac
    from mutagen.mp3 import MP3 as _mp3
    from mutagen.wave import WAVE as _wave
    from mutagen.apev2 import APEv2File as _apev2file
    from mutagen.oggvorbis import OggVorbis as _oggvorbis
    from mutagen.id3._frames import TIT2 as _tit2, TPE1 as _tpe1, TALB as _talb, TDRC as _tdrc, TCON as _tcon
    mutagen_available = True
except ImportError:
    pass

# 导出别名供使用
FLAC = _flac
MP3 = _mp3
WAVE = _wave
APEv2File = _apev2file
OggVorbis = _oggvorbis
TIT2 = _tit2
TPE1 = _tpe1
TALB = _talb
TDRC = _tdrc
TCON = _tcon

# ==================== 模块可用性检查 ====================
fingerprint_matcher_available = False
music_tagger_available = False

try:
    from Fingerprint import FingerprintMatcher, format_recording_info
    from music_tagger.platforms.qqmusic import QQMusicApi
    from music_tagger.platforms.netease import NetEaseMusicClient
    fingerprint_matcher_available = True
except ImportError:
    pass

try:
    from music_tagger.core import MusicTagger
    music_tagger_available = True
except ImportError:
    pass

# ==================== 目录配置 ====================
# 主目录
MAIN_DIR = r'D:\music'

# 日志目录（项目目录下）
import os
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(PROJECT_DIR, 'log')

# 网易云音乐目录
NETEASE_DIR = r'G:\Neteasymusic'
NETEASE_VIP_DIR = r'G:\Neteasymusic\VipSOngsDownload'
NETEASE_TMP_DIR = r'G:\NeTmp'
TEMP_COMPLETED_DIR = r'G:\Temp'

# QQ音乐目录
QQ_DIR = r'G:\QQMusic'
QQ_VIP_DIR = r'G:\QQMusic\VipSOngsDownload'
QQ_TMP_DIR = r'G:\QQTmp'

# 临时移动目录
TEMP_MOVE_DIR = r'G:\Tmp'

# 外部程序路径
UM_EXE = r'um.exe'
SOUNDALIKE_EXE = r'soundalike.exe'

# 支持的文件扩展名
MUSIC_EXTENSIONS = {'.flac', '.mp3', '.wav', '.ape', '.ogg', '.mflac', '.mgg'}
AUDIO_EXTENSIONS = {'.flac', '.mp3', '.wav', '.ape', '.ogg'}  # 解压后的格式
VIP_EXTENSIONS = {'.mflac', '.mgg'}  # VIP加密格式
