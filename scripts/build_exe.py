# -*- coding: utf-8 -*-
"""把项目打成免 Python 环境的绿色可执行包，产物固定在仓库的 ``dist/``。

用法（在项目根目录，构建机需要 Python 3.11+）：
    python scripts/build_exe.py                # 完整打包 + 产物自检
    python scripts/build_exe.py --all-tools    # 附带 tools/ 全部平台二进制（默认只带本机平台）
    python scripts/build_exe.py --skip-verify  # 跳过启动自检
    python scripts/build_exe.py --no-install   # 缺 PyInstaller 时不要自动安装
Windows 上可直接双击根目录的 ``build_exe.bat``。

重复打包采用覆盖写入：``dist/config.ini`` 与 ``dist/log/`` 属于用户数据，永不删除；
PyInstaller 每次在 ``build/pyinstaller/runs/<时间戳>_<pid>/`` 下的全新目录构建，
避免它删除旧输出目录（会被批量删除保护拦下），中间产物保留以便排查，可手动清理。

**为什么不是单文件**：frida 要加载随包分发的 DLL，onedir 启动更快也更不容易被
杀软误判；``tools/``、``web/``、``config.ini``、``log/`` 都放在 exe 旁边，
由 ``runtime_paths.project_dir()`` 把它们定位到 exe 所在目录（dist/）。

dist/ 布局：

    dist/
    ├── music_helper.exe        CLI 主程序（--web 也是它）
    ├── _internal/              Python 运行时 + 全部第三方 Python 依赖
    ├── tools/                  外部程序（um / soundalike / fpcalc / Frida hook / QQ 安装包）
    ├── web/                    Web 八步向导的 index.html + static/
    ├── log/                    日志、报告、journal、回收站
    ├── config.ini / config.example.ini
    ├── 使用说明.txt / 使用文档.html / LICENSE
    ├── 启动Web向导.bat / 命令行.bat
    └── 打包清单.txt

脚本只依赖标准库 + 构建期的 PyInstaller；产物运行时不需要 Python。
"""

import argparse
import importlib.util
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / 'dist'
BUILD = ROOT / 'build' / 'pyinstaller'
# PyInstaller 的 COLLECT 在输出目录已存在时会整目录删除（上百个文件），
# 既慢又容易被批量删除保护拦下。每次构建用全新的运行目录，永不复用。
RUN_TAG = datetime.now().strftime('%Y%m%d_%H%M%S') + f'_{os.getpid()}'
RUN_DIR = BUILD / 'runs' / RUN_TAG
PYI_DIST = RUN_DIR / 'dist' / 'music_helper'
EXE_NAME = 'music_helper.exe' if os.name == 'nt' else 'music_helper'

# 运行期真正会 import 的第三方包（缺一个打包出来的 exe 就会缺功能）
REQUIRED_MODULES = ('requests', 'mutagen', 'Cryptodome', 'frida',
                    'fastapi', 'uvicorn', 'pydantic', 'certifi')
OPTIONAL_MODULES = ('opencc',)

# __getattr__ 惰性导入 / uvicorn 字符串动态导入，静态分析扫不到，必须显式声明
HIDDEN_IMPORTS = (
    'tagger.platforms.qqmusic',
    'tagger.platforms.netease',
    'tagger.platforms._netease_crypto',
    'uvicorn.logging',
    'uvicorn.loops.auto',
    'uvicorn.loops.asyncio',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.http.h11_impl',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan.on',
    'uvicorn.lifespan.off',
)

# tools/ 里随包分发的外部程序，按本机平台挑选；--all-tools 则整目录复制
TOOLS_COMMON = ('hook_qq_music.js',)
TOOLS_WINDOWS = (
    'um.exe', 'soundalike.exe', 'fpcalc.exe',
    'QQMusic_Setup_1951.exe', 'Q音屏蔽更新.zip',
)
TOOLS_MACOS = (
    'um-darwin-arm64', 'um-darwin-amd64',
    'soundalike-darwin-arm64', 'soundalike-darwin-amd64',
    'fpcalc', 'QQMusicMac_Mgr_8.8.0_20230903.dmg',
    'QQ 音乐 Mac 屏蔽升级.tar.gz',
)

# 重复打包时会被清掉的条目；config.ini 与 log/ 属于用户数据，特意不在其中
OWNED_ENTRIES = {
    EXE_NAME, '_internal', 'tools', 'web', 'config.example.ini', 'LICENSE',
    '使用说明.txt', '使用文档.html', '打包清单.txt',
    '启动Web向导.bat', '命令行.bat', 'start-web.sh', 'cli.sh',
}


