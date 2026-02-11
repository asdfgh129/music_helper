import os
import csv
import shutil
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.wave import WAVE
from mutagen.apev2 import APEv2File
from mutagen.oggvorbis import OggVorbis
from mutagen.id3 import ID3, TIT2, TPE1, TPE2, TALB, TRCK, TYER, APIC, error, ID3NoHeaderError
# from opencc import OpenCC
import re
import logging
import traceback


# Configure logging
logging.basicConfig(filename='archive.log', level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')


# 繁体转简体
# cc = OpenCC('t2s')

# 读取目标目录下每个音乐文件的元数据信息
def generate_music_metadata(directory):
    metadata = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.lower().endswith(('.mp3', '.flac', '.wav')):
                try:
                    path = os.path.join(root, file)
                    if file.lower().endswith('.mp3'):
                        audio = MP3(path)
                        year = audio.get('TDRC', [None])[0]  # 获取MP3文件中的年份信息
                        title = audio.get('TIT2', [None])[0] or 'Unknown'
                        artist = audio.get('TPE1', [None])[0] or 'Unknown'
                        album = audio.get('TALB', [None])[0] or 'Unknown'
                       
                    elif file.lower().endswith('.flac'):
                        audio = FLAC(path)
                        year = audio.get('date', [None])[0]  # 获取FLAC文件中的年份信息
                        title = audio.get('title', [None])[0]  # 获取标题
                        artist = audio.get('artist', [None])[0]  # 获取艺术家
                        album = audio.get('album', [None])[0]  # 获取专辑
                    elif file.lower().endswith('.wav'):
                        audio = WAVE(path)
                        year = audio.get('TDRC', [None])[0]  # 获取WAV文件中的年份信息
                        title = audio.get('TIT2', [None])[0] or 'Unknown'
                        artist = audio.get('TPE1', [None])[0] or 'Unknown'
                        album = audio.get('TALB', [None])[0] or 'Unknown'
                        # year = audio.get(TYER, [None])[0] or 'Unknown'
                    
                    metadata.append({
                        'title': title,
                        'artist': artist,
                        'album': album,
                        'year': year,
                        'filename': file,
                        'filepath': path
                    })
                except error:
                    logging.error(f"Error reading metadata for {file}")
                    logging.error(traceback.format_exc())
    
    
    # 将数据结构转化为csv文件
    # with open( filename + '.csv', 'w', newline='', encoding='utf-8') as csvfile:
    #    writer = csv.DictWriter(csvfile, fieldnames=['title', 'artist', 'album', 'year', 'filename', 'filepath'])
    #    writer.writeheader()
    #    writer.writerows(metadata)
    return metadata

# 拆分艺术家名称
def split_artist(artist):
    return [a.strip() for a in artist.lower().replace('；', ',').replace(';', ',').replace('，', ',').replace('&', ',').replace('/', ',').split(',') if a.strip()]


def find_missing_lrc_files(root_dir):
    missing_lrc_files = []

    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.endswith('.flac') or filename.endswith('.mp3') or filename.endswith(".wav"):
                base_filename = os.path.splitext(filename)[0]
                lrc_filename = base_filename + '.lrc'
                lrc_filepath = os.path.join(dirpath, lrc_filename)

                if not os.path.exists(lrc_filepath):
                    temp_lrc = os.path.join(temp_dir, lrc_filename)
                    if os.path.exists(temp_lrc):
                        shutil.move(temp_lrc, lrc_filepath)
                    else:
                        missing_lrc_files.append((filename, dirpath))

    return missing_lrc_files

def delete_duplicates(dest_metadata, temp_metadata, temp_dir):
    for temp_item in temp_metadata:
        for dest_item in dest_metadata:
            if temp_item['title'].lower() == dest_item['title'].lower() and split_artist(temp_item['artist']) == split_artist(dest_item['artist']):
                temp_filepath = temp_item['filepath']
                temp_file_ext = os.path.splitext(temp_item['filename'])[1].lower()
                dest_file_ext = os.path.splitext(dest_item['filename'])[1].lower()

                # 如果dest_metadata中的是flac或wav文件，或者temp_metadata中的是mp3文件，则删除temp_dir中的对应音乐文件和lrc文件（如果存在的话）
                if (dest_file_ext in ['.flac', '.wav']) or (temp_file_ext == '.mp3'):
                    if os.path.exists(temp_filepath):
                        logging.warning(f"Delete {temp_filepath}")
                        os.remove(temp_filepath)
                    temp_lrc = os.path.splitext(temp_filepath)[0] + '.lrc'
                    if os.path.exists(temp_lrc):
                        logging.warning(f"Delete {temp_lrc}")
                        os.remove(temp_lrc)
                # 如果dest_metadata中的是flac，则删除temp_dir中的对应音乐文件和lrc文件（如果存在的话）
                if (dest_file_ext in ['.flac']) or temp_file_ext == dest_file_ext:
                    if os.path.exists(temp_filepath):
                        logging.warning(f"Delete {temp_filepath}")
                        os.remove(temp_filepath)
                    temp_lrc = os.path.splitext(temp_filepath)[0] + '.lrc'
                    if os.path.exists(temp_lrc):
                        logging.warning(f"Delete {temp_lrc}")
                        os.remove(temp_lrc)

def move_to_dir(music_dir):
    print("开始根据日期移动音乐文件...")
    # moved_files = []  # 记录移动后的文件路径
    for root, dirs, files in os.walk(music_dir):
        for file in files:
            if any(file.lower().endswith(ext) for ext in music_extensions):
                file_path = os.path.join(root, file)
                try:
                    if file.lower().endswith('.mp3'):
                        audio = MP3(file_path)
                        date = audio.get('TDRC', [None])[0]  # 获取MP3文件中的年份信息
                       
                    elif file.lower().endswith('.flac'):
                        audio = FLAC(file_path)
                        date = audio.get('date', [None])[0]  # 获取FLAC文件中的年份信息
                    elif file.lower().endswith('.wav'):
                        audio = WAVE(file_path)
                        date = audio.get('TDRC', [None])[0]  # 获取WAV文件中的年份信息
                    elif file.lower().endswith('.ape'):
                        audio = APEv2File(file_path)
                        date = audio.get('Year', [None])[0]
                        #audio = mutagen.File(file_path, easy=True)

                    if date:
                            date = str(date)
                            date = date[:4]
                            
                    if date and date.isdigit():
                        year = int(date)
                        if year <= 1979:
                            decade_dir = os.path.join(music_dir, "1950-1979")
                        else:
                            decade = (year // 10) * 10
                            decade_dir = os.path.join(music_dir, f"{decade}-{decade+9}")
                        year_dir = os.path.join(decade_dir, date)
                        
                        # 确保十年目录存在
                        os.makedirs(decade_dir, exist_ok=True)
                        # 确保年份目录存在
                        os.makedirs(year_dir, exist_ok=True)
                        
                        # 检查文件是否已经在正确的目录中
                        if root != year_dir:
                            # 生成新的文件路径，确保文件名唯一
                            new_file_path = os.path.join(year_dir, file)
                            counter = 1
                            while os.path.exists(new_file_path):
                                base, ext = os.path.splitext(file)
                                new_file_path = os.path.join(year_dir, f"{base}_{counter}{ext}")
                                counter += 1
                            shutil.move(file_path, new_file_path)
                            # 记录移动后的文件路径
                            # moved_files.append(new_file_path)
                            # print(f"移动文件: {file}")
                            logging.info(f"移动前路径: {file_path}")
                            logging.info(f"移动后路径: {new_file_path}")

                            # 移动对应的.lrc文件
                            lrc_file = os.path.splitext(file_path)[0] + '.lrc'
                            if os.path.exists(lrc_file):
                                new_lrc_file = os.path.splitext(new_file_path)[0] + '.lrc'
                                shutil.move(lrc_file, new_lrc_file)
                                # moved_files.append(new_lrc_file)  # 记录移动后的.lrc文件路径
                                # print(f"移动文件: {os.path.basename(lrc_file)}")
                                logging.info(f"移动前路径: {lrc_file}")
                                logging.info(f"移动后路径: {new_lrc_file}")
                    else:
                        logging.error(f'error:未找到 {file_path} 的发行日期！')
                except Exception as e:
                    logging.error(f"处理文件 {file_path} 时出错: {e}")
                    logging.error(traceback.print_exc())
    # return moved_files



def find_orphan_lrc_files(directory):
    # 支持的音乐文件扩展名
    
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
                    logging.warning(f"Delete {lrc_file_path}")
                    os.remove(lrc_file_path)

    return orphan_lrc_files


def read_and_process_metadata(file_path):
    try:
        if file_path.lower().endswith('.flac'):
            audio = FLAC(file_path)
        elif file_path.lower().endswith('.mp3'):
            audio = MP3(file_path)
        elif file_path.lower().endswith('.wav'):
            audio = WAVE(file_path)
        elif file_path.lower().endswith('.ape'):
            audio = APEv2File(file_path)
        elif file_path.lower().endswith('.ogg'):
            audio = OggVorbis(file_path)
        else:
            logging.warning(f"不支持的文件格式: {file_path}")
            return None

        tags = {}
        if audio.tags is not None:
            for key in audio.tags.keys():
                tags[key] = audio.tags[key]

        # Define the tags to process
        tags_to_process = {
            'TIT2': '标题',
            'TALB': '专辑',
            'TPE1': '艺术家',
            'TPE2': '专辑艺术家'
        }

        changed = False
        for tag, description in tags_to_process.items():
            if tag in tags:

                if isinstance(tags[tag][0], list):
                    original_value = tags[tag][0] if tags[tag][0] else ''
                else:
                    original_value = tags[tag].text[0] if hasattr(tags[tag],'text') else str(tags[tag])
                    
                
                # 繁体转简体
                # value = cc.convert(original_value)

                # 英文首字母大写
                value = re.sub(r'\b(\w)', lambda m: m.group(1).upper(), value.lower())

                if value != original_value:
                    logging.info(f"处理文件: {file_path}")
                    logging.info(f"标签 {description} ({tag}) 的值从 '{original_value}' 改为 '{value}'")
                    if file_path.lower().endswith('.mp3') or file_path.lower().endswith('.wav'):
                        if tag == 'TIT2':
                            audio.tags['TIT2'] = TIT2(encoding=3, text=value)
                        elif tag == 'TALB':
                            audio.tags['TALB'] = TALB(encoding=3, text=value)
                        elif tag == 'TPE1':
                            audio.tags['TPE1'] = TPE1(encoding=3, text=value)
                        elif tag == 'TPE2':
                            audio.tags['TPE2'] = TPE2(encoding=3, text=value)
                    elif file_path.lower().endswith('.flac') or file_path.lower().endswith('.ape') or file_path.lower().endswith('.ogg'):
                        audio[tag] = value

                    changed = True

        if changed:
            audio.save()
            logging.info(f"处理文件: {file_path} 成功")

        return tags

    except Exception as e:
        logging.error(f"读取文件 {file_path} 时出错: {e}")
        logging.error(traceback.format_exc())
        return None

def process_music_files_in_directory(music_dir):
    for root, dirs, files in os.walk(music_dir):
        for file in files:
            file_path = os.path.join(root, file)
            if any(file.lower().endswith(ext) for ext in music_extensions):
                logging.info(f"正在处理文件: {file_path}")
                read_and_process_metadata(file_path)
                

# 设置目录路径
dest_dir = 'D:\\music\\'

temp_dir = 'G:\\temp\\'

music_extensions = {'.flac', '.mp3', '.wav', '.ape', '.ogg'}

# 第一步
# print("修改源文件夹音乐文件的元数据，进行繁简转换和英文规范化")
# logging.info("修改源文件夹音乐文件的元数据，进行繁简转换和英文规范化")
# process_music_files_in_directory(temp_dir)

# 第二步：
print("读取目标文件夹音乐文件的元数据")
logging.info("读取目标文件夹音乐文件的元数据")
dest_metadata = generate_music_metadata(dest_dir)

# 第三步：
print("读取临时文件夹中的音乐文件的元数据")
logging.info("读取临时文件夹中的音乐文件的元数据")
temp_metadata = generate_music_metadata(temp_dir)

# 第四步：
print("比对两份源数据，删除在目标文件夹已存在的临时目录音乐文件")
logging.info("比对两份源数据，删除在目标文件夹已存在的临时目录音乐文件")

delete_duplicates(dest_metadata, temp_metadata, temp_dir)

# 第五步：
print("移动音乐文件和歌词文件到年份文件夹")
logging.info("移动音乐文件和歌词文件到年份文件夹")
move_to_dir(temp_dir)

# 第六步：
print("检查缺失lrc的音乐文件")
logging.info("检查缺失lrc的音乐文件")

missing_files = find_missing_lrc_files(temp_dir)

if missing_files:
    logging.info("The following files are missing corresponding .lrc files:")

    for file_info in missing_files:
        logging.warning(f"File: {file_info[0]}, Directory: {file_info[1]}")
    print("存在没有歌词的歌曲，请查阅log")
else:
    logging.info("No missing .lrc files found.")

# 第七步
print("检查孤立的lrc文件")
logging.info("检查孤立的lrc文件")
orphan_lrc_files = find_orphan_lrc_files(temp_dir)

