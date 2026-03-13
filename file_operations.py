# -*- coding: utf-8 -*-
"""
文件操作模块 - 文件扫描、移动、整理等操作
"""

import os
import shutil
import re
from config import (
    MUSIC_EXTENSIONS, AUDIO_EXTENSIONS, VIP_EXTENSIONS,
    NETEASE_VIP_EXTENSIONS, QQ_VIP_EXTENSIONS,
    MAIN_DIR, NETEASE_DIR, NETEASE_VIP_DIR, QQ_DIR, QQ_VIP_DIR,
    TEMP_COMPLETED_DIR
)
import utils
import metadata


def scan_music_files(directories, month=None, file_type='all'):
    """扫描指定目录中的音乐文件

    Args:
        directories: 要扫描的目录列表
        month: 月份（YYYYMM格式），None表示当前月
        file_type: 文件类型
            - 'all': 所有音乐文件（包括加密和普通）
            - 'normal': 只扫描普通音频文件（不包括加密格式）
            - 'vip': 只扫描加密文件
    """
    if month is None:
        month = utils.get_current_month()

    # 根据文件类型确定要扫描的扩展名
    if file_type == 'normal':
        extensions = AUDIO_EXTENSIONS  # 普通音频
    elif file_type == 'vip':
        extensions = VIP_EXTENSIONS  # 加密文件
    else:
        extensions = MUSIC_EXTENSIONS  # 所有文件

    music_files = []

    for directory in directories:
        if not os.path.exists(directory):
            utils.main_logger.warning(f'目录不存在: {directory}')
            continue

        utils.main_logger.info(f'扫描目录: {directory}')

        for root, _, files in os.walk(directory):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in extensions:
                    filepath = os.path.join(root, file)
                    file_month = utils.get_file_modification_month(filepath)

                    if file_month == month:
                        music_files.append({
                            'filepath': filepath,
                            'filename': file,
                            'month': file_month,
                            'directory': directory
                        })

    main_logger.info(f'找到 {len(music_files)} 个指定月份({month})的音乐文件（类型: {file_type}）')
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
            utils.main_logger.info(f'移动文件: {src} -> {dst}')
            moved_count += 1

            # 同时移动LRC文件（如果存在）
            src_lrc = os.path.splitext(src)[0] + '.lrc'
            if os.path.exists(src_lrc):
                dst_lrc = os.path.splitext(dst)[0] + '.lrc'
                shutil.move(src_lrc, dst_lrc)
                utils.main_logger.info(f'移动歌词: {src_lrc} -> {dst_lrc}')
        except Exception as e:
            utils.main_logger.error(f'移动文件失败 {src}: {e}')

    return moved_count


def copy_files_to_temp(files, temp_dir):
    """拷贝文件到临时目录"""
    os.makedirs(temp_dir, exist_ok=True)
    copied_count = 0

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
            shutil.copy2(src, dst)
            utils.main_logger.info(f'拷贝文件: {src} -> {dst}')
            copied_count += 1

            # 同时拷贝LRC文件（如果存在）
            src_lrc = os.path.splitext(src)[0] + '.lrc'
            if os.path.exists(src_lrc):
                dst_lrc = os.path.splitext(dst)[0] + '.lrc'
                shutil.copy2(src_lrc, dst_lrc)
                utils.main_logger.info(f'拷贝歌词: {src_lrc} -> {dst_lrc}')
        except Exception as e:
            utils.main_logger.error(f'拷贝文件失败 {src}: {e}')

    return copied_count


def move_decrypted_files_back(completed_dir, source_dir):
    """将解密后的文件移动回原VIP目录

    Args:
        completed_dir: 解密后的文件所在的目录（TEMP_COMPLETED_DIR）
        source_dir: 原VIP目录（NETEASE_VIP_DIR 或 QQ_VIP_DIR）

    将 completed_dir 下的所有文件移动回 source_dir。
    """
    if not os.path.exists(completed_dir):
        utils.main_logger.warning(f'解密目录不存在: {completed_dir}')
        return 0

    moved_count = 0

    # 移动解密后的文件回原目录
    for file in os.listdir(completed_dir):
        src_path = os.path.join(completed_dir, file)

        # 跳过目录
        if os.path.isdir(src_path):
            continue

        dst_path = os.path.join(source_dir, file)

        # 如果目标文件已存在，添加序号
        counter = 1
        original_dst = dst_path
        while os.path.exists(dst_path):
            base, ext = os.path.splitext(original_dst)
            dst_path = f'{base}_{counter}{ext}'
            counter += 1

        try:
            shutil.move(src_path, dst_path)
            utils.main_logger.info(f'移动解密文件: {src_path} -> {dst_path}')
            moved_count += 1
        except Exception as e:
            utils.main_logger.error(f'移动文件失败 {src_path}: {e}')

    utils.main_logger.info(f'完成: 移动 {moved_count} 个解密文件到 {source_dir}')
    return moved_count


