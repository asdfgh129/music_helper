# -*- coding: utf-8 -*-

import os
import sys
import argparse
import logging
import shutil
import subprocess
import re
import time
from datetime import datetime
from typing import Any

# 第三方库导入
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

try:
    from Decrypto.source_finder import guess_song_url
except ImportError:
    def guess_song_url(file_basename: str) -> str | None:
        return None

# 尝试导入声纹匹配和音乐标签更新模块
fingerprint_matcher_available = False
music_tagger_available = False
FingerprintMatcher: Any = None
QQMusicApi: Any = None
NetEaseMusicClient: Any = None
MusicTagger: Any = None
try:
    from Fingerprint.musicbrainz_matcher import FingerprintMatcher, format_recording_info
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
QQ_PY = r'qq.py'
SOUNDALIKE_EXE = r'soundalike.exe'

# 支持的文件扩展名
MUSIC_EXTENSIONS = {'.flac', '.mp3', '.wav', '.ape', '.ogg', '.mflac', '.mgg'}
AUDIO_EXTENSIONS = {'.flac', '.mp3', '.wav', '.ape', '.ogg'}  # 解压后的格式
VIP_EXTENSIONS = {'.mflac', '.mgg'}  # VIP加密格式

# ==================== 全局变量 ====================
main_logger: logging.Logger = logging.getLogger('music_manager_init')
log_file: str | None = None

# ==================== 日志系统 ====================
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

# ==================== 工具函数 ====================
def get_file_modification_month(filepath):
    """获取文件修改时间戳（年月格式：YYYYMM）"""
    try:
        mtime = os.path.getmtime(filepath)
        dt = datetime.fromtimestamp(mtime)
        return dt.strftime('%Y%m')
    except Exception as e:
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

def get_music_metadata(filepath):
    """获取音乐文件元数据"""
    if not mutagen_available:
        return None
    
    try:
        ext = os.path.splitext(filepath)[1].lower()
        
        if ext == '.mp3':
            audio = MP3(filepath)
            tags = {
                'title': str(audio.get('TIT2', '')) if audio.get('TIT2') else '',
                'artist': str(audio.get('TPE1', '')) if audio.get('TPE1') else '',
                'album': str(audio.get('TALB', '')) if audio.get('TALB') else '',
                'year': str(audio.get('TDRC', '')) if audio.get('TDRC') else (str(audio.get('TYER', '')) if audio.get('TYER') else ''),
                'genre': str(audio.get('TCON', '')) if audio.get('TCON') else ''
            }
        elif ext == '.flac':
            audio = FLAC(filepath)
            tags = {
                'title': audio.get('title', [''])[0] if audio.get('title') else '',
                'artist': audio.get('artist', [''])[0] if audio.get('artist') else '',
                'album': audio.get('album', [''])[0] if audio.get('album') else '',
                'year': audio.get('date', [''])[0] if audio.get('date') else '',
                'genre': audio.get('genre', [''])[0] if audio.get('genre') else ''
            }
        elif ext == '.wav':
            audio = WAVE(filepath)
            tags = {
                'title': str(audio.get('TIT2', '')) if audio.get('TIT2') else '',
                'artist': str(audio.get('TPE1', '')) if audio.get('TPE1') else '',
                'album': str(audio.get('TALB', '')) if audio.get('TALB') else '',
                'year': str(audio.get('TDRC', '')) if audio.get('TDRC') else '',
                'genre': str(audio.get('TCON', '')) if audio.get('TCON') else ''
            }
        elif ext == '.ape':
            audio = APEv2File(filepath)
            tags = {
                'title': str(audio.get('Title', '')) if audio.get('Title') else '',
                'artist': str(audio.get('Artist', '')) if audio.get('Artist') else '',
                'album': str(audio.get('Album', '')) if audio.get('Album') else '',
                'year': str(audio.get('Year', '')) if audio.get('Year') else '',
                'genre': str(audio.get('Genre', '')) if audio.get('Genre') else ''
            }
        elif ext == '.ogg':
            audio = OggVorbis(filepath)
            tags = {
                'title': audio.get('title', [''])[0] if audio.get('title') else '',
                'artist': audio.get('artist', [''])[0] if audio.get('artist') else '',
                'album': audio.get('album', [''])[0] if audio.get('album') else '',
                'year': audio.get('date', [''])[0] if audio.get('date') else '',
                'genre': audio.get('genre', [''])[0] if audio.get('genre') else ''
            }
        else:
            return None
        
        # 提取年份的前4位数字
        if tags['year']:
            year_match = re.search(r'(\d{4})', str(tags['year']))
            if year_match:
                tags['year'] = year_match.group(1)
        
        return tags
    except Exception as e:
        main_logger.error(f'读取元数据失败 {filepath}: {e}')
        return None

