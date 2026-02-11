import os
import shutil
from mutagen.mp3 import MP3
from mutagen.flac import FLAC
from mutagen.wave import WAVE

def find_missing_lrc_files(root_dir):
    missing_lrc_files = []

    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.endswith('.flac') or filename.endswith('.mp3') or filename.endswith(".wav") or filename.endswith(".ogg"):
                base_filename = os.path.splitext(filename)[0]
                lrc_filename = base_filename + '.lrc'
                lrc_filepath = os.path.join(dirpath, lrc_filename)

                if not os.path.exists(lrc_filepath):
                    shutil.move(os.path.join(dirpath,filename), temp_path)
                    missing_lrc_files.append((filename, dirpath))

    return missing_lrc_files


print('检查缺失lrc的音乐文件')
root_directory = 'G:\\temp'
temp_path = 'G:\\tmp'
missing_files = find_missing_lrc_files(root_directory)


if missing_files:
    print("The following files are missing corresponding .lrc files:")

    for file_info in missing_files:
        print(f"File: {file_info[0]}, Directory: {file_info[1]}")
else:
    print("No missing .lrc files found.")


def find_orphan_lrc_files(directory):
    # 支持的音乐文件扩展名
    music_extensions = {'.flac', '.mp3', '.wav', '.ape', '.ogg'}
    # 存储孤立的.lrc文件
    orphan_lrc_files = []

    # 遍历目录及子目录
    for root, dirs, files in os.walk(directory):
        # 检查每个文件
        for file in files:
            # 如果是.lrc文件
            if file.endswith('.lrc'):
                lrc_file_path = os.path.join(root, file)
                # 获取.lrc文件的基本名称（不含扩展名）
                base_name = os.path.splitext(file)[0]
                # 检查是否存在对应的音乐文件
                has_music_file = False
                for ext in music_extensions:
                    if any(os.path.splitext(f)[0] == base_name and f.endswith(ext) for f in files):
                        has_music_file = True
                        break
                # 如果没有对应的音乐文件
                if not has_music_file:
                    orphan_lrc_files.append(lrc_file_path)

    return orphan_lrc_files


# 执行功能
orphan_lrc_files = find_orphan_lrc_files(root_directory)

# 打印结果
print("Orphan .lrc files:")
for lrc_file in orphan_lrc_files:
    print(lrc_file)
