# -*- coding: utf-8 -*-
"""重复文件检测模块

找出所有文件名中含有"(1)"、"(2)"、"(3)"的文件及其对应的原始文件
"""

import os
import logging

logger = logging.getLogger(__name__)


def find_special_and_counterpart_files(directory: str) -> tuple[list[tuple[str, str]], dict[str, str]]:
    """找出所有含有"(1)"、"(2)"、"(3)"的文件及其对应的原始文件

    Args:
        directory: 要搜索的目录

    Returns:
        (special_files, counterpart_files) 元组：
        - special_files: 特殊文件列表，每个元素是 (filepath, cleaned_name) 元组
        - counterpart_files: 字典，键为特殊文件路径，值为对应的原始文件路径或"None"
    """
    # 找出所有含有"(1)"、"(2)"、"(3)"的文件
    special_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            if any(f"({num})" in file for num in ['1', '2', '3', '4', '5']) and not file.endswith('.lrc'):
                cleaned_name = file.replace('(1)', '').replace('(2)', '').replace('(3)', '').rsplit('.', 1)[0].rstrip()
                special_files.append((os.path.join(root, file), cleaned_name))

    # 打印找到的特殊文件
    for special_file, special_name in special_files:
        logger.info(f"Special file: {special_file}, filename: {special_name}")

    # 根据含有"(1)"、"(2)"、"(3)"的文件，找出不含有这些的同名文件
    counterpart_files = {}

    for special_file, special_name in special_files:
        found_counterpart = False
        for root, _, files in os.walk(directory):
            for file in files:
                # 跳过含有"(1)"、"(2)"、"(3)"的文件和.lrc文件
                if any(f"({num})" in file for num in ['1', '2', '3', '4', '5']) or file.endswith('.lrc'):
                    continue

                base_name = file.rsplit('.', 1)[0]
                if special_name == base_name:
                    counterpart_files[special_file] = os.path.join(root, file)
                    found_counterpart = True
                    break

        if not found_counterpart:
            counterpart_files[special_file] = "None"

    return special_files, counterpart_files


def main():
    """主函数：检测重复文件"""
    directory = 'D:\\music\\'

    print("开始检测重复文件...")
    special_files, counterpart_files = find_special_and_counterpart_files(directory)

    print("\nFiles with '(1)', '(2)', '(3)' and their counterparts:")
    for file, counterpart in counterpart_files.items():
        if counterpart != "None":
            print(f"File: {file}, Counterpart: {counterpart}")
        else:
            print(f"File: {file}, No counterpart found")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    main()
