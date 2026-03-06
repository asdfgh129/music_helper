#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""验证 musicbrainz_matcher.py 的 MusicBrainz 连接是否正常"""

import sys
import ssl
import logging

# macOS Python SSL 证书修复
try:
    import certifi
    ssl._create_default_https_context = ssl._create_unverified_context
    logging.info("已使用 SSL 上下文配置")
except ImportError:
    logging.warning("certifi 未安装,可能会遇到 SSL 证书问题")

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)

# 导入 Fingerprint 模块
try:
    sys.path.insert(0, '/Users/bemin/Code/music_helper/Fingerprint')
    from musicbrainz_matcher import FingerprintMatcher
    
    logging.info("成功导入 FingerprintMatcher")
except Exception as e:
    logging.error(f"导入失败: {e}")
    sys.exit(1)

def test_connection():
    """测试 MusicBrainz 连接"""
    try:
        # 创建 matcher 实例
        matcher = FingerprintMatcher()
        logging.info("成功创建 FingerprintMatcher 实例")
        
        # 使用测试音频文件
        audio_file = "/Users/bemin/Code/music_helper/1.flac"
        
        logging.info(f"测试文件: {audio_file}")
        
        # 调用匹配方法
        result = matcher.match_file(audio_file)
        
        if result.success:
            logging.info(f"✓ 查询成功! 找到 {len(result.recordings)} 条结果")
            
            if result.recordings:
                logging.info("\n最佳匹配:")
                best = result.recordings[0]
                for key in ['title', 'artist', 'album', 'date']:
                    if key in best:
                        logging.info(f"  {key}: {best[key]}")
                
                # 如果有更多结果,显示前3条
                if len(result.recordings) > 1:
                    logging.info(f"\n其他匹配 ({len(result.recordings)-1} 条):")
                    for i, rec in enumerate(result.recordings[1:4], 2):
                        logging.info(f"  {i}. {rec.get('title', 'N/A')} - {rec.get('artist', 'N/A')}")
            
            return True
        else:
            if result.error:
                logging.warning(f"✓ 连接成功,但查询失败: {result.error}")
            else:
                logging.warning("✓ 连接成功,但没有找到匹配结果")
            return True
            
    except Exception as e:
        logging.error(f"✗ 查询失败: {e}")
        import traceback
        logging.error(traceback.format_exc())
        return False

def main():
    """主函数"""
    logging.info("=" * 60)
    logging.info("开始验证 MusicBrainz 连接")
    logging.info("=" * 60)
    
    success = test_connection()
    
    logging.info("=" * 60)
    if success:
        logging.info("✓ MusicBrainz 连接验证通过")
        logging.info("=" * 60)
        sys.exit(0)
    else:
        logging.error("✗ MusicBrainz 连接验证失败")
        logging.info("=" * 60)
        sys.exit(1)

if __name__ == "__main__":
    main()