def set_music_metadata(filepath, tags):
    """设置音乐文件元数据"""
    if not mutagen_available:
        return False
    
    try:
        ext = os.path.splitext(filepath)[1].lower()
        
        if ext == '.mp3':
            try:
                audio = MP3(filepath)
            except Exception:
                audio = MP3()
                audio.save(filepath)
                audio = MP3(filepath)
            
            if audio.tags is None:
                audio.add_tags()
            
            if tags.get('title'):
                audio.tags['TIT2'] = TIT2(encoding=3, text=tags['title'])
            if tags.get('artist'):
                audio.tags['TPE1'] = TPE1(encoding=3, text=tags['artist'])
            if tags.get('album'):
                audio.tags['TALB'] = TALB(encoding=3, text=tags['album'])
            if tags.get('year'):
                audio.tags['TDRC'] = TDRC(encoding=3, text=tags['year'])
            if tags.get('genre'):
                audio.tags['TCON'] = TCON(encoding=3, text=tags['genre'])
            
            audio.save()
            
        elif ext == '.flac':
            audio = FLAC(filepath)
            if tags.get('title'):
                audio['title'] = tags['title']
            if tags.get('artist'):
                audio['artist'] = tags['artist']
            if tags.get('album'):
                audio['album'] = tags['album']
            if tags.get('year'):
                audio['date'] = tags['year']
            if tags.get('genre'):
                audio['genre'] = tags['genre']
            audio.save()
            
        elif ext == '.ogg':
            audio = OggVorbis(filepath)
            if tags.get('title'):
                audio['title'] = tags['title']
            if tags.get('artist'):
                audio['artist'] = tags['artist']
            if tags.get('album'):
                audio['album'] = tags['album']
            if tags.get('year'):
                audio['date'] = tags['year']
            if tags.get('genre'):
                audio['genre'] = tags['genre']
            audio.save()
            
        else:
            return False
        
        return True
    except Exception as e:
        main_logger.error(f'写入元数据失败 {filepath}: {e}')
        return False

def has_lrc_file(music_filepath):
    """检查音乐文件是否有对应的LRC歌词文件"""
    lrc_path = os.path.splitext(music_filepath)[0] + '.lrc'
    return os.path.exists(lrc_path)

def parse_musicbrainz_recording(recording, filename):
    """解析MusicBrainz录音记录为标签字典"""
    tags = {}

    try:
        # 歌曲标题
        title = recording.get('title', '')
        if title:
            tags['title'] = title

        # 艺术家
        artist_credit = recording.get('artist-credit', [])
        if artist_credit:
            artists = []
            for credit in artist_credit:
                artist = credit.get('artist', {})
                artists.append(artist.get('name', ''))
            tags['artist'] = '; '.join(artists)

        # 专辑
        releases = recording.get('releases', [])
        if releases:
            # 选择第一个发行的专辑
            album = releases[0].get('title', '')
            if album:
                tags['album'] = album

        # 年份
        if releases:
            date = releases[0].get('date', '')
            if date:
                # 提取年份（日期格式可能是YYYY-MM-DD或YYYY）
                year_match = re.search(r'(\d{4})', date)
                if year_match:
                    tags['year'] = year_match.group(1)

        # 流派（MusicBrainz不一定有）
        genre = recording.get('genre', '')
        if genre:
            tags['genre'] = genre

        return tags if tags else None

    except Exception as e:
        main_logger.error(f'解析MusicBrainz记录失败: {e}')
        return None

def fetch_qq_music_tags(qq_api, title, artist, filename):
    """从QQ音乐获取标签信息"""
    try:
        # 构建搜索关键词
        query = f"{artist} {title}".strip() if artist else title

        # 搜索歌曲
        search_result = qq_api.getQQMusicSearch(query, page=1, size=5)

        if search_result and search_result.get('data'):
            songs = search_result['data']

            # 查找最佳匹配
            for song in songs:
                song_title = song.get('name', '')
                song_artists = song.get('singer', [])
                song_artist_names = ','.join([s.get('name', '') for s in song_artists])

                # 简单匹配逻辑
                title_match = title.lower() in song_title.lower() or song_title.lower() in title.lower()

                artist_match = True
                if artist:
                    artist_lower = artist.lower()
                    song_artist_lower = song_artist_names.lower()
                    # 检查是否有艺术家名称匹配
                    artist_match = any(a.lower() in song_artist_lower or song_artist_lower in a.lower()
                                     for a in artist.replace(';', ',').split(','))

                if title_match and (not artist or artist_match):
                    # 获取详细信息
                    album = song.get('album', {}).get('title', '')
                    mid = song.get('mid', '')

                    # 构建标签信息
                    tags = {
                        'title': song_title,
                        'artist': song_artist_names,
                        'album': album,
                        'year': '',
                        'genre': ''
                    }

                    # 获取封面URL
                    if mid:
                        tags['album_img'] = f"http://y.qq.com/music/photo_new/T002R300x300M000{mid}.jpg"

                    return tags

        return None

    except Exception as e:
        main_logger.error(f'从QQ音乐获取标签失败: {e}')
        return None

