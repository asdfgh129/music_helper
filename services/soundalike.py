# -*- coding: utf-8 -*-
"""声纹去重服务 - 包装外部 soundalike 工具

soundalike 的真实参数（从 0.1.4 二进制字符串确认）：
    -db <file>               声纹库；不传时在 CWD 生成临时库
    -check -db <file>        校验库与文件系统一致性
    -move-interactive <dir>  交互式把重复文件移到该目录（不能等于 -temp 或音乐目录）
    -temp <dir>              只扫描、不写库的工作区
    -log-sec=1               秒级日志

因此本模块固定用 `-db config.DB_PATH`，并把 CWD 设到库文件所在目录，避免
「库建在哪个目录取决于启动位置」的老问题。库不存在时 soundalike 会自动建库并
索引 LIBRARY_DIR，这就是首次初始化。
"""

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


def _db_dir():
    return os.path.dirname(os.path.abspath(config.DB_PATH)) or config.PROJECT_DIR


def _exec(cmd, cwd=None):
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
            cwd=cwd,
        ), ''
    except FileNotFoundError:
        return None, f'找不到外部程序: {cmd[0]}'
    except subprocess.TimeoutExpired:
        return None, f'执行超时（>{config.SUBPROCESS_TIMEOUT}s）'
    except OSError as exc:
        return None, f'无法执行外部程序: {cmd[0]}（{exc}）'


def db_exists():
    return os.path.isfile(config.DB_PATH)


def run(debug=False, with_temp=True):
    """运行声纹去重并更新数据库

    Args:
        debug: 开启外部程序的秒级日志
        with_temp: 是否把工作区也纳入去重范围
    """
    cmd = [
        config.SOUNDALIKE_EXE,
        '-db', config.DB_PATH,
        '-move-interactive', config.DUPLICATE_DIR,
    ]
    if with_temp:
        cmd += ['-temp', config.WORKSPACE_DIR]
    cmd.append(config.LIBRARY_DIR)
    if debug:
        cmd.append('-log-sec=1')

    completed, error = _exec(cmd, cwd=_db_dir())
    if error:
        return ToolResult(False, None, error)
    return ToolResult(completed.returncode == 0, completed.returncode, '')


def check(main_dir=None):
    """检查 soundalike 数据库与目录文件的一致性"""
    cmd = [config.SOUNDALIKE_EXE, '-check', '-db', config.DB_PATH, main_dir or config.LIBRARY_DIR]
    completed, error = _exec(cmd, cwd=_db_dir())
    if error:
        return ToolResult(False, None, error)
    return ToolResult(completed.returncode == 0, completed.returncode, '')
