# -*- coding: utf-8 -*-
"""P2 本机解码子进程：把浏览器不能解码的音频派生为临时 MP3 缓存。

``services/media.py`` 保持严格只读；**本模块是试听链路里唯一写盘的地方**，
且只写 ``config.LOG_DIR/_media_cache/`` 下的派生文件——属于运行产物，不进音乐库、
不改原文件、不生成 ``core.ops.Plan``、不进 ``web/tasks.py`` 串行队列。

为什么不把 ffmpeg 的 stdout 直接喂给浏览器：MP3 容器要写总长度与 seek 表，管道流
没有可映射的字节范围，浏览器拖不动进度条。先落成文件，再复用
``/api/media/stream`` 的同一套 Range 实现，前端几乎无感。

FFmpeg 是**可选外部工具，不随仓库分发**（避免几十 MB 二进制与 GPL 传染）。
探测顺序见 ``ffmpeg_exe()``；一处都没有时全部接口优雅降级到「用系统播放器打开」。
契约见 docs/media-player.md §7。
"""

import hashlib
import importlib
import importlib.util
import os
import re
import subprocess
import threading
import time
from collections import deque

import config
import utils

# 必须与 services/media.py 的 NOT_PLAYABLE_REASON 对齐；tests/test_media.py 有断言
NEEDS_TRANSCODE = frozenset({'.ape', '.wma', '.dsf'})

# 改命令或输出参数时换版本号，避免复用旧参数生成的缓存
CACHE_VERSION = 'v1-mp3-192k-44100'
CACHE_DIR_NAME = '_media_cache'
MAX_CACHE_FILES = 12
MAX_CACHE_BYTES = 512 * 1024 * 1024
TRANSCODE_TIMEOUT = 15 * 60  # 秒；看门狗 kill，避免损坏文件把线程永久挂住
_CACHE_NAME_RE = re.compile(r'^[0-9a-f]{32}\.(mp3|part)$')
# -progress pipe:1 的标准字段；这些不能混进错误日志尾部
_PROGRESS_KEYS = frozenset({
    'frame', 'fps', 'stream_0_0_q', 'bitrate', 'total_size',
    'out_time_us', 'out_time_ms', 'out_time', 'dup_frames', 'drop_frames',
    'speed', 'progress',
})

_JOBS = {}
_JOBS_LOCK = threading.Lock()

# Windows 上起子进程不要弹黑窗口
_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0


class TranscodeError(RuntimeError):
    """解码失败；消息可以直接展示给用户"""


def _default_ffmpeg_name():
    """PATH 查找用的程序名（tools/ 下的按平台产物由 config._default_ffmpeg 负责）"""
    return 'ffmpeg.exe' if os.name == 'nt' else 'ffmpeg'


def ffmpeg_exe():
    """返回一个可执行的 FFmpeg 路径，找不到返回空串

    顺序：``config.FFMPEG_EXE``（config.ini / 环境变量 / tools/ 随包二进制）
    → 系统 PATH → 可选的 ``imageio-ffmpeg`` 包。三者都没有不算错误，
    只是 P2 不可用，UI 会明确提示并退回系统播放器。
    """
    configured = str(getattr(config, 'FFMPEG_EXE', '') or '')
    resolved = utils.resolve_tool(configured, _default_ffmpeg_name())
    if resolved and os.path.isfile(resolved) and not utils.tool_problem(resolved, 'FFmpeg'):
        return resolved
    # 动态导入：PyInstaller 静态分析看不到，绿色版没装这个包也不会打包失败/告警
    try:
        if importlib.util.find_spec('imageio_ffmpeg') is not None:
            module = importlib.import_module('imageio_ffmpeg')
            candidate = module.get_ffmpeg_exe()
            if candidate and os.path.isfile(candidate) \
                    and not utils.tool_problem(candidate, 'FFmpeg'):
                return candidate
    except Exception:  # noqa: BLE001 - 可选包坏了不该影响主流程
        pass
    return ''


def missing_hint():
    """FFmpeg 缺失时给一句能照着做的提示（不假装功能可用）"""
    return ('未找到 FFmpeg。三选一即可启用内置试听：'
            '① pip install imageio-ffmpeg；'
            '② 系统安装 ffmpeg 并加入 PATH；'
            '③ 把 ffmpeg 放到 tools/ 并在 config.ini 的 [tools] ffmpeg_exe 指定路径。'
            '也可以直接用系统播放器打开。')


