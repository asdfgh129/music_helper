# -*- coding: utf-8 -*-
"""声纹去重服务 - 包装外部 soundalike 工具

soundalike 的真实参数（从二进制 `-h` 输出确认）：
    -db <file>               声纹库；不传时在 CWD 生成临时库
    -check -db <file>        校验库与文件系统一致性
    -move-interactive <dir>  把重复文件移到该目录；音质能分出高下时不询问，
                             音质相同（同格式同码率）才要求人工挑一个保留
    -temp <dir>              只扫描、不写库的工作区
    -fpcalc-length <sec>     指纹采样长度，必须与 config.FPCALC_LENGTH 一致
    -file-regexp <re>        哪些扩展名参与扫描；不传时用 soundalike 内置的
                             (aiff|flac|m4a|mp3|oga|ogg|opus|wav|wma|ape)，不含 dsf
    -dry-run                 只打印「将移动谁」，不动文件、不改库
    -log-sec=1               秒级日志

因此本模块固定用 `-db config.DB_PATH`，并把 CWD 设到库文件所在目录，避免
「库建在哪个目录取决于启动位置」的老问题。库不存在时 soundalike 会自动建库并
索引 LIBRARY_DIR，这就是首次初始化。

三种运行方式：
    run()     带 `-move-interactive`，按音质取舍：差的自动移走，音质相同才问
    report()  不带移动参数，只列出候选组，不动任何音频文件（`--soundalike-report`）
    dry_run=True 时再叠 `-dry-run`，连自动移走的那部分也只打印不执行

`-fpcalc-length` 必须显式传入：声纹库会把指纹参数写进 Settings 表，两边不一致时
soundalike 直接拒绝打开库；改 `FPCALC_LENGTH` 等于换了一套指纹，必须重建库。

平台：程序由 `config.SOUNDALIKE_EXE` 按 `sys.platform` + 架构挑（Windows 是
`soundalike.exe`，macOS 是 `soundalike-darwin-<arch>`），配置路径不存在时再在 `PATH`
里找同名程序。开跑前用 `utils.tool_problem()` 校验「这份产物在本机能不能跑」，
缺文件、缺 `chmod +x`、拿错平台的产物都在这里直接报出来，而不是等 subprocess 抛异常。
"""

import os
import sqlite3
import subprocess
import sys
from dataclasses import dataclass

import config
import utils

# soundalike 认得、但流水线不处理的格式：只参与声纹比对，不影响其他步骤。
# 与 config.AUDIO_EXTENSIONS 取并集传给 `-file-regexp`，否则这些文件连指纹都不会算。
_EXTRA_SCAN_EXTENSIONS = ('.aif', '.aiff', '.aifc', '.oga', '.dff', '.wv', '.tta', '.tak')


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


def exe_path():
    """当前平台该用的 soundalike：配置路径 > PATH 里的同名程序

    config.SOUNDALIKE_EXE 已按平台挑好（Windows `soundalike.exe`、macOS
    `soundalike-darwin-<arch>`），这里再兜一层 PATH，方便 Linux 上用
    `go build -o ~/bin/soundalike` 那类方案。
    """
    return utils.resolve_tool(config.SOUNDALIKE_EXE, 'soundalike')


def exe_problem():
    """soundalike 在本机能否执行；可用返回空串，否则返回提示"""
    return utils.tool_problem(exe_path(), '声纹工具 soundalike')


def platform_info():
    """当前平台与选中的程序（--debug / 排错时打日志用）"""
    return f'{utils.platform_label()} / {exe_path()}'


def _env():
    """让外部程序能找到 tools/ 里的 fpcalc

    soundalike 只按 PATH 查 fpcalc，不读配置。macOS 上 fpcalc 随仓库放在
    tools/，不注入 PATH 就会报 `fpcalc not in path`。
    """
    env = dict(os.environ)
    tools_dir = getattr(config, 'TOOLS_DIR', '')
    if tools_dir and os.path.isdir(tools_dir):
        parts = [part for part in env.get('PATH', '').split(os.pathsep) if part]
        if os.path.normcase(tools_dir) not in {os.path.normcase(part) for part in parts}:
            env['PATH'] = os.pathsep.join([tools_dir] + parts)
    return env


def _exec(cmd, cwd=None, capture=True):
    """执行外部程序

    Args:
        capture: False 时把 stdout/stderr 直接交给当前终端。交互式运行时必须
                 这样——soundalike 的提示语不打换行，一旦被管道捕获，用户只会
                 看到一个「卡住」的进程。
    """
    if not os.path.exists(cmd[0]) and os.sep in cmd[0]:
        return None, f'找不到外部程序: {cmd[0]}'
    kwargs = {'capture_output': True} if capture else {'stdout': None, 'stderr': None}
    try:
        return subprocess.run(
            [str(part) for part in cmd],
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=config.SUBPROCESS_TIMEOUT,
            check=False,
            cwd=cwd,
            env=_env(),
            **kwargs,
        ), ''
    except FileNotFoundError:
        return None, f'找不到外部程序: {cmd[0]}'
    except subprocess.TimeoutExpired:
        return None, f'执行超时（>{config.SUBPROCESS_TIMEOUT}s）'
    except OSError as exc:
        return None, f'无法执行外部程序: {cmd[0]}（{exc}）'


def db_exists():
    return os.path.isfile(config.DB_PATH)


