# -*- coding: utf-8 -*-
"""git_uplink.py - 用已采集的免费节点临时自建本地代理，给 git pull / push 出境用

背景：本机存在「api.github.com 能通、github.com:443 被重置」的网络，
典型表现是 git push 报 502 / connection reset。节点采集任务里已经有现成的
节点池（clash 格式，mihomo 原生可读），这里把那条链路压成一个单文件工具：
从节点池逐条试起一个本地代理，探测 https://github.com/ 通了就把 git 流量指向它。

与 free-nodes 空间里 uplink.py 的差别：那边要支撑四内核 + URI 转换，依赖
collect_nodes/test_nodes/layout/pool 四个模块（约 5000 行）；本文件只保留
「clash 配置 → 起 mihomo → 探测 → 给 git 用」这段最短路径，零第三方依赖。

用法：
    python scripts/git_uplink.py start                  # 起通道并常驻（打印代理地址）
    eval "$(python scripts/git_uplink.py env)"          # 让当前 shell 的 git 走它
    python scripts/git_uplink.py run -- git push origin master
    python scripts/git_uplink.py push origin master     # 等价简写
    python scripts/git_uplink.py pull origin master
    python scripts/git_uplink.py status                 # 通道还活着吗
    python scripts/git_uplink.py stop                   # 用完停掉（务必）

约定：进度日志一律走 stderr，stdout 只留给可被 eval 的机器可读输出。
"""

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNTIME_DIR = os.path.join(ROOT, '.workbuddy', 'runtime')
SESSION_FILE = os.path.join(RUNTIME_DIR, 'git_uplink.json')

# 节点源（clash/mihomo 配置）默认查找顺序，先到先得
CONFIG_CANDIDATES = (
    os.path.expanduser('~/.workbuddy/data/git-uplink/clash.yaml'),
    os.path.expanduser('~/WorkBuddy/Test/free-nodes/nodes/pool/pool_clash.yaml'),
    os.path.expanduser('~/WorkBuddy/Test/free-nodes/nodes/available_clash.yaml'),
)
# mihomo 内核默认位置
EXE_CANDIDATES = (
    os.path.expanduser('~/.workbuddy/data/free-nodes-tools/bin/mihomo/mihomo.exe'),
    os.path.expanduser('~/.workbuddy/data/free-nodes-tools/bin/mihomo/mihomo'),
)

DEFAULT_PROBE = 'https://github.com/'
PROXY_KEYS = ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy')
CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0
DETACHED_PROCESS = 0x00000008 if os.name == 'nt' else 0


def log(msg):
    """进度输出走 stderr，避免污染 eval 用的 stdout。"""
    print(msg, file=sys.stderr, flush=True)


def _ensure_console_encoding():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors='replace')
        except (AttributeError, ValueError):
            pass


# ---------------------------------------------------------------- 节点源

def find_config(explicit=None):
    """定位 clash 配置：显式参数 → 环境变量 → 默认候选路径。"""
    for path in (explicit, os.environ.get('GIT_UPLINK_CONFIG')):
        if path:
            if os.path.exists(path):
                return path
            raise SystemExit(f'[uplink] 指定的节点配置不存在：{path}')
    for path in CONFIG_CANDIDATES:
        if os.path.exists(path):
            return path
    raise SystemExit(
        '[uplink] 找不到节点配置（clash 格式）。三选一：\n'
        '  1) --config <path> 指定\n'
        '  2) 设环境变量 GIT_UPLINK_CONFIG\n'
        '  3) 把 free-nodes 采集出来的 pool_clash.yaml 放到 '
        + CONFIG_CANDIDATES[0]
    )


def find_exe(explicit=None):
    for path in (explicit, os.environ.get('MIHOMO_EXE')):
        if path:
            if os.path.exists(path):
                return path
            raise SystemExit(f'[uplink] 指定的内核不存在：{path}')
    for path in EXE_CANDIDATES:
        if os.path.exists(path):
            return path
    found = shutil.which('mihomo')
    if found:
        return found
    raise SystemExit('[uplink] 找不到 mihomo 内核，可用 --exe 或环境变量 MIHOMO_EXE 指定')