class BuildError(RuntimeError):
    """打包过程中的可预期失败（依赖缺失、命令失败、自检不过）"""


def log(message):
    print(f'[打包] {message}', flush=True)


def human(size):
    for unit in ('B', 'KB', 'MB', 'GB'):
        if size < 1024 or unit == 'GB':
            return f'{size:.1f} {unit}' if unit != 'B' else f'{size} B'
        size /= 1024
    return f'{size:.1f} GB'


def dir_size(path):
    return sum(p.stat().st_size for p in path.rglob('*') if p.is_file())


def module_available(name):
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def ensure_build_deps(auto_install):
    """PyInstaller 是构建期依赖；运行期依赖必须本机装齐，否则打出来的包会缺功能。"""
    try:
        import PyInstaller
        version = PyInstaller.__version__
    except ImportError:
        if not auto_install:
            raise BuildError('缺少 PyInstaller，请先执行 pip install -r requirements-build.txt') from None
        log('未安装 PyInstaller，按 requirements-build.txt 自动安装…')
        subprocess.check_call([sys.executable, '-m', 'pip', 'install',
                               '--disable-pip-version-check', '-r',
                               str(ROOT / 'requirements-build.txt')])
        importlib.invalidate_caches()
        try:
            import PyInstaller
            version = PyInstaller.__version__
        except ImportError as exc:
            raise BuildError('PyInstaller 安装后仍无法导入') from exc
    log(f'PyInstaller {version} / Python {sys.version.split()[0]} / {sys.platform}')

    missing = [name for name in REQUIRED_MODULES if not module_available(name)]
    if missing:
        raise BuildError(
            '运行期依赖未装齐：' + ', '.join(missing) +
            '\n请先执行 python -m pip install -r requirements.txt -r requirements-dev.txt '
            '再打包（PyInstaller 只能收集本机已安装的包）')
    log('运行期依赖检查通过：' + ', '.join(REQUIRED_MODULES))
    optional = [name for name in OPTIONAL_MODULES if module_available(name)]
    log('可选依赖：' + (', '.join(optional) or '无（OpenCC 缺失时繁简转换自动降级）'))


def pyinstaller_args():
    args = [
        sys.executable, '-m', 'PyInstaller',
        '--noconfirm', '--clean', '--onedir', '--console',
        '--name', 'music_helper',
        '--distpath', str(RUN_DIR / 'dist'),
        '--workpath', str(RUN_DIR / 'work'),
        '--specpath', str(RUN_DIR),
        '--paths', str(ROOT),
    ]
    for name in HIDDEN_IMPORTS:
        args += ['--hidden-import', name]
    # frida 的 .pyd / 注入器，certifi 的 CA 证书：光靠 hook 容易漏
    args += ['--collect-all', 'frida', '--collect-data', 'certifi']
    if module_available('opencc'):
        args += ['--collect-data', 'opencc']  # 只带繁简字典，代码交给静态分析
    args.append(str(ROOT / 'main.py'))
    return args


