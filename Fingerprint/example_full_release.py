#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
示例：加载完整Release信息

演示如何使用fingerprint_matcher.py加载与Picard一致的完整Release信息。
这包括所有音轨、完整标签、关系等。
"""

from fingerprint_matcher import FingerprintMatcher, format_complete_tags, map_recording_to_tags


def example_load_full_release():
    """示例：加载完整Release信息"""
    
    print("=" * 80)
    print("示例：加载完整Release信息")
    print("=" * 80)
    
    # 创建匹配器
    matcher = FingerprintMatcher()
    
    # 匹配音频文件
    audio_file = "test_song.mp3"
    result = matcher.match_file(audio_file)
    
    if result.success and result.best_match:
        print(f"\n✓ 找到最佳匹配: {result.best_match.get('title', 'Unknown')}")
        
        # 方法1：仅使用recording数据（默认，不加载完整release）
        print("\n" + "=" * 80)
        print("方法1：使用默认recording数据")
        print("=" * 80)
        tags_basic = map_recording_to_tags(result.best_match)
        print(f"\n基本标签（来自recording）:")
        print(f"  - 标题: {tags_basic.get('title', 'N/A')}")
        print(f"  - 专辑: {tags_basic.get('album', 'N/A')}")
        print(f"  - 艺术家: {tags_basic.get('artist', 'N/A')}")
        print(f"  - 音轨号: {tags_basic.get('tracknumber', 'N/A')}")
        
        # 方法2：加载完整Release信息（与Picard一致）
        print("\n" + "=" * 80)
        print("方法2：加载完整Release信息（推荐，与Picard一致）")
        print("=" * 80)
        
        # 加载完整release
        full_release = matcher.load_full_release_for_best_match(result.best_match)
        
        if full_release:
            print(f"\n✓ 成功加载完整Release!")
            print(f"\n完整Release信息:")
            print(f"  - Release ID: {full_release.get('id')}")
            print(f"  - Release标题: {full_release.get('title')}")
            print(f"  - 发行状态: {full_release.get('status', 'N/A')}")
            
            # 显示媒体信息
            media_list = full_release.get('media', [])
            print(f"\n媒体信息 ({len(media_list)} 个媒体):")
            for idx, medium in enumerate(media_list[:3], 1):
                format_type = medium.get('format', 'Unknown')
                position = medium.get('position', 0)
                track_count = medium.get('track-count', 0)
                print(f"  碟片 #{idx}:")
                print(f"    - 格式: {format_type}")
                print(f"    - 位置: {position}")
                print(f"    - 音轨数: {track_count}")
                
                # 显示音轨信息
                tracks = medium.get('tracks', [])
                if tracks:
                    print(f"    - 音轨列表 (显示前5首):")
                    for track in tracks[:5]:
                        track_number = track.get('number', '?')
                        track_recording = track.get('recording', {})
                        track_title = track_recording.get('title', 'Unknown')
                        track_id = track_recording.get('id', 'N/A')
                        print(f"      [{track_number}] {track_title} (ID: {track_id})")
                    if len(tracks) > 5:
                        print(f"      ... 还有 {len(tracks) - 5} 首音轨")
            
            # 显示唱片公司信息
            labels = full_release.get('label-info', [])
            if labels:
                print(f"\n唱片公司 ({len(labels)} 个):")
                for label_info in labels:
                    label = label_info.get('label', {})
                    label_name = label.get('name', 'N/A')
                    catalog_number = label_info.get('catalog-number', 'N/A')
                    print(f"  - {label_name} (编号: {catalog_number})")
            
            # 显示标签/流派
            tags_mb = full_release.get('tags', [])
            if tags_mb:
                print(f"\n标签/流派 ({len(tags_mb)} 个):")
                for tag in tags_mb:
                    tag_name = tag.get('name', 'N/A')
                    tag_count = tag.get('count', 0)
                    print(f"  - {tag_name} (计数: {tag_count})")
            
            # 显示关系信息（如果加载了）
            if 'artist-relation-list' in full_release:
                print(f"\n艺术家关系:")
                for rel in full_release['artist-relation-list'][:5]:
                    rel_type = rel.get('type', 'Unknown')
                    rel_artist = rel.get('artist', {})
                    artist_name = rel_artist.get('name', 'N/A')
                    print(f"  - {rel_type}: {artist_name}")
            
            # 使用完整release更新recording并映射标签
            print("\n" + "=" * 80)
            print("更新后的完整标签映射")
            print("=" * 80)
            tags_complete = map_recording_to_tags(result.best_match)
            print(f"\n所有可用标签:")
            print(f"  - 标题: {tags_complete.get('title', 'N/A')}")
            print(f"  - 专辑: {tags_complete.get('album', 'N/A')}")
            print(f"  - 艺术家: {tags_complete.get('artist', 'N/A')}")
            print(f"  - 专辑艺术家: {tags_complete.get('albumartist', 'N/A')}")
            print(f"  - 音轨号: {tags_complete.get('tracknumber', 'N/A')}")
            print(f"  - 碟号: {tags_complete.get('discnumber', 'N/A')}")
            print(f"  - 总音轨数: {tags_complete.get('totaltracks', 'N/A')}")
            print(f"  - 总碟数: {tags_complete.get('totaldiscs', 'N/A')}")
            print(f"  - 专辑总音轨数: {tags_complete.get('totalalbumtracks', 'N/A')}")
            print(f"  - 发行日期: {tags_complete.get('date', 'N/A')}")
            print(f"  - 发行国家: {tags_complete.get('releasecountry', 'N/A')}")
            print(f"  - 发行状态: {tags_complete.get('releasestatus', 'N/A')}")
            print(f"  - 专辑类型: {', '.join(tags_complete.get('releasetype', []))}")
            print(f"  - 唱片公司: {', '.join(tags_complete.get('label', []))}")
            print(f"  - 编号: {', '.join(tags_complete.get('catalognumber', []))}")
            print(f"  - 条码: {tags_complete.get('barcode', 'N/A')}")
            print(f"  - 媒体格式: {tags_complete.get('media', 'N/A')}")
            print(f"  - 流派: {', '.join(tags_complete.get('genre', []))}")
            
            # 显示完整格式化信息
            print("\n" + "=" * 80)
            print("完整格式化标签信息")
            print("=" * 80)
            print(format_complete_tags(result.best_match))
            
        else:
            print("\n✗ 未能加载完整Release信息")
            print("可能原因:")
            print("  - 最佳匹配没有release信息")
            print("  - 网络连接问题")
            print("  - MusicBrainz API错误")
    else:
        print(f"\n✗ 匹配失败: {result.error}")


def example_inc_parameters():
    """示例：使用不同的inc参数加载release"""
    
    print("\n" + "=" * 80)
    print("示例：自定义inc参数")
    print("=" * 80)
    
    print("\n可以自定义inc参数来控制加载的信息量:")
    print("\n最小inc参数（快速，较少数据）:")
    min_inc = ['media', 'recordings']
    print(f"  {min_inc}")
    
    print("\n标准inc参数（推荐）:")
    std_inc = [
        'aliases',
        'annotation',
        'artist-credits',
        'artists',
        'collections',
        'discids',
        'isrcs',
        'labels',
        'media',
        'recordings',
        'release-groups',
    ]
    print(f"  {std_inc}")
    
    print("\n完整inc参数（包含所有关系）:")
    full_inc = std_inc + [
        'artist-rels',
        'recording-rels',
        'label-rels',
        'release-group-level-rels',
        'release-rels',
        'series-rels',
        'url-rels',
        'work-rels',
        'recording-level-rels',
        'work-level-rels',
    ]
    print(f"  {full_inc}")
    
    print("\n使用示例:")
    print("""
