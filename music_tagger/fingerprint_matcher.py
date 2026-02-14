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
from typing import Optional, Dict, List, Callable, Any
from urllib.parse import urlencode
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


class AcoustIDConfig:
    """AcoustID配置常量"""
    ACOUSTID_KEY = 'v8pQ6oyB'
    ACOUSTID_URL = 'https://api.acoustid.org/v2'
    MUSICBRAINZ_URL = 'https://musicbrainz.org/ws/2'
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
    def __init__(self, success: bool, recordings: Optional[List[Dict]] = None, error: Optional[str] = None):
        self.success = success
        self.recordings = recordings or []
        self.error = error


class HTTPClient:
    """简单的HTTP客户端"""
    
    def __init__(self, user_agent: Optional[str] = None):
        self.user_agent = user_agent or f'Picard-FingerprintMatcher/{AcoustIDConfig.DEFAULT_CLIENT_VERSION}'
    
    def post(self, url: str, data: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> tuple[Optional[dict], Optional[str]]:
        """发送POST请求"""
        all_headers = {
            'User-Agent': self.user_agent,
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json',
        }
        if headers:
            all_headers.update(headers)
        
        encoded_data = urlencode(data).encode('utf-8')
        request = Request(url, data=encoded_data, headers=all_headers, method='POST')
        
        try:
            with urlopen(request, timeout=30) as response:
                content = response.read().decode('utf-8')
                return json.loads(content), None
        except HTTPError as e:
            error_msg = f"HTTP Error {e.code}: {e.reason}"
            return None, error_msg
        except URLError as e:
            error_msg = f"URL Error: {e.reason}"
            return None, error_msg
        except json.JSONDecodeError as e:
            error_msg = f"JSON Decode Error: {e}"
            return None, error_msg
        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            return None, error_msg
    
    def get(self, url: str, params: Optional[Dict[str, Any]] = None) -> tuple[Optional[dict], Optional[str]]:
        """发送GET请求"""
        if params:
            url = f"{url}?{urlencode(params)}"
        
        headers = {
            'User-Agent': self.user_agent,
            'Accept': 'application/json',
        }
        request = Request(url, headers=headers)
        
        try:
            with urlopen(request, timeout=30) as response:
                content = response.read().decode('utf-8')
                return json.loads(content), None
        except HTTPError as e:
            error_msg = f"HTTP Error {e.code}: {e.reason}"
            return None, error_msg
        except URLError as e:
            error_msg = f"URL Error: {e.reason}"
            return None, error_msg
        except json.JSONDecodeError as e:
            error_msg = f"JSON Decode Error: {e}"
            return None, error_msg
        except Exception as e:
            error_msg = f"Unexpected error: {e}"
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
        
        try:
            result = subprocess.run(
                [self.fpcalc_path, '-json', '-length', '120', audio_file_path],
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
        return {
            'name': artist['name'],
            'sort-name': artist['name'],
            'id': artist['id'],
        }
    
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
    
    def __init__(self, http_client: HTTPClient):
        self.http_client = http_client
        self.recording_cache = {}
        self.missing_metadata = []
    
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
        results = doc.get('results') or []
        recording_map = {}
        incomplete_counts = {}
        
        for result in results:
            recordings = result.get('recordings') or []
            result_score = self._get_score(result)
            acoustid = result.get('id')
            max_sources = self._max_source_count_raw(recordings)
            
            for recording in sorted(recordings, key=lambda r: r.get('sources', 1), reverse=True):
                mbid = recording.get('id')
                sources = recording.get('sources', 1)
                
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
                # 从MusicBrainz API获取
                url = f"{AcoustIDConfig.MUSICBRAINZ_URL}/recording/{mbid}"
                params = {'inc': 'artists+release-groups+releases+media'}
                
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


class AcoustIDClient:
    """AcoustID客户端 - 主要的指纹匹配客户端"""
    
    def __init__(self, client_version: Optional[str] = None):
        self.http_client = HTTPClient()
        self.client_key = AcoustIDConfig.ACOUSTID_KEY
        self.client_version = client_version or AcoustIDConfig.DEFAULT_CLIENT_VERSION
        self.resolver = RecordingResolver(self.http_client)
    
    def _encode_acoustid_args(self, args: Dict[str, Any]) -> str:
        """编码AcoustID请求参数"""
        args['client'] = self.client_key
        args['clientversion'] = self.client_version
        args['format'] = 'json'
        return urlencode(args)
    
    def query_acoustid(self, fingerprint: str, duration: int) -> tuple[Optional[dict], Optional[str]]:
        """使用指纹查询AcoustID"""
        params = {
            'fingerprint': fingerprint,
            'duration': str(duration),
            'meta': 'recordings releasegroups releases tracks compress sources',
        }

        url = f"{AcoustIDConfig.ACOUSTID_URL}/lookup"

        logger.info(f"Querying AcoustID with fingerprint ({len(fingerprint)} chars, {duration}s)")
        document, error = self.http_client.post(url, params)

        if error or document is None:
            logger.error(f"AcoustID query error: {error}")
            return None, error

        status = document.get('status')
        if status != 'ok':
            error_msg = document.get('error', {}).get('message', 'Unknown error')
            logger.error(f"AcoustID API error: {error_msg}")
            return None, error_msg

        logger.info(f"AcoustID returned {len(document.get('results', []))} results")
        return document, None
    
    def match_fingerprint(self, fingerprint: str, duration: int) -> MatchResult:
        """匹配指纹并返回录音信息"""
        document, error = self.query_acoustid(fingerprint, duration)

        if error or document is None:
            return MatchResult(success=False, recordings=[], error=error or "Unknown error")

        # 解析录音信息
        try:
            recordings = self.resolver.resolve(document)
            logger.info(f"Resolved {len(recordings)} recordings")
            return MatchResult(success=True, recordings=recordings)
        except Exception as e:
            error_msg = f"Failed to resolve recordings: {e}"
            logger.error(error_msg)
            return MatchResult(success=False, recordings=[], error=error_msg)


class FingerprintMatcher:
    """指纹匹配器 - 整合所有功能的主类"""
    
    def __init__(self, fpcalc_path: Optional[str] = None, client_version: Optional[str] = None):
        self.calculator = FingerprintCalculator(fpcalc_path)
        self.acoustid_client = AcoustIDClient(client_version)
    
    def match_file(self, audio_file_path: str) -> MatchResult:
        """匹配音频文件"""
        logger.info(f"Processing file: {audio_file_path}")
        
        # 计算指纹
        fingerprint_result = self.calculator.calculate(audio_file_path)
        
        if not fingerprint_result.success:
            return MatchResult(
                success=False,
                recordings=[],
                error="Failed to calculate fingerprint"
            )
        
        # 查询匹配
        return self.acoustid_client.match_fingerprint(
            fingerprint_result.fingerprint,
            fingerprint_result.duration
        )
    
    def match_from_fingerprint(self, fingerprint: str, duration: int) -> MatchResult:
        """从已有指纹匹配"""
        logger.info(f"Matching from existing fingerprint ({len(fingerprint)} chars, {duration}s)")
        return self.acoustid_client.match_fingerprint(fingerprint, duration)


def format_recording_info(recording: dict) -> str:
    """格式化录音信息用于显示"""
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
    info += f"Match Score: {score:.1f}%\n"
    info += f"Sources: {sources}\n"
    info += f"AcoustID: {acoustid}\n"
    info += f"MusicBrainz ID: {mbid}\n"
    
    releases = recording.get('releases', [])
    if releases:
        info += f"Releases ({len(releases)}):\n"
        for release in releases[:3]:  # 只显示前3个发行
            info += f"  - {release.get('title', 'Unknown')} ({release.get('date', 'N/A')})\n"
    
    info += f"{'='*60}"
    return info


def main():
    """示例用法"""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python fingerprint_matcher.py <audio_file_path> [fpcalc_path]")
        print("\n示例:")
        print("  python fingerprint_matcher.py song.mp3")
        print("  python fingerprint_matcher.py song.flac /usr/local/bin/fpcalc")
        sys.exit(1)
    
    audio_file = sys.argv[1]
    fpcalc_path = sys.argv[2] if len(sys.argv) > 2 else None
    
    # 创建匹配器
    matcher = FingerprintMatcher(fpcalc_path=fpcalc_path)
    
    # 匹配文件
    result = matcher.match_file(audio_file)
    
    if result.success:
        print(f"\n成功! 找到 {len(result.recordings)} 个匹配结果:")
        for i, recording in enumerate(result.recordings, 1):
            print(f"\n结果 #{i}:")
            print(format_recording_info(recording))
    else:
        print(f"\n匹配失败: {result.error}")
        sys.exit(1)


if __name__ == '__main__':
    main()
