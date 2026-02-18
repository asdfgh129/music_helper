# -*- coding: utf-8 -*-
"""音乐文件归档管理模块

提供音乐文件元数据管理、重复检测、按年份组织等功能
"""

import os
import logging
import shutil
import traceback
from typing import Any

from config import (
    mutagen_available,
    MP3, FLAC, WAVE, APEv2File, OggVorbis
)

logger = logging.getLogger(__name__)

# 支持的音乐文件扩展名
MUSIC_EXTENSIONS = {'.flac', '.mp3', '.wav', '.ape', '.ogg'}


def generate_music_metadata(directory: str) -> list[dict[str, Any]]:
    """读取目录下每个音乐文件的元数据信息

    Args:
        directory: 要扫描的目录

    Returns:
        元数据列表，每个元素包含 title, artist, album, year, filename, filepath
    """
    if not mutagen_available:
        logger.error("Mutagen library is not available")
        return []

    metadata = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.lower().endswith(('.mp3', '.flac', '.wav')):
                try:
                    path = os.path.join(root, file)
                    year = None
                    title = 'Unknown'
                    artist = 'Unknown'
                    album = 'Unknown'

                    if file.lower().endswith('.mp3'):
                        audio = MP3(path)
                        year = audio.get('TDRC')
                        title = audio.get('TIT2')
                        artist = audio.get('TPE1')
                        album = audio.get('TALB')
                    elif file.lower().endswith('.flac'):
                        audio = FLAC(path)
                        year = audio.get('date')
                        title = audio.get('title')
                        artist = audio.get('artist')
                        album = audio.get('album')
                    elif file.lower().endswith('.wav'):
                        audio = WAVE(path)
                        year = audio.get('TDRC')
                        title = audio.get('TIT2')
                        artist = audio.get('TPE1')
                        album = audio.get('TALB')

                    # 提取实际值
                    if year and len(year) > 0:
                        year = year[0]
                    if title and len(title) > 0:
                        title = title[0]
                    if artist and len(artist) > 0:
                        artist = artist[0]
                    if album and len(album) > 0:
                        album = album[0]

                    metadata.append({
                        'title': title or 'Unknown',
                        'artist': artist or 'Unknown',
                        'album': album or 'Unknown',
                        'year': year,
                        'filename': file,
                        'filepath': path
                    })
                except Exception as e:
                    logger.error(f"Error reading metadata for {file}: {e}")
                    logger.error(traceback.format_exc())

    return metadata


def split_artist(artist: str) -> list[str]:
    """拆分艺术家名称

    Args:
        artist: 艺术家字符串，可能包含多个艺术家

    Returns:
        艺术家列表
    """
    return [a.strip() for a in artist.lower()
            .replace('；', ',').replace(';', ',')
            .replace('，', ',').replace('&', ',')
            .replace('/', ',').split(',') if a.strip()]


def find_missing_lrc_files(root_dir: str, temp_dir: str = None) -> list[tuple[str, str]]:
    """查找缺失lrc文件的音乐文件

    Args:
        root_dir: 要搜索的根目录
        temp_dir: 如果指定，从此目录尝试恢复lrc文件

    Returns:
        缺失lrc文件的列表，每个元素是 (filename, dirpath) 元组
    """
    missing_lrc_files = []

    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.lower().endswith(('.flac', '.mp3', '.wav')):
                base_filename = os.path.splitext(filename)[0]
                lrc_filename = base_filename + '.lrc'
                lrc_filepath = os.path.join(dirpath, lrc_filename)

                if not os.path.exists(lrc_filepath):
                    # 尝试从临时目录恢复
                    if temp_dir:
                        temp_lrc = os.path.join(temp_dir, lrc_filename)
                        if os.path.exists(temp_lrc):
                            try:
                                shutil.move(temp_lrc, lrc_filepath)
                                logger.info(f"Recovered lrc: {lrc_filename}")
                                continue
                            except Exception as e:
                                logger.error(f"Failed to recover lrc {lrc_filename}: {e}")

                    missing_lrc_files.append((filename, dirpath))

    return missing_lrc_files


