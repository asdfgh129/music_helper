#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动匹配音乐文件并显示完整标签信息（类似 Picard 原项目）

这个脚本演示了如何使用 fingerprint_matcher.py 来：
1. 自动匹配一首音乐文件
2. 自动选择最合适的专辑和录音
3. 加载完整的 Release 信息
4. 显示所有可用的标签信息（与 Picard 原项目相同）

用法:
    python auto_match_example.py <audio_file_path> [fpcalc_path]

示例:
    python auto_match_example.py song.mp3
    python auto_match_example.py song.flac /usr/local/bin/fpcalc
"""

import sys
import os

# 添加 picard 目录到 Python 路径，以便导入 fingerprint_matcher
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fingerprint_matcher import FingerprintMatcher


def auto_match_and_display(audio_file: str, fpcalc_path: str = None):
    """
    自动匹配音乐文件并显示完整的标签信息

    Args:
        audio_file: 音频文件路径
        fpcalc_path: fpcalc 可执行文件路径（可选）
    """
    # 创建匹配器
    matcher = FingerprintMatcher(fpcalc_path=fpcalc_path)

    print(f"\n正在分析文件: {audio_file}")
    print(f"文件大小: {os.path.getsize(audio_file) / 1024 / 1024:.2f} MB")

    # 匹配文件
    result = matcher.match_file(audio_file)

    if not result.success:
        print(f"\n❌ 匹配失败: {result.error}")
        return False

    if not result.recordings:
        print("\n❌ 未找到任何匹配的录音信息")
        return False

    # 自动选择最佳匹配
    if not result.best_match:
        print("\n⚠️  警告: 无法自动选择最佳匹配，使用第一个结果")
        best_recording = result.recordings[0]
    else:
        best_recording = result.best_match

    print(f"\n✓ 找到 {len(result.recordings)} 个候选结果")

    # 自动加载完整的 Release 信息以获取更完整的标签
    print("正在加载完整的 Release 信息...")
    full_release = matcher.load_full_release_for_best_match(best_recording)

    if full_release:
        print("✓ 完整 Release 信息加载成功\n")
    else:
        print("⚠️  完整 Release 信息加载失败，使用部分信息\n")

    # 显示完整的标签信息（与 Picard 原项目相同）
    # 这里会显示所有可用的标签，包括：
    # - 标题、艺术家、专辑、音轨号、长度、日期
    # - acoustid、musicbrainz 专辑id、musicbrainz 专辑组id
    # - musicbrainz 专辑艺术家id、musicbrainz 录音id、musicbrainz 艺术家id、musicbrainz 音轨id
    # - 专辑唱片公司、专辑状态、专辑类型、专辑艺术家
    # - 发行国或地区、媒体、总碟数、总音轨数、条码、流派、碟号、编号
    # - 艺术家、艺术家专辑排序顺序、艺术家排序顺序、首发年份、首发日期
    # 等等
    from fingerprint_matcher import format_complete_tags
    print(format_complete_tags(best_recording, show_cover=False))

    # 显示调试信息
    if len(result.recordings) > 1:
        print(f"\n{'─' * 80}")
        print(f"[调试信息] 共找到 {len(result.recordings)} 个候选结果，已自动选择最佳匹配")
        print(f"{'─' * 80}")
        for i, recording in enumerate(result.recordings[:3], 1):
            score = recording.get('score', 0)
            title = recording.get('title', '未知标题')
            artist = recording.get('artist-credit', [{}])[0].get('name', '未知艺术家') if recording.get('artist-credit') else '未知艺术家'
            print(f"  {i}. {title} - {artist}")
            print(f"     得分: {score}")
            print(f"     MusicBrainz ID: {recording.get('id', 'N/A')}")

    return True


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python auto_match_example.py <audio_file_path> [fpcalc_path]")
        print("\n示例:")
        print("  python auto_match_example.py song.mp3")
        print("  python auto_match_example.py song.flac /usr/local/bin/fpcalc")
        print("\n这个脚本会自动:")
        print("  1. 分析音频文件的指纹")
        print("  2. 从 AcoustID 查询匹配的录音")
        print("  3. 自动选择最合适的专辑和录音")
        print("  4. 从 MusicBrainz 加载完整的 Release 信息")
        print("  5. 显示所有可用的标签信息（与 Picard 原项目相同）")
        sys.exit(1)

    audio_file = sys.argv[1]
    fpcalc_path = sys.argv[2] if len(sys.argv) > 2 else None

    # 检查文件是否存在
    if not os.path.exists(audio_file):
        print(f"❌ 错误: 文件不存在: {audio_file}")
        sys.exit(1)

    # 执行自动匹配
    success = auto_match_and_display(audio_file, fpcalc_path)

    sys.exit(0 if success else 1)
