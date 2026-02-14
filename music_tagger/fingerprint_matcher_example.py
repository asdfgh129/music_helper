#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
指纹匹配器使用示例
演示如何使用fingerprint_matcher模块
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

        for i, recording in enumerate(result.recordings, 1):
            print(f"--- 结果 #{i} ---")
            print(format_recording_info(recording))
    else:
        print(f"\n匹配失败: {result.error}")


def example_calculate_fingerprint():
    """示例2: 仅计算指纹，不查询"""
    print("\n" + "=" * 70)
    print("示例2: 仅计算指纹")
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
    """示例3: 使用已有指纹查询"""
    print("\n" + "=" * 70)
    print("示例3: 使用已有指纹查询")
    print("=" * 70)

    # 创建匹配器
    matcher = FingerprintMatcher()

    # 假设这是之前计算的指纹
    fingerprint = "AQADzkyRjkSK..."  # 替换为实际指纹
    duration = 180  # 秒

    print(f"\n正在查询指纹 ({len(fingerprint)} 字符, {duration} 秒)...")

    # 使用已有指纹查询
    result = matcher.match_from_fingerprint(fingerprint, duration)

    if result.success:
        print(f"\n成功! 找到 {len(result.recordings)} 个匹配结果\n")
        for i, recording in enumerate(result.recordings, 1):
            print(f"--- 结果 #{i} ---")
            print(format_recording_info(recording))
    else:
        print(f"\n查询失败: {result.error}")


def example_batch_process():
    """示例4: 批量处理多个文件"""
    print("\n" + "=" * 70)
    print("示例4: 批量处理多个文件")
    print("=" * 70)

    # 创建匹配器
    matcher = FingerprintMatcher()

    # 文件列表
    audio_files = ["song1.mp3", "song2.flac", "song3.wav"]

    print(f"\n正在处理 {len(audio_files)} 个文件...")

    for i, audio_file in enumerate(audio_files, 1):
        print(f"\n[{i}/{len(audio_files)}] 处理: {audio_file}")

        result = matcher.match_file(audio_file)

        if result.success and result.recordings:
            best_match = result.recordings[0]
            title = best_match.get('title', 'Unknown')
            artists = []
            for artist_credit in best_match.get('artist-credit', []):
                artists.append(artist_credit.get('artist', {}).get('name', 'Unknown'))
            print(f"  ✓ 匹配: {title} - {', '.join(artists)}")
        else:
            print(f"  ✗ 未找到匹配")

    print("\n批量处理完成!")


def example_extract_recording_info():
    """示例5: 提取录音信息用于其他用途"""
    print("\n" + "=" * 70)
    print("示例5: 提取录音信息")
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


if __name__ == '__main__':
    import sys

    print("指纹匹配器示例")
    print("=" * 70)

    if len(sys.argv) > 1:
        # 如果指定了音频文件，运行示例1
        example_basic()
    else:
        print("\n运行不同示例:")
        print("  1. 基本用法 - 需要提供音频文件")
        print("  2. 计算指纹 - 需要提供音频文件")
        print("  3. 批量处理 - 需要提供音频文件")
        print("\n用法:")
        print("  python fingerprint_matcher_example.py audio_file.mp3")
        sys.exit(0)
