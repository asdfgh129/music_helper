# -*- coding: utf-8 -*-
"""命令行入口：`python -m fingerprint <audio_file> [fpcalc_path]`

只用于人工验证一条链路（算指纹 → 查 AcoustID → 打印完整标签），
不参与流水线。流水线走 `tagger` 的 `Tagger.update()`。
"""

import sys

from .formatting import format_complete_tags
from .matcher import FingerprintMatcher


def main(argv=None):
    """匹配单个音频文件并打印完整标签信息"""
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv:
        print("Usage: python -m fingerprint <audio_file_path> [fpcalc_path]")
        print("\n示例:")
        print("  python -m fingerprint song.mp3")
        print("  python -m fingerprint song.flac /usr/local/bin/fpcalc")
        sys.exit(1)

    audio_file = argv[0]
    fpcalc_path = None

    for arg in argv[1:]:
        if not arg.startswith('--'):
            fpcalc_path = arg

    matcher = FingerprintMatcher(fpcalc_path=fpcalc_path)
    result = matcher.match_file(audio_file)

    if not result.success:
        print(f"\n匹配失败: {result.error}")
        sys.exit(1)

    if not result.recordings:
        print("\n未找到任何匹配的录音信息")
        sys.exit(1)

    if not result.best_match:
        print("\n警告: 无法自动选择最佳匹配，使用第一个结果")
        best_recording = result.recordings[0]
    else:
        best_recording = result.best_match

    print("正在加载完整的 Release 信息...")
    full_release = matcher.load_full_release_for_best_match(best_recording)

    if full_release:
        print("✓ 完整 Release 信息加载成功\n")
    else:
        print("⚠ 完整 Release 信息加载失败，使用部分信息\n")

    print(format_complete_tags(best_recording, show_cover=False))

    if len(result.recordings) > 1:
        print(f"\n[调试信息] 共找到 {len(result.recordings)} 个候选结果，已自动选择最佳匹配")
        for i, recording in enumerate(result.recordings[:3], 1):
            score = recording.get('score', 0)
            title = recording.get('title', '未知标题')
            print(f"  {i}. {title} (得分: {score})")


if __name__ == '__main__':
    main()