def cache_dir():
    path = os.path.join(config.LOG_DIR, CACHE_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def cache_key(target):
    """源路径 + mtime_ns + size + 参数版本；源文件一改缓存立即失效"""
    stat = os.stat(target)
    raw = f'{os.path.realpath(target)}|{stat.st_mtime_ns}|{stat.st_size}|{CACHE_VERSION}'
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:32]


def _cache_paths(key):
    root = cache_dir()
    return os.path.join(root, key + '.part'), os.path.join(root, key + '.mp3')


def ready_path(target):
    """已就绪的派生 MP3 绝对路径；没有或源文件已变动返回 None"""
    try:
        key = cache_key(target)
    except OSError:
        return None
    _, final = _cache_paths(key)
    try:
        if os.path.isfile(final) and os.path.getsize(final) > 0:
            return final
    except OSError:  # pragma: no cover - 竞态下文件被清理
        return None
    return None


def build_command(exe, source, destination):
    """统一的解码参数；三种格式共用，DSF 的 1bit DSD 会先被解成 PCM 再重采样

    ``-progress pipe:1`` 供状态条读取已解码时长；``stderr`` 合并到同一管道，
    避免两边分别 PIPE 时其中一条写满造成死锁。
    """
    return [
        exe, '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
        '-i', source,
        '-map', '0:a:0', '-vn', '-sn', '-dn',
        '-c:a', 'libmp3lame', '-b:a', '192k', '-ar', '44100', '-ac', '2',
        '-map_metadata', '-1',
        '-progress', 'pipe:1', '-nostats',
        '-f', 'mp3', destination,
    ]


def parse_progress(line, current=0.0):
    """从 ``-progress pipe:1`` 的一行里取「已解码秒数」；非进度行原样返回

    坑：FFmpeg 的 ``out_time_ms`` 名为毫秒，实际输出的仍是**微秒**（与
    ``out_time_us`` 同值，历史遗留）。按 1000 换算会把 1 秒显示成 17 分钟。
    两个字段统一按微秒处理，另支持可读的 ``out_time=HH:MM:SS.xx`` 兜底。
    取最大值避免进度回退。
    """
    if '=' not in line:
        return current
    key, _, value = line.partition('=')
    value = value.strip()
    if key in ('out_time_us', 'out_time_ms'):
        try:
            return max(current, int(value) / 1_000_000)
        except ValueError:
            return current
    if key == 'out_time' and value.count(':') == 2:
        try:
            hours, minutes, seconds = value.split(':')
            return max(current, 3600 * int(hours) + 60 * int(minutes) + float(seconds))
        except ValueError:
            return current
    return current


def _job_snapshot(job):
    return {
        'status': job['status'],
        'error': job.get('error', ''),
        'hint': job.get('hint', ''),
        'decoded': round(job.get('decoded', 0.0), 2),
        'size': job.get('size', 0),
    }


def status(target, start=False):
    """查询（可选地启动）转码任务，前端轮询这个结果

    ``status`` 取值：``not_needed`` / ``unavailable`` / ``idle`` / ``running`` /
    ``done`` / ``failed``。``start=True`` 是幂等的：同一 key 已有 running 任务
    不会重复起子进程。
    """
    ext = os.path.splitext(target)[1].lower()
    if ext not in NEEDS_TRANSCODE:
        return {'available': True, **_job_snapshot({'status': 'not_needed'})}
    try:
        key = cache_key(target)
    except OSError:
        return {'available': True, 'status': 'failed',
                'error': '源文件已不存在或无法读取', 'hint': '',
                'decoded': 0, 'size': 0}
    exe = ffmpeg_exe()
    if not exe:
        return {'available': False, 'status': 'unavailable',
                'error': 'FFmpeg 不可用', 'hint': missing_hint(),
                'decoded': 0, 'size': 0}
    cached = ready_path(target)
    if cached:
        with _JOBS_LOCK:
            finished = _JOBS.pop(key, None)
        return {'available': True, 'status': 'done',
                'error': '', 'hint': '',
                'decoded': round(finished['decoded'], 2) if finished else 0.0,
                'size': os.path.getsize(cached)}
    with _JOBS_LOCK:
        job = _JOBS.get(key)
    if job and job['status'] == 'running':
        return {'available': True, **_job_snapshot(job)}
    if not start:
        if job:  # 保留上一次的失败原因，供 UI 展示「重新解码」
            return {'available': True, **_job_snapshot(job)}
        return {'available': True, 'status': 'idle',
                'error': '', 'hint': '', 'decoded': 0, 'size': 0}
    # start=True 且上次失败时，_start 会覆盖旧 job 重跑，前端的「重新解码」才有意义
    return {'available': True, **_job_snapshot(_start(target, key, exe))}