def delete_duplicates(dest_metadata: list[dict], temp_metadata: list[dict]) -> int:
    """删除在目标目录已存在的临时目录文件

    Args:
        dest_metadata: 目标目录的元数据
        temp_metadata: 临时目录的元数据

    Returns:
        删除的文件数量
    """
    deleted_count = 0

    for temp_item in temp_metadata:
        for dest_item in dest_metadata:
            if (temp_item['title'].lower() == dest_item['title'].lower() and
                split_artist(temp_item['artist']) == split_artist(dest_item['artist'])):

                temp_filepath = temp_item['filepath']
                temp_file_ext = os.path.splitext(temp_item['filename'])[1].lower()
                dest_file_ext = os.path.splitext(dest_item['filename'])[1].lower()

                # 删除规则
                should_delete = (dest_file_ext in ['.flac', '.wav']) or (temp_file_ext == '.mp3')
                should_delete = should_delete or (dest_file_ext == '.flac' or temp_file_ext == dest_file_ext)

                if should_delete and os.path.exists(temp_filepath):
                    logger.warning(f"Delete {temp_filepath}")
                    os.remove(temp_filepath)
                    deleted_count += 1

                    # 删除对应的lrc文件
                    temp_lrc = os.path.splitext(temp_filepath)[0] + '.lrc'
                    if os.path.exists(temp_lrc):
                        logger.warning(f"Delete {temp_lrc}")
                        os.remove(temp_lrc)

    return deleted_count


