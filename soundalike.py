# -*- coding: utf-8 -*-
"""
声纹识别去重模块 - 使用 Soundalike 工具进行声纹识别和去重
"""

import subprocess
from config import TEMP_MOVE_DIR, TEMP_COMPLETED_DIR, MAIN_DIR, SOUNDALIKE_EXE
from utils import main_logger


def run_soundalike_fingerprinting():
    """运行声纹识别去重（使用--temp参数）"""
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
            errors='replace'
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


def run_soundalike_fingerprinting_without_temp():
    """运行声纹识别去重（不带--temp参数）"""
    main_logger.info('开始声纹识别去重（不带--temp参数）')

    try:
        # 构建命令（不带-temp参数）
        cmd = [
            SOUNDALIKE_EXE,
            '-move-interactive', TEMP_MOVE_DIR,
            MAIN_DIR
        ]
        main_logger.info(f'执行命令: {" ".join(cmd)}')

        # 执行声纹识别程序
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
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
            errors='replace'
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
