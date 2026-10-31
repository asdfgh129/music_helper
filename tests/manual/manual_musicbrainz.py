#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MusicBrainz 连通性自检（手工运行，不被 pytest 收集）

把原来两个各自为政的脚本（连接测试 / 裸 API 测试）合并成一个，用 --mode 区分：
    match（默认）：fpcalc → AcoustID → MusicBrainz 全链路，用 test/fixtures/1.flac 真跑一次
    api          ：只用标准库直接打 MusicBrainz Web Service，用来区分「网络/证书问题」与
                   「指纹匹配链路问题」

用法：
    python test/manual/manual_musicbrainz.py                  # 全链路匹配
    python test/manual/manual_musicbrainz.py --mode api       # 裸 API
    python test/manual/manual_musicbrainz.py --debug          # 打开调试日志
    python test/manual/manual_musicbrainz.py --file D:/x.flac  # 换样本

需要真实网络；match 模式还要求 fpcalc 与 ACOUSTID key 可用。
"""

import argparse
import json
import logging
import os
import ssl
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# 本文件在 test/manual/ 下，仓库根是上上两级；此前写成 '..' 只指到 test/，
# 导致 `from fingerprint import ...` 必然失败（只有 CWD 恰好在仓库根时才侥幸能跑）
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

DEFAULT_SAMPLE = ROOT / 'test' / 'fixtures' / '1.flac'
MB_URL = 'https://musicbrainz.org/ws/2/recording'
USER_AGENT = 'MusicHelper-ManualCheck/1.0 ( https://github.com/asdfgh129/music_helper )'


def check_api(query='recording:"Love Story" AND artist:"Taylor Swift"'):
    """裸 API：不经过项目代码，只验证 MusicBrainz 能不能访问。"""
    url = f'{MB_URL}?{urlencode({"query": query, "limit": 5, "fmt": "json"})}'
    logging.info('请求 URL: %s', url)
    request = Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'})

    def _fetch(context):
        with urlopen(request, timeout=30, context=context) as response:
            return json.loads(response.read().decode('utf-8'))

    try:
        try:
            data = _fetch(ssl.create_default_context())
        except ssl.SSLError as exc:
            # 证书链有问题的机器上退一步，但要明确说出来，别让人以为一切正常
            logging.warning('证书校验失败（%s），改用不校验上下文重试', exc)
            data = _fetch(ssl._create_unverified_context())
    except (URLError, OSError, ValueError) as exc:
        logging.error('✗ MusicBrainz 不可达: %s', exc)
        return False

    recordings = data.get('recordings', [])
    logging.info('✓ 裸 API 通过，返回 %d 条结果', len(recordings))
    for index, item in enumerate(recordings[:3], 1):
        credit = item.get('artist-credit') or [{}]
        logging.info('  %d. %s - %s', index, item.get('title', 'N/A'),
                     credit[0].get('name', 'N/A'))
    return True


def check_matcher(sample, debug=False):
    """全链路：指纹计算 + AcoustID 查询 + MusicBrainz 取标签。"""
    try:
        from fingerprint import FingerprintMatcher
    except Exception as exc:  # noqa: BLE001 - 手工脚本，缺依赖就直说
        logging.error('✗ 导入 fingerprint 失败: %s', exc)
        return False

    if not os.path.exists(sample):
        logging.error('✗ 样本不存在: %s', sample)
        return False

    logging.info('样本: %s', sample)
    try:
        matcher = FingerprintMatcher(debug_mode=debug)
        result = matcher.match_file(str(sample))
    except Exception as exc:  # noqa: BLE001
        logging.error('✗ 匹配过程抛异常: %s', exc, exc_info=debug)
        return False

    if not result.success:
        logging.error('✗ 匹配失败: %s', result.error or '未知原因')
        return False

    logging.info('✓ 匹配成功，%d 条结果', len(result.recordings))
    for index, item in enumerate(result.recordings[:3], 1):
        logging.info('  %d. %s - %s（%s）', index, item.get('title', 'N/A'),
                     item.get('artist', 'N/A'), item.get('date', 'N/A'))
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description='MusicBrainz 连通性自检')
    parser.add_argument('--mode', choices=('match', 'api'), default='match',
                        help='match=全链路（默认），api=裸接口')
    parser.add_argument('--file', default=str(DEFAULT_SAMPLE), help='match 模式使用的样本')
    parser.add_argument('--debug', action='store_true', help='打开调试日志')
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')

    logging.info('=' * 60)
    ok = check_api() if args.mode == 'api' else check_matcher(args.file, args.debug)
    logging.info('=' * 60)
    logging.info('%s', '通过' if ok else '未通过')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