def fetch_netease_tags(netease_api, title, artist, filename):
    """从网易云音乐获取标签信息"""
    try:
        # 搜索歌曲
        songs = netease_api.fetch_id3_by_title(title)

        if songs:
            # 查找最佳匹配
            for song in songs:
                song_title = song.get('name', '')
                song_artist = song.get('artist', '')
                song_album = song.get('album', '')
                song_year = song.get('year', '')
                song_album_img = song.get('album_img', '')

                # 简单匹配逻辑
                title_match = title.lower() in song_title.lower() or song_title.lower() in title.lower()

                artist_match = True
                if artist:
                    artist_lower = artist.lower()
                    song_artist_lower = song_artist.lower()
                    # 检查是否有艺术家名称匹配
                    artist_match = any(a.lower() in song_artist_lower or song_artist_lower in a.lower()
                                     for a in artist.replace(';', ',').split(','))

                if title_match and (not artist or artist_match):
                    # 构建标签信息
                    tags = {
                        'title': song_title,
                        'artist': song_artist,
                        'album': song_album,
                        'year': song_year,
                        'genre': ''
                    }

                    # 添加封面
                    if song_album_img:
                        tags['album_img'] = song_album_img

                    return tags

        return None

    except Exception as e:
        main_logger.error(f'从网易云音乐获取标签失败: {e}')
        return None

def fetch_album_cover(qq_api, netease_api, title, artist, album):
    """从音乐平台获取专辑封面"""
    try:
        # 先尝试QQ音乐
        if qq_api:
            search_result = qq_api.getQQMusicSearch(f"{artist} {title}".strip(), page=1, size=1)
            if search_result and search_result.get('data'):
                song = search_result['data'][0]
                mid = song.get('mid', '')
                if mid:
                    return f"http://y.qq.com/music/photo_new/T002R300x300M000{mid}.jpg"

        # 再尝试网易云音乐
        if netease_api:
            songs = netease_api.fetch_id3_by_title(title)
            if songs:
                album_img = songs[0].get('album_img', '')
                if album_img:
                    return album_img

        return None

    except Exception as e:
        main_logger.error(f'获取专辑封面失败: {e}')
        return None

# ==================== 核心功能 ====================
def scan_music_files(directories, month=None):
    """扫描指定目录中的音乐文件"""
    if month is None:
        month = get_current_month()
    
    music_files = []
    
    for directory in directories:
        if not os.path.exists(directory):
            main_logger.warning(f'目录不存在: {directory}')
            continue
        
        main_logger.info(f'扫描目录: {directory}')
        
        for root, dirs, files in os.walk(directory):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in MUSIC_EXTENSIONS:
                    filepath = os.path.join(root, file)
                    file_month = get_file_modification_month(filepath)
                    
                    if file_month == month:
                        music_files.append({
                            'filepath': filepath,
                            'filename': file,
                            'month': file_month,
                            'directory': directory
                        })
    
    main_logger.info(f'找到 {len(music_files)} 个指定月份({month})的音乐文件')
    return music_files

def move_files_to_temp(files, temp_dir):
    """移动文件到临时目录"""
    os.makedirs(temp_dir, exist_ok=True)
    moved_count = 0
    
    for file_info in files:
        src = file_info['filepath']
        dst = os.path.join(temp_dir, file_info['filename'])
        
        # 如果目标文件已存在，添加序号
        counter = 1
        original_dst = dst
        while os.path.exists(dst):
            base, ext = os.path.splitext(original_dst)
            dst = f'{base}_{counter}{ext}'
            counter += 1
        
        try:
            shutil.move(src, dst)
            main_logger.info(f'移动文件: {src} -> {dst}')
            moved_count += 1
            
            # 同时移动LRC文件（如果存在）
            src_lrc = os.path.splitext(src)[0] + '.lrc'
            if os.path.exists(src_lrc):
                dst_lrc = os.path.splitext(dst)[0] + '.lrc'
                shutil.move(src_lrc, dst_lrc)
                main_logger.info(f'移动歌词: {src_lrc} -> {dst_lrc}')
        except Exception as e:
            main_logger.error(f'移动文件失败 {src}: {e}')
    
    return moved_count

def decrypt_netease_vip(month=None):
    """解密网易云音乐VIP文件"""
    main_logger.info('开始处理网易云音乐VIP文件')
    op_logger, log_path = create_operation_log('Neteasy')
    
    # 扫描VIP目录
    vip_files = scan_music_files([NETEASE_VIP_DIR], month)
    
    if not vip_files:
        main_logger.info('没有找到需要处理的网易云VIP文件')
        return 0
    
    # 移动VIP文件到临时目录
    main_logger.info(f'移动 {len(vip_files)} 个VIP文件到临时目录')
    move_files_to_temp(vip_files, NETEASE_TMP_DIR)
    
    # 运行um.exe进行解密
    main_logger.info('运行um.exe解密网易云音乐文件')
    op_logger.info(f'开始解密，输入目录: {NETEASE_TMP_DIR}，输出目录: {TEMP_COMPLETED_DIR}')
    
    try:
        # 构建命令
        cmd = [UM_EXE, '-i', NETEASE_TMP_DIR, '-o', TEMP_COMPLETED_DIR]
        main_logger.info(f'执行命令: {" ".join(cmd)}')
        
        # 执行解密程序
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore'
        )
        
        # 记录输出
        if result.stdout:
            op_logger.info(f'标准输出:\n{result.stdout}')
        if result.stderr:
            op_logger.warning(f'标准错误:\n{result.stderr}')
        
        op_logger.info(f'返回码: {result.returncode}')
        
        # 统计完成的文件
        completed_count = 0
        for root, dirs, files in os.walk(TEMP_COMPLETED_DIR):
            for file in files:
                if os.path.splitext(file)[1].lower() in AUDIO_EXTENSIONS:
                    completed_count += 1
        
        op_logger.info(f'解密完成，共处理 {completed_count} 个文件')
        main_logger.info(f'网易云VIP解密完成: {completed_count} 个文件')
        
        return completed_count
        
    except Exception as e:
        error_msg = f'解密网易云音乐失败: {e}'
        main_logger.error(error_msg)
        op_logger.error(error_msg)
        return 0

