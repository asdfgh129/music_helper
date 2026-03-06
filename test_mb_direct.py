#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""直接测试 MusicBrainz API 连接"""

import ssl
import logging

# 配置 SSL
ssl._create_default_https_context = ssl._create_unverified_context

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

def test_musicbrainz_direct():
    """直接测试 MusicBrainz API"""
    from urllib.request import urlopen, Request
    from urllib.parse import urlencode
    import json
    
    # 测试 MusicBrainz lookup API
    url = "https://musicbrainz.org/ws/2/recording"
    params = {
        'query': 'recording:"Love Story" AND artist:"Taylor Swift"',
        'limit': 5,
        'fmt': 'json'
    }
    
    full_url = f"{url}?{urlencode(params)}"
    logging.info(f"测试 MusicBrainz API: {full_url}")
    
    headers = {
        'User-Agent': 'Python-Test/1.0',
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
            
            return True
    except Exception as e:
        logging.error(f"✗ MusicBrainz 查询失败: {e}")
        import traceback
        logging.error(traceback.format_exc())
        return False

def main():
    logging.info("=" * 60)
    logging.info("测试 MusicBrainz 直接连接")
    logging.info("=" * 60)
    success = test_musicbrainz_direct()
    logging.info("=" * 60)
    return 0 if success else 1

if __name__ == "__main__":
    exit(main())