def load_proxies(path):
    """读出配置里的代理列表。节点池文件是 JSON（同时也是合法 YAML）。"""
    try:
        with open(path, encoding='utf-8', errors='replace') as handle:
            text = handle.read()
    except OSError as exc:
        raise SystemExit(f'[uplink] 读取节点配置失败：{exc}')
    data = None
    try:
        data = json.loads(text)
    except ValueError:
        try:
            import yaml  # 可选依赖，装了就能直接读 yaml 版订阅
            data = yaml.safe_load(text)
        except ImportError:
            raise SystemExit('[uplink] 配置不是 JSON，且未安装 PyYAML（pip install pyyaml）')
        except Exception as exc:
            raise SystemExit(f'[uplink] 配置解析失败：{str(exc)[:80]}')
    if not isinstance(data, dict):
        raise SystemExit('[uplink] 配置格式不对：期望 clash/mihomo 的映射结构')
    proxies = [p for p in (data.get('proxies') or [])
               if isinstance(p, dict) and p.get('server') and p.get('port') and p.get('type')]
    if not proxies:
        raise SystemExit('[uplink] 配置里没有可用 proxies 条目')
    return proxies


# ---------------------------------------------------------------- 起停内核

def _free_port(start=26000):
    for port in range(start, start + 500):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(('127.0.0.1', port))
                return port
            except OSError:
                continue
    return 0


def _tcp_alive(host, port, timeout=2.0):
    try:
        with socket.create_connection((host, int(port)), timeout):
            return True
    except (OSError, ValueError):
        return False


def _prefilter(proxies, timeout, workers=32):
    """TCP 预筛：连服务器都连不上的不必花时间起内核（每个要 1-3 秒）。"""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        alive = list(pool.map(lambda p: _tcp_alive(p['server'], p['port'], timeout), proxies))
    return [p for p, ok in zip(proxies, alive) if ok]


def build_config(proxy, port):
    """单节点全局模式配置：所有流量都走这一个节点，省去分组与规则。"""
    name = proxy.get('name') or f"{proxy['type']}-{proxy['server']}:{proxy['port']}"
    return {
        'mixed-port': port,
        'allow-lan': False,
        'mode': 'global',
        'log-level': 'warning',
        'proxies': [dict(proxy, name=name)],
        'proxy-groups': [{'name': 'GLOBAL', 'type': 'select', 'proxies': [name]}],
        'rules': ['MATCH,GLOBAL'],
    }


