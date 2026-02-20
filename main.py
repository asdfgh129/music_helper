# -*- coding: utf-8 -*-
"""
音乐文件管理系统 - 主程序入口
"""

import sys
import argparse
import time

import utils
import vip_decrypt
import soundalike
import tag_updater
import file_operations
from config import MAIN_DIR, TEMP_COMPLETED_DIR, __version__


def main():
    """主程序入口"""
    # 设置命令行参数解析
    parser = argparse.ArgumentParser(
        description=f'音乐文件管理系统 v{__version__}',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
使用示例:
  # 完整处理流程（默认处理当前月份，归档临时目录）
  python main.py

  # 处理指定月份
  python main.py --month 202406

  # 仅检查主目录
  python main.py --check

  # 归档临时目录
  python main.py --archive

  # 手动归档临时目录
  python main.py --archive-manual

  # 检查数据库一致性
  python main.py --checkdb

  # 显示版本信息
  python main.py --version
        '''
    )

    parser.add_argument(
        '--version',
        action='version',
        version=f'%(prog)s v{__version__}'
    )

    parser.add_argument(
        '--month',
        type=str,
        default=None,
        help='指定扫描的月份 (格式: YYYYMM，默认: 当前月份)'
    )

    parser.add_argument(
        '--check',
        action='store_true',
        help='检查主目录D:\\music的文件'
    )

    parser.add_argument(
        '--archive',
        action='store_true',
        help='归档临时目录G:\\Temp到主目录'
    )

    parser.add_argument(
        '--archive-manual',
        action='store_true',
        help='手动归档临时目录G:\\Temp（同2.5-2.10步骤）'
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
    utils.setup_logging()

    # 检查数据库一致性模式
    if args.checkdb:
        utils.main_logger.info('运行数据库一致性检查模式')
        success = soundalike.check_database_consistency()
        sys.exit(0 if success else 1)

    # 获取月份参数
    month = args.month
    if month is None:
        month = utils.get_current_month()
        utils.main_logger.info(f'使用当前月份: {month}')
    else:
        if not utils.validate_month_format(month):
            utils.main_logger.error(f'月份格式错误: {month}，应为YYYYMM格式（如202406）')
            sys.exit(1)
        utils.main_logger.info(f'使用指定月份: {month}')

    # 记录开始时间
    start_time = time.time()
    utils.main_logger.info('='*60)
    utils.main_logger.info('音乐文件管理系统 - 开始处理')
    utils.main_logger.info('='*60)

    # 确定处理目录
    if args.check:
        target_dir = MAIN_DIR
        utils.main_logger.info(f'使用 check 模式，只处理主目录: {target_dir}')
    else:
        target_dir = TEMP_COMPLETED_DIR
        utils.main_logger.info(f'使用默认模式，只处理临时目录: {target_dir}')

    # 步骤1: 解密VIP文件和移动普通文件（check模式下跳过）
    if not args.skip_vip and not args.check and not args.archive_manual:
        utils.main_logger.info('\n' + '='*60)
        utils.main_logger.info('步骤 1: 处理VIP文件')
        utils.main_logger.info('='*60)

        # 网易云VIP
        netease_count = vip_decrypt.decrypt_netease_vip(month)

        # QQ VIP
        qq_count = vip_decrypt.decrypt_qq_vip(month)

        # 拷贝普通文件
        netease_normal_count = file_operations.copy_netease_normal_files(month)
        qq_normal_count = file_operations.copy_qq_normal_files(month)

        utils.main_logger.info(f'VIP解密完成: 网易 {netease_count} 个, QQ {qq_count} 个')
        utils.main_logger.info(f'普通文件拷贝完成: 网易 {netease_normal_count} 个, QQ {qq_normal_count} 个')

    if args.check or args.archive_manual:
        utils.main_logger.info('\n' + '='*60)
        utils.main_logger.info('check 模式: 跳过VIP文件解密和移动')
        utils.main_logger.info('='*60)

    # 步骤2: 声纹识别去重
    if not args.skip_fingerprint:
        utils.main_logger.info('\n' + '='*60)
        utils.main_logger.info('步骤 2: 声纹识别去重')
        utils.main_logger.info('='*60)
        # check模式下不带--temp参数
        if args.check:
            soundalike.run_soundalike_fingerprinting_without_temp()
        else:
            soundalike.run_soundalike_fingerprinting()

    # 步骤3: 更新标签
    if not args.skip_tag_update:
        utils.main_logger.info('\n' + '='*60)
        utils.main_logger.info('步骤 3: 更新标签信息')
        utils.main_logger.info('='*60)
        success, fail, tag_success = tag_updater.update_tags_from_fingerprint(target_dir=target_dir)
        utils.main_logger.info(f'标签更新汇总: 成功 {success}, 失败 {fail}, 标签更新 {tag_success}')

    # 步骤4: 检查文件
    if not args.skip_check:
        utils.main_logger.info('\n' + '='*60)
        utils.main_logger.info('步骤 4: 检查文件一致性')
        utils.main_logger.info('='*60)
        file_operations.check_filename_consistency(
            check_master=args.check or args.check_master,
            check_temp=not args.check and not args.archive_manual
        )

    # 步骤5: 年份分类（默认模式和归档模式下执行）
    if not args.skip_organize and not args.check:
        utils.main_logger.info('\n' + '='*60)
        utils.main_logger.info('步骤 5: 按年份分类整理')
        utils.main_logger.info('='*60)
        file_operations.organize_by_year()

    # 记录结束时间
    end_time = time.time()
    elapsed = end_time - start_time

    utils.main_logger.info('\n' + '='*60)
    utils.main_logger.info('音乐文件管理系统 - 处理完成')
    utils.main_logger.info(f'总耗时: {elapsed:.2f} 秒')
    utils.main_logger.info(f'主日志文件: {utils.log_file}')
    utils.main_logger.info('='*60)


if __name__ == '__main__':
    main()
