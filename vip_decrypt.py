# -*- coding: utf-8 -*-
"""
VIP解密模块 - 网易云和QQ音乐VIP文件解密
"""

import os
import subprocess
from config import (
    NETEASE_DIR, NETEASE_VIP_DIR, NETEASE_TMP_DIR,
    QQ_DIR, QQ_VIP_DIR, QQ_TMP_DIR,
    TEMP_COMPLETED_DIR, AUDIO_EXTENSIONS, NETEASE_VIP_EXTENSIONS, QQ_VIP_EXTENSIONS, UM_EXE
)
import utils
import file_operations


def decrypt_netease_vip(month=None):
    """解密网易云音乐VIP加密文件"""
    utils.main_logger.info('开始处理网易云音乐VIP加密文件')

    # 扫描VIP加密文件
    vip_files = file_operations.scan_music_files([NETEASE_VIP_DIR], month)

    if not vip_files:
        utils.main_logger.info('没有找到需要处理的网易云VIP文件')
        return 0

    # 移动VIP文件到临时目录
    utils.main_logger.info(f'移动 {len(vip_files)} 个VIP文件到临时目录')
    file_operations.move_files_to_temp(vip_files, NETEASE_TMP_DIR)

    # 运行um.exe进行解密
    utils.main_logger.info('运行um.exe解密网易云音乐文件')
    op_logger = utils.create_operation_log('Neteasy')
    op_logger.info(f'开始解密，输入目录: {NETEASE_TMP_DIR}，输出目录: {TEMP_COMPLETED_DIR}')

    try:
        # 构建命令
        cmd = [UM_EXE, '-i', NETEASE_TMP_DIR, '-o', TEMP_COMPLETED_DIR]
        utils.main_logger.info(f'执行命令: {" ".join(cmd)}')

        # 执行解密程序
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )

        # 记录输出
        if result.stdout:
            op_logger.info(f'标准输出:\n{result.stdout}')
        if result.stderr:
            op_logger.warning(f'标准错误:\n{result.stderr}')

        op_logger.info(f'返回码: {result.returncode}')

        # 统计完成的文件
        completed_count = 0
        for root, _, files in os.walk(TEMP_COMPLETED_DIR):
            for file in files:
                if os.path.splitext(file)[1].lower() in AUDIO_EXTENSIONS:
                    completed_count += 1

        op_logger.info(f'解密完成，共处理 {completed_count} 个文件')

        # 将解密后的文件移回原目录
        utils.main_logger.info('将解密后的文件移回原目录')
        moved_back_count = file_operations.move_decrypted_files_back(TEMP_COMPLETED_DIR)
        op_logger.info(f'已移回 {moved_back_count} 个文件到原目录')
        utils.main_logger.info(f'网易云VIP解密完成: {completed_count} 个文件，已移回 {moved_back_count} 个文件')

        return completed_count

    except Exception as e:
        error_msg = f'解密网易云音乐失败: {e}'
        utils.main_logger.error(error_msg)
        op_logger.error(error_msg)
        return 0


def decrypt_qq_vip(month=None):
    """解密QQ音乐VIP加密文件"""
    utils.main_logger.info('开始处理QQ音乐VIP加密文件')

    # 扫描VIP加密文件
    vip_files = file_operations.scan_music_files([QQ_VIP_DIR], month)

    if not vip_files:
        utils.main_logger.info('没有找到需要处理的QQ VIP文件')
        return 0

    # 移动VIP文件到临时目录
    utils.main_logger.info(f'移动 {len(vip_files)} 个VIP文件到临时目录')
    file_operations.move_files_to_temp(vip_files, QQ_TMP_DIR)

    # 直接导入qq.py的run_decrypt函数并调用
    utils.main_logger.info('运行qq.py解密QQ音乐文件')
    op_logger = utils.create_operation_log('QQ')
    op_logger.info(f'开始解密，输入目录: {QQ_TMP_DIR}，输出目录: {TEMP_COMPLETED_DIR}')

    try:
        # 导入Decrypto模块
        try:
            from Decrypto import run_decrypt
        except ImportError:
            utils.main_logger.error('Decrypto模块不可用')
            op_logger.error('Decrypto模块不可用')
            return 0

        run_decrypt(QQ_TMP_DIR, TEMP_COMPLETED_DIR)

        # 统计完成的文件
        completed_count = 0
        for root, _, files in os.walk(TEMP_COMPLETED_DIR):
            for file in files:
                if os.path.splitext(file)[1].lower() in AUDIO_EXTENSIONS:
                    completed_count += 1

        op_logger.info(f'解密完成，共处理 {completed_count} 个文件')

        # 将解密后的文件移回原目录
        utils.main_logger.info('将解密后的文件移回原目录')
        moved_back_count = file_operations.move_decrypted_files_back(TEMP_COMPLETED_DIR)
        op_logger.info(f'已移回 {moved_back_count} 个文件到原目录')
        utils.main_logger.info(f'QQ VIP解密完成: {completed_count} 个文件，已移回 {moved_back_count} 个文件')

        return completed_count

    except Exception as e:
        error_msg = f'解密QQ音乐失败: {e}'
        utils.main_logger.error(error_msg)
        op_logger.error(error_msg)
        return 0