def _wait_port(port, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(('127.0.0.1', port), 0.3):
                return True
        except OSError:
            time.sleep(0.12)
    return False


def probe(port, url=DEFAULT_PROBE, timeout=12):
    """经本地代理访问探测地址，拿到 2xx/3xx 才算通。返回 (ok, 延迟毫秒)。"""
    handler = urllib.request.ProxyHandler({'http': f'http://127.0.0.1:{port}',
                                           'https': f'http://127.0.0.1:{port}'})
    opener = urllib.request.build_opener(handler)
    started = time.time()
    try:
        with opener.open(url, timeout=timeout) as resp:
            ok = 200 <= getattr(resp, 'status', 200) < 400
    except urllib.error.HTTPError as exc:
        ok = 200 <= exc.code < 400
    except Exception:  # noqa: BLE001 - 任何异常都只意味着这条通道不可用
        return False, 0
    return ok, int((time.time() - started) * 1000)


class Uplink:
    """一条正在运行的本地代理通道。"""

    def __init__(self, port, proc, name, tmpdir, pid=0):
        self.port = port
        self.proc = proc
        self.name = name
        self.tmpdir = tmpdir
        self.pid = int(pid or (proc.pid if proc is not None else 0))

    @property
    def url(self):
        return f'http://127.0.0.1:{self.port}'

    def describe(self):
        return f'{self.name[:40]}（本地 {self.url}）'


def _cleanup(tmpdir):
    if not tmpdir:
        return
    try:
        for name in os.listdir(tmpdir):
            try:
                os.remove(os.path.join(tmpdir, name))
            except OSError:
                pass
        os.rmdir(tmpdir)
    except OSError:
        pass


def _pid_alive(pid):
    pid = int(pid or 0)
    if pid <= 0:
        return False
    if os.name == 'nt':
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if not ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == 259  # STILL_ACTIVE
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _kill_pid(pid):
    pid = int(pid or 0)
    if pid <= 0:
        return
    try:
        if os.name == 'nt':
            subprocess.run(['taskkill', '/F', '/PID', str(pid)],
                           capture_output=True, timeout=10)
        else:
            os.kill(pid, 15)
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------- 会话状态

def save_session(up):
    os.makedirs(RUNTIME_DIR, exist_ok=True)
    with open(SESSION_FILE, 'w', encoding='utf-8') as handle:
        json.dump({'url': up.url, 'port': up.port, 'pid': up.pid,
                   'name': up.name, 'tmpdir': up.tmpdir,
                   'created': time.strftime('%Y-%m-%d %H:%M:%S')},
                  handle, ensure_ascii=False, indent=1)


def load_session():
    try:
        with open(SESSION_FILE, encoding='utf-8') as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get('port') else None


def clear_session():
    try:
        os.remove(SESSION_FILE)
    except OSError:
        pass


def stop(up=None):
    """停掉通道（内核进程 + 临时目录）并清掉状态。"""
    if up is not None:
        if up.proc is not None:
            try:
                up.proc.kill()
                up.proc.wait(timeout=3)
            except Exception:  # noqa: BLE001
                pass
        elif up.pid:
            _kill_pid(up.pid)
        _cleanup(up.tmpdir)
        log(f'[uplink] 已停止通道 {up.url}')
    else:
        session = load_session()
        if session:
            _kill_pid(session.get('pid'))
            _cleanup(session.get('tmpdir'))
            log(f'[uplink] 已停止遗留通道（pid {session.get("pid")}）')
    clear_session()


def resume(probe_url=DEFAULT_PROBE, timeout=12):
    """复用上次登记的通道：进程活着且探测通过才算数。"""
    session = load_session()
    if not session:
        return None
    port = int(session.get('port') or 0)
    if not port or not _pid_alive(session.get('pid')):
        stop()
        return None
    if not _wait_port(port, 2.0):
        stop()
        return None
    ok, latency = probe(port, probe_url, timeout)
    if not ok:
        log('[uplink] 上次登记的通道已不通，重建')
        stop()
        return None
    log(f'[uplink] 复用已有通道 {session.get("url")}（{latency}ms）')
    return Uplink(port, None, session.get('name', ''), session.get('tmpdir', ''),
                  pid=session.get('pid'))


# ---------------------------------------------------------------- 建立通道

def start(exe=None, config=None, port=0, max_tries=12, pool_scan=80,
          probe_url=DEFAULT_PROBE, probe_timeout=12, startup_timeout=8,
          prefilter=True):
    """逐条试节点起代理，第一个能访问 probe_url 的留下。全失败返回 None。"""
    exe = find_exe(exe)
    config_path = find_config(config)
    proxies = load_proxies(config_path)
    log(f'[uplink] 节点源 {config_path}（{len(proxies)} 个节点）')

    cand = proxies[:pool_scan] if pool_scan else proxies
    if prefilter:
        before = len(cand)
        cand = _prefilter(cand, 2.0)
        log(f'[uplink] TCP 预筛 {before} → {len(cand)} 个可连')
    if not cand:
        log('[uplink] 没有可连节点')
        return None

    port = port or _free_port()
    if not port:
        log('[uplink] 找不到空闲本地端口')
        return None

    for index, proxy in enumerate(cand[:max_tries], 1):
        name = proxy.get('name') or f"{proxy['type']}@{proxy['server']}"
        tmpdir = tempfile.mkdtemp(prefix='gitup_')
        cfg_path = os.path.join(tmpdir, 'config.yaml')
        proc = None
        try:
            with open(cfg_path, 'w', encoding='utf-8') as handle:
                json.dump(build_config(proxy, port), handle, ensure_ascii=False, indent=1)
            proc = subprocess.Popen(
                [exe, '-d', tmpdir, '-f', cfg_path],
                cwd=tmpdir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS,
            )
            if not _wait_port(port, startup_timeout):
                raise RuntimeError('内核启动超时')
            ok, latency = probe(port, probe_url, probe_timeout)
            if not ok:
                raise RuntimeError('探测失败')
            up = Uplink(port, proc, name, tmpdir)
            log(f'[uplink] 通道就绪（第 {index} 个候选）：{up.describe()}，{latency}ms')
            return up
        except Exception as exc:  # noqa: BLE001
            if proc is not None:
                try:
                    proc.kill()
                    proc.wait(timeout=3)
                except Exception:  # noqa: BLE001
                    pass
            _cleanup(tmpdir)
            if os.name == 'nt' and port:
                _kill_pid(_listener_pid(port))
            log(f'[uplink] 候选 {index} 不通：{str(exc)[:60]}')
    log(f'[uplink] {min(len(cand), max_tries)} 个候选全部失败')
    return None


def _listener_pid(port):
    """Windows 下兜底找占用端口的进程（内核已被 kill 时通常返回 0）。"""
    try:
        out = subprocess.run(['netstat', '-ano'], capture_output=True, text=True,
                             timeout=10).stdout
    except Exception:  # noqa: BLE001
        return 0
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[1].endswith(f':{port}') and parts[3] == 'LISTENING':
            return int(parts[4])
    return 0


def ensure(keep=False, **kwargs):
    """复用已有通道，没有再新建。返回 (Uplink, 是否新建)。"""
    up = resume(kwargs.get('probe_url', DEFAULT_PROBE))
    if up:
        return up, False
    up = start(**{k: v for k, v in kwargs.items() if k != 'keep'})
    if up:
        save_session(up)
        return up, True
    return None, False


def direct_ok(url=DEFAULT_PROBE, timeout=10):
    """屏蔽代理后直连实测；用于「代理起不来但本来就能通」的兜底判断。"""
    saved = {key: os.environ.pop(key, None) for key in PROXY_KEYS}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=timeout) as resp:
            return 200 <= getattr(resp, 'status', 200) < 400
    except urllib.error.HTTPError as exc:
        return 200 <= exc.code < 400
    except Exception:  # noqa: BLE001
        return False
    finally:
        for key, value in saved.items():
            if value is not None:
                os.environ[key] = value