def run_pyinstaller():
    log('开始 PyInstaller 构建（首次约 1-3 分钟）…')
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(pyi_args := pyinstaller_args(), cwd=str(ROOT), text=True,
                          encoding='utf-8', errors='replace',
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if proc.returncode != 0:
        log_path = RUN_DIR / 'pyinstaller.log'
        log_path.write_text(proc.stdout or '', encoding='utf-8')
        raise BuildError(f'PyInstaller 失败（{proc.returncode}），日志尾部：\n'
                         + '\n'.join((proc.stdout or '').splitlines()[-25:])
                         + f'\n完整日志：{log_path}')
    log('PyInstaller 构建完成：' + ' '.join(pyi_args[:6]) + ' …')
    if not (PYI_DIST / EXE_NAME).is_file():
        raise BuildError(f'未找到预期产物 {PYI_DIST / EXE_NAME}')


def reset_dist():
    """清理本脚本生成的顶层单文件；目录一律覆盖写入，不做整目录删除。

    config.ini 与 log/ 是用户数据，永远保留；_internal/ 由 PyInstaller 产物覆盖，
    同名文件会更新，偶有旧文件残留也不影响运行。
    """
    DIST.mkdir(parents=True, exist_ok=True)
    for name in OWNED_ENTRIES:
        target = DIST / name
        if target.is_dir() and not target.is_symlink():
            continue  # _internal / tools / web 交给 copytree(dirs_exist_ok=True)
        if target.exists() or target.is_symlink():
            target.unlink()
    leftovers = [p.name for p in DIST.iterdir()
                 if p.name not in OWNED_ENTRIES | {'config.ini', 'log'}]
    if leftovers:
        log('dist/ 中保留了非本脚本生成的文件：' + ', '.join(leftovers))


def copy_bundle():
    log('组装 dist/ …')
    shutil.copytree(PYI_DIST, DIST, dirs_exist_ok=True)


def prune_third_party_docs():
    """collect-data 会把第三方包自带的 README.md 也带进 _internal/。

    这些不是项目文档，留着会被文档校验 / 索引工具误扫，逐个删掉即可
    （只清理 .md，且限量，避免把依赖目录整体删除）。
    """
    internal = DIST / '_internal'
    if not internal.is_dir():
        return
    stale = [path for path in internal.rglob('*.md') if path.is_file()][:20]
    for path in stale:
        path.unlink()
    if stale:
        log(f'清理第三方包自带文档 {len(stale)} 个（非项目文档）')


def copy_tools(all_tools):
    src = ROOT / 'tools'
    dst = DIST / 'tools'
    dst.mkdir(parents=True, exist_ok=True)
    names = sorted(p.name for p in src.iterdir() if p.is_file()) if all_tools else None
    if names is None:
        names = list(TOOLS_COMMON) + list(
            TOOLS_WINDOWS if os.name == 'nt' else TOOLS_MACOS)
    copied, missing = [], []
    for name in names:
        path = src / name
        if not path.is_file():
            missing.append(name)
            continue
        shutil.copy2(path, dst / name)
        copied.append(name)
    # 上次用了 --all-tools、这次只带本机平台时，把多出来的单文件删掉
    for stale in dst.iterdir():
        if stale.is_file() and stale.name not in copied:
            stale.unlink()
            log('移除上次打包留下的外部程序: ' + stale.name)
    log(f'外部程序 {len(copied)} 个（{human(dir_size(dst))}）：' + ', '.join(copied))
    if missing:
        log('警告：tools/ 里缺少 ' + ', '.join(missing))
    return missing


def copy_web_assets():
    dst = DIST / 'web'
    shutil.copytree(ROOT / 'web' / 'static', dst / 'static', dirs_exist_ok=True)
    shutil.copy2(ROOT / 'web' / 'index.html', dst / 'index.html')
    log('Web 静态资源已复制（web/index.html + web/static/）')


def copy_support_files():
    shutil.copy2(ROOT / 'config.example.ini', DIST / 'config.example.ini')
    # 不覆盖用户已改过的 config.ini；打包产物里绝不塞入构建机本地的 config.ini
    if not (DIST / 'config.ini').exists():
        shutil.copy2(ROOT / 'config.example.ini', DIST / 'config.ini')
    shutil.copy2(ROOT / 'LICENSE', DIST / 'LICENSE')
    docs_index = ROOT / 'docs' / 'index.html'
    if docs_index.is_file():
        shutil.copy2(docs_index, DIST / '使用文档.html')
    log_dir = DIST / 'log'
    for name in ('', 'reports', '_trash'):
        (log_dir / name).mkdir(parents=True, exist_ok=True)


def _write_text(path, text, encoding='utf-8-sig'):
    path.write_text(text, encoding=encoding)


def write_launchers():
    if os.name == 'nt':
        web_bat = '''@echo off
cd /d "%~dp0"
title Music Helper - Web 八步向导
echo 正在启动 Web 八步向导，浏览器会自动打开 http://127.0.0.1:8000/
echo 关闭本窗口或按 Ctrl+C 即可停止服务。
echo.
"music_helper.exe" --web
if errorlevel 1 pause
'''
        cli_bat = '''@echo off
cd /d "%~dp0"
echo Music Helper 命令行（本窗口已切到程序目录）
echo   music_helper.exe --help              查看全部参数
echo   music_helper.exe --dry-run           只出计划，不动文件
echo   music_helper.exe --web               启动 Web 八步向导
echo.
cmd /k
'''
        # cmd 按系统 ANSI 代码页读取 .bat，中文 Windows 用 GBK 才不乱码
        _write_text(DIST / '启动Web向导.bat', web_bat, 'gbk')
        _write_text(DIST / '命令行.bat', cli_bat, 'gbk')
    else:
        web_sh = ('#!/bin/sh\ncd "$(dirname "$0")"\n'
                  'exec ./music_helper --web "$@"\n')
        cli_sh = ('#!/bin/sh\ncd "$(dirname "$0")"\n'
                  'exec ./music_helper "$@"\n')
        _write_text(DIST / 'start-web.sh', web_sh, 'utf-8')
        _write_text(DIST / 'cli.sh', cli_sh, 'utf-8')
        for name in ('start-web.sh', 'cli.sh'):
            (DIST / name).chmod(0o755)


def write_readme(all_tools, tool_count):
    web_launcher = '启动Web向导.bat' if os.name == 'nt' else 'start-web.sh'
    cli_launcher = '命令行.bat' if os.name == 'nt' else 'cli.sh'
    shell = 'cmd' if os.name == 'nt' else '终端'
    text = f'''Music Helper {_version()} —— 绿色版使用说明
生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}
平台：{sys.platform} / {'Windows' if os.name == 'nt' else 'macOS 或 Linux'}

【无需 Python】
本目录是可直接运行的完整程序。{EXE_NAME} 自带 Python 运行时和全部 Python
第三方依赖（在 _internal/ 里），目标机器上不需要安装 Python、pip 或任何依赖包。
不要把 {EXE_NAME} 单独拷走：_internal/、tools/、web/ 必须和它放在一起。

【怎么用】
1. 用记事本打开 config.ini，把 [paths] 下的音乐库 / 工作区目录改成自己的路径。
   也可以不改配置，直接用 Web 向导第 1 步在界面里设置（会写回本文件）。
2. 运行「{web_launcher}」：服务只监听 127.0.0.1:8000，浏览器自动打开八步向导；
   关掉黑窗口或按 Ctrl+C 即停止。若 8000 被占用，用
       {EXE_NAME} --web --web-port 8001
3. 命令行：运行「{cli_launcher}」，或直接在 {shell} 里执行
       {EXE_NAME} --help          查看全部参数
       {EXE_NAME} --dry-run       只出计划，不动任何文件
       {EXE_NAME} --version       查看版本
4. 日志、报告、操作流水与回收站都在 log/ 下。
5. 「使用文档.html」是离线文档索引，双击即可查看全部项目文档（无需联网）。

【目录说明】
  {EXE_NAME:<18} CLI 与 Web 共用的主程序
  _internal/         Python 运行时 + requests / mutagen / frida / pycryptodomex /
                     fastapi / uvicorn / pydantic 等依赖，勿删勿改
  tools/             {tool_count} 个外部程序：um（解密）、soundalike（声纹去重）、
                     fpcalc（指纹）、hook_qq_music.js（Frida 注入）、
                     QQ 音乐旧版安装包与屏蔽更新补丁
                     {'（已包含全部平台二进制）' if all_tools else '（仅当前平台所需）'}
  web/               八步向导的页面与 Vue 运行时，无 CDN、无需 Node
  config.ini         本机配置；重复打包不会被覆盖
  log/               运行产物

【注意】
- QQ 音乐解密依赖本机安装并登录 QQ 音乐客户端；未安装时会调用 tools/ 里的安装包，
  请遵守各音乐平台服务条款，仅用于学习与个人使用（见 LICENSE）。
- 在线标签查询、封面与歌词需要联网；无网络时本地整理流程仍可用。
- 本包由项目根目录的 build_exe.bat / scripts/build_exe.py 生成；源码更新后重新打包即可。

【重建命令】（构建机需要 Python 3.11+，产物本身不需要）
  python -m pip install -r requirements.txt -r requirements-dev.txt -r requirements-build.txt
  python scripts/build_exe.py
'''
    _write_text(DIST / '使用说明.txt', text)


def write_manifest(all_tools):
    lines = [
        f'Music Helper {_version()} 打包清单',
        f'生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
        f'构建环境: Python {sys.version.split()[0]} / {sys.platform}',
        f'外部程序范围: {"全部平台" if all_tools else "仅当前平台"}',
        '',
        '顶层内容（大小 / 说明）',
    ]
    for path in sorted(DIST.iterdir(), key=lambda p: p.name):
        size = dir_size(path) if path.is_dir() else path.stat().st_size
        lines.append(f'  {path.name:<28} {human(size):>10}')
    lines += ['', 'tools/ 明细']
    for path in sorted((DIST / 'tools').iterdir(), key=lambda p: p.name):
        lines.append(f'  {path.name:<40} {human(path.stat().st_size):>10}')
    lines += ['', f'合计: {human(dir_size(DIST))}', '']
    _write_text(DIST / '打包清单.txt', '\n'.join(lines))


def _version():
    """版本号唯一来源是 config.__version__，这里只读不执行源码。"""
    text = (ROOT / 'config.py').read_text(encoding='utf-8')
    match = re.search(r"^__version__\s*=\s*['\"]([^'\"]+)['\"]", text, re.M)
    return match.group(1) if match else '?'


def _run_exe(args, timeout=40):
    return subprocess.run([str(DIST / EXE_NAME), *args], cwd=str(ROOT),
                          capture_output=True, text=True, encoding='utf-8',
                          errors='replace', timeout=timeout)


def verify():
    """从项目根（而非 dist/）启动 exe，顺便验证路径不依赖当前工作目录。"""
    log('产物自检：--version / --help / Web 服务')
    result = _run_exe(['--version'])
    if result.returncode != 0 or _version() not in result.stdout:
        raise BuildError('exe --version 失败：\n' + result.stdout + result.stderr)
    result = _run_exe(['--help'])
    if result.returncode != 0 or '--web' not in result.stdout:
        raise BuildError('exe --help 失败或缺少 --web：\n' + result.stdout + result.stderr)

    for name in TOOLS_COMMON + (TOOLS_WINDOWS if os.name == 'nt' else TOOLS_MACOS):
        path = DIST / 'tools' / name
        if not path.is_file() or path.stat().st_size == 0:
            raise BuildError(f'外部程序缺失或为空: {path}')
    if not (DIST / 'web' / 'static' / 'index.html').is_file():
        raise BuildError('Web 静态资源缺失: web/static/index.html')

    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    proc = subprocess.Popen(
        [str(DIST / EXE_NAME), '--web', '--no-browser', '--web-port', str(port)],
        cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding='utf-8', errors='replace')
    output, ok = '', False
    try:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                output = proc.stdout.read() if proc.stdout else ''
                break
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=1) as resp:
                    body = resp.read(4096).lower()
                    ok = resp.status == 200 and b'<html' in body
                    if ok:
                        break
            except (urllib.error.URLError, OSError, TimeoutError):
                time.sleep(0.4)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
    if not ok:
        raise BuildError('Web 服务自检未通过（页面没返回 200）：\n'
                         + '\n'.join(output.splitlines()[-30:]))
    log(f'自检通过：exe 可运行、外部程序齐全、Web 向导 http://127.0.0.1:{port}/ 返回 200')


