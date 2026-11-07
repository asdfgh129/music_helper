# -*- coding: utf-8 -*-
"""繁体 → 简体转换

MusicBrainz 的曲目记录里混有繁体中文（港台发行版），直接写进标签会让同一首歌
出现两种写法。这里在 HTTP 响应解析后统一转一次简体，后续匹配与写盘都拿简体。

依赖 OpenCC；缺失时只降级转换能力并告警，不影响匹配本身。
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    import opencc
    OPENCC_CONVERTER = opencc.OpenCC('t2s')  # 繁体转简体
    HAS_OPENCC = True
    logger.info("OpenCC loaded successfully for Traditional/Simplified Chinese conversion")
except (ImportError, OSError):
    OPENCC_CONVERTER = None
    HAS_OPENCC = False
    logger.warning(
        "OpenCC not available. Traditional Chinese text will not be converted to Simplified Chinese. "
        "To enable complete conversion, install opencc: pip install opencc"
    )


def traditional_to_simplified(text: str) -> str:
    """将繁体中文转换为简体中文（OpenCC 覆盖全部汉字）"""
    if not text or not isinstance(text, str):
        return text

    if not HAS_OPENCC or OPENCC_CONVERTER is None:
        raise ImportError(
            "OpenCC is not available. Please install it with: pip install opencc"
        )

    try:
        return OPENCC_CONVERTER.convert(text)
    except Exception as e:  # noqa: BLE001 - 转换失败时原样返回，不让一次异常毁掉整次查询
        logger.error(f"Failed to convert Traditional Chinese to Simplified: {e}")
        return text


def convert_dict_to_simplified(data: Any) -> Any:
    """递归把字典/列表里的繁体中文字符串转成简体"""
    if isinstance(data, dict):
        return {convert_dict_to_simplified(k): convert_dict_to_simplified(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [convert_dict_to_simplified(item) for item in data]
    elif isinstance(data, str):
        return traditional_to_simplified(data)
    else:
        return data