# ---------------------------------------------------------------- git 接入

def proxy_env(url):
    """给子进程用的环境变量副本：覆盖掉系统里可能已经失效的代理设置。"""
    env = dict(os.environ)
    for key in PROXY_KEYS:
        if url:
            env[key] = url
        else:
            env.pop(key, None)
    return env


def run_command(argv, url=None, keep=False):
    """带代理执行命令；git 命令额外用 -c 显式指定代理，避免被环境里旧配置顶掉。"""
    cmd = list(argv)
    if url and os.path.basename(cmd[0]).lower().startswith('git'):
        cmd[1:1] = ['-c', f'http.proxy={url}', '-c', f'https.proxy={url}']
    log(f'[uplink] 执行：{" ".join(cmd)}')
    try:
        return subprocess.run(cmd, env=proxy_env(url), cwd=ROOT).returncode
    except FileNotFoundError:
        log(f'[uplink] 找不到可执行文件：{cmd[0]}')
        return 127


def _git_flow(args, git_args):
    """push / pull / run 共用：复用或建立通道 → 执行 → 收尾。"""
    if args.no_proxy:
        return run_command(git_args, url=None)

    up, created = ensure(probe_url=args.probe, exe=args.exe, config=args.config,
                         max_tries=args.max_tries, pool_scan=args.pool_scan)
    if up is None:
        if not args.allow_direct:
            log('[uplink] 未能建立代理通道，且指定了 --no-direct，放弃')
            return 1
        if not direct_ok(args.probe):
            log('[uplink] 代理没起来，直连实测也不通；仍按直连尝试（大概率失败）')
        return run_command(git_args, url=None)

    code = run_command(git_args, url=up.url)
    if created and not args.keep and not keep_after(code):
        stop(up)
    return code


def keep_after(code):
    """失败时保留通道，方便改完立刻重试（成功则收尾，不留后台进程）。"""
    if code != 0:
        log('[uplink] 命令失败，通道保留以便重试（用完记得 stop）')
        return True
    return False


# ---------------------------------------------------------------- CLI

SHELL_ENV = {
    'bash': 'export {0}={1}',
    'powershell': '$env:{0}="{1}"',
    'cmd': 'set {0}={1}',
}


def cmd_env(args):
    """输出可直接 eval 的代理环境变量。"""
    up, created = ensure(probe_url=args.probe, exe=args.exe, config=args.config,
                         max_tries=args.max_tries, pool_scan=args.pool_scan)
    if up is None:
        log('[uplink] 没有可用通道，未输出任何环境变量')
        return 1
    template = SHELL_ENV[args.shell]
    for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy'):
        print(template.format(key, up.url))
    print(template.format('GIT_UPLINK_PID', up.pid))
    if created:
        log('[uplink] 提示：通道已在后台常驻，用完执行 stop 收尾')
    return 0


