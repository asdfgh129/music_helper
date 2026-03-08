#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
独立的音乐文件指纹匹配模块
从AcoustID API查询指纹并从MusicBrainz获取标签信息
无需UI或PyQt依赖
"""

import json
import logging
import subprocess
import re
import os
import sys
from typing import Optional, Dict, List, Callable, Any, Union, Tuple
from urllib.parse import urlencode, quote
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from datetime import datetime
import ssl

# macOS SSL 证书修复
# 创建默认的 SSL 上下文以避免证书验证失败
_ssl_context = None
try:
    _ssl_context = ssl._create_unverified_context()
except Exception:
    pass

# 添加项目根目录到路径以导入 config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from config import FPCALC_LENGTH
except ImportError:
    # 如果无法导入，使用默认值
    FPCALC_LENGTH = 120
    logging.warning(f"无法从 config 导入 FPCALC_LENGTH，使用默认值: {FPCALC_LENGTH}")

# 导入OpenCC进行完整的繁简转换
try:
    import opencc
    OPENCC_CONVERTER = opencc.OpenCC('t2s')  # 繁体转简体
    HAS_OPENCC = True
    logger = logging.getLogger(__name__)
    logger.info("OpenCC loaded successfully for Traditional/Simplified Chinese conversion")
except (ImportError, OSError) as e:
    OPENCC_CONVERTER = None
    HAS_OPENCC = False
    logger = logging.getLogger(__name__)
    logger.warning(
        "OpenCC not available. Traditional Chinese text will not be converted to Simplified Chinese. "
        "To enable complete conversion, install opencc: pip install opencc"
    )

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def traditional_to_simplified(text: str) -> str:
    """
    将繁体中文转换为简体中文

    使用OpenCC库进行完整的繁简转换，覆盖所有汉字
    """
    if not text or not isinstance(text, str):
        return text

    if not HAS_OPENCC or OPENCC_CONVERTER is None:
        raise ImportError(
            "OpenCC is not available. Please install it with: pip install opencc"
        )

    try:
        return OPENCC_CONVERTER.convert(text)
    except Exception as e:
        logger.error(f"Failed to convert Traditional Chinese to Simplified: {e}")
        return text


def convert_dict_to_simplified(data: Any) -> Any:
    """
    递归将字典中的繁体中文字符串转换为简体中文

    使用OpenCC进行完整转换，确保所有繁体字都能正确转换
    """
    if isinstance(data, dict):
        return {convert_dict_to_simplified(k): convert_dict_to_simplified(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [convert_dict_to_simplified(item) for item in data]
    elif isinstance(data, str):
        return traditional_to_simplified(data)
    else:
        return data


# ============ 相似度计算相关函数 (来自 Picard) ============

_split_words_re = re.compile(r'\W+', re.UNICODE)


def normalize(orig_string: str) -> str:
    """标准化字符串：转换为小写并移除非字母数字字符"""
    string = re.sub(r'[^a-zA-Z0-9]', '', orig_string.lower())
    if not string:
        string = orig_string
    return string


def similarity2(a: str, b: str) -> float:
    """
    计算多词字符串的相似度 (基于编辑距离)

    Returns:
        相似度分数 0.0-1.0
    """
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0

    alist = list(filter(bool, _split_words_re.split(a.lower())))
    blist = list(filter(bool, _split_words_re.split(b.lower())))

    alen, blen = len(alist), len(blist)
    if not alen or not blen:
        return 0.0
    if alen > blen:
        alist, blist = blist, alist
        alen, blen = blen, alen

    # 计算编辑距离的简化版本
    score = 0.0
    for av in alist:
        ms = 0.0
        mp = None
        for position, bv in enumerate(blist):
            # 简化的字符串相似度计算
            s = _string_similarity(av, bv)
            if s > ms:
                ms = s
                mp = position
        if mp is not None:
            score += ms
            if ms > 0.6:
                del blist[mp]

    return score / (alen + len(blist) * 0.4)


def _string_similarity(a: str, b: str) -> float:
    """计算两个字符串的相似度（简化版编辑距离）"""
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0

    # 使用简化的编辑距离算法
    len_a, len_b = len(a), len(b)
    if len_a == 0:
        return 0.0
    if len_b == 0:
        return 0.0

    # 动态规划计算编辑距离
    dp = [[0] * (len_b + 1) for _ in range(len_a + 1)]
    for i in range(len_a + 1):
        dp[i][0] = i
    for j in range(len_b + 1):
        dp[0][j] = j

    for i in range(1, len_a + 1):
        for j in range(1, len_b + 1):
            if a[i - 1] == b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1]) + 1

    max_len = max(len_a, len_b)
    return 1.0 - (dp[len_a][len_b] / max_len)


def length_score(a: int, b: int) -> float:
    """
    计算时长相似度分数

    Args:
        a: 文件时长（毫秒）
        b: 候选录音时长（毫秒）

    Returns:
        相似度 0.0-1.0，30秒(30000ms)以内差异按线性递减
    """
    if a is None or b is None:
        return 0.0
    LENGTH_SCORE_THRES_MS = 30000
    return 1.0 - min(abs(a - b), LENGTH_SCORE_THRES_MS) / float(LENGTH_SCORE_THRES_MS)


def trackcount_score(actual: int, expected: int) -> float:
    """
    计算曲目数量相似度

    Args:
        actual: 实际曲目数
        expected: 候选专辑曲目数

    Returns:
        相似度分数
    """
    if actual > expected:
        return 0.0
    elif actual < expected:
        return 0.3
    else:
        return 1.0


def extract_year_from_date(dt: str) -> Optional[int]:
    """
    从日期字符串中提取年份

    Args:
        dt: 日期字符串 (如 "2024", "2024-01", "2024-01-15")

    Returns:
        年份，如果无法解析则返回 None
    """
    try:
        if isinstance(dt, str):
            dt = dt.strip()
            # 尝试多种日期格式
            date_formats = [
                "%Y",
                "%Y-%m",
                "%Y-%m-%d",
                "%Y.%m",
                "%Y.%m.%d",
                "%Y/%m/%d",
                "%d.%m.%Y",
                "%m/%d/%Y",
                "%m.%d.%Y",
                "%d/%m/%Y",
            ]
            for fmt in date_formats:
                try:
                    parsed_date = datetime.strptime(dt, fmt)
                    return parsed_date.year
                except ValueError:
                    continue
        return None
    except (ValueError, TypeError):
        return None


def linear_combination_of_weights(parts: List[Tuple[float, int]]) -> float:
    """
    计算加权线性组合

    Args:
        parts: 列表，每个元素是 (value, weight) 元组
               value 是 0.0-1.0 之间的值
               weight 是正数权重

    Returns:
        加权平均值
    """
    total = 0.0
    sum_of_products = 0.0
    for value, weight in parts:
        if value < 0.0:
            raise ValueError("Value must be greater than or equal to 0.0")
        if value > 1.0:
            raise ValueError("Value must be lesser than or equal to 1.0")
        if weight < 0:
            raise ValueError("Weight must be greater than or equal to 0.0")
        total += weight
        sum_of_products += value * weight
    if total == 0.0:
        return 0.0
    return sum_of_products / total


def get_score(track: dict) -> float:
    """
    获取录音的搜索分数

    Args:
        track: 录音数据字典

    Returns:
        搜索分数 (默认 1.0)
    """
    return track.get('score', 1.0) / 100.0 if track.get('score') else 1.0


def artist_credit_from_node(artist_credits: List[dict]) -> Tuple[str, List[str]]:
    """
    从艺术家信用节点提取艺术家信息

    Args:
        artist_credits: 艺术家信用列表

    Returns:
        (艺术家字符串, 艺术家名称列表)
    """
    artists = []
    names = []
    for artist_credit in artist_credits:
        artist = artist_credit.get('artist', {})
        name = artist.get('name', '')
        artists.append(name)
        names.append(name)
        if 'joinphrase' in artist_credit:
            artists[-1] += artist_credit['joinphrase']
    return (' '.join(artists), names)


class AcoustIDConfig:
    """AcoustID配置常量"""
    ACOUSTID_KEY = 'v8pQ6oyB'
    ACOUSTID_URL = 'https://api.acoustid.org/v2'
    MUSICBRAINZ_URL = 'https://musicbrainz.org/ws/2'
    COVER_ART_ARCHIVE_URL = 'https://coverartarchive.org'
    FPCALC_NAMES = ['fpcalc', 'pyfpcalc']
    DEFAULT_CLIENT_VERSION = '2.12.0'


class FingerprintResult:
    """指纹查询结果"""
    def __init__(self, fingerprint: str, duration: int, success: bool = True):
        self.fingerprint = fingerprint
        self.duration = duration
        self.success = success
        self.error = None


class Recording:
    """录音信息"""
    def __init__(self, recording: dict, result_score: float = 1.0, sources: int = 1):
        self.recording = recording
        self.result_score = result_score
        self.sources = sources


class MatchResult:
    """匹配结果"""
    def __init__(self, success: bool, recordings: Optional[List[Dict]] = None, error: Optional[str] = None, best_match: Optional[Dict] = None):
        self.success = success
        self.recordings = recordings or []
        self.error = error
        self.best_match = best_match  # 最佳匹配的录音


class HTTPClient:
    """简单的HTTP客户端"""

    def __init__(self, user_agent: Optional[str] = None, debug_mode: bool = False):
        self.user_agent = user_agent or f'Picard-FingerprintMatcher/{AcoustIDConfig.DEFAULT_CLIENT_VERSION}'
        self.debug_mode = debug_mode
        if debug_mode:
            logger.debug("HTTPClient 初始化")
            logger.debug(f"  user_agent = {self.user_agent}")
    
    def post(self, url: str, data: Union[Dict[str, Any], str], headers: Optional[Dict[str, str]] = None) -> tuple[Optional[dict], Optional[str]]:
        """发送POST请求"""
        if self.debug_mode:
            logger.debug("="*60)
            logger.debug("HTTPClient.post 开始")
            logger.debug("="*60)
            logger.debug(f"method = POST")
            logger.debug(f"url = {url}")
            logger.debug(f"data type = {type(data).__name__}")
            logger.debug(f"data length = {len(str(data))}")
            logger.debug(f"headers = {headers}")

        all_headers = {
            'User-Agent': self.user_agent,
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json',
        }
        if headers:
            all_headers.update(headers)

        # 如果data是字典，则编码；如果是字符串，则直接使用
        if isinstance(data, dict):
            encoded_data = urlencode(data).encode('utf-8')
        else:
            encoded_data = data.encode('utf-8')

        if self.debug_mode:
            logger.debug(f"encoded_data length = {len(encoded_data)} bytes")

        request = Request(url, data=encoded_data, headers=all_headers, method='POST')

        try:
            if self.debug_mode:
                logger.debug("发送请求...")
                import time
                start_time = time.time()

            with urlopen(request, timeout=30, context=_ssl_context) as response:
                content = response.read().decode('utf-8')

                if self.debug_mode:
                    elapsed = time.time() - start_time
                    logger.debug(f"响应 received in {elapsed:.3f}s")
                    logger.debug(f"status code = {response.status}")
                    logger.debug(f"content length = {len(content)} chars")

                # 解析JSON并将繁体中文转换为简体中文
                parsed_json = json.loads(content)
                converted_json = convert_dict_to_simplified(parsed_json)

                if self.debug_mode:
                    logger.debug(f"JSON 解析成功")

                return converted_json, None
        except HTTPError as e:
            error_msg = f"HTTP Error {e.code}: {e.reason}"
            if self.debug_mode:
                logger.debug(f"HTTP Error: {e.code} - {e.reason}")
            return None, error_msg
        except URLError as e:
            error_msg = f"URL Error: {e.reason}"
            if self.debug_mode:
                logger.debug(f"URL Error: {e.reason}")
            return None, error_msg
        except json.JSONDecodeError as e:
            error_msg = f"JSON Decode Error: {e}"
            if self.debug_mode:
                logger.debug(f"JSON Decode Error: {e}")
            return None, error_msg
        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            if self.debug_mode:
                logger.debug(f"Unexpected error: {e}")
            return None, error_msg
    
    def get(self, url: str, params: Optional[Dict[str, Any]] = None) -> tuple[Optional[dict], Optional[str]]:
        """发送GET请求"""
        if self.debug_mode:
            logger.debug("="*60)
            logger.debug("HTTPClient.get 开始")
            logger.debug("="*60)
            logger.debug(f"method = GET")
            logger.debug(f"url = {url}")
            logger.debug(f"params = {params}")

        if params:
            url = f"{url}?{urlencode(params)}"

        if self.debug_mode:
            logger.debug(f"final url = {url}")

        headers = {
            'User-Agent': self.user_agent,
            'Accept': 'application/json',
        }
        request = Request(url, headers=headers)

        try:
            if self.debug_mode:
                logger.debug("发送请求...")
                import time
                start_time = time.time()

            with urlopen(request, timeout=30, context=_ssl_context) as response:
                content = response.read().decode('utf-8')

                if self.debug_mode:
                    elapsed = time.time() - start_time
                    logger.debug(f"响应 received in {elapsed:.3f}s")
                    logger.debug(f"status code = {response.status}")
                    logger.debug(f"content length = {len(content)} chars")

                # 解析JSON并将繁体中文转换为简体中文
                parsed_json = json.loads(content)
                converted_json = convert_dict_to_simplified(parsed_json)

                if self.debug_mode:
                    logger.debug(f"JSON 解析成功")

                return converted_json, None
        except HTTPError as e:
            error_msg = f"HTTP Error {e.code}: {e.reason}"
            if self.debug_mode:
                logger.debug(f"HTTP Error: {e.code} - {e.reason}")
            return None, error_msg
        except URLError as e:
            error_msg = f"URL Error: {e.reason}"
            if self.debug_mode:
                logger.debug(f"URL Error: {e.reason}")
            return None, error_msg
        except json.JSONDecodeError as e:
            error_msg = f"JSON Decode Error: {e}"
            if self.debug_mode:
                logger.debug(f"JSON Decode Error: {e}")
            return None, error_msg
        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            if self.debug_mode:
                logger.debug(f"Unexpected error: {e}")
            return None, error_msg


class FingerprintCalculator:
    """指纹计算器 - 使用fpcalc"""
    
    def __init__(self, fpcalc_path: Optional[str] = None):
        self.fpcalc_path = fpcalc_path or self._find_fpcalc()
    
    def _find_fpcalc(self) -> Optional[str]:
        """查找fpcalc可执行文件"""
        import shutil
        for name in AcoustIDConfig.FPCALC_NAMES:
            path = shutil.which(name)
            if path:
                logger.info(f"Found fpcalc: {path}")
                return path
        return None
    
    def calculate(self, audio_file_path: str) -> FingerprintResult:
        """计算音频文件的指纹"""
        if not self.fpcalc_path:
            return FingerprintResult('', 0, success=False)

        # 使用配置的指纹长度
        logger.info(f"使用指纹长度: {FPCALC_LENGTH} 秒")

        try:
            result = subprocess.run(
                [self.fpcalc_path, '-json', '-length', str(FPCALC_LENGTH), audio_file_path],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0 or result.returncode == 3:  # 3 = 解码警告但有结果
                if result.returncode == 3 and result.stderr:
                    logger.warning(f"fpcalc warning: {result.stderr}")
                
                output = json.loads(result.stdout)
                duration = int(output.get('duration', 0))
                fingerprint = output.get('fingerprint', '')
                
                if fingerprint and duration:
                    logger.info(f"Fingerprint calculated: {len(fingerprint)} chars, duration: {duration}s")
                    return FingerprintResult(fingerprint, duration, success=True)
            
            logger.error(f"fpcalc failed: {result.stderr}")
            return FingerprintResult('', 0, success=False)
            
        except subprocess.TimeoutExpired:
            logger.error("fpcalc timeout")
            return FingerprintResult('', 0, success=False)
        except FileNotFoundError:
            logger.error(f"fpcalc not found at {self.fpcalc_path}")
            return FingerprintResult('', 0, success=False)
        except json.JSONDecodeError:
            logger.error("fpcalc output parse error")
            return FingerprintResult('', 0, success=False)
        except Exception as e:
            logger.error(f"fpcalc error: {e}")
            return FingerprintResult('', 0, success=False)


class JSONHelpers:
    """JSON数据格式转换工具"""
    
    @staticmethod
    def _make_releases_node(recording: dict) -> List[dict]:
        """创建发行信息节点"""
        release_list = []
        for release_group in recording.get('releasegroups', []):
            for release in release_group.get('releases', []):
                release_mb = {
                    'id': release['id'],
                    'release-group': {
                        'id': release_group['id'],
                    }
                }
                
                if 'type' in release_group:
                    release_mb['release-group']['primary-type'] = release_group['type']
                if 'secondarytypes' in release_group:
                    release_mb['release-group']['secondary-types'] = release_group['secondarytypes']
                
                release_mb['title'] = release.get('title', release_group.get('title', ''))
                
                if 'country' in release:
                    release_mb['country'] = release['country']
                if 'date' in release:
                    release_mb['date'] = release['date']
                if 'medium_count' in release:
                    release_mb['medium-count'] = release['medium_count']
                if 'track_count' in release:
                    release_mb['track-count'] = release['track_count']
                
                release_mb['media'] = []
                for medium in release.get('mediums', []):
                    media_mb = {}
                    if 'format' in medium:
                        media_mb['format'] = medium['format']
                    if 'track_count' in medium:
                        media_mb['track-count'] = medium['track_count']
                    if 'position' in medium:
                        media_mb['position'] = medium['position']
                    if 'tracks' in medium:
                        media_mb['track'] = medium['tracks']
                        for track_mb in media_mb['track']:
                            track_mb['number'] = track_mb['position']
                    release_mb['media'].append(media_mb)
                
                if 'releaseevents' in release:
                    for releaseevent in release['releaseevents']:
                        release_copy = release_mb.copy()
                        release_copy['country'] = releaseevent.get('country', '')
                        release_copy['date'] = releaseevent.get('date', '')
                        release_list.append(release_copy)
                else:
                    release_list.append(release_mb)
        
        return release_list
    
    @staticmethod
    def _make_artist_node(artist: dict) -> dict:
        """创建艺术家节点"""
        node = {
            'name': artist['name'],
            'sort-name': artist.get('sort-name', artist['name']),
            'id': artist['id'],
        }

        # 添加艺术家类型（如果可用）
        if 'type' in artist:
            node['type'] = artist['type']

        return node
    
    @staticmethod
    def _make_artist_credit_node(artists: List[dict]) -> List[dict]:
        """创建艺术家信用节点"""
        artist_list = []
        for i, artist in enumerate(artists):
            node = {
                'artist': JSONHelpers._make_artist_node(artist),
                'name': artist['name'],
            }
            if i > 0:
                node['joinphrase'] = '; '
            artist_list.append(node)
        return artist_list
    
    @staticmethod
    def parse_recording(recording: dict) -> Optional[dict]:
        """将AcoustID格式转换为MusicBrainz格式"""
        if 'id' not in recording:
            return None
        
        recording_mb = {'id': recording['id']}
        
        if 'title' in recording:
            recording_mb['title'] = recording['title']
        
        if 'artists' in recording:
            recording_mb['artist-credit'] = JSONHelpers._make_artist_credit_node(recording['artists'])
        
        if 'releasegroups' in recording:
            recording_mb['releases'] = JSONHelpers._make_releases_node(recording)
        
        if 'duration' in recording:
            try:
                recording_mb['length'] = int(recording['duration']) * 1000
            except (TypeError, ValueError):
                pass
        
        if 'sources' in recording:
            recording_mb['sources'] = recording['sources']
        
        return recording_mb
    
    @staticmethod
    def recording_has_metadata(recording: dict) -> bool:
        """检查录音是否有完整元数据"""
        return 'id' in recording and recording.get('title') is not None


class RecordingResolver:
    """录音信息解析器 - 从AcoustID和MusicBrainz获取完整录音信息"""

    SOURCE_THRESHOLD_NO_METADATA = 0.25
    MAX_NO_METADATA_RECORDINGS = 3

    def __init__(self, http_client: HTTPClient, debug_mode: bool = False):
        self.http_client = http_client
        self.recording_cache = {}
        self.missing_metadata = []
        self.debug_mode = debug_mode
        if debug_mode:
            logger.debug("RecordingResolver 初始化")
    
    def _get_score(self, node: dict) -> float:
        """获取分数"""
        try:
            return float(node.get('score', 1.0))
        except (TypeError, ValueError):
            return 1.0
    
    def _max_source_count(self, recordings: List[Recording]) -> int:
        """获取最大来源数"""
        sources = {r.sources for r in recordings}
        sources.add(1)
        return max(sources)
    
    def _max_source_count_raw(self, recordings: List[dict]) -> int:
        """从原始录音数据获取最大来源数"""
        sources = {r.get('sources', 1) for r in recordings}
        sources.add(1)
        return max(sources)
    
    def resolve(self, doc: dict) -> List[dict]:
        """解析AcoustID查询结果"""
        if self.debug_mode:
            logger.debug("="*60)
            logger.debug("RecordingResolver.resolve 开始")
            logger.debug("="*60)

        results = doc.get('results') or []
        recording_map = {}
        incomplete_counts = {}

        if self.debug_mode:
            logger.debug(f"results count = {len(results)}")

        for i, result in enumerate(results):
            recordings = result.get('recordings') or []
            result_score = self._get_score(result)
            acoustid = result.get('id')
            max_sources = self._max_source_count_raw(recordings)

            if self.debug_mode:
                logger.debug(f"\n结果 {i+1}/{len(results)}:")
                logger.debug(f"  acoustid = {acoustid}")
                logger.debug(f"  result_score = {result_score}")
                logger.debug(f"  recordings count = {len(recordings)}")
                logger.debug(f"  max_sources = {max_sources}")

            for j, recording in enumerate(sorted(recordings, key=lambda r: r.get('sources', 1), reverse=True)):
                mbid = recording.get('id')
                sources = recording.get('sources', 1)

                if self.debug_mode:
                    logger.debug(f"  录音 {j+1}:")
                    logger.debug(f"    mbid = {mbid}")
                    logger.debug(f"    sources = {sources}")
                    logger.debug(f"    title = {recording.get('title', 'N/A')}")

                if acoustid not in recording_map:
                    recording_map[acoustid] = {}

                if JSONHelpers.recording_has_metadata(recording):
                    mb_recording = JSONHelpers.parse_recording(recording)
                    if mb_recording:
                        self.recording_cache[mbid] = mb_recording
                        recording_map[acoustid][recording['id']] = Recording(
                            recording=mb_recording,
                            result_score=result_score,
                            sources=sources,
                        )
                else:
                    if (sources / max_sources > self.SOURCE_THRESHOLD_NO_METADATA
                        and incomplete_counts.get(acoustid, 0) < self.MAX_NO_METADATA_RECORDINGS):
                        self.missing_metadata.append({
                            'mbid': mbid,
                            'acoustid': acoustid,
                            'result_score': result_score,
                            'sources': sources,
                        })
                        incomplete_counts[acoustid] = incomplete_counts.get(acoustid, 0) + 1
        
        # 加载缺失的元数据
        self._load_missing_metadata(recording_map)
        
        # 解析录音映射
        return list(self._parse_recording_map(recording_map))
    
    def _load_missing_metadata(self, recording_map: dict):
        """从MusicBrainz加载缺失的元数据"""
        for item in self.missing_metadata:
            mbid = item['mbid']

            if mbid in self.recording_cache:
                mb_recording = self.recording_cache[mbid]
            else:
                # 从MusicBrainz API获取 - 请求更多元数据包括流派
                url = f"{AcoustIDConfig.MUSICBRAINZ_URL}/recording/{mbid}"
                params = {'inc': 'artists+release-groups+releases+media+artist-credits+isrcs+tags'}

                mb_recording, error = self.http_client.get(url, params)
                if error:
                    logger.warning(f"Failed to load metadata for {mbid}: {error}")
                    continue

                if mb_recording and 'id' in mb_recording:
                    self.recording_cache[mbid] = mb_recording

            if mb_recording and mb_recording.get('id'):
                acoustid = item['acoustid']
                if acoustid not in recording_map:
                    recording_map[acoustid] = {}

                if mbid not in recording_map[acoustid]:
                    recording_map[acoustid][mbid] = Recording(
                        recording=mb_recording,
                        result_score=item['result_score'],
                        sources=item['sources'],
                    )
                else:
                    recording_map[acoustid][mbid].sources += item['sources']
    
    def _parse_recording_map(self, recording_map: dict):
        """解析录音映射并计算分数"""
        for acoustid, recordings in recording_map.items():
            recording_list = recordings.values()
            max_sources = self._max_source_count(recording_list)
            
            for recording in recording_list:
                parsed_recording = recording.recording
                if parsed_recording is not None:
                    score = min(recording.sources / max_sources, 1.0) * 100
                    parsed_recording['score'] = score * recording.result_score
                    parsed_recording['acoustid'] = acoustid
                    parsed_recording['sources'] = recording.sources
                yield parsed_recording


class ReleaseLoader:
    """Release加载器 - 从MusicBrainz加载完整的Release信息"""

    def __init__(self, http_client: HTTPClient, debug_mode: bool = False):
        self.http_client = http_client
        self._cache = {}
        self.debug_mode = debug_mode
        if debug_mode:
            logger.debug("ReleaseLoader 初始化")
    
    def load_release_by_id(self, release_id: str, inc: Optional[list] = None) -> Optional[dict]:
        """
        从MusicBrainz加载完整的Release信息

        Args:
            release_id: MusicBrainz Release ID
            inc: 要包含的额外信息列表

        Returns:
            Release数据字典,失败返回None
        """
        if self.debug_mode:
            logger.debug("="*60)
            logger.debug("ReleaseLoader.load_release_by_id 开始")
            logger.debug("="*60)
            logger.debug(f"release_id = {release_id}")

        if release_id in self._cache:
            if self.debug_mode:
                logger.debug("从缓存返回")
            return self._cache[release_id]

        # 默认inc参数,与Picard保持一致
        if inc is None:
            inc = [
                'aliases',           # 别名
                'annotation',        # 注释
                'artist-credits',    # 艺术家credits
                'artists',           # 艺术家
                'collections',        # 集合
                'discids',           # Disc ID
                'isrcs',            # ISRC代码
                'labels',            # 唱片公司
                'media',             # 媒体格式
                'recordings',        # 录音列表(包含所有音轨)
                'release-groups',    # 发行组
                'artist-rels',       # 艺术家关系
                'recording-rels',    # 录音关系
                'label-rels',        # 唱片公司关系
                'release-group-level-rels',  # 发行组级关系
                'release-rels',     # 发行关系
                'series-rels',       # 系列关系
                'url-rels',          # URL关系
                'work-rels',         # 作品关系
                'recording-level-rels',  # 录音级关系
                'work-level-rels',      # 作品级关系
            ]

        # 构建inc参数
        inc_param = '+'.join(inc)
        url = f"{AcoustIDConfig.MUSICBRAINZ_URL}/release/{release_id}"

        if self.debug_mode:
            logger.debug(f"inc = {', '.join(inc[:5])}... (共{len(inc)}项)")
            logger.debug(f"url = {url}?inc={inc_param}")
        params = {'inc': inc_param}
        
        logger.info(f"Loading release {release_id} from MusicBrainz with inc={inc_param}")
        
        release_data, error = self.http_client.get(url, params)
        
        if error or release_data is None:
            logger.error(f"Failed to load release {release_id}: {error}")
            return None
        
        # 缓存结果
        self._cache[release_id] = release_data
        
        return release_data
    
    def clear_cache(self):
        """清除缓存"""
        self._cache.clear()


class AcoustIDClient:
    """AcoustID客户端 - 主要的指纹匹配客户端"""

    def __init__(self, client_version: Optional[str] = None, debug_mode: bool = False):
        self.http_client = HTTPClient(debug_mode=debug_mode)
        self.client_key = AcoustIDConfig.ACOUSTID_KEY
        self.client_version = client_version or AcoustIDConfig.DEFAULT_CLIENT_VERSION
        self.resolver = RecordingResolver(self.http_client, debug_mode=debug_mode)
        self.release_loader = ReleaseLoader(self.http_client, debug_mode=debug_mode)
        self.debug_mode = debug_mode
        if debug_mode:
            logger.debug("AcoustIDClient 初始化")
            logger.debug(f"  client_key = {self.client_key}")
            logger.debug(f"  client_version = {self.client_version}")
    
    def _encode_acoustid_args(self, args: Dict[str, Any]) -> str:
        """编码AcoustID请求参数，与原始Picard实现保持一致"""
        args['client'] = self.client_key
        args['clientversion'] = self.client_version
        args['format'] = 'json'
        # 手动编码每个值，使用quote的safe=''确保空格编码为%20
        return '&'.join(f"{key}={quote(str(value), safe='')}" for key, value in args.items())
    
    def query_acoustid(self, fingerprint: str, duration: int) -> tuple[Optional[dict], Optional[str]]:
        """使用指纹查询AcoustID"""
        if self.debug_mode:
            logger.debug("="*60)
            logger.debug("开始查询 AcoustID API")
            logger.debug("="*60)

        params = {
            'fingerprint': fingerprint,
            'duration': str(duration),
            'meta': 'recordings releasegroups releases tracks artists usermeta compress sources',
        }

        url = f"{AcoustIDConfig.ACOUSTID_URL}/lookup"

        if self.debug_mode:
            logger.debug(f"AcoustID 查询参数:")
            logger.debug(f"  url = {url}")
            logger.debug(f"  fingerprint length = {len(fingerprint)}")
            logger.debug(f"  fingerprint = {fingerprint[:50]}...")
            logger.debug(f"  duration = {duration}s")
            logger.debug(f"  meta = recordings releasegroups releases tracks artists usermeta compress sources")

        logger.info(f"Querying AcoustID with fingerprint ({len(fingerprint)} chars, {duration}s)")

        # 编码参数并添加必需的client, clientversion, format参数
        body = self._encode_acoustid_args(params)

        if self.debug_mode:
            logger.debug(f"  请求体长度 = {len(body)} chars")

        document, error = self.http_client.post(url, body)

        if error or document is None:
            if self.debug_mode:
                logger.debug(f"  查询失败: {error}")
            logger.error(f"AcoustID query error: {error}")
            return None, error

        if self.debug_mode:
            logger.debug(f"  响应状态: {document.get('status')}")

        status = document.get('status')
        if status != 'ok':
            error_msg = document.get('error', {}).get('message', 'Unknown error')
            if self.debug_mode:
                logger.debug(f"  API 错误: {error_msg}")
            logger.error(f"AcoustID API error: {error_msg}")
            return None, error_msg

        results = document.get('results', [])
        logger.info(f"AcoustID returned {len(results)} results")

        if self.debug_mode:
            logger.debug(f"  返回结果数 = {len(results)}")
            if results:
                logger.debug(f"  第一个结果: {json.dumps(results[0], ensure_ascii=False, indent=2)[:500]}...")

        return document, None
    
    def match_fingerprint(self, fingerprint: str, duration: int, metadata: Optional[Dict] = None) -> MatchResult:
        """
        匹配指纹并返回录音信息（使用最佳匹配算法）

        Args:
            fingerprint: 音频指纹
            duration: 时长（秒）
            metadata: 可选的现有元数据，用于提高匹配精度

        Returns:
            MatchResult 包含最佳匹配的录音
        """
        if self.debug_mode:
            logger.debug("="*60)
            logger.debug("开始匹配指纹")
            logger.debug("="*60)
            logger.debug(f"fingerprint length = {len(fingerprint)}")
            logger.debug(f"duration = {duration}s")
            logger.debug(f"metadata = {json.dumps(metadata, ensure_ascii=False) if metadata else None}")

        document, error = self.query_acoustid(fingerprint, duration)

        if error or document is None:
            if self.debug_mode:
                logger.debug(f"查询失败: {error}")
            return MatchResult(success=False, recordings=[], error=error or "Unknown error")

        # 解析录音信息
        try:
            if self.debug_mode:
                logger.debug("开始解析录音信息...")

            recordings = self.resolver.resolve(document)
            logger.info(f"Resolved {len(recordings)} recordings")

            if self.debug_mode:
                logger.debug(f"解析出 {len(recordings)} 条录音")

            # 如果提供了元数据，使用相似度算法选择最佳匹配
            if metadata and recordings:
                if self.debug_mode:
                    logger.debug("使用元数据进行最佳匹配...")

                best_match = self._find_best_match(recordings, metadata, duration * 1000)
                logger.info(f"Best match selected with score: {best_match.get('score', 0):.1f}%")

                if self.debug_mode:
                    logger.debug(f"最佳匹配分数: {best_match.get('score', 0):.1f}%")
                    logger.debug(f"最佳匹配: {json.dumps(best_match, ensure_ascii=False, indent=2)[:500]}...")

                return MatchResult(success=True, recordings=recordings, best_match=best_match)
            else:
                # 如果没有提供元数据，选择 AcoustID 分数最高的
                if self.debug_mode:
                    logger.debug("未提供元数据，使用 AcoustID 分数选择最佳匹配...")

                best_match = max(recordings, key=lambda r: r.get('score', 0), default=None)
                if best_match:
                    logger.info(f"Best match by AcoustID score: {best_match.get('score', 0):.1f}%")
                    if self.debug_mode:
                        logger.debug(f"AcoustID 最佳匹配分数: {best_match.get('score', 0):.1f}%")
                return MatchResult(success=True, recordings=recordings, best_match=best_match)
        except Exception as e:
            error_msg = f"Failed to resolve recordings: {e}"
            if self.debug_mode:
                logger.debug(f"解析录音失败: {e}")
            logger.error(error_msg)
            return MatchResult(success=False, recordings=[], error=error_msg)

    def _find_best_match(self, recordings: List[Dict], metadata: Dict, file_duration_ms: int) -> Optional[Dict]:
        """
        使用 Picard 的相似度算法选择最佳匹配

        Args:
            recordings: 候选录音列表
            metadata: 现有文件元数据
            file_duration_ms: 文件时长（毫秒）

        Returns:
            最佳匹配的录音
        """
        if not recordings:
            return None

        # 文件比较权重（来自 Picard）
        FILE_COMPARISON_WEIGHTS = {
            'title': 13,           # 最高权重 - 标题匹配最关键
            'releasetype': 14,     # 最高 - 偏好官方发行
            'length': 10,          # 时长匹配
            'artist': 4,           # 艺术家名称匹配
            'date': 4,             # 发行日期匹配
            'totaltracks': 4,      # 曲目数量匹配
            'releasecountry': 2,   # 国家偏好
            'format': 2,           # 格式偏好 (CD, vinyl 等)
            'isvideo': 2,          # 视频标志匹配
        }

        # 发行类型分数（默认值）
        RELEASE_TYPE_SCORES = {
            'Album': 1.0,
            'Single': 0.8,
            'EP': 0.7,
            'Other': 0.5,
            'Broadcast': 0.4,
            'Compilation': 0.6,
        }

        best_recording = None
        best_similarity = -1.0

        for recording in recordings:
            parts = []

            # 1. 标题相似度
            if 'title' in metadata:
                a = metadata['title']
                b = recording.get('title', '')
                parts.append((similarity2(a, b), FILE_COMPARISON_WEIGHTS['title']))

            # 2. 艺术家相似度
            if 'artist' in metadata:
                a = metadata['artist']
                artist_credits = recording.get('artist-credit', [])
                b, _ = artist_credit_from_node(artist_credits)
                parts.append((similarity2(a, b), FILE_COMPARISON_WEIGHTS['artist']))

            # 3. 时长分数
            file_length = file_duration_ms
            if file_length > 0 and 'length' in recording:
                track_length = recording['length']
                score = length_score(file_length, track_length)
                parts.append((score, FILE_COMPARISON_WEIGHTS['length']))

            # 4. 获取搜索分数
            search_score = get_score(recording)

            # 5. 处理发行信息
            releases = recording.get('releases', [])
            if releases:
                # 对每个发行计算相似度，选择最高的
                best_release_similarity = -1.0

                for release in releases:
                    release_parts = parts.copy()

                    # 5.1 专辑标题相似度
                    if 'album' in metadata:
                        album_title = metadata['album']
                        release_title = release.get('title', '')
                        release_parts.append((similarity2(album_title, release_title), 8))

                    # 5.2 曲目数量分数
                    if 'totaltracks' in metadata:
                        try:
                            metadata_totaltracks = int(metadata['totaltracks'])
                            release_trackcount = release.get('track-count', 0)
                            if release_trackcount:
                                score = trackcount_score(metadata_totaltracks, release_trackcount)
                                release_parts.append((score, FILE_COMPARISON_WEIGHTS['totaltracks']))
                        except (ValueError, TypeError):
                            pass

                    # 5.3 日期匹配
                    if 'date' in metadata:
                        metadata_date = metadata['date']
                        release_date = release.get('date', '')
                        if release_date:
                            if release_date == metadata_date:
                                date_match_factor = 1.00
                            else:
                                release_year = extract_year_from_date(release_date)
                                metadata_year = extract_year_from_date(metadata_date)
                                if release_year is not None and metadata_year is not None:
                                    if release_year == metadata_year:
                                        date_match_factor = 0.95
                                    elif abs(release_year - metadata_year) <= 2:
                                        date_match_factor = 0.85
                                    else:
                                        date_match_factor = 0.0
                                else:
                                    date_match_factor = 0.0
                        else:
                            date_match_factor = 0.25
                        release_parts.append((date_match_factor, FILE_COMPARISON_WEIGHTS['date']))

                    # 5.4 发行类型分数
                    if 'release-group' in release:
                        release_group = release['release-group']
                        release_type = release_group.get('primary-type', 'Other')
                        type_score = RELEASE_TYPE_SCORES.get(release_type, RELEASE_TYPE_SCORES['Other'])
                        release_parts.append((type_score, FILE_COMPARISON_WEIGHTS['releasetype']))

                    # 5.5 国家偏好（简化版，默认给中等分数）
                    release_parts.append((0.5, FILE_COMPARISON_WEIGHTS['releasecountry']))

                    # 5.6 格式偏好（简化版，默认给中等分数）
                    release_parts.append((0.5, FILE_COMPARISON_WEIGHTS['format']))

                    # 计算该发行的总相似度
                    similarity = linear_combination_of_weights(release_parts) * search_score
                    if similarity > best_release_similarity:
                        best_release_similarity = similarity

                similarity = best_release_similarity
            else:
                # 如果没有发行信息，使用默认分数
                default_type_score = RELEASE_TYPE_SCORES['Other']
                parts.append((default_type_score, FILE_COMPARISON_WEIGHTS['releasetype']))
                similarity = linear_combination_of_weights(parts) * search_score

            # 记录最佳匹配
            if similarity > best_similarity:
                best_similarity = similarity
                best_recording = recording

        # 在录音上保存计算出的相似度
        if best_recording:
            best_recording['_calculated_similarity'] = best_similarity

        return best_recording


class FingerprintMatcher:
    """指纹匹配器 - 整合所有功能的主类"""

    def __init__(self, fpcalc_path: Optional[str] = None, client_version: Optional[str] = None, debug_mode: bool = False):
        self.calculator = FingerprintCalculator(fpcalc_path)
        self.acoustid_client = AcoustIDClient(client_version)
        self.debug_mode = debug_mode
        if debug_mode:
            logger.debug("="*60)
            logger.debug("FingerprintMatcher 初始化")
            logger.debug(f"  debug_mode = {debug_mode}")
            logger.debug(f"  fpcalc_path = {fpcalc_path}")
            logger.debug(f"  client_version = {client_version}")
            logger.debug("="*60)
    
    def match_file(self, audio_file_path: str, metadata: Optional[Dict] = None) -> MatchResult:
        """
        匹配音频文件

        Args:
            audio_file_path: 音频文件路径
            metadata: 可选的现有元数据（包含 title, artist, album, date, totaltracks 等）
                       用于提高匹配精度

        Returns:
            MatchResult 包含最佳匹配的录音
        """
        if self.debug_mode:
            logger.debug("="*60)
            logger.debug("开始匹配音频文件")
            logger.debug("="*60)
            logger.debug(f"audio_file_path = {audio_file_path}")
            logger.debug(f"metadata = {json.dumps(metadata, ensure_ascii=False) if metadata else None}")
            logger.debug(f"文件存在: {os.path.exists(audio_file_path)}")
            if os.path.exists(audio_file_path):
                logger.debug(f"文件大小: {os.path.getsize(audio_file_path)} bytes")

        logger.info(f"Processing file: {audio_file_path}")

        # 计算指纹
        fingerprint_result = self.calculator.calculate(audio_file_path)

        if self.debug_mode:
            logger.debug(f"指纹计算结果:")
            logger.debug(f"  success = {fingerprint_result.success}")
            logger.debug(f"  fingerprint = {fingerprint_result.fingerprint[:50]}..." if fingerprint_result.fingerprint else "  fingerprint = None")
            logger.debug(f"  duration = {fingerprint_result.duration}")
            logger.debug(f"  error = {fingerprint_result.error}")

        if not fingerprint_result.success:
            if self.debug_mode:
                logger.debug(f"指纹计算失败: {fingerprint_result.error}")
            return MatchResult(
                success=False,
                recordings=[],
                error="Failed to calculate fingerprint"
            )

        # 查询匹配
        if self.debug_mode:
            logger.debug("开始查询 AcoustID API...")

        result = self.acoustid_client.match_fingerprint(
            fingerprint_result.fingerprint,
            fingerprint_result.duration,
            metadata
        )

        if self.debug_mode:
            logger.debug(f"AcoustID 查询结果:")
            logger.debug(f"  success = {result.success}")
            logger.debug(f"  recordings count = {len(result.recordings)}")
            if result.recordings:
                logger.debug(f"  最佳匹配: {result.recordings[0].get('title', 'N/A')}")
            logger.debug(f"  error = {result.error}")
            logger.debug("="*60)

        return result
    
    def match_from_fingerprint(self, fingerprint: str, duration: int, metadata: Optional[Dict] = None) -> MatchResult:
        """
        从已有指纹匹配

        Args:
            fingerprint: 音频指纹
            duration: 时长（秒）
            metadata: 可选的现有元数据，用于提高匹配精度

        Returns:
            MatchResult 包含最佳匹配结果
        """
        logger.info(f"Matching from existing fingerprint ({len(fingerprint)} chars, {duration}s)")
        return self.acoustid_client.match_fingerprint(fingerprint, duration, metadata)
    
    def load_full_release_for_best_match(self, best_match: Dict, inc: Optional[list] = None) -> Optional[Dict]:
        """
        为最佳匹配加载完整的Release信息
        
        这与Picard的流程一致:
        1. AcoustID匹配 → 2. 选择最佳recording → 3. 获取release_id → 4. 加载完整release
        
        Args:
            best_match: 最佳匹配的recording数据
            inc: 要包含的额外信息列表（可选）
        
        Returns:
            完整的Release数据字典,失败返回None
        """
        releases = best_match.get('releases', [])
        if not releases:
            logger.warning("No releases found in best match, cannot load full release")
            return None
        
        # 使用第一个release的ID（通常是最佳匹配）
        release_id = releases[0].get('id')
        if not release_id:
            logger.warning("No release ID found in best match")
            return None
        
        logger.info(f"Loading full release information for {release_id}")
        
        # 使用ReleaseLoader加载完整release
        release_data = self.acoustid_client.release_loader.load_release_by_id(release_id, inc)
        
        if release_data:
            # 将完整release数据合并到best_match中
            # 更新releases列表中的第一个元素
            if 'releases' in best_match and len(best_match['releases']) > 0:
                # 合并release数据到现有recording中
                self._merge_release_to_recording(best_match, release_data)
        
        return release_data
    
    def _merge_release_to_recording(self, recording: Dict, release: Dict):
        """
        将完整的Release数据合并到recording中
        
        Args:
            recording: recording数据字典
            release: 完整的release数据字典
        """
        # 更新releases列表中的第一个release
        if 'releases' in recording and len(recording['releases']) > 0:
            recording['releases'][0].update(release)
        
        # 确保release-group也更新
        if 'release-group' in release:
            if 'releases' in recording and len(recording['releases']) > 0:
                recording['releases'][0]['release-group'] = release['release-group']
        
        logger.debug(f"Merged full release data into recording for release {release.get('id')}")


def format_recording_info(recording: dict, show_similarity: bool = False) -> str:
    """
    格式化录音信息用于显示

    Args:
        recording: 录音数据
        show_similarity: 是否显示计算出的相似度分数

    Returns:
        格式化的字符串
    """
    title = recording.get('title', 'Unknown')
    artists = []

    for artist_credit in recording.get('artist-credit', []):
        artist = artist_credit.get('artist', {})
        artists.append(artist.get('name', 'Unknown'))
        if 'joinphrase' in artist_credit:
            artists[-1] += artist_credit['joinphrase']

    artist_str = ' '.join(artists)
    score = recording.get('score', 0)
    sources = recording.get('sources', 0)
    acoustid = recording.get('acoustid', 'N/A')
    mbid = recording.get('id', 'N/A')

    info = f"\n{'='*60}\n"
    info += f"Title: {title}\n"
    info += f"Artist: {artist_str}\n"
    info += f"AcoustID Score: {score:.1f}%\n"
    info += f"Sources: {sources}\n"

    # 显示计算出的相似度分数（如果可用）
    if show_similarity and '_calculated_similarity' in recording:
        similarity = recording['_calculated_similarity']
        info += f"Calculated Similarity: {similarity * 100:.1f}%\n"

    info += f"AcoustID: {acoustid}\n"
    info += f"MusicBrainz ID: {mbid}\n"

    releases = recording.get('releases', [])
    if releases:
        info += f"Releases ({len(releases)}):\n"
        for release in releases[:3]:  # 只显示前3个发行
            release_title = release.get('title', 'Unknown')
            release_date = release.get('date', 'N/A')
            release_group = release.get('release-group', {})
            release_type = release_group.get('primary-type', 'N/A')
            info += f"  - {release_title} ({release_date}) [{release_type}]\n"

    info += f"{'='*60}"
    return info


def get_cover_art_url(release_id: str) -> Optional[str]:
    """
    获取封面图片的 URL

    Args:
        release_id: MusicBrainz 发行 ID

    Returns:
        封面图片 URL，如果失败则返回 None
    """
    try:
        url = f"{AcoustIDConfig.COVER_ART_ARCHIVE_URL}/release/{release_id}/front-500.jpg"
        # 不需要实际下载，只检查是否存在
        return url
    except Exception as e:
        logger.warning(f"Failed to get cover art URL: {e}")
        return None


def map_recording_to_tags(recording: dict) -> dict:
    """
    将MusicBrainz recording数据映射到Picard风格的标签字典

    参考picard/const/tags.py中定义的120+个标签字段

    Args:
        recording: 从MusicBrainz获取的recording数据

    Returns:
        包含所有标签的字典
    """
    tags = {}

    # ========== 基本信息 ==========
    tags['title'] = recording.get('title', '')

    # 录音ID
    tags['musicbrainz_recordingid'] = recording.get('id', '')
    tags['acoustid_id'] = recording.get('acoustid', '')

    # 长度
    length_ms = recording.get('length', 0)
    if length_ms:
        tags['length'] = f"{length_ms // 60000}:{(length_ms % 60000) // 1000:02d}"

    # ========== 艺术家信息 ==========
    artist_credit = recording.get('artist-credit', [])
    if artist_credit:
        # 提取艺术家名称 (标准化)
        artists = []
        for credit in artist_credit:
            if isinstance(credit, dict):
                artist = credit.get('artist', {})
                name = artist.get('name', '')
                joinphrase = credit.get('joinphrase', '')
                if name:
                    artists.append(name + joinphrase)
        tags['artist'] = ''.join(artists).rstrip()

        # 提取艺术家名称列表 (原始)
        artists_list = []
        for credit in artist_credit:
            if isinstance(credit, dict):
                artist = credit.get('artist', {})
                name = artist.get('name', '')
                if name:
                    artists_list.append(name)
        tags['artists'] = artists_list

        # 提取艺术家ID
        artist_ids = []
        for credit in artist_credit:
            if isinstance(credit, dict):
                artist = credit.get('artist', {})
                artist_id = artist.get('id', '')
                if artist_id:
                    artist_ids.append(artist_id)
        tags['musicbrainz_artistid'] = artist_ids

        # 提取排序名称
        artists_sort = []
        for credit in artist_credit:
            if isinstance(credit, dict):
                artist = credit.get('artist', {})
                sort_name = artist.get('sort-name', '')
                joinphrase = credit.get('joinphrase', '')
                if sort_name:
                    artists_sort.append(sort_name + joinphrase)
        tags['artistsort'] = ''.join(artists_sort).rstrip()

        # 提取排序名称列表
        artists_sort_list = []
        for credit in artist_credit:
            if isinstance(credit, dict):
                artist = credit.get('artist', {})
                sort_name = artist.get('sort-name', '')
                if sort_name:
                    artists_sort_list.append(sort_name)
        tags['artists_sort'] = artists_sort_list

        # 提取国家信息
        countries = []
        for credit in artist_credit:
            if isinstance(credit, dict):
                artist = credit.get('artist', {})
                country = artist.get('country', 'XX')
                countries.append(country)
        tags['artists_countries'] = countries

    # ========== ISRC信息 ==========
    isrcs = recording.get('isrcs', [])
    if isrcs:
        tags['isrc'] = isrcs

    # ========== Release/Album信息 ==========
    releases = recording.get('releases', [])
    if releases:
        # 使用第一个release的信息
        release = releases[0]

        # 专辑标题
        tags['album'] = release.get('title', '')

        # Release ID
        tags['musicbrainz_releaseid'] = release.get('id', '')

        # 发行日期
        date = release.get('date', '')
        if date:
            tags['date'] = date
            # 提取年份
            year = extract_year_from_date(date)
            if year:
                tags['originalyear'] = str(year)
                tags['originaldate'] = date

        # 发行国家
        country = release.get('country', '')
        if country:
            tags['releasecountry'] = country
            tags['releasecountries'] = [country]

        # 发行状态
        status = release.get('status', '')
        if status:
            tags['releasestatus'] = status

        # 发行类型
        release_group = release.get('release-group', {})
        if release_group:
            tags['musicbrainz_releasegroupid'] = release_group.get('id', '')
            tags['releasegroup'] = release_group.get('title', '')

            # 主要类型
            primary_type = release_group.get('primary-type', '')
            if primary_type:
                tags['primaryreleasetype'] = primary_type
                tags['releasetype'] = [primary_type]

            # 次要类型
            secondary_types = release_group.get('secondary-types', [])
            if secondary_types:
                tags['secondaryreleasetype'] = secondary_types
                tags['releasetype'] = tags.get('releasetype', []) + secondary_types

            # 首次发行日期
            first_release_date = release_group.get('first-release-date', '')
            if first_release_date:
                tags['releasegroup_firstreleasedate'] = first_release_date

        # 唱片公司标签
        label_info = release.get('label-info', [])
        labels = []
        catalog_numbers = []
        for info in label_info:
            label = info.get('label', {})
            label_name = label.get('name', '')
            if label_name:
                labels.append(label_name)
            catalog_number = info.get('catalog-number', '')
            if catalog_number:
                catalog_numbers.append(catalog_number)
        if labels:
            tags['label'] = labels
        if catalog_numbers:
            tags['catalognumber'] = catalog_numbers

        # 条码
        barcode = release.get('barcode', '')
        if barcode:
            tags['barcode'] = barcode

        # ASIN
        asin = release.get('asin', '')
        if asin:
            tags['asin'] = asin

        # 媒体信息
        media_list = release.get('media', [])
        if media_list:
            # 格式
            formats = []
            for medium in media_list:
                fmt = medium.get('format', '')
                if fmt:
                    formats.append(fmt)
            if formats:
                tags['media'] = ', '.join(formats)

            # 碟片和音轨信息
            total_tracks = 0
            total_discs = len(media_list)

            for medium in media_list:
                track_count = medium.get('track-count', 0)
                total_tracks += track_count

                # 查找当前音轨在媒体中的位置
                track_list = medium.get('track', [])
                for track in track_list:
                    track_recording = track.get('recording', {})
                    if track_recording.get('id') == recording.get('id'):
                        # 找到了当前音轨
                        tags['discnumber'] = str(medium.get('position', 1))
                        tags['tracknumber'] = str(track.get('position', 0))
                        tags['musicbrainz_trackid'] = track.get('id', '')

                        # 碟片子标题
                        disc_subtitle = medium.get('title', '')
                        if disc_subtitle:
                            tags['discsubtitle'] = disc_subtitle

                        # 碟片总数
                        tags['totaldiscs'] = str(total_discs)

                        # 音轨总数
                        tags['totaltracks'] = str(track_count)

                        # 专辑总音轨数
                        tags['totalalbumtracks'] = str(total_tracks)

                        break

        # ========== 专辑艺术家 ==========
        # 从release的artist-credit获取
        release_artist_credit = release.get('artist-credit', [])
        if release_artist_credit:
            # 专辑艺术家 (标准化)
            album_artists = []
            for credit in release_artist_credit:
                if isinstance(credit, dict):
                    artist = credit.get('artist', {})
                    name = artist.get('name', '')
                    joinphrase = credit.get('joinphrase', '')
                    if name:
                        album_artists.append(name + joinphrase)
            tags['albumartist'] = ''.join(album_artists).rstrip()

            # 专辑艺术家列表
            album_artists_list = []
            for credit in release_artist_credit:
                if isinstance(credit, dict):
                    artist = credit.get('artist', {})
                    name = artist.get('name', '')
                    if name:
                        album_artists_list.append(name)
            tags['albumartists'] = album_artists_list

            # 专辑艺术家ID
            album_artist_ids = []
            for credit in release_artist_credit:
                if isinstance(credit, dict):
                    artist = credit.get('artist', {})
                    artist_id = artist.get('id', '')
                    if artist_id:
                        album_artist_ids.append(artist_id)
            tags['musicbrainz_albumartistid'] = album_artist_ids

            # 专辑艺术家排序
            album_artists_sort = []
            for credit in release_artist_credit:
                if isinstance(credit, dict):
                    artist = credit.get('artist', {})
                    sort_name = artist.get('sort-name', '')
                    joinphrase = credit.get('joinphrase', '')
                    if sort_name:
                        album_artists_sort.append(sort_name + joinphrase)
            tags['albumartistsort'] = ''.join(album_artists_sort).rstrip()

            # 专辑艺术家排序列表
            album_artists_sort_list = []
            for credit in release_artist_credit:
                if isinstance(credit, dict):
                    artist = credit.get('artist', {})
                    sort_name = artist.get('sort-name', '')
                    if sort_name:
                        album_artists_sort_list.append(sort_name)
            tags['albumartists_sort'] = album_artists_sort_list

    # ========== 标签/流派 ==========
    tags_dict = recording.get('tags', [])
    if tags_dict:
        genres = []
        folksonomy_tags = []
        for tag in tags_dict:
            tag_name = tag.get('name', '')
            if tag_name:
                folksonomy_tags.append(tag_name)
                # 简单判断是否为流派标签
                # 这里可以扩展更复杂的流派过滤逻辑
                genres.append(tag_name)
        if genres:
            tags['genre'] = genres
            tags['genres'] = folksonomy_tags
            tags['folksonomy_tags'] = folksonomy_tags

    # ========== 备注信息 ==========
    disambiguation = recording.get('disambiguation', '')
    if disambiguation:
        tags['recordingcomment'] = disambiguation

    # ========== 相似度/得分 ==========
    score = recording.get('score', 0)
    if score:
        tags['score'] = str(score)

    sources = recording.get('sources', 0)
    if sources:
        tags['sources'] = str(sources)

    return tags


def format_complete_tags(recording: dict, show_cover: bool = True) -> str:
    """
    格式化完整的标签信息，包括所有可用的元数据

    Args:
        recording: 录音数据
        show_cover: 是否显示封面图片 URL

    Returns:
        完整的标签信息字符串
    """
    # 映射到标签字典
    tags = map_recording_to_tags(recording)

    lines = []
    lines.append("=" * 80)
    lines.append("完整标签信息")
    lines.append("=" * 80)

    # 基本信息区
    lines.append("\n【基本信息】")
    lines.append(f"歌曲名称: {tags.get('title', 'Unknown')}")

    # 艺术家信息
    artist = tags.get('artist', '')
    if artist:
        lines.append(f"艺术家: {artist}")

    # 专辑信息
    album = tags.get('album', '')
    if album:
        lines.append(f"专辑: {album}")

    # 时长
    length = tags.get('length', '')
    if length:
        lines.append(f"时长: {length}")

    # AcoustID 信息
    acoustid = tags.get('acoustid_id', '')
    if acoustid:
        lines.append(f"AcoustID: {acoustid}")

    # MusicBrainz ID
    mb_recording_id = tags.get('musicbrainz_recordingid', '')
    if mb_recording_id:
        lines.append(f"MusicBrainz 录音ID: {mb_recording_id}")

    mb_release_id = tags.get('musicbrainz_releaseid', '')
    if mb_release_id:
        lines.append(f"MusicBrainz 专辑ID: {mb_release_id}")

    mb_releasegroup_id = tags.get('musicbrainz_releasegroupid', '')
    if mb_releasegroup_id:
        lines.append(f"MusicBrainz 专辑组ID: {mb_releasegroup_id}")

    mb_track_id = tags.get('musicbrainz_trackid', '')
    if mb_track_id:
        lines.append(f"MusicBrainz 音轨ID: {mb_track_id}")

    # 艺术家ID
    artist_ids = tags.get('musicbrainz_artistid', [])
    if artist_ids:
        lines.append(f"MusicBrainz 艺术家ID: {', '.join(artist_ids)}")

    # 专辑艺术家
    albumartist = tags.get('albumartist', '')
    if albumartist:
        lines.append(f"专辑艺术家: {albumartist}")

    # 专辑艺术家ID
    albumartist_ids = tags.get('musicbrainz_albumartistid', [])
    if albumartist_ids:
        lines.append(f"MusicBrainz 专辑艺术家ID: {', '.join(albumartist_ids)}")

    # 艺术家排序
    artistsort = tags.get('artistsort', '')
    if artistsort:
        lines.append(f"艺术家排序顺序: {artistsort}")

    # 专辑艺术家排序
    albumartistsort = tags.get('albumartistsort', '')
    if albumartistsort:
        lines.append(f"专辑艺术家排序顺序: {albumartistsort}")

    # 音轨和碟片信息
    tracknumber = tags.get('tracknumber', '')
    if tracknumber:
        lines.append(f"音轨号: {tracknumber}")

    discnumber = tags.get('discnumber', '')
    if discnumber:
        lines.append(f"碟号: {discnumber}")

    totaltracks = tags.get('totaltracks', '')
    if totaltracks:
        lines.append(f"总音轨数: {totaltracks}")

    totaldiscs = tags.get('totaldiscs', '')
    if totaldiscs:
        lines.append(f"总碟数: {totaldiscs}")

    totalalbumtracks = tags.get('totalalbumtracks', '')
    if totalalbumtracks:
        lines.append(f"专辑总音轨数: {totalalbumtracks}")

    # 日期信息
    date = tags.get('date', '')
    if date:
        lines.append(f"发行日期: {date}")

    originaldate = tags.get('originaldate', '')
    if originaldate:
        lines.append(f"首发日期: {originaldate}")

    originalyear = tags.get('originalyear', '')
    if originalyear:
        lines.append(f"首发年份: {originalyear}")

    # 发行信息
    country = tags.get('releasecountry', '')
    if country:
        lines.append(f"发行国/地区: {country}")

    status = tags.get('releasestatus', '')
    if status:
        lines.append(f"专辑状态: {status}")

    releasetype = tags.get('releasetype', [])
    if releasetype:
        lines.append(f"专辑类型: {', '.join(releasetype)}")

    primaryreleasetype = tags.get('primaryreleasetype', '')
    if primaryreleasetype:
        lines.append(f"主要专辑类型: {primaryreleasetype}")

    secondaryreleasetype = tags.get('secondaryreleasetype', [])
    if secondaryreleasetype:
        lines.append(f"次要专辑类型: {', '.join(secondaryreleasetype)}")

    # 唱片公司
    labels = tags.get('label', [])
    if labels:
        lines.append(f"专辑唱片公司: {', '.join(labels)}")

    # 目录编号
    catalog_numbers = tags.get('catalognumber', [])
    if catalog_numbers:
        lines.append(f"编号: {', '.join(catalog_numbers)}")

    # 条码
    barcode = tags.get('barcode', '')
    if barcode:
        lines.append(f"条码: {barcode}")

    # ASIN
    asin = tags.get('asin', '')
    if asin:
        lines.append(f"ASIN: {asin}")

    # 媒体格式
    media = tags.get('media', '')
    if media:
        lines.append(f"媒体格式: {media}")

    # 流派/标签
    genres = tags.get('genre', [])
    if genres:
        lines.append(f"流派: {', '.join(genres)}")

    # ISRC
    isrcs = tags.get('isrc', [])
    if isrcs:
        lines.append(f"ISRC: {', '.join(isrcs)}")

    # 碟片子标题
    discsubtitle = tags.get('discsubtitle', '')
    if discsubtitle:
        lines.append(f"碟片标题: {discsubtitle}")

    # 备注
    recordingcomment = tags.get('recordingcomment', '')
    if recordingcomment:
        lines.append(f"备注: {recordingcomment}")

    # 相似度/得分信息
    score = tags.get('score', '')
    if score:
        lines.append(f"匹配得分: {score}")

    sources = tags.get('sources', '')
    if sources:
        lines.append(f"提交来源: {sources}")

    # 封面图片
    if show_cover:
        release_id = tags.get('musicbrainz_releaseid', '')
        if release_id:
            cover_url = get_cover_art_url(release_id)
            if cover_url:
                lines.append(f"\n封面图片: {cover_url}")

    # 备注
    lines.append("\n【备注】")
    lines.append("※ 封面图片来源于 Cover Art Archive (coverartarchive.org)")
    lines.append("※ 流派标签可能不完整，MusicBrainz 使用社区贡献的标签系统")
    lines.append("※ 更多详细信息请访问: https://musicbrainz.org/recording/" + recording.get('id', ''))

    lines.append("\n" + "=" * 80)

    return '\n'.join(lines)


def main():
    """
    自动匹配音乐文件并显示完整的标签信息（类似 Picard 原项目）

    用法:
        python fingerprint_matcher.py <audio_file_path> [fpcalc_path]

    示例:
        python fingerprint_matcher.py song.mp3
        python fingerprint_matcher.py song.flac /usr/local/bin/fpcalc
    """
    import sys

    if len(sys.argv) < 2:
        print("Usage: python fingerprint_matcher.py <audio_file_path> [fpcalc_path]")
        print("\n示例:")
        print("  python fingerprint_matcher.py song.mp3")
        print("  python fingerprint_matcher.py song.flac /usr/local/bin/fpcalc")
        sys.exit(1)

    audio_file = sys.argv[1]
    fpcalc_path = None

    # 解析命令行参数
    for arg in sys.argv[2:]:
        if not arg.startswith('--'):
            fpcalc_path = arg

    # 创建匹配器
    matcher = FingerprintMatcher(fpcalc_path=fpcalc_path)

    # 匹配文件
    result = matcher.match_file(audio_file)

    if not result.success:
        print(f"\n匹配失败: {result.error}")
        sys.exit(1)

    if not result.recordings:
        print("\n未找到任何匹配的录音信息")
        sys.exit(1)

    # 自动选择最佳匹配
    if not result.best_match:
        print("\n警告: 无法自动选择最佳匹配，使用第一个结果")
        best_recording = result.recordings[0]
    else:
        best_recording = result.best_match

    # 自动加载完整的 Release 信息以获取更完整的标签
    print("正在加载完整的 Release 信息...")
    full_release = matcher.load_full_release_for_best_match(best_recording)

    if full_release:
        print("✓ 完整 Release 信息加载成功\n")
    else:
        print("⚠ 完整 Release 信息加载失败，使用部分信息\n")

    # 显示完整的标签信息（与 Picard 原项目相同）
    print(format_complete_tags(best_recording, show_cover=False))

    # 显示调试信息（可选）
    if len(result.recordings) > 1:
        print(f"\n[调试信息] 共找到 {len(result.recordings)} 个候选结果，已自动选择最佳匹配")
        for i, recording in enumerate(result.recordings[:3], 1):  # 只显示前3个
            score = recording.get('score', 0)
            title = recording.get('title', '未知标题')
            print(f"  {i}. {title} (得分: {score})")


if __name__ == '__main__':
    main()