def _start(target, key, exe):
    """起一个 daemon 线程；不进 web/tasks.py 的单工作者队列"""
    with _JOBS_LOCK:
        running = _JOBS.get(key)
        if running and running['status'] == 'running':
            return running
        job = {'status': 'running', 'error': '', 'hint': '',
               'decoded': 0.0, 'size': 0, 'started_at': time.time()}
        _JOBS[key] = job
    thread = threading.Thread(target=_worker, args=(target, key, exe, job),
                              daemon=True, name=f'mh-transcode-{key[:8]}')
    thread.start()
    return job


def _kill_later(proc, delay):
    def _kill():
        try:
            if proc.poll() is None:
                proc.kill()
        except OSError:  # pragma: no cover - 进程刚好结束
            pass

    timer = threading.Timer(delay, _kill)
    timer.daemon = True
    timer.start()
    return timer


def _worker(target, key, exe, job):
    part, final = _cache_paths(key)
    proc = None
    timer = None
    try:
        command = build_command(exe, target, part)
        proc = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace',
            creationflags=_NO_WINDOW)
        timer = _kill_later(proc, TRANSCODE_TIMEOUT)
        tail = deque(maxlen=20)
        for line in proc.stdout or ():
            line = line.strip()
            if not line:
                continue
            job['decoded'] = parse_progress(line, job['decoded'])
            if line.partition('=')[0] not in _PROGRESS_KEYS:
                tail.append(line)
        proc.wait()
        if proc.returncode != 0:
            detail = '；'.join(list(tail)[-4:]) or f'退出码 {proc.returncode}'
            raise TranscodeError(f'解码失败：{detail}')
        if not os.path.isfile(part) or os.path.getsize(part) <= 0:
            raise TranscodeError('解码结束但没有产生音频数据')
        os.replace(part, final)  # 原子落盘：前端永远看不到半截 mp3
        job['status'] = 'done'
        job['size'] = os.path.getsize(final)
    except TranscodeError as exc:
        job['status'] = 'failed'
        job['error'] = str(exc)
        job['hint'] = _failure_hint(str(exc))
    except Exception as exc:  # noqa: BLE001 - 子进程异常一律转成可展示的状态
        job['status'] = 'failed'
        job['error'] = f'解码失败：{exc}'
        job['hint'] = _failure_hint(str(exc))
    finally:
        if timer:
            timer.cancel()
        if proc and proc.poll() is None:  # pragma: no cover - 超时看门狗兜底
            try:
                proc.kill()
            except OSError:
                pass
        _remove_quietly(part)
        try:
            prune_cache()
        except OSError:  # pragma: no cover - 清理失败不影响本次试听
            pass


def _failure_hint(message):
    low = message.lower()
    if 'drm' in low or 'protected' in low or 'encrypt' in low:
        return '该文件带 DRM / 加密保护，FFmpeg 也无法解码；请用原平台客户端或系统播放器。'
    if 'invalid data' in low or 'no such file' in low:
        return '文件可能已损坏或不是有效的音频；可换用系统播放器确认。'
    return '可用系统播放器打开，或点「重新解码」再试一次。'


def _remove_quietly(path):
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:  # pragma: no cover
        pass


def prune_cache():
    """按 mtime 保留最近的 MAX_CACHE_FILES 个 / MAX_CACHE_BYTES 字节

    只删本模块自己命名的 ``<32 hex>.mp3|.part``，绝不碰目录里的其它文件。
    """
    root = cache_dir()
    entries = []
    for name in os.listdir(root):
        if not _CACHE_NAME_RE.match(name):
            continue
        path = os.path.join(root, name)
        if os.path.isfile(path):
            entries.append(path)
    entries.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    total = 0
    for index, path in enumerate(entries):
        size = os.path.getsize(path)
        if index >= MAX_CACHE_FILES or total + size > MAX_CACHE_BYTES:
            _remove_quietly(path)
        else:
            total += size
    return total


def clear_jobs():
    """仅供测试：清掉内存态任务表，不删缓存文件"""
    with _JOBS_LOCK:
        _JOBS.clear()