def decrypt_qq_vip(month=None):
    """解密QQ音乐VIP文件"""
    main_logger.info('开始处理QQ音乐VIP文件')
    op_logger, log_path = create_operation_log('QQ')

    # 扫描VIP目录
    vip_files = scan_music_files([QQ_VIP_DIR], month)

    if not vip_files:
        main_logger.info('没有找到需要处理的QQ VIP文件')
        return 0

    # 移动VIP文件到临时目录
    main_logger.info(f'移动 {len(vip_files)} 个VIP文件到临时目录')
    move_files_to_temp(vip_files, QQ_TMP_DIR)

    # 直接导入qq.py的run_decrypt函数并调用
    main_logger.info('运行qq.py解密QQ音乐文件')
    op_logger.info(f'开始解密，输入目录: {QQ_TMP_DIR}，输出目录: {TEMP_COMPLETED_DIR}')

    try:
        # 导入Decrypto/qq.py模块
        import Decrypto.qq as qq
        qq.run_decrypt(QQ_TMP_DIR, TEMP_COMPLETED_DIR)

        # 统计完成的文件
        completed_count = 0
        for root, dirs, files in os.walk(TEMP_COMPLETED_DIR):
            for file in files:
                if os.path.splitext(file)[1].lower() in AUDIO_EXTENSIONS:
                    completed_count += 1

        op_logger.info(f'解密完成，共处理 {completed_count} 个文件')
        main_logger.info(f'QQ VIP解密完成: {completed_count} 个文件')

        return completed_count

    except Exception as e:
        error_msg = f'解密QQ音乐失败: {e}'
        main_logger.error(error_msg)
        op_logger.error(error_msg)
        return 0

def run_soundalike_fingerprinting():
    """运行声纹识别去重"""
    main_logger.info('开始声纹识别去重')
    
    try:
        # 构建命令
        cmd = [
            SOUNDALIKE_EXE,
            '-move-interactive', TEMP_MOVE_DIR,
            '-temp', TEMP_COMPLETED_DIR,
            MAIN_DIR
        ]
        main_logger.info(f'执行命令: {" ".join(cmd)}')
        
        # 执行声纹识别程序
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore'
        )
        
        # 记录输出
        if result.stdout:
            main_logger.info(f'声纹识别输出:\n{result.stdout}')
        if result.stderr:
            main_logger.warning(f'声纹识别错误:\n{result.stderr}')
        
        main_logger.info(f'声纹识别完成，返回码: {result.returncode}')
        return result.returncode == 0
        
    except Exception as e:
        main_logger.error(f'声纹识别失败: {e}')
        return False

