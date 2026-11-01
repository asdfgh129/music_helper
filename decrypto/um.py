# -*- coding: utf-8 -*-
"""um（unlock-music CLI）封装 —— 三平台统一的离线解密通道

um 是纯 Go 程序（unlock-music CLI），同一份源码能编出 Windows / macOS 产物，
仓库按 Go 的命名约定一起放了三份，`config.UM_EXE` 按 `sys.platform` + 架构挑：

    Windows   tools/um.exe
    macOS     tools/um-darwin-arm64 / tools/um-darwin-amd64
    Linux     tools/um（自行编译，或装到 PATH）

本模块在 config 之上补三件事：

1. **开跑前校验能不能执行**：文件缺失、从 Windows 克隆后缺 `chmod +x`、
   拿错了平台的文件（Mach-O 给 Windows 或反之），都在这层拦住并给出具体命令，
   而不是等 subprocess 抛 `Exec format error`；
2. **新版 qmc 的凭据**：`.mflac/.mgg` 里 qmc2 / mflac1 这类要用 QQ 音乐客户端的
   mmkv 与 16 位密钥才能解开，这里负责找（配置优先，其次扫常见数据目录）；
3. **逐个文件调用**：um 处理目录时遇到一个解不开的文件会直接 FATAL 退出，
   整批都不处理；逐个调能把坏文件隔离出去，其余照常产出。

网易云 `.ncm` 不需要凭据，仍可以整目录一次调用（见 `run`）。
"""

import glob
import os
import subprocess
import sys

import config
import utils

# 缺凭据时给用户的提示：说明为什么需要、怎么补、以及在本平台到底该不该找
QMC_HINT = (
    '新版 qmc（mflac/mgg 里的 qmc2、mflac1 等）的密钥来自 QQ 音乐客户端的 mmkv 库：'
    'macOS 上是 ~/Library/Containers/com.tencent.QQMusicMac/Data/Library/'
    'Application Support/QQMusicMac/mmkv/MMKVStreamEncryptId；'
    'Windows 版客户端不产生这个文件，官方对 19.51 以上版本的说法是「提取方法未公开」，'
    '本项目的 Windows 通道走 Frida（tools/hook_qq_music.js）或改用 19.51 及以下版本下载。'
    '确实拿到 mmkv 且它被加密时（macOS 2023.09.03 之后的客户端会加密）才需要 '
    '--qmc-mmkv-key（16 位 ASCII，即 MMKV 库自身密码，无法自动获取）；'
    '配置项：[tools] qmc_mmkv / qmc_mmkv_key，或 MUSIC_HELPER_QMC_MMKV / MUSIC_HELPER_QMC_KEY'
)

# QQ 音乐客户端的常见数据目录（找不到就让用户显式指定，不做更深的猜测）
_MMKV_ROOTS = {
    'nt': [
        os.path.join(os.environ.get('APPDATA', ''), 'Tencent', 'QQMusic'),
        os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Tencent', 'QQMusic'),
    ],
    'darwin': [
        os.path.expanduser('~/Library/Containers/*/Data/Library/Application Support/QQMusic'),
        os.path.expanduser('~/Library/Application Support/QQMusic'),
        os.path.expanduser('~/Library/Group Containers/*/Library/Application Support/QQMusic'),
    ],
}

# 各平台值得自动去找的 mmkv 库文件名：
#   darwin  `MMKVStreamEncryptId` 存的就是歌曲 ekey，是唯一有价值的密钥库
#   nt      Windows 客户端不产生该文件，数据目录下的 mmkv.default 只是客户端自己的
#           配置库，硬塞给 um 只会得到 "key not found"，所以不做自动发现
_MMKV_PATTERNS = {
    'darwin': ('MMKVStreamEncryptId', 'mmkv*.default'),
    'nt': (),
}


def platform_label():
    return utils.platform_label()


def exe_path():
    """当前平台该用的 um 程序（配置 > tools/ 默认 > PATH）"""
    return utils.resolve_tool(config.UM_EXE, 'um')


def exe_problem():
    """um 在本机能否执行；可用返回空串，否则返回提示"""
    problem = utils.tool_problem(exe_path(), 'um（unlock-music CLI）')
    if problem and sys.platform == 'darwin':
        problem += ('；macOS 版可从源码编译（上游 GitHub 仓库因 DMCA 整站 451，'
                    '只能走国内 Go module 代理，proxy.golang.org 同样拿不到）：'
                    'GOPROXY=https://goproxy.cn CGO_ENABLED=0 GOOS=darwin GOARCH=arm64 '
                    'go install unlock-music.dev/cli/cmd/um@v0.2.12')
    return problem


def available():
    return not exe_problem()


def _platform_key():
    """查表用的平台键（Windows 用 nt，其余用 sys.platform）"""
    return 'nt' if os.name == 'nt' else sys.platform


