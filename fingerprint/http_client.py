# -*- coding: utf-8 -*-
"""AcoustID / MusicBrainz 的 HTTP 客户端

用标准库 `urllib` 而不是 requests：这条链路的调用频率低（一首一次），
没必要为它引入额外依赖，也让 fingerprint 包能独立于 `requirements.txt` 运行。

两个细节：
- SSL 上下文默认**不校验证书**（`_create_unverified_context`）。这是 macOS 上
  Python 缺少根证书导致 AcoustID 查询失败的兼容处理，不是疏忽。
- 响应解析后立刻做繁简转换（`convert_dict_to_simplified`），保证下游拿到的
  标题/艺术家已经是简体——转一次比在每个使用点转更不容易漏。
"""

import json
import logging
import ssl
import time
from typing import Any, Dict, Optional, Union
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import AcoustIDConfig
from .textconv import convert_dict_to_simplified

logger = logging.getLogger(__name__)

# macOS SSL 证书修复：创建默认的 SSL 上下文以避免证书验证失败
_ssl_context = None
try:
    _ssl_context = ssl._create_unverified_context()
except Exception:  # noqa: BLE001
    pass


class HTTPClient:
    """带错误归一化的极简 HTTP 客户端

    所有失败都收敛成 `(None, 错误串)`，调用方只需要判 `error`，
    不必关心是 DNS、超时还是 JSON 解析失败。
    """

    def __init__(self, user_agent: Optional[str] = None, debug_mode: bool = False):
        self.user_agent = user_agent or f'Picard-FingerprintMatcher/{AcoustIDConfig.DEFAULT_CLIENT_VERSION}'
        self.debug_mode = debug_mode
        if debug_mode:
            logger.debug("HTTPClient 初始化")
            logger.debug(f"  user_agent = {self.user_agent}")

    def post(self, url: str, data: Union[Dict[str, Any], str],
             headers: Optional[Dict[str, str]] = None) -> tuple[Optional[dict], Optional[str]]:
        """发送 POST 请求，返回 (解析后的 JSON, 错误串)"""
        if self.debug_mode:
            logger.debug("=" * 60)
            logger.debug("HTTPClient.post 开始")
            logger.debug("=" * 60)
            logger.debug("method = POST")
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

        # 字典走 urlencode；字符串视为已编码的请求体（AcoustID 要求手动编码）
        if isinstance(data, dict):
            encoded_data = urlencode(data).encode('utf-8')
        else:
            encoded_data = data.encode('utf-8')

        if self.debug_mode:
            logger.debug(f"encoded_data length = {len(encoded_data)} bytes")

        request = Request(url, data=encoded_data, headers=all_headers, method='POST')

        try:
            start_time = time.time() if self.debug_mode else None
            if self.debug_mode:
                logger.debug("发送请求...")

            with urlopen(request, timeout=30, context=_ssl_context) as response:
                content = response.read().decode('utf-8')

                if self.debug_mode:
                    logger.debug(f"响应 received in {time.time() - start_time:.3f}s")
                    logger.debug(f"status code = {response.status}")
                    logger.debug(f"content length = {len(content)} chars")

                converted_json = convert_dict_to_simplified(json.loads(content))

                if self.debug_mode:
                    logger.debug("JSON 解析成功")

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
        except Exception as e:  # noqa: BLE001
            error_msg = f"Unexpected error: {e}"
            if self.debug_mode:
                logger.debug(f"Unexpected error: {e}")
            return None, error_msg

    def get(self, url: str, params: Optional[Dict[str, Any]] = None) -> tuple[Optional[dict], Optional[str]]:
        """发送 GET 请求，返回 (解析后的 JSON, 错误串)"""
        if self.debug_mode:
            logger.debug("=" * 60)
            logger.debug("HTTPClient.get 开始")
            logger.debug("=" * 60)
            logger.debug("method = GET")
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
            start_time = time.time() if self.debug_mode else None
            if self.debug_mode:
                logger.debug("发送请求...")

            with urlopen(request, timeout=30, context=_ssl_context) as response:
                content = response.read().decode('utf-8')

                if self.debug_mode:
                    logger.debug(f"响应 received in {time.time() - start_time:.3f}s")
                    logger.debug(f"status code = {response.status}")
                    logger.debug(f"content length = {len(content)} chars")

                converted_json = convert_dict_to_simplified(json.loads(content))

                if self.debug_mode:
                    logger.debug("JSON 解析成功")

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
        except Exception as e:  # noqa: BLE001
            error_msg = f"Unexpected error: {e}"
            if self.debug_mode:
                logger.debug(f"Unexpected error: {e}")
            return None, error_msg