def move_to_dir(music_dir: str) -> int:
    """将音乐文件按年份移动到相应目录

    Args:
        music_dir: 音乐文件所在目录

    Returns:
        移动的文件数量
    """
    if not mutagen_available:
        logger.error("Mutagen library is not available")
        return 0

    logger.info("开始根据日期移动音乐文件...")
    moved_count = 0

    for root, _, files in os.walk(music_dir):
        for file in files:
            if any(file.lower().endswith(ext) for ext in MUSIC_EXTENSIONS):
                file_path = os.path.join(root, file)
                try:
                    audio = None
                    date = None

                    if file.lower().endswith('.mp3'):
                        audio = MP3(file_path)
                        date = audio.get('TDRC')
                    elif file.lower().endswith('.flac'):
                        audio = FLAC(file_path)
                        date = audio.get('date')
                    elif file.lower().endswith('.wav'):
                        audio = WAVE(file_path)
                        date = audio.get('TDRC')
                    elif file.lower().endswith('.ape'):
                        audio = APEv2File(file_path)
                        date = audio.get('Year')
                    elif file.lower().endswith('.ogg'):
                        audio = OggVorbis(file_path)
                        date = audio.get('DATE')

                    if date and len(date) > 0:
                        date = str(date[0])[:4]

                    if date and date.isdigit():
                        year = int(date)
                        # 确定年代目录
                        if year <= 1979:
                            decade_dir = os.path.join(music_dir, "1950-1979")
                        else:
                            decade = (year // 10) * 10
                            decade_dir = os.path.join(music_dir, f"{decade}-{decade+9}")
                        year_dir = os.path.join(decade_dir, date)

                        # 确保目录存在
                        os.makedirs(decade_dir, exist_ok=True)
                        os.makedirs(year_dir, exist_ok=True)

                        # 如果文件不在正确目录，移动它
                        if root != year_dir:
                            new_file_path = os.path.join(year_dir, file)
                            counter = 1
                            while os.path.exists(new_file_path):
                                base, ext = os.path.splitext(file)
                                new_file_path = os.path.join(year_dir, f"{base}_{counter}{ext}")
                                counter += 1

                            shutil.move(file_path, new_file_path)
                            logger.info(f"移动: {file_path} -> {new_file_path}")
                            moved_count += 1

                            # 移动对应的lrc文件
                            lrc_file = os.path.splitext(file_path)[0] + '.lrc'
                            if os.path.exists(lrc_file):
                                new_lrc_file = os.path.splitext(new_file_path)[0] + '.lrc'
                                shutil.move(lrc_file, new_lrc_file)
                                logger.info(f"移动: {lrc_file} -> {new_lrc_file}")
                    else:
                        logger.warning(f'未找到 {file_path} 的发行日期')

                except Exception as e:
                    logger.error(f"处理文件 {file_path} 时出错: {e}")
                    logger.error(traceback.format_exc())

    return moved_count


def find_orphan_lrc_files(directory: str, delete: bool = False) -> list[str]:
    """查找孤立的lrc文件

    Args:
        directory: 要搜索的目录
        delete: 是否删除孤立的lrc文件

    Returns:
        孤立的lrc文件路径列表
    """
    orphan_lrc_files = []

    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.lrc'):
                lrc_file_path = os.path.join(root, file)
                base_name = os.path.splitext(file)[0]

                # 检查是否存在对应的音乐文件
                has_music_file = False
                for ext in MUSIC_EXTENSIONS:
                    if any(os.path.splitext(f)[0] == base_name and f.lower().endswith(ext)
                           for f in files):
                        has_music_file = True
                        break

                if not has_music_file:
                    orphan_lrc_files.append(lrc_file_path)
                    if delete:
                        logger.warning(f"Delete {lrc_file_path}")
                        try:
                            os.remove(lrc_file_path)
                        except Exception as e:
                            logger.error(f"Failed to delete {lrc_file_path}: {e}")

    return orphan_lrc_files


def main():
    """主函数：执行音乐归档流程"""
    # 设置目录路径
    dest_dir = 'D:\\music\\'
    temp_dir = 'G:\\temp\\'

    # 配置日志
    logging.basicConfig(
        filename='archive.log',
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    # 第一步：读取目标文件夹元数据
    print("读取目标文件夹音乐文件的元数据")
    logger.info("读取目标文件夹音乐文件的元数据")
    dest_metadata = generate_music_metadata(dest_dir)
    logger.info(f"找到 {len(dest_metadata)} 个目标文件")

    # 第二步：读取临时文件夹元数据
    print("读取临时文件夹中的音乐文件的元数据")
    logger.info("读取临时文件夹中的音乐文件的元数据")
    temp_metadata = generate_music_metadata(temp_dir)
    logger.info(f"找到 {len(temp_metadata)} 个临时文件")

    # 第三步：删除重复文件
    print("比对两份源数据，删除在目标文件夹已存在的临时目录音乐文件")
    logger.info("比对两份源数据，删除在目标文件夹已存在的临时目录音乐文件")
    deleted_count = delete_duplicates(dest_metadata, temp_metadata)
    print(f"删除了 {deleted_count} 个重复文件")

    # 第四步：移动文件到年份目录
    print("移动音乐文件和歌词文件到年份文件夹")
    logger.info("移动音乐文件和歌词文件到年份文件夹")
    moved_count = move_to_dir(temp_dir)
    print(f"移动了 {moved_count} 个文件")

    # 第五步：检查缺失lrc
    print("检查缺失lrc的音乐文件")
    logger.info("检查缺失lrc的音乐文件")
    missing_files = find_missing_lrc_files(temp_dir, temp_dir)

    if missing_files:
        print(f"存在 {len(missing_files)} 个没有歌词的歌曲，请查阅log")
        for file_info in missing_files:
            logger.warning(f"Missing lrc: {file_info[0]} in {file_info[1]}")
    else:
        print("No missing .lrc files found.")
        logger.info("No missing .lrc files found.")

    # 第六步：检查孤立lrc
    print("检查孤立的lrc文件")
    logger.info("检查孤立的lrc文件")
    orphan_count = len(find_orphan_lrc_files(temp_dir, delete=True))
    print(f"处理了 {orphan_count} 个孤立的lrc文件")


if __name__ == '__main__':
    main()
