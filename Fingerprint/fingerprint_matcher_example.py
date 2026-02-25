#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
指纹匹配器使用示例
演示如何使用fingerprint_matcher模块

依赖安装:
    pip install opencc

外部工具:
    需要安装 fpcalc:
    - macOS: brew install chromaprint
    - Ubuntu: sudo apt-get install libchromaprint-tools
    - Windows: 从 https://acoustid.org/chromaprint 下载
"""

from fingerprint_matcher import (
    FingerprintMatcher,
    FingerprintCalculator,
    AcoustIDClient,
    format_recording_info,
)


def example_basic():
    """示例1: 基本用法 - 匹配单个音频文件"""
    print("=" * 70)
    print("示例1: 基本用法 - 匹配单个音频文件")
    print("=" * 70)

    # 创建匹配器
    matcher = FingerprintMatcher()

    # 假设有一个音频文件
    audio_file = "example.mp3"

    print(f"\n正在处理文件: {audio_file}")

    # 匹配文件
    result = matcher.match_file(audio_file)

    if result.success:
        print(f"\n成功! 找到 {len(result.recordings)} 个匹配结果\n")

        # 显示最佳匹配（自动选择的）
        if result.best_match:
            print("=" * 70)
            print("最佳匹配 (自动选择最合适的标签):")
            print("=" * 70)
            print(format_recording_info(result.best_match, show_similarity=True))
            print()

        # 显示所有候选结果
        for i, recording in enumerate(result.recordings, 1):
            print(f"--- 结果 #{i} ---")
            print(format_recording_info(recording))
    else:
        print(f"\n匹配失败: {result.error}")


def example_with_metadata():
    """示例2: 使用现有元数据提高匹配精度"""
    print("\n" + "=" * 70)
    print("示例2: 使用现有元数据 - 提高匹配精度")
    print("=" * 70)

    # 创建匹配器
    matcher = FingerprintMatcher()

    # 准备现有元数据（从文件标签中提取）
    # 提供的元数据越多，匹配越准确
    metadata = {
        'title': '月亮代表我的心',
        'artist': '邓丽君',
        'album': '邓丽君金曲精选',
        'date': '1999',
        'totaltracks': '20',
    }

    print(f"\n使用现有元数据进行匹配:")
    print(f"  标题: {metadata['title']}")
    print(f"  艺术家: {metadata['artist']}")
    print(f"  专辑: {metadata['album']}")

    audio_file = "example.mp3"
    result = matcher.match_file(audio_file, metadata=metadata)

    if result.success:
        print(f"\n找到 {len(result.recordings)} 个候选结果")

        if result.best_match:
            print(f"\n{'='*70}")
            print("最佳匹配 (根据元数据相似度算法):")
            print(f"{'='*70}")
            # show_similarity=True 显示计算出的相似度分数
            print(format_recording_info(result.best_match, show_similarity=True))

            best_title = result.best_match.get('title', 'Unknown')
            best_artist = ' '.join([
                ac.get('artist', {}).get('name', 'Unknown')
                for ac in result.best_match.get('artist-credit', [])
            ])
            similarity = result.best_match.get('_calculated_similarity', 0)
            print(f"\n✓ 选择最佳匹配: {best_title} - {best_artist}")
            print(f"✓ 计算相似度: {similarity * 100:.1f}%")
    else:
        print(f"\n匹配失败: {result.error}")


def example_calculate_fingerprint():
    """示例3: 仅计算指纹，不查询"""
    print("\n" + "=" * 70)
    print("示例3: 仅计算指纹")
    print("=" * 70)

    # 创建指纹计算器
    calculator = FingerprintCalculator()

    audio_file = "example.mp3"
    print(f"\n正在计算指纹: {audio_file}")

    # 计算指纹
    fingerprint_result = calculator.calculate(audio_file)

    if fingerprint_result.success:
        print(f"\n指纹计算成功!")
        print(f"  指纹长度: {len(fingerprint_result.fingerprint)} 字符")
        print(f"  音频时长: {fingerprint_result.duration} 秒")
        print(f"  指纹预览: {fingerprint_result.fingerprint[:50]}...")
    else:
        print(f"\n指纹计算失败")


def example_query_with_fingerprint():
    """示例4: 使用已有指纹查询"""
    print("\n" + "=" * 70)
    print("示例4: 使用已有指纹查询")
    print("=" * 70)

    # 创建匹配器
    matcher = FingerprintMatcher()

    # 假设这是之前计算的指纹
    fingerprint = "AQADzkyRjkSK..."  # 替换为实际指纹
    duration = 180  # 秒

    print(f"\n正在查询指纹 ({len(fingerprint)} 字符, {duration} 秒)...")

    # 可选：提供元数据以提高匹配精度
    metadata = {
        'title': '你的歌曲',
        'artist': '艺术家名称',
    }

    # 使用已有指纹查询
    result = matcher.match_from_fingerprint(fingerprint, duration, metadata=metadata)

    if result.success:
        print(f"\n成功! 找到 {len(result.recordings)} 个匹配结果\n")

        if result.best_match:
            print("最佳匹配:")
            print(format_recording_info(result.best_match, show_similarity=True))
            print()

        for i, recording in enumerate(result.recordings, 1):
            print(f"--- 结果 #{i} ---")
            print(format_recording_info(recording))
    else:
        print(f"\n查询失败: {result.error}")


def example_batch_process():
    """示例5: 批量处理多个文件"""
    print("\n" + "=" * 70)
    print("示例5: 批量处理多个文件")
    print("=" * 70)

    # 创建匹配器
    matcher = FingerprintMatcher()

    # 文件列表
    audio_files = ["song1.mp3", "song2.flac", "song3.wav"]

    print(f"\n正在处理 {len(audio_files)} 个文件...")

    results = []

    for i, audio_file in enumerate(audio_files, 1):
        print(f"\n[{i}/{len(audio_files)}] 处理: {audio_file}")

        result = matcher.match_file(audio_file)

        if result.success and result.best_match:
            best = result.best_match
            title = best.get('title', 'Unknown')
            artist = ' '.join([
                ac.get('artist', {}).get('name', 'Unknown')
                for ac in best.get('artist-credit', [])
            ])
            score = best.get('score', 0)
            similarity = best.get('_calculated_similarity', 0)

            print(f"  ✓ 最佳匹配: {title} - {artist}")
            print(f"    AcoustID 分数: {score:.1f}%")
            print(f"    计算相似度: {similarity * 100:.1f}%")

            results.append({
                'file': audio_file,
                'title': title,
                'artist': artist,
                'success': True
            })
        else:
            print(f"  ✗ 未找到匹配: {result.error}")
            results.append({
                'file': audio_file,
                'success': False,
                'error': result.error
            })

    # 输出摘要
    print(f"\n{'='*70}")
    print("处理摘要")
    print(f"{'='*70}")
    success_count = sum(1 for r in results if r['success'])
    print(f"成功: {success_count}/{len(results)}")
    print(f"失败: {len(results) - success_count}/{len(results)}")


def example_extract_recording_info():
    """示例6: 提取录音信息用于其他用途"""
    print("\n" + "=" * 70)
    print("示例6: 提取录音信息")
    print("=" * 70)

    # 创建匹配器
    matcher = FingerprintMatcher()

    audio_file = "example.mp3"
    result = matcher.match_file(audio_file)

    if result.success and result.recordings:
        recording = result.recordings[0]

        # 提取各种信息
        print("\n提取的信息:")
        print(f"  标题: {recording.get('title', 'Unknown')}")
        print(f"  MusicBrainz ID: {recording.get('id', 'Unknown')}")
        print(f"  AcoustID: {recording.get('acoustid', 'Unknown')}")
        print(f"  匹配分数: {recording.get('score', 0):.1f}%")
        print(f"  时长: {recording.get('length', 0) / 1000:.1f} 秒")

        # 提取艺术家信息
        artists = []
        for artist_credit in recording.get('artist-credit', []):
            artist = artist_credit.get('artist', {})
            artists.append({
                'name': artist.get('name', 'Unknown'),
                'mbid': artist.get('id', 'Unknown')
            })

        print(f"  艺术家数量: {len(artists)}")
        for artist in artists:
            print(f"    - {artist['name']} (MBID: {artist['mbid']})")

        # 提取发行信息
        releases = recording.get('releases', [])
        print(f"  发行数量: {len(releases)}")
        for release in releases[:3]:  # 只显示前3个
            print(f"    - {release.get('title', 'Unknown')} ({release.get('date', 'N/A')})")


def example_metadata_from_file_tags():
    """示例7: 从音频文件标签提取元数据"""
    print("\n" + "=" * 70)
    print("示例7: 使用音频文件的现有标签")
    print("=" * 70)

    print("\n推荐使用以下库读取音频文件标签:")
    print("  pip install mutagen")
    print("  或 pip install pytaglib")

    # 使用 mutagen 的示例代码（需要先安装）
    """
    from mutagen.easyid3 import EasyID3
    from mutagen.mp3 import MP3
    from mutagen.flac import FLAC

    def extract_metadata_from_audio(audio_file):
        \"\"\"从音频文件提取元数据\"\"\"
        # 根据文件扩展名选择合适的库
        if audio_file.endswith('.mp3'):
            audio = MP3(audio_file, ID3=EasyID3)
        elif audio_file.endswith('.flac'):
            audio = FLAC(audio_file)
        else:
            return {}

        metadata = {}

        if 'title' in audio:
            metadata['title'] = audio['title'][0]
        if 'artist' in audio:
            metadata['artist'] = audio['artist'][0]
        if 'album' in audio:
            metadata['album'] = audio['album'][0]
        if 'date' in audio:
            metadata['date'] = audio['date'][0]
        if 'tracknumber' in audio:
            metadata['tracknumber'] = audio['tracknumber'][0]
        if 'totaltracks' in audio:
            metadata['totaltracks'] = audio['totaltracks'][0]

        # 时长
        metadata['length'] = int(audio.info.length * 1000)  # 转换为毫秒

        return metadata

    # 使用示例
    matcher = FingerprintMatcher()

    audio_file = "song.mp3"
    metadata = extract_metadata_from_audio(audio_file)

    # 使用元数据进行匹配
    result = matcher.match_file(audio_file, metadata=metadata)
    """

    print("\n提取元数据后，可以这样使用:")
    print("""
    # 提取元数据
    metadata = extract_metadata_from_audio('song.mp3')

    # 使用元数据进行匹配
    result = matcher.match_file('song.mp3', metadata=metadata)

    if result.success and result.best_match:
        print(f"最佳匹配: {result.best_match['title']}")
    """)


if __name__ == '__main__':
    import sys

    print("指纹匹配器示例")
    print("=" * 70)
    print()
    print("可用示例:")
    print("  1. 基本用法 - 匹配单个音频文件")
    print("  2. 使用现有元数据 - 提高匹配精度")
    print("  3. 仅计算指纹")
    print("  4. 使用已有指纹查询")
    print("  5. 批量处理多个文件")
    print("  6. 提取录音信息")
    print("  7. 从音频文件标签提取元数据")
    print()
    print("用法:")
    print("  python fingerprint_matcher_example.py [audio_file_path]")
    print()

    if len(sys.argv) > 1:
        # 如果指定了音频文件，运行示例1
        example_basic()
        example_with_metadata()
    else:
        print("注意: 要运行示例，请提供音频文件路径")
        print("示例:")
        print("  python fingerprint_matcher_example.py song.mp3")
        sys.exit(0)