# 使用标准inc
matcher = FingerprintMatcher()
result = matcher.match_file('song.mp3')

if result.success and result.best_match:
    # 加载标准release信息
    release = matcher.load_full_release_for_best_match(
        result.best_match,
        inc=std_inc
    )

# 使用最小inc（快速）
release_min = matcher.load_full_release_for_best_match(
    result.best_match,
        inc=['media', 'recordings']
)

# 使用完整inc（包含关系）
release_full = matcher.load_full_release_for_best_match(
    result.best_match,
        inc=full_inc
)
    """)


def main():
    """运行所有示例"""
    print("\n" + "=" * 80)
    print("fingerprint_matcher 完整Release加载示例")
    print("=" * 80)
    
    # 注意：这些示例需要实际的音频文件才能运行
    # 要运行这些示例，请替换为实际的音频文件路径
    
    print("\n⚠ 注意：这些示例需要实际的音频文件")
    print("要运行这些示例，请修改代码中的audio_file路径\n")
    
    # 示例1：加载完整release
    # example_load_full_release()
    
    # 示例2：自定义inc参数
    example_inc_parameters()
    
    print("\n" + "=" * 80)
    print("示例说明完成")
    print("=" * 80)
    print("\n要使用完整Release加载功能，请:")
    print("1. 修改audio_file路径为实际的音频文件")
    print("2. 取消注释 example_load_full_release() 调用")
    print("3. 运行此脚本")
    print("\n或在命令行使用:")
    print("  python fingerprint_matcher.py song.mp3 --load-full-release")


if __name__ == '__main__':
    main()