def check_filename_consistency(check_master=True, check_temp=True, debug_mode=False):
    """检查文件名与标签的一致性"""
    utils.main_logger.info('开始检查文件名一致性')
    op_logger = utils.create_operation_log('Check', debug_mode=debug_mode)

    directories = []
    if check_temp:
        directories.append(TEMP_COMPLETED_DIR)
    if check_master:
        directories.append(MAIN_DIR)

    inconsistent_files = []
    duplicate_files = []
    missing_lrc_files = []
    orphan_lrc_files = []

    # 收集所有音乐文件信息
    music_info_list = []

    for directory in directories:
        if not os.path.exists(directory):
            continue

        for root, _, files in os.walk(directory):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext not in AUDIO_EXTENSIONS:
                    continue

                filepath = os.path.join(root, file)
                tags = metadata.get_music_metadata(filepath)

                if tags:
                    music_info_list.append({
                        'filepath': filepath,
                        'filename': file,
                        'tags': tags
                    })

    # 检查只有"-"分隔符的文件名，修改为" - "
    utils.main_logger.info('检查只有"-"分隔符的文件名')
    files_renamed = []
    for directory in directories:
        if not os.path.exists(directory):
            continue

        for root, _, files in os.walk(directory):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext not in AUDIO_EXTENSIONS:
                    continue

                filepath = os.path.join(root, file)
                name = os.path.splitext(file)[0]

                # 检查是否只有"-"分隔符
                if ' - ' not in name and '-' in name:
                    # 检查是否有多个"-"（避免误判如歌曲名中包含-）
                    if name.count('-') == 1:
                        # 只有单个"-"，需要改为" - "
                        new_name = name.replace('-', ' - ')
                        new_filename = new_name + ext
                        new_filepath = os.path.join(root, new_filename)

                        # 检查重名
                        if os.path.exists(new_filepath):
                            # 重名，删除原文件
                            op_logger.warning(f'发现重名文件，删除: {file}')
                            try:
                                os.remove(filepath)
                                files_renamed.append({'file': file, 'action': 'deleted (duplicate)'})

                                # 删除对应的LRC文件（如果存在）
                                lrc_path = os.path.splitext(filepath)[0] + '.lrc'
                                if os.path.exists(lrc_path):
                                    os.remove(lrc_path)
                                    op_logger.warning(f'删除对应的LRC文件: {os.path.basename(lrc_path)}')
                            except Exception as e:
                                op_logger.error(f'删除文件失败 {file}: {e}')
                        else:
                            # 不重名，重命名文件
                            op_logger.warning(f'重命名文件: {file} -> {new_filename}')
                            try:
                                os.rename(filepath, new_filepath)
                                files_renamed.append({'file': file, 'new_name': new_filename, 'action': 'renamed'})

                                # 重命名对应的LRC文件（如果存在）
                                lrc_path = os.path.splitext(filepath)[0] + '.lrc'
                                if os.path.exists(lrc_path):
                                    new_lrc_filename = new_name + '.lrc'
                                    new_lrc_path = os.path.join(root, new_lrc_filename)
                                    os.rename(lrc_path, new_lrc_path)
                                    op_logger.warning(f'重命名LRC文件: {os.path.basename(lrc_path)} -> {new_lrc_filename}')
                            except Exception as e:
                                op_logger.error(f'重命名文件失败 {file}: {e}')

    if files_renamed:
        main_logger.info(f'文件名分隔符处理完成: {len(files_renamed)} 个文件')
        for item in files_renamed:
            op_logger.info(f"  - {item['file']}: {item['action']}")

    # 检查孤立的LRC文件（只有LRC文件，没有对应音乐文件）
    main_logger.info('检查孤立LRC文件')
    for directory in directories:
        if not os.path.exists(directory):
            continue

        for root, _, files in os.walk(directory):
            for file in files:
                if not file.lower().endswith('.lrc'):
                    continue

                lrc_path = os.path.join(root, file)
                # 去掉.lrc扩展名，尝试匹配音乐文件
                name_without_ext = os.path.splitext(file)[0]

                has_music_file = False
                for ext in AUDIO_EXTENSIONS:
                    music_path = os.path.join(root, name_without_ext + ext)
                    if os.path.exists(music_path):
                        has_music_file = True
                        break

                if not has_music_file:
                    orphan_lrc_files.append(lrc_path)
                    op_logger.warning(f'发现孤立LRC文件: {file}')

    # 检查文件名一致性
    main_logger.info('检查文件名与标签一致性')
    for info in music_info_list:
        filename_artist, filename_title = utils.parse_filename(info['filename'])
        tag_artist = info['tags'].get('artist', '')
        tag_title = info['tags'].get('title', '')

        # 标准化比较
        filename_artists = set(utils.split_artist(utils.normalize_text(filename_artist)))
        tag_artists = set(utils.split_artist(utils.normalize_text(tag_artist)))

        consistent = True

        # 检查艺术家
        if filename_artists and tag_artists:
            if not (filename_artists & tag_artists):  # 没有交集
                consistent = False

        # 检查歌曲名
        norm_filename_title = utils.normalize_text(filename_title)
        norm_tag_title = utils.normalize_text(tag_title)
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
            key = (utils.normalize_text(tag_artist), utils.normalize_text(tag_title))
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
        if not utils.has_lrc_file(info['filepath']):
            missing_lrc_files.append(info)
            op_logger.warning(f'缺少歌词文件: {info["filename"]}')

    # 记录统计
    op_logger.info(f'\n{"="*50}')
    op_logger.info(f'检查结果统计:')
    op_logger.info(f'文件名分隔符处理: {len(files_renamed)} 个')
    op_logger.info(f'文件名不一致: {len(inconsistent_files)} 个')
    op_logger.info(f'重复文件组: {len(duplicate_files)} 组')
    op_logger.info(f'缺少歌词: {len(missing_lrc_files)} 个')
    op_logger.info(f'孤立LRC: {len(orphan_lrc_files)} 个')

    main_logger.info(f'文件检查完成: 分隔符处理 {len(files_renamed)}, 不一致 {len(inconsistent_files)}, 重复 {len(duplicate_files)}, 缺歌词 {len(missing_lrc_files)}, 孤立LRC {len(orphan_lrc_files)}')

    return len(inconsistent_files), len(duplicate_files), len(missing_lrc_files)


