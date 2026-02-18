# -*- coding: utf-8 -*-
"""
音乐文件管理系统 - 主程序入口
"""

import sys
import argparse
import time

from utils import setup_logging, get_current_month, validate_month_format, main_logger, log_file
from vip_decrypt import decrypt_netease_vip, decrypt_qq_vip
from soundalike import run_soundalike_fingerprinting, check_database_consistency
from tag_updater import update_tags_from_fingerprint
from file_operations import (
    check_filename_consistency, organize_by_year,
    move_netease_normal_files, move_qq_normal_files
)
from config import MAIN_DIR, TEMP_COMPLETED_DIR


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
        if not validate_month_format(month):
            main_logger.error(f'月份格式错误: {month}，应为YYYYMM格式（如202406）')
            sys.exit(1)
        main_logger.info(f'使用指定月份: {month}')

    # 记录开始时间
    start_time = time.time()
    main_logger.info('='*60)
    main_logger.info('音乐文件管理系统 - 开始处理')
    main_logger.info('='*60)

    # 确定处理目录
    if args.check_master:
        target_dir = MAIN_DIR
        main_logger.info(f'使用 check-master 模式，只处理主目录: {target_dir}')
    else:
        target_dir = TEMP_COMPLETED_DIR
        main_logger.info(f'使用默认模式，只处理临时目录: {target_dir}')

    # 步骤1: 解密VIP文件和移动普通文件（check-master模式下跳过）
    if not args.skip_vip and not args.check_master:
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

    if args.check_master:
        main_logger.info('\n' + '='*60)
        main_logger.info('check-master 模式: 跳过VIP文件解密和移动')
        main_logger.info('='*60)

    # 步骤2: 声纹识别去重
    if not args.skip_fingerprint:
        main_logger.info('\n' + '='*60)
        main_logger.info('步骤 2/7: 声纹识别去重')
        main_logger.info('='*60)
        # check-master模式下不带--temp参数
        if args.check_master:
            from soundalike import run_soundalike_fingerprinting_without_temp
            run_soundalike_fingerprinting_without_temp()
        else:
            run_soundalike_fingerprinting()

    # 步骤3: 更新标签
    if not args.skip_tag_update:
        main_logger.info('\n' + '='*60)
        main_logger.info('步骤 3/7: 更新标签信息')
        main_logger.info('='*60)
        success, fail, tag_success = update_tags_from_fingerprint(target_dir=target_dir)
        main_logger.info(f'标签更新汇总: 成功 {success}, 失败 {fail}, 标签更新 {tag_success}')

    # 步骤4: 检查文件
    if not args.skip_check:
        main_logger.info('\n' + '='*60)
        main_logger.info('步骤 4/7: 检查文件一致性')
        main_logger.info('='*60)
        check_filename_consistency(
            check_master=args.check_master,
            check_temp=not args.uncheck_temp and not args.check_master
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
