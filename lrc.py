# -*- coding: utf-8 -*-
"""LRC歌词文件管理模块

查找缺失的歌词文件和孤立的歌词文件
"""

import os
import shutil
import logging

from config import mutagen_available

# 从config优雅降级导入mutagen模块
if mutagen_available:
    from config import MP3, FLAC, WAVE

logger = logging.getLogger(__name__)


def find_missing_lrc_files(root_dir: str, temp_path: str = None) -> list[tuple[str, str]]:
    """查找缺失.lrc文件的音乐文件

    Args:
        root_dir: 要搜索的根目录
        temp_path: 如果指定，将缺失lrc的文件移动到此目录

    Returns:
        缺失lrc文件的列表，每个元素是 (filename, dirpath) 元组
    """
    missing_lrc_files = []

    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.lower().endswith(('.flac', '.mp3', '.wav', '.ogg')):
                base_filename = os.path.splitext(filename)[0]
                lrc_filename = base_filename + '.lrc'
                lrc_filepath = os.path.join(dirpath, lrc_filename)

                if not os.path.exists(lrc_filepath):
                    # 如果指定了临时目录，移动文件
                    if temp_path:
                        try:
                            if not os.path.exists(temp_path):
                                os.makedirs(temp_path, exist_ok=True)
                            shutil.move(os.path.join(dirpath, filename),
                                       os.path.join(temp_path, filename))
                            logger.info(f"Moved file without lrc: {filename} -> {temp_path}")
                        except Exception as e:
                            logger.error(f"Failed to move {filename}: {e}")
                    missing_lrc_files.append((filename, dirpath))

    return missing_lrc_files


def find_orphan_lrc_files(directory: str) -> list[str]:
    """查找孤立的.lrc文件（没有对应音乐文件的歌词）

    Args:
        directory: 要搜索的目录

    Returns:
        孤立的lrc文件路径列表
    """
    # 支持的音乐文件扩展名
    music_extensions = {'.flac', '.mp3', '.wav', '.ape', '.ogg'}
    orphan_lrc_files = []

    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.lrc'):
                lrc_file_path = os.path.join(root, file)
                base_name = os.path.splitext(file)[0]

                # 检查是否存在对应的音乐文件
                has_music_file = False
                for ext in music_extensions:
                    if any(os.path.splitext(f)[0] == base_name and f.lower().endswith(ext)
                           for f in files):
                        has_music_file = True
                        break

                if not has_music_file:
                    orphan_lrc_files.append(lrc_file_path)

    return orphan_lrc_files


def main():
    """主函数：检查缺失和孤立的lrc文件"""
    root_directory = 'G:\\temp'
    temp_path = 'G:\\tmp'

    # 检查缺失lrc的音乐文件
    print('检查缺失lrc的音乐文件')
    missing_files = find_missing_lrc_files(root_directory, temp_path)

    if missing_files:
        print("The following files are missing corresponding .lrc files:")
        for file_info in missing_files:
            print(f"File: {file_info[0]}, Directory: {file_info[1]}")
    else:
        print("No missing .lrc files found.")

    # 检查孤立的lrc文件
    print("\n检查孤立的lrc文件")
    orphan_lrc_files = find_orphan_lrc_files(root_directory)

    if orphan_lrc_files:
        print("Orphan .lrc files:")
        for lrc_file in orphan_lrc_files:
            print(lrc_file)
    else:
        print("No orphan .lrc files found.")


if __name__ == '__main__':
    main()
