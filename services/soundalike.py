# -*- coding: utf-8 -*-
"""声纹去重服务 - 包装外部 soundalike 工具"""

import os
import subprocess
from dataclasses import dataclass

import config


@dataclass
class ToolResult:
    ok: bool
    returncode: int = None
    message: str = ''

    def summary(self):
        state = '成功' if self.ok else '失败'
        code = '' if self.returncode is None else f'（返回码 {self.returncode}）'
        return f'{state}{code} {self.message}'.strip()


def _exec(cmd):
    if not os.path.exists(cmd[0]) and os.sep in cmd[0]:
        return None, f'找不到外部程序: {cmd[0]}'
    try:
        return subprocess.run(
            [str(part) for part in cmd],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=config.SUBPROCESS_TIMEOUT,
            check=False,
        ), ''
    except FileNotFoundError:
        return None, f'找不到外部程序: {cmd[0]}'
    except subprocess.TimeoutExpired:
        return None, f'执行超时（>{config.SUBPROCESS_TIMEOUT}s）'


def run(debug=False, with_temp=True):
    """运行声纹去重并更新数据库

    Args:
        debug: 开启外部程序的秒级日志
        with_temp: 是否把临时目录也纳入去重范围
    """
    cmd = [config.SOUNDALIKE_EXE, '-move-interactive', config.TEMP_MOVE_DIR]
    if with_temp:
        cmd += ['-temp', config.TEMP_COMPLETED_DIR]
    cmd.append(config.MAIN_DIR)
    if debug:
        cmd.append('-log-sec=1')

    completed, error = _exec(cmd)
    if error:
        return ToolResult(False, None, error)
    return ToolResult(completed.returncode == 0, completed.returncode, '')


def check(main_dir=None):
    """检查 soundalike 数据库与目录文件的一致性"""
    completed, error = _exec([config.SOUNDALIKE_EXE, '-check', main_dir or config.MAIN_DIR])
    if error:
        return ToolResult(False, None, error)
    return ToolResult(completed.returncode == 0, completed.returncode, '')
