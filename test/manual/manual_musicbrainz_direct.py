#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MusicBrainz 直接 API 测试
直接测试 MusicBrainz Web Service API 连接
"""

import ssl
import logging
import sys
from urllib.request import urlopen, Request
from urllib.parse import urlencode
import json

# macOS SSL 证书修复
try:
    ssl._create_default_https_context = ssl._create_unverified_context
    logging.info("已配置 SSL 上下文")
except Exception:
    pass

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)

def test_musicbrainz_direct():
    """直接测试 MusicBrainz API"""
    logging.info("=" * 60)
    logging.info("测试 MusicBrainz 直接 API 连接")
    logging.info("=" * 60)
    
    # 测试 MusicBrainz lookup API
    url = "https://musicbrainz.org/ws/2/recording"
    params = {
        'query': 'recording:"Love Story" AND artist:"Taylor Swift"',
        'limit': 5,
        'fmt': 'json'
    }
    
    full_url = f"{url}?{urlencode(params)}"
    logging.info(f"请求 URL: {full_url}")
    
    headers = {
        'User-Agent': 'Python-MusicHelper-Test/1.0',
        'Accept': 'application/json',
    }
    
    try:
        request = Request(full_url, headers=headers)
        with urlopen(request, timeout=30) as response:
            content = response.read().decode('utf-8')
            data = json.loads(content)
            
            recordings = data.get('recordings', [])
            logging.info(f"✓ MusicBrainz 查询成功! 找到 {len(recordings)} 条结果")
            
            for i, rec in enumerate(recordings[:3], 1):
                title = rec.get('title', 'N/A')
                artist = rec.get('artist-credit', [{}])[0].get('name', 'N/A') if rec.get('artist-credit') else 'N/A'
                logging.info(f"  {i}. {title} - {artist}")
            
            logging.info("=" * 60)
            logging.info("✓ MusicBrainz 直接 API 测试通过")
            logging.info("=" * 60)
            return True
    except Exception as e:
        logging.error(f"✗ MusicBrainz 查询失败: {e}")
        import traceback
        logging.error(traceback.format_exc())
        logging.info("=" * 60)
        return False

def main():
    """主函数"""
    success = test_musicbrainz_direct()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