def update_tags_from_fingerprint():
    """根据声纹信息从在线数据库更新标签"""
    main_logger.info('开始从声纹信息更新标签')
    op_logger, log_path = create_operation_log('UpdateTags')

    if not mutagen_available:
        main_logger.error('mutagen库未安装，无法更新标签')
        return 0, 0, 0

    success_count = 0
    fail_count = 0
    incomplete_tags = []
    failed_files = []
    fingerprint_success_count = 0
    online_success_count = 0

    # 初始化指纹匹配器
    fingerprint_matcher = None
    if fingerprint_matcher_available:
        fingerprint_matcher = FingerprintMatcher()
        main_logger.info('声纹匹配器已初始化')
    else:
        main_logger.warning('声纹匹配模块不可用，将跳过指纹查询')

    # 初始化音乐API客户端
    qq_api = None
    netease_api = None
    if fingerprint_matcher_available:
        try:
            qq_api = QQMusicApi()
            netease_api = NetEaseMusicClient()
            main_logger.info('音乐API客户端已初始化')
        except Exception as e:
            main_logger.warning(f'音乐API客户端初始化失败: {e}')

    # 扫描临时完成目录
    for root, dirs, files in os.walk(TEMP_COMPLETED_DIR):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext not in AUDIO_EXTENSIONS:
                continue

            filepath = os.path.join(root, file)
            op_logger.info(f'处理文件: {filepath}')

            try:
                # 获取当前标签
                current_tags = get_music_metadata(filepath)
                if not current_tags:
                    # 从文件名解析
                    artist, title = parse_filename(file)
                    current_tags = {
                        'title': title,
                        'artist': artist,
                        'album': '',
                        'year': '',
                        'genre': ''
                    }

                # 第一步：尝试使用声纹查询MusicBrainz
                tag_updated = False
                if fingerprint_matcher and fingerprint_matcher_available:
                    try:
                        op_logger.info(f'  尝试声纹查询: {file}')
                        result = fingerprint_matcher.match_file(filepath)

                        if result.success and result.recordings:
                            # 选择最佳匹配（分数最高的）
                            best_recording = max(result.recordings, key=lambda x: x.get('score', 0))
                            score = best_recording.get('score', 0)

                            if score >= 50:  # 分数阈值
                                op_logger.info(f'  声纹匹配成功 (分数: {score:.1f}%)')

                                # 解析MusicBrainz记录
                                new_tags = parse_musicbrainz_recording(best_recording, file)

                                if new_tags:
                                    # 更新标签
                                    set_music_metadata(filepath, new_tags)
                                    tag_updated = True
                                    fingerprint_success_count += 1
                                    op_logger.info(f'  标签已从MusicBrainz更新: {new_tags.get("artist")} - {new_tags.get("title")}')

                                # 尝试下载封面
                                if music_tagger_available and new_tags.get('album'):
                                    try:
                                        tagger = MusicTagger(filepath)
                                        album_artists = []
                                        for artist_credit in best_recording.get('artist-credit', []):
                                            album_artists.append(artist_credit.get('artist', {}).get('name', ''))

                                        # 从QQ音乐或网易云音乐获取封面
                                        cover_url = fetch_album_cover(
                                            qq_api, netease_api,
                                            new_tags.get('title', ''),
                                            new_tags.get('artist', ''),
                                            new_tags.get('album', '')
                                        )

                                        if cover_url:
                                            op_logger.info(f'  已下载封面: {cover_url[:50]}...')
                                    except Exception as e:
                                        op_logger.warning(f'  下载封面失败: {e}')
                            else:
                                op_logger.info(f'  声纹匹配分数较低 ({score:.1f}%)，尝试其他方式')
                        else:
                            op_logger.info(f'  声纹查询无结果，尝试其他方式')
                    except Exception as e:
                        op_logger.warning(f'  声纹查询失败: {e}')

                # 第二步：如果声纹查询失败，使用歌曲名和歌手从音乐网站查询
                if not tag_updated and qq_api and netease_api:
                    try:
                        op_logger.info(f'  尝试在线音乐平台查询: {file}')

                        # 获取查询信息（优先使用标签信息，否则使用文件名）
                        title = current_tags.get('title', '')
                        artist = current_tags.get('artist', '')

                        if not title:
                            artist, title = parse_filename(file)

                        if title:
                            # 优先尝试QQ音乐
                            tag_info = fetch_qq_music_tags(qq_api, title, artist, file)
                            source = 'QQ音乐'

                            # 如果QQ音乐失败，尝试网易云音乐
                            if not tag_info:
                                tag_info = fetch_netease_tags(netease_api, title, artist, file)
                                source = '网易云音乐'

                            if tag_info:
                                # 更新标签
                                set_music_metadata(filepath, tag_info)
                                tag_updated = True
                                online_success_count += 1
                                op_logger.info(f'  标签已从{source}更新: {tag_info.get("artist")} - {tag_info.get("title")}')

                                # 尝试下载封面
                                if music_tagger_available and tag_info.get('album_img'):
                                    try:
                                        tagger = MusicTagger(filepath)
                                        tagger.update_tags({
                                            'album_img': tag_info['album_img']
                                        }, is_raw_thumbnail=False)
                                        op_logger.info(f'  已从{source}下载封面')
                                    except Exception as e:
                                        op_logger.warning(f'  下载封面失败: {e}')
                        else:
                            op_logger.warning(f'  无法确定歌曲名称，跳过在线查询')
                    except Exception as e:
                        op_logger.warning(f'  在线查询失败: {e}')

                # 检查标签完整性
                updated_tags = get_music_metadata(filepath) if tag_updated else current_tags
                missing_fields = []
                if updated_tags is not None and not updated_tags.get('title'):
                    missing_fields.append('歌曲名')
                if updated_tags is not None and not updated_tags.get('artist'):
                    missing_fields.append('歌手')
                if updated_tags is not None and not updated_tags.get('year'):
                    missing_fields.append('年份')

                # 检查封面（仅对MP3和FLAC）
                has_cover = False
                if ext == '.mp3':
                    try:
                        audio = MP3(filepath)
                        if audio.tags and 'APIC:' in str(audio.tags.keys()):
                            has_cover = True
                    except Exception:
                        pass
                elif ext == '.flac':
                    try:
                        audio = FLAC(filepath)
                        if audio.pictures:
                            has_cover = True
                    except Exception:
                        pass

                if not has_cover:
                    missing_fields.append('封面')

                if missing_fields:
                    incomplete_tags.append({
                        'filepath': filepath,
                        'filename': file,
                        'missing': missing_fields,
                        'current_tags': updated_tags
                    })
                    op_logger.warning(f'标签不完整: {file} - 缺少: {", ".join(missing_fields)}')

                success_count += 1
                op_logger.info(f'处理完成: {file}')

            except Exception as e:
                fail_count += 1
                failed_files.append({'filepath': filepath, 'error': str(e)})
                op_logger.error(f'标签更新失败 {file}: {e}')

    # 记录统计信息
    op_logger.info(f'\n{"="*50}')
    op_logger.info(f'标签更新统计:')
    op_logger.info(f'处理总数: {success_count + fail_count}')
    op_logger.info(f'成功: {success_count}')
    op_logger.info(f'失败: {fail_count}')
    op_logger.info(f'  - 声纹匹配成功: {fingerprint_success_count}')
    op_logger.info(f'  - 在线查询成功: {online_success_count}')

    if incomplete_tags:
        op_logger.info(f'\n标签不完整的文件 ({len(incomplete_tags)} 个):')
        for item in incomplete_tags:
            op_logger.info(f"  - {item['filename']}: 缺少 {', '.join(item['missing'])}")

    if failed_files:
        op_logger.info(f'\n更新失败的文件 ({len(failed_files)} 个):')
        for item in failed_files:
            op_logger.info(f"  - {item['filepath']}: {item['error']}")

    main_logger.info(f'标签更新完成: 成功 {success_count}, 失败 {fail_count}, 声纹 {fingerprint_success_count}, 在线 {online_success_count}')
    return success_count, fail_count, fingerprint_success_count + online_success_count