def main(argv=None):
    parser = argparse.ArgumentParser(description='生成 dist/ 绿色可执行包（免 Python 环境）')
    parser.add_argument('--all-tools', action='store_true',
                        help='附带 tools/ 下全部平台二进制（默认只带当前平台所需）')
    parser.add_argument('--skip-verify', action='store_true', help='跳过启动自检')
    parser.add_argument('--no-install', action='store_true',
                        help='缺少 PyInstaller 时不要自动安装，直接报错')
    args = parser.parse_args(argv)

    ensure_build_deps(auto_install=not args.no_install)
    run_pyinstaller()
    reset_dist()
    copy_bundle()
    prune_third_party_docs()
    missing = copy_tools(args.all_tools)
    copy_web_assets()
    copy_support_files()
    write_launchers()
    tool_count = len(list((DIST / 'tools').iterdir()))
    write_readme(args.all_tools, tool_count)
    write_manifest(args.all_tools)
    if not args.skip_verify:
        verify()

    if missing:
        log('注意：以下外部程序在 tools/ 里不存在：' + ', '.join(missing))
    log(f'本次构建中间产物：{RUN_DIR}（已被 .gitignore 忽略）')
    log('历史构建目录会留在 build/pyinstaller/runs/，可按需手动整体删除')
    log(f'完成：{DIST}  共 {human(dir_size(DIST))}')
    log(f'入口：{DIST / EXE_NAME}；Web：{DIST / ("启动Web向导.bat" if os.name == "nt" else "start-web.sh")}')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except BuildError as exc:
        print(f'[打包失败] {exc}', file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print('\n[打包] 用户中断', file=sys.stderr)
        sys.exit(130)
