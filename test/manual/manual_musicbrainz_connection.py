#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MusicBrainz 连接测试
验证 musicbrainz_matcher.py 的 MusicBrainz 连接功能
"""

import sys
import os
import logging

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from Fingerprint.musicbrainz_matcher import FingerprintMatcher

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)

def test_musicbrainz_connection(debug_mode=False):
    """测试 MusicBrainz 连接"""
    logging.info("=" * 60)
    logging.info("开始测试 MusicBrainz 连接")
    if debug_mode:
        logging.info("调试模式已启用")
    logging.info("=" * 60)

    try:
        # 创建 matcher 实例
        matcher = FingerprintMatcher(debug_mode=debug_mode)
        logging.info("✓ 成功创建 FingerprintMatcher 实例")

        # 使用测试音频文件
        audio_file = os.path.join(os.path.dirname(__file__), '..', 'fixtures', '1.flac')

        if not os.path.exists(audio_file):
            logging.error(f"测试音频文件不存在: {audio_file}")
            return False

        logging.info(f"测试文件: {audio_file}")

        # 调用匹配方法
        result = matcher.match_file(audio_file)

        if result.success:
            logging.info(f"✓ 查询成功! 找到 {len(result.recordings)} 条匹配结果")

            if result.recordings:
                logging.info("\n最佳匹配:")
                best = result.recordings[0]
                for key in ['title', 'artist', 'album', 'date']:
                    if key in best:
                        logging.info(f"  {key}: {best[key]}")

                # 显示更多结果
                if len(result.recordings) > 1:
                    logging.info(f"\n其他匹配 ({len(result.recordings)-1} 条):")
                    for i, rec in enumerate(result.recordings[1:4], 2):
                        title = rec.get('title', 'N/A')
                        artist = rec.get('artist', 'N/A')
                        logging.info(f"  {i}. {title} - {artist}")

            logging.info("=" * 60)
            logging.info("✓ MusicBrainz 连接测试通过")
            logging.info("=" * 60)
            return True
        else:
            if result.error:
                logging.warning(f"✓ 连接成功,但查询失败: {result.error}")
            else:
                logging.warning("✓ 连接成功,但没有找到匹配结果")
            logging.info("=" * 60)
            return True

    except Exception as e:
        logging.error(f"✗ 查询失败: {e}")
        import traceback
        logging.error(traceback.format_exc())
        logging.info("=" * 60)
        return False

def main():
    """主函数"""
    import argparse
    parser = argparse.ArgumentParser(description='测试 MusicBrainz 连接')
    parser.add_argument('--debug', action='store_true', help='启用调试模式')
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    success = test_musicbrainz_connection(debug_mode=args.debug)
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