def check_filename_consistency(check_master=True, check_temp=True):
    """检查文件名与标签的一致性"""
    main_logger.info('开始检查文件名一致性')
    op_logger, log_path = create_operation_log('Check')
    
    if not mutagen_available:
        main_logger.error('mutagen库未安装，无法检查标签')
        return 0, 0, 0
    
    directories = []
    if check_temp:
        directories.append(TEMP_COMPLETED_DIR)
    if check_master:
        directories.append(MAIN_DIR)
    
    inconsistent_files = []
    duplicate_files = []
    missing_lrc_files = []
    
    # 收集所有音乐文件信息
    music_info_list = []
    
    for directory in directories:
        if not os.path.exists(directory):
            continue
        
        for root, dirs, files in os.walk(directory):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext not in AUDIO_EXTENSIONS:
                    continue
                
                filepath = os.path.join(root, file)
                tags = get_music_metadata(filepath)
                
                if tags:
                    music_info_list.append({
                        'filepath': filepath,
                        'filename': file,
                        'tags': tags
                    })
    
    # 检查文件名一致性
    main_logger.info('检查文件名与标签一致性')
    for info in music_info_list:
        filename_artist, filename_title = parse_filename(info['filename'])
        tag_artist = info['tags'].get('artist', '')
        tag_title = info['tags'].get('title', '')
        
        # 标准化比较
        filename_artists = set(split_artist(normalize_text(filename_artist)))
        tag_artists = set(split_artist(normalize_text(tag_artist)))
        
        consistent = True
        
        # 检查艺术家
        if filename_artists and tag_artists:
            if not (filename_artists & tag_artists):  # 没有交集
                consistent = False
        
        # 检查歌曲名
        norm_filename_title = normalize_text(filename_title)
        norm_tag_title = normalize_text(tag_title)
        if norm_filename_title and norm_tag_title:
            if norm_filename_title != norm_tag_title:
                # 允许部分匹配
                if norm_filename_title not in norm_tag_title and norm_tag_title not in norm_filename_title:
                    consistent = False
        
        if not consistent:
            inconsistent_files.append({
                'filepath': info['filepath'],
                'filename': info['filename'],
                'filename_artist': filename_artist,
                'filename_title': filename_title,
                'tag_artist': tag_artist,
                'tag_title': tag_title
            })
            op_logger.warning(f'文件名不一致: {info["filename"]}')
            op_logger.warning(f'  文件名解析: {filename_artist} - {filename_title}')
            op_logger.warning(f'  标签信息: {tag_artist} - {tag_title}')
    
    # 查找重复文件
    main_logger.info('查找重复音乐文件')
    artist_title_map = {}
    for info in music_info_list:
        tag_artist = info['tags'].get('artist', '')
        tag_title = info['tags'].get('title', '')
        
        if tag_artist and tag_title:
            key = (normalize_text(tag_artist), normalize_text(tag_title))
            if key not in artist_title_map:
                artist_title_map[key] = []
            artist_title_map[key].append(info)
    
    for key, files in artist_title_map.items():
        if len(files) > 1:
            duplicate_files.append({
                'artist_title': key,
                'files': files
            })
            op_logger.warning(f'发现重复文件: {key[0]} - {key[1]}')
            for f in files:
                op_logger.warning(f'  - {f["filepath"]}')
    
    # 检查歌词文件
    main_logger.info('检查歌词文件')
    for info in music_info_list:
        if not has_lrc_file(info['filepath']):
            missing_lrc_files.append(info)
            op_logger.warning(f'缺少歌词文件: {info["filename"]}')
    
    # 记录统计
    op_logger.info(f'\n{"="*50}')
    op_logger.info(f'检查结果统计:')
    op_logger.info(f'文件名不一致: {len(inconsistent_files)} 个')
    op_logger.info(f'重复文件组: {len(duplicate_files)} 组')
    op_logger.info(f'缺少歌词: {len(missing_lrc_files)} 个')
    
    main_logger.info(f'文件检查完成: 不一致 {len(inconsistent_files)}, 重复 {len(duplicate_files)}, 缺歌词 {len(missing_lrc_files)}')
    
    return len(inconsistent_files), len(duplicate_files), len(missing_lrc_files)