def cmd_start(args):
    stop()  # 先清掉上一次的遗留，避免端口与进程堆积
    up = start(exe=args.exe, config=args.config, port=args.port,
               max_tries=args.max_tries, pool_scan=args.pool_scan,
               probe_url=args.probe)
    if not up:
        return 1
    save_session(up)
    time.sleep(0.8)
    if not _pid_alive(up.pid):
        clear_session()
        log('[uplink] 内核进程启动后立即退出，通道无法常驻。')
        log('[uplink] 改用一次性调用：python scripts/git_uplink.py run -- git push ...')
        return 1
    print(up.url)
    return 0


def cmd_status(args):
    session = load_session()
    if not session:
        log('[uplink] 无已登记通道（未 start 或已 stop）')
        return 1
    alive = _pid_alive(session.get('pid'))
    ok, latency = probe(int(session['port']), args.probe, 10) if alive else (False, 0)
    log(f'[uplink] 通道 {session.get("url")}｜节点 {session.get("name")}'
        f'｜进程 {"存活" if alive else "已退出"}｜探测 {"通" if ok else "不通"}'
        f'{f"，{latency}ms" if ok else ""}｜建立于 {session.get("created")}')
    return 0 if (alive and ok) else 1


def cmd_run(args):
    argv = args.command
    if argv and argv[0] == '--':
        argv = argv[1:]
    if not argv:
        log('[uplink] run 需要命令，例如：run -- git push origin master')
        return 2
    return _git_flow(args, argv)


def cmd_git(args):
    sub = args.action
    extra = list(args.git_args)
    if extra and extra[0] == '--':
        extra = extra[1:]
    return _git_flow(args, ['git', sub] + extra)


def build_parser():
    parser = argparse.ArgumentParser(
        description='用免费节点临时自建本地代理，供 git pull / push 使用',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''示例:
  python scripts/git_uplink.py start                    # 起通道
  eval "$(python scripts/git_uplink.py env)"            # bash 里临时生效
  python scripts/git_uplink.py push origin master       # 带代理推送
  python scripts/git_uplink.py pull                     # 带代理拉取
  python scripts/git_uplink.py run -- git ls-remote origin
  python scripts/git_uplink.py status / stop
''')
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--config', help='clash/mihomo 节点配置路径')
    common.add_argument('--exe', help='mihomo 内核路径')
    common.add_argument('--probe', default=DEFAULT_PROBE, help=f'探测地址（默认 {DEFAULT_PROBE}）')
    common.add_argument('--max-tries', type=int, default=12, help='最多试几个节点（默认 12）')
    common.add_argument('--pool-scan', type=int, default=80, help='参与 TCP 预筛的节点数（默认 80）')
    common.add_argument('--no-proxy', action='store_true', help='不起代理，直接执行')
    common.add_argument('--no-direct', dest='allow_direct', action='store_false',
                        help='代理不可用时不允许直连兜底（默认允许）')
    common.add_argument('--keep', action='store_true', help='命令结束后保留通道')

    subs = parser.add_subparsers(dest='action_name', required=True)
    sub_start = subs.add_parser('start', parents=[common], help='建立通道并常驻')
    sub_start.add_argument('--port', type=int, default=0, help='本地端口（默认自动选）')
    sub_start.set_defaults(func=cmd_start)

    sub_env = subs.add_parser('env', parents=[common], help='输出可 eval 的代理环境变量')
    sub_env.add_argument('--shell', choices=list(SHELL_ENV), default='bash')
    sub_env.set_defaults(func=cmd_env)

    sub_status = subs.add_parser('status', parents=[common], help='查看通道状态')
    sub_status.set_defaults(func=cmd_status)

    sub_stop = subs.add_parser('stop', parents=[common], help='停止通道')
    sub_stop.set_defaults(func=lambda args: (stop(), 0)[1])

    sub_run = subs.add_parser('run', parents=[common], help='带代理执行任意命令')
    sub_run.add_argument('command', nargs=argparse.REMAINDER)
    sub_run.set_defaults(func=cmd_run)

    for name in ('push', 'pull', 'fetch'):
        sub = subs.add_parser(name, parents=[common], help=f'带代理执行 git {name}')
        sub.add_argument('git_args', nargs=argparse.REMAINDER)
        sub.set_defaults(func=cmd_git, action=name)
    return parser


def main(argv=None):
    _ensure_console_encoding()
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