def organize_by_year(debug_mode=False):
    """按年份分类整理音乐文件"""
    main_logger.info('开始按年份分类整理')
    op_logger = utils.create_operation_log('Organize', debug_mode=debug_mode)

    success_count = 0
    unknown_count = 0
    unknown_dir = os.path.join(TEMP_COMPLETED_DIR, 'unknown')
    os.makedirs(unknown_dir, exist_ok=True)

    # 扫描临时完成目录
    for root, _, files in os.walk(TEMP_COMPLETED_DIR):
        # 跳过unknown目录本身
        unknown_dir_path = os.path.join(TEMP_COMPLETED_DIR, 'unknown')
        if root == unknown_dir_path or root.startswith(unknown_dir_path + os.sep):
            continue

        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext not in AUDIO_EXTENSIONS:
                continue

            filepath = os.path.join(root, file)

            # 获取标签
            tags = metadata.get_music_metadata(filepath)

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
            if not year_str:
                # 移动到unknown
                dst = os.path.join(unknown_dir, file)
                try:
                    shutil.move(filepath, dst)
                    op_logger.warning(f'年份为空，移动到unknown: {file}')
                    unknown_count += 1
                except Exception as e:
                    op_logger.error(f'移动文件失败 {file}: {e}')
                continue

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


def copy_netease_normal_files(month=None):
    """拷贝网易云音乐普通文件到临时目录"""
    main_logger.info('开始拷贝网易云音乐普通文件')

    files = scan_music_files([NETEASE_DIR], month, file_type='normal')
    # 排除VIP目录
    files = [f for f in files if NETEASE_VIP_DIR not in f['filepath']]

    if files:
        count = copy_files_to_temp(files, TEMP_COMPLETED_DIR)
        main_logger.info(f'拷贝 {count} 个网易云普通文件到临时完成目录')
        return count
    return 0


def copy_qq_normal_files(month=None):
    """拷贝QQ音乐普通文件到临时目录"""
    main_logger.info('开始拷贝QQ音乐普通文件')

    files = scan_music_files([QQ_DIR], month, file_type='normal')
    # 排除VIP目录
    files = [f for f in files if QQ_VIP_DIR not in f['filepath']]

    if files:
        count = copy_files_to_temp(files, TEMP_COMPLETED_DIR)
        main_logger.info(f'拷贝 {count} 个QQ普通文件到临时完成目录')
        return count
    return 0