def organize_by_year():
    """按年份分类整理音乐文件"""
    main_logger.info('开始按年份分类整理')
    op_logger, log_path = create_operation_log('Organize')
    
    if not mutagen_available:
        main_logger.error('mutagen库未安装，无法读取年份信息')
        return 0, 0
    
    success_count = 0
    unknown_count = 0
    unknown_dir = os.path.join(TEMP_COMPLETED_DIR, 'unknown')
    os.makedirs(unknown_dir, exist_ok=True)
    
    # 扫描临时完成目录
    for root, dirs, files in os.walk(TEMP_COMPLETED_DIR):
        # 跳过unknown目录本身
        if 'unknown' in root:
            continue
        
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext not in AUDIO_EXTENSIONS:
                continue
            
            filepath = os.path.join(root, file)
            
            # 获取标签
            tags = get_music_metadata(filepath)
            
            if not tags:
                # 移动到unknown
                dst = os.path.join(unknown_dir, file)
                try:
                    shutil.move(filepath, dst)
                    op_logger.warning(f'无法读取标签，移动到unknown: {file}')
                    unknown_count += 1
                except Exception as e:
                    op_logger.error(f'移动文件失败 {file}: {e}')
                continue
            
            # 检查必要标签
            missing = []
            if not tags.get('title'):
                missing.append('歌曲名')
            if not tags.get('artist'):
                missing.append('歌手')
            if not tags.get('year'):
                missing.append('年份')
            
            if missing:
                # 移动到unknown
                dst = os.path.join(unknown_dir, file)
                try:
                    shutil.move(filepath, dst)
                    op_logger.warning(f'标签不完整({", ".join(missing)})，移动到unknown: {file}')
                    unknown_count += 1
                except Exception as e:
                    op_logger.error(f'移动文件失败 {file}: {e}')
                continue
            
            # 解析年份
            year_str = tags.get('year', '')
            year_match = re.search(r'(\d{4})', str(year_str))
            
            if not year_match:
                # 移动到unknown
                dst = os.path.join(unknown_dir, file)
                try:
                    shutil.move(filepath, dst)
                    op_logger.warning(f'无法解析年份，移动到unknown: {file}')
                    unknown_count += 1
                except Exception as e:
                    op_logger.error(f'移动文件失败 {file}: {e}')
                continue
            
            year = int(year_match.group(1))
            
            # 确定目标目录
            if year <= 1979:
                decade_dir = '1950-1979'
            else:
                decade = (year // 10) * 10
                decade_dir = f'{decade}-{decade+9}'
            
            year_dir = os.path.join(TEMP_COMPLETED_DIR, decade_dir, str(year))
            os.makedirs(year_dir, exist_ok=True)
            
            # 移动文件
            dst = os.path.join(year_dir, file)
            counter = 1
            original_dst = dst
            while os.path.exists(dst):
                base, ext = os.path.splitext(original_dst)
                dst = f'{base}_{counter}{ext}'
                counter += 1
            
            try:
                shutil.move(filepath, dst)
                op_logger.info(f'移动文件到 {decade_dir}/{year}: {file}')
                
                # 同时移动LRC文件
                src_lrc = os.path.splitext(filepath)[0] + '.lrc'
                if os.path.exists(src_lrc):
                    dst_lrc = os.path.splitext(dst)[0] + '.lrc'
                    shutil.move(src_lrc, dst_lrc)
                    op_logger.info(f'移动歌词文件: {os.path.basename(src_lrc)}')
                
                success_count += 1
            except Exception as e:
                op_logger.error(f'移动文件失败 {file}: {e}')
    
    # 记录统计
    op_logger.info(f'\n{"="*50}')
    op_logger.info(f'分类整理统计:')
    op_logger.info(f'成功分类: {success_count}')
    op_logger.info(f'未知(移动到unknown): {unknown_count}')
    
    main_logger.info(f'年份分类完成: 成功 {success_count}, 未知 {unknown_count}')
    return success_count, unknown_count

def check_database_consistency():
    """检查数据库一致性"""
    main_logger.info('开始检查数据库一致性')
    
    try:
        # 构建命令
        cmd = [SOUNDALIKE_EXE, '-check', MAIN_DIR]
        main_logger.info(f'执行命令: {" ".join(cmd)}')
        
        # 执行检查程序
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore'
        )
        
        # 记录输出
        if result.stdout:
            main_logger.info(f'数据库检查输出:\n{result.stdout}')
        if result.stderr:
            main_logger.warning(f'数据库检查错误:\n{result.stderr}')
        
        main_logger.info(f'数据库检查完成，返回码: {result.returncode}')
        return result.returncode == 0
        
    except Exception as e:
        main_logger.error(f'数据库检查失败: {e}')
        return False

def move_netease_normal_files(month=None):
    """移动网易云音乐普通文件"""
    main_logger.info('开始移动网易云音乐普通文件')
    
    files = scan_music_files([NETEASE_DIR], month)
    # 排除VIP目录
    files = [f for f in files if NETEASE_VIP_DIR not in f['filepath']]
    
    if files:
        count = move_files_to_temp(files, TEMP_COMPLETED_DIR)
        main_logger.info(f'移动 {count} 个网易云普通文件到临时完成目录')
        return count
    return 0