def db_fpcalc_length():
    """读声纹库 Settings 里记录的指纹采样长度；库不存在或读不到返回 None

    库把 `-fpcalc-length` 写进 Settings 表，参数与库不一致时 soundalike 会
    拒绝打开。这里先读出来，好在开跑前给出能照着做的提示，而不是一个返回码 1。
    只读打开，不会像 `sqlite3.connect` 那样顺手建出一个空库。
    """
    if not db_exists():
        return None
    connection = None
    row = None
    try:
        uri = 'file:' + str(config.DB_PATH).replace('\\', '/') + '?mode=ro'
        connection = sqlite3.connect(uri, uri=True)
        row = connection.execute('SELECT Desc FROM Settings').fetchone()
    except (sqlite3.Error, OSError):
        return None
    finally:
        # 必须显式 close：Windows 上有打开的句柄会挡住外部程序建库/删库
        if connection is not None:
            connection.close()
    if not row or not row[0]:
        return None
    for part in str(row[0]).split(','):
        key, _, value = part.partition('=')
        if key.strip() == 'length':
            try:
                return float(value)
            except ValueError:
                return None
    return None


def settings_problem():
    """声纹库与 config.FPCALC_LENGTH 是否冲突；冲突时返回提示文本"""
    length = db_fpcalc_length()
    if length is None:
        return ''
    wanted = float(config.FPCALC_LENGTH)
    if abs(length - wanted) < 0.001:
        return ''
    return (f'声纹库的指纹长度是 {length:g} 秒，与 fpcalc_length={wanted:g} 不一致；'
            f'soundalike 会拒绝打开该库。删掉 {config.DB_PATH} 重新 --init，'
            f'或把 config.ini 的 fpcalc_length 改成 {length:g}')


def same_volume(first, second):
    """两个目录是否在同一个卷上

    soundalike 的 `-temp` 用「第一个音乐目录」推算相对路径，跨盘时
    filepath.Rel 直接报错，整次扫描以失败结束。这里先判断，避免跑到一半才炸。
    """
    drive_a = os.path.splitdrive(os.path.abspath(first))[0]
    drive_b = os.path.splitdrive(os.path.abspath(second))[0]
    return os.path.normcase(drive_a) == os.path.normcase(drive_b)


def temp_supported():
    """工作区能否参与声纹比对（要求与 LIBRARY_DIR 同盘）"""
    return same_volume(config.WORKSPACE_DIR, config.LIBRARY_DIR)


def file_regexp():
    """参与声纹扫描的扩展名正则（soundalike `-file-regexp` 用）

    soundalike 内置的正则不含 `.dsf`/`.dff`，而 DSD 恰恰是「不同音质同一首歌」
    里最该留下的一份；不显式传就可能整类文件都不参与比对。
    """
    extensions = {str(ext).lstrip('.').lower() for ext in config.AUDIO_EXTENSIONS}
    extensions |= {ext.lstrip('.') for ext in _EXTRA_SCAN_EXTENSIONS}
    return r'(?i)\.(' + '|'.join(sorted(extensions)) + ')$'


def build_command(with_temp=True, interactive=True, debug=False, dry_run=False):
    cmd = [
        exe_path(),
        '-db', config.DB_PATH,
        '-fpcalc-length', str(config.FPCALC_LENGTH),
        '-file-regexp', file_regexp(),
    ]
    if interactive:
        cmd += ['-move-interactive', config.DUPLICATE_DIR]
    if dry_run:
        cmd.append('-dry-run')
    if with_temp:
        cmd += ['-temp', config.WORKSPACE_DIR]
    cmd.append(config.LIBRARY_DIR)
    if debug:
        cmd.append('-log-sec=1')
    return cmd


def run(debug=False, with_temp=True, dry_run=False):
    """运行声纹去重并更新数据库（按音质取舍重复文件）

    音质能分出高下时（不同格式层级，或同格式码率差 ≥2%），较差的那份直接移入
    DUPLICATE_DIR，不询问；只有音质完全相同才让人挑一个保留，非交互运行下则一个
    都不动，避免随机删。

    Args:
        debug: 开启外部程序的秒级日志
        with_temp: 是否把工作区也纳入去重范围
        dry_run: 只打印计划，不移动文件、不改库
    """
    problem = exe_problem()
    if problem:
        return ToolResult(False, None, problem)
    problem = settings_problem()
    if problem:
        return ToolResult(False, None, problem)
    # 试运行时 soundalike 不会再问「保留哪个」，所以可以捕获输出再记日志；
    # 正式运行必须把终端让给它，否则提示语被管道吞掉，用户只看到进程卡住。
    interactive = sys.stdin is not None and sys.stdin.isatty()
    cmd = build_command(with_temp=with_temp, interactive=True, debug=debug, dry_run=dry_run)
    completed, error = _exec(cmd, cwd=_db_dir(), capture=not interactive)
    if error:
        return ToolResult(False, None, error)
    if dry_run and completed.stdout:
        for line in completed.stdout.splitlines():
            if line.strip():
                print(line)
    return ToolResult(completed.returncode == 0, completed.returncode, '')


def report(debug=False, with_temp=True):
    """只列候选组：不移动文件，也不写声纹库（等同 `--soundalike --dry-run`）

    以前这里跑的是「正经扫描、只是不带移动参数」，副作用是把指纹写进库；
    下一轮正式运行时这些文件被当成「已经处理过」，重复就再也报不出来。
    现在统一走试运行：能复用库里已有指纹，但一份都不写。
    """
    return run(debug=debug, with_temp=with_temp, dry_run=True)


def check(main_dir=None):
    """检查 soundalike 数据库与目录文件的一致性"""
    problem = exe_problem()
    if problem:
        return ToolResult(False, None, problem)
    problem = settings_problem()
    if problem:
        return ToolResult(False, None, problem)
    cmd = [exe_path(), '-check', '-db', config.DB_PATH, main_dir or config.LIBRARY_DIR]
    completed, error = _exec(cmd, cwd=_db_dir())
    if error:
        return ToolResult(False, None, error)
    return ToolResult(completed.returncode == 0, completed.returncode, '')
