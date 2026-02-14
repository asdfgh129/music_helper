# -*- coding: utf-8 -*-
"""
命令行工具
"""
import argparse
import os
import sys


def cmd_info(args):
    """查看音乐文件信息"""
    from .core import MusicTagger

    tagger = MusicTagger(args.file)
    info = tagger.to_dict()
    
    print("=" * 60)
    print("音乐文件信息")
    print("=" * 60)
    print(f"文件名: {info['filename']}")
    print(f"标题: {info['title']}")
    print(f"艺术家: {info['artist']}")
    print(f"专辑: {info['album']}")
    print(f"专辑艺术家: {info.get('albumartist', 'N/A')}")
    print(f"年份: {info['year']}")
    print(f"流派: {info['genre']}")
    print(f"音轨号: {info['tracknumber']}")
    print(f"碟片号: {info['discnumber']}")
    print(f"时长: {info['duration']}秒")
    print(f"大小: {info['size']}MB")
    print(f"比特率: {info['bit_rate']}kbps")
    print(f"格式: {info.get('suffix', 'N/A')}")
    print(f"封面: {'有' if info['artwork'] else '无'}")
    print("=" * 60)


def cmd_search(args):
    """搜索音乐"""
    from .platforms import MusicResource

    print(f"正在从 {args.source} 搜索: {args.query}")
    songs = MusicResource(args.source).fetch_id3_by_title(args.query)
    
    if not songs:
        print("未找到结果")
        return
    
    print(f"\n找到 {len(songs)} 条结果:\n")
    for i, song in enumerate(songs, 1):
        print(f"{i}. {song['name']} - {song['artist']}")
        print(f"   专辑: {song.get('album', 'N/A')}")
        print(f"   年份: {song.get('year', 'N/A')}")
        if song.get('score'):
            print(f"   匹配度: {song['score']}")
        print()


def cmd_auto_tag(args):
    """自动匹配标签"""
    from .core import auto_tag

    source_list = args.source.split(",")
    print(f"开始批量匹配...")
    print(f"文件夹: {args.folder}")
    print(f"数据源: {source_list}")
    print(f"模式: {args.mode}")
    print()

    results = auto_tag(args.folder, source_list, args.mode)

    success_count = sum(1 for r in results if r['status'] == 'success')
    failed_count = len(results) - success_count

    print("\n" + "=" * 60)
    print("处理完成")
    print("=" * 60)
    print(f"总计: {len(results)} 个文件")
    print(f"成功: {success_count} 个")
    print(f"失败: {failed_count} 个")
    print("=" * 60)


def cmd_smart_search(args):
    """智能搜索"""
    from .matcher import SmartTagClient

    client = SmartTagClient()
    results = client.fetch_id3_by_title({
        "title": args.query,
        "full_path": args.file if args.file else ""
    })

    print(f"\n智能匹配结果(按匹配度排序):\n")
    for i, song in enumerate(results, 1):
        print(f"{i}. [{song.get('resource', 'unknown')}] {song['name']} - {song['artist']}")
        print(f"   专辑: {song.get('album', 'N/A')}")
        print(f"   匹配度: {song['score']}")
        print()


def main():
    parser = argparse.ArgumentParser(description='Music Tagger - 音乐文件标签管理工具')
    subparsers = parser.add_subparsers(dest='command', help='可用命令')

    # 查看信息命令
    parser_info = subparsers.add_parser('info', help='查看音乐文件信息')
    parser_info.add_argument('file', help='音乐文件路径')
    parser_info.set_defaults(func=cmd_info)

    # 搜索命令
    parser_search = subparsers.add_parser('search', help='搜索音乐')
    parser_search.add_argument('query', help='搜索关键词')
    parser_search.add_argument('--source', default='netease',
                             help='数据源',
                             choices=['netease', 'qmusic', 'migu', 'kugou', 'kuwo', 'acoustid', 'smart_tag'])
    parser_search.set_defaults(func=cmd_search)

    # 自动匹配命令
    parser_auto = subparsers.add_parser('auto-tag', help='批量自动匹配标签')
    parser_auto.add_argument('folder', help='音乐文件夹路径')
    parser_auto.add_argument('--source', default='qmusic,netease,migu,kugou',
                           help='数据源(逗号分隔)')
    parser_auto.add_argument('--mode', default='strict',
                           choices=['strict', 'simple'],
                           help='匹配模式: strict(严格) | simple(简单)')
    parser_auto.set_defaults(func=cmd_auto_tag)

    # 智能搜索命令
    parser_smart = subparsers.add_parser('smart-search', help='智能搜索(多平台并行)')
    parser_smart.add_argument('query', help='搜索关键词')
    parser_smart.add_argument('--file', help='音乐文件路径(用于本地标签匹配)')
    parser_smart.set_defaults(func=cmd_smart_search)

    args = parser.parse_args()

    if args.command:
        args.func(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