def move_qq_normal_files(month=None):
    """移动QQ音乐普通文件"""
    main_logger.info('开始移动QQ音乐普通文件')
    
    files = scan_music_files([QQ_DIR], month)
    # 排除VIP目录
    files = [f for f in files if QQ_VIP_DIR not in f['filepath']]
    
    if files:
        count = move_files_to_temp(files, TEMP_COMPLETED_DIR)
        main_logger.info(f'移动 {count} 个QQ普通文件到临时完成目录')
        return count
    return 0

# ==================== 主程序 ====================
def main():
    """主程序入口"""
    # 设置命令行参数解析
    parser = argparse.ArgumentParser(
        description='音乐文件管理系统',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
使用示例:
  # 完整处理流程（默认处理当前月份）
  python main.py
  
  # 处理指定月份
  python main.py --month 202406
  
  # 仅检查主目录
  python main.py --check-master
  
  # 不检查临时目录
  python main.py --uncheck-temp
  
  # 检查数据库一致性
  python main.py --checkdb
        '''
    )
    
    parser.add_argument(
        '--month',
        type=str,
        default=None,
        help='指定扫描的月份 (格式: YYYYMM，默认: 当前月份)'
    )
    
    parser.add_argument(
        '--check-master',
        action='store_true',
        help='检查主目录D:\\music的文件'
    )
    
    parser.add_argument(
        '--uncheck-temp',
        action='store_true',
        help='不检查临时已完成目录G:\\Temp'
    )
    
    parser.add_argument(
        '--checkdb',
        action='store_true',
        help='仅检查数据库和目录文件的一致性状态'
    )
    
    parser.add_argument(
        '--skip-vip',
        action='store_true',
        help='跳过VIP文件解密步骤'
    )
    
    parser.add_argument(
        '--skip-fingerprint',
        action='store_true',
        help='跳过声纹识别步骤'
    )
    
    parser.add_argument(
        '--skip-tag-update',
        action='store_true',
        help='跳过标签更新步骤'
    )
    
    parser.add_argument(
        '--skip-check',
        action='store_true',
        help='跳过文件检查步骤'
    )
    
    parser.add_argument(
        '--skip-organize',
        action='store_true',
        help='跳过年份分类步骤'
    )
    
    args = parser.parse_args()
    
    # 设置日志
    setup_logging()
    
    # 检查数据库一致性模式
    if args.checkdb:
        main_logger.info('运行数据库一致性检查模式')
        success = check_database_consistency()
        sys.exit(0 if success else 1)
    
    # 获取月份参数
    month = args.month
    if month is None:
        month = get_current_month()
        main_logger.info(f'使用当前月份: {month}')
    else:
        main_logger.info(f'使用指定月份: {month}')
    
    # 记录开始时间
    start_time = time.time()
    main_logger.info('='*60)
    main_logger.info('音乐文件管理系统 - 开始处理')
    main_logger.info('='*60)
    
    # 步骤1: 处理VIP文件
    if not args.skip_vip:
        main_logger.info('\n' + '='*60)
        main_logger.info('步骤 1/7: 处理VIP文件')
        main_logger.info('='*60)
        
        # 网易云VIP
        netease_count = decrypt_netease_vip(month)
        
        # QQ VIP
        qq_count = decrypt_qq_vip(month)
        
        # 移动普通文件
        netease_normal_count = move_netease_normal_files(month)
        qq_normal_count = move_qq_normal_files(month)
        
        main_logger.info(f'VIP处理完成: 网易 {netease_count} 个, QQ {qq_count} 个')
        main_logger.info(f'普通文件: 网易 {netease_normal_count} 个, QQ {qq_normal_count} 个')
    
    # 步骤2: 声纹识别去重
    if not args.skip_fingerprint:
        main_logger.info('\n' + '='*60)
        main_logger.info('步骤 2/7: 声纹识别去重')
        main_logger.info('='*60)
        run_soundalike_fingerprinting()
    
    # 步骤3: 更新标签
    if not args.skip_tag_update:
        main_logger.info('\n' + '='*60)
        main_logger.info('步骤 3/7: 更新标签信息')
        main_logger.info('='*60)
        success, fail, tag_success = update_tags_from_fingerprint()
        main_logger.info(f'标签更新汇总: 成功 {success}, 失败 {fail}, 标签更新 {tag_success}')
    
    # 步骤4: 检查文件
    if not args.skip_check:
        main_logger.info('\n' + '='*60)
        main_logger.info('步骤 4/7: 检查文件一致性')
        main_logger.info('='*60)
        check_filename_consistency(
            check_master=args.check_master,
            check_temp=not args.uncheck_temp
        )
    
    # 步骤5: 年份分类
    if not args.skip_organize:
        main_logger.info('\n' + '='*60)
        main_logger.info('步骤 5/7: 按年份分类整理')
        main_logger.info('='*60)
        organize_by_year()
    
    # 记录结束时间
    end_time = time.time()
    elapsed = end_time - start_time
    
    main_logger.info('\n' + '='*60)
    main_logger.info('音乐文件管理系统 - 处理完成')
    main_logger.info(f'总耗时: {elapsed:.2f} 秒')
    main_logger.info(f'主日志文件: {log_file}')
    main_logger.info('='*60)

if __name__ == '__main__':
    main()
