# -*- coding: utf-8 -*-
"""调用 fpcalc 计算音频指纹

fpcalc 是 Chromaprint 的命令行工具，输出 JSON：`{"duration": 秒, "fingerprint": 串}`。
本模块只负责「路径 → (指纹, 时长)」，查库与打分在 `acoustid`。

`-length` 用 `config.FPCALC_LENGTH`（默认 120 秒），**这个值必须与 AcoustID 侧
建库时一致**，否则同一首歌算出来的指纹对不上，表现为「明明有这张专辑却查不到」。
"""

import json
import logging
import os
import shutil
import subprocess
import sys
from typing import Optional

from .models import AcoustIDConfig, FingerprintResult

logger = logging.getLogger(__name__)

# 允许作为脚本或包导入两种方式下都能找到项目根目录的 config.py；
# 冻结后 config 已在 PYZ 里，__file__ 也不是项目根，不需要再插路径
if not getattr(sys, 'frozen', False):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from config import FPCALC_LENGTH
except ImportError:
    FPCALC_LENGTH = 120
    logging.warning(f"无法从 config 导入 FPCALC_LENGTH，使用默认值: {FPCALC_LENGTH}")


class FingerprintCalculator:
    """指纹计算器——找 fpcalc、跑它、解它的 JSON"""

    def __init__(self, fpcalc_path: Optional[str] = None):
        self.fpcalc_path = fpcalc_path or self._find_fpcalc()

    def _find_fpcalc(self) -> Optional[str]:
        """在 PATH 里找 fpcalc；找不到返回 None，由调用方降级"""
        for name in AcoustIDConfig.FPCALC_NAMES:
            path = shutil.which(name)
            if path:
                logger.info(f"Found fpcalc: {path}")
                return path
        return None

    def calculate(self, audio_file_path: str) -> FingerprintResult:
        """计算音频文件的指纹；任何失败都返回 success=False 而不是抛异常"""
        if not self.fpcalc_path:
            return FingerprintResult('', 0, success=False)

        logger.info(f"使用指纹长度: {FPCALC_LENGTH} 秒")

        try:
            result = subprocess.run(
                [self.fpcalc_path, '-json', '-length', str(FPCALC_LENGTH), audio_file_path],
                capture_output=True,
                text=True,
                timeout=60
            )

            # 3 = 解码有警告但仍有指纹，这种情况照常使用
            if result.returncode == 0 or result.returncode == 3:
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
        except Exception as e:  # noqa: BLE001
            logger.error(f"fpcalc error: {e}")
            return FingerprintResult('', 0, success=False)