def _search_roots():
    roots = _MMKV_ROOTS.get(_platform_key(), [])
    expanded = []
    for root in roots:
        if not root:
            continue
        expanded.extend(glob.glob(root) or [root])
    return [path for path in expanded if os.path.isdir(path)]


def find_mmkv(patterns=None):
    """在 QQ 音乐常见数据目录里找 mmkv 密钥库（需要同名 .crc 才算可用）

    只做一次浅层 glob：搜到的路径会在日志里打出来，用户看到不对就直接用
    `qmc_mmkv` 配置项覆盖，比猜一堆深层路径可靠。

    Windows 上直接返回空：那边客户端不写 `MMKVStreamEncryptId`，目录里的
    `mmkv.default` 是它自己的配置库，传给 um 只会得到 "key not found"。
    """
    if patterns is None:
        patterns = _MMKV_PATTERNS.get(_platform_key(), ())
    if not patterns:
        return ''
    for root in _search_roots():
        for pattern in patterns:
            for candidate in glob.glob(os.path.join(root, pattern), recursive=True):
                if os.path.isfile(candidate + '.crc'):
                    return candidate
    return ''


def qmc_credentials():
    """新版 qmc 需要的 (mmkv 路径, 密钥)

    配置（config.ini / 环境变量）优先；没配 mmkv 时才去扫描常见目录。
    密钥无法自动获取，只能由用户提供——它随账号下发，不落在文件里。
    """
    mmkv = str(getattr(config, 'QMC_MMKV', '') or '')
    key = str(getattr(config, 'QMC_MMKV_KEY', '') or '')
    if not mmkv:
        mmkv = find_mmkv()
    return mmkv, key


def build_command(exe, input_path, output_dir, mmkv='', key='', overwrite=False):
    """拼 um 的命令行

    `--remove-source` 不用：加密原文件的去向由 `core.ops.Plan` 统一管
    （`ENCRYPTED_SOURCE_MODE` 决定归还/回收站/保留），外部程序不许自己删。

    `--overwrite` 默认不加：目标已存在时 um 只打一行 `output file already exist, skip`
    然后正常退出（实测不会卡住等人输入），这样不会覆盖工作区里已经打好标签的同名文件。
    """
    cmd = [str(exe), '-i', str(input_path), '-o', str(output_dir)]
    if mmkv:
        cmd += ['--qmc-mmkv', str(mmkv)]
    if key:
        cmd += ['--qmc-mmkv-key', str(key)]
    if overwrite:
        cmd.append('--overwrite')
    return cmd


def _exec(cmd, logger=None):
    if logger:
        logger.info(f'执行命令: {" ".join(str(part) for part in cmd)}')
    try:
        completed = subprocess.run(
            [str(part) for part in cmd],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=config.SUBPROCESS_TIMEOUT,
            check=False,
        )
    except FileNotFoundError:
        return None, f'找不到可执行文件: {cmd[0]}'
    except subprocess.TimeoutExpired:
        return None, f'执行超时（>{config.SUBPROCESS_TIMEOUT}s）'
    except OSError as exc:
        return None, f'无法执行 {cmd[0]}：{exc}'
    if logger:
        if completed.stdout:
            logger.info(f'标准输出:\n{completed.stdout.strip()}')
        if completed.stderr:
            logger.warning(f'标准错误:\n{completed.stderr.strip()}')
    return completed, ''


def run(input_path, output_dir, mmkv=None, key=None, logger=None):
    """对单个文件或整个目录调一次 um

    凭据必须**成对**传：只给 `--qmc-mmkv` 不给密钥时，um 会去开 vault 并因
    「failed to load vault: failed to decode key: unexpected EOF」失败——连本来
    不需要凭据的旧版 qmc 也一起解不开（实测踩过）。所以只有一半时直接丢掉。

    Returns:
        (completed, error)：error 非空表示没能跑起来（缺程序、超时）
    """
    problem = exe_problem()
    if problem:
        return None, problem
    if mmkv is None and key is None:
        mmkv, key = qmc_credentials()
    mmkv, key = mmkv or '', key or ''
    if not (mmkv and key):
        mmkv, key = '', ''
    os.makedirs(output_dir, exist_ok=True)
    cmd = build_command(exe_path(), input_path, output_dir, mmkv, key)
    return _exec(cmd, logger)


def failure_detail(completed):
    """从 um 的输出里挑一行最有信息量的错误（优先 FATAL 行）"""
    if completed is None:
        return ''
    lines = []
    for stream in (completed.stderr or '', completed.stdout or ''):
        lines.extend(line.strip() for line in stream.splitlines() if line.strip())
    for line in reversed(lines):
        if 'FATAL' in line:
            return line
    for line in reversed(lines):
        if 'error' in line.lower():
            return line
    return lines[-1] if lines else ''
