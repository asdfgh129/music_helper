# -*- coding: utf-8 -*-
"""
Web UI 阶段 4：后台任务队列 + 实时日志 / 进度。

设计要点：
- 单进程串行：一条 worker 线程从队列取任务逐个执行，契合「config 是模块级全局态、
  本机单配置」的现实，避免并发读写全局配置或 Plan/journal。
- 日志捕获：流水线各阶段都打 utils.main_logger，任务运行时给它挂一个按任务缓冲的
  Handler，前端轮询即可拿到阶段日志与进度，无需改任何业务代码。
- 直接复用 main.flow_* 入口函数，不新增业务分支。
"""

import logging
import queue
import threading
import time
import types
import uuid
from datetime import datetime
from typing import Dict, List, Optional

import utils

# --------------------------------------------------------------------------- #
# 阶段关键字（按出现顺序），用于从日志推断进度百分比                            #
# --------------------------------------------------------------------------- #

_STAGES = {
    "pipeline": [
        ("解密", ["网易云解密", "QQ音乐解密", "解密"]),
        ("声纹去重", ["声纹去重"]),
        ("标签更新", ["标签更新完成", "标签更新"]),
        ("工作区检查", ["工作区检查", "检查文件名", "元数据", "重复"]),
        ("待补全分流", ["待补全分流", "工作区分流"]),
        ("年份归档", ["归档完成", "归档"]),
    ],
    "check": [
        ("声纹库检查", ["声纹库", "声纹库与目录一致性"]),
        ("最终库检查", ["最终库检查", "文件名 / 元数据", "步骤 2"]),
    ],
    "decrypt": [("解密", ["网易云解密", "QQ音乐解密", "解密"])],
    "dedupe": [("声纹去重", ["声纹去重"])],
    "dedupe-report": [("声纹候选", ["声纹候选", "声纹去重"])],
    "manual-archive": [
        ("标签更新", ["标签更新完成", "标签更新"]),
        ("按标签重命名", ["按标签规范化", "重命名"]),
        ("年份入库", ["入库成功", "入库"]),
    ],
}

_LABELS = {
    "pipeline": "工作区完整流水线",
    "check": "最终库检查",
    "decrypt": "解密",
    "dedupe": "声纹去重",
    "dedupe-report": "声纹候选清单",
    "manual-archive": "手动归档入库",
}

_SUPPORTED = [
    {"kind": "pipeline", "label": "工作区完整流水线",
     "desc": "解密 → 去重 → 标签 → 检查 → 分流 → 归档", "default_dry_run": True},
    {"kind": "check", "label": "最终库检查",
     "desc": "检查 LIBRARY_DIR 并按需修复", "default_dry_run": True},
    {"kind": "decrypt", "label": "解密（网+QQ）",
     "desc": "按 OS 路由，一次性处理两个源", "default_dry_run": True},
    {"kind": "dedupe", "label": "声纹去重",
     "desc": "音质差的自动移走，同质量才询问", "default_dry_run": True},
    {"kind": "dedupe-report", "label": "声纹候选清单",
     "desc": "只列候选组，不移动文件", "default_dry_run": True},
    {"kind": "manual-archive", "label": "手动归档入库",
     "desc": "WORKSPACE_DIR → LIBRARY_DIR（按年份）", "default_dry_run": True},
]


def supported_actions():
    return _SUPPORTED


# --------------------------------------------------------------------------- #
# 日志缓冲 Handler                                                            #
# --------------------------------------------------------------------------- #

class _LogLine:
    __slots__ = ("ts", "level", "msg")
    def __init__(self, ts, level, msg):
        self.ts = ts
        self.level = level
        self.msg = msg


class _TaskHandler(logging.Handler):
    def __init__(self, task):
        super().__init__()
        self.task = task
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record):
        try:
            line = self.format(record)
            ts = record.created
            level = record.levelname
        except Exception:  # noqa: BLE001
            return
        self.task.append_log(ts, level, line)


# --------------------------------------------------------------------------- #
# 任务对象                                                                    #
# --------------------------------------------------------------------------- #

class Task:
    def __init__(self, task_id, kind, opts):
        self.id = task_id
        self.kind = kind
        self.opts = dict(opts or {})
        self.label = _LABELS.get(kind, kind)
        self.status = "queued"            # queued | running | done | error
        self.created_at = time.time()
        self.started_at = None
        self.finished_at = None
        self.logs: List[_LogLine] = []
        self._logs_lock = threading.Lock()
        self.stage_index = -1
        self.stage = "排队中"
        self.progress = 0
        self.result = None
        self.error = None

    def append_log(self, ts, level, msg):
        with self._logs_lock:
            stages = _STAGES.get(self.kind, [])
            for idx, (name, keys) in enumerate(stages):
                if any(k in msg for k in keys) and idx > self.stage_index:
                    self.stage_index = idx
                    self.stage = name
                    self.progress = int((idx + 1) / len(stages) * 100)
            self.logs.append(_LogLine(ts, level, msg))
            if len(self.logs) > 4000:
                del self.logs[: len(self.logs) - 4000]

    def to_dict(self, tail=200):
        with self._logs_lock:
            logs = [{"ts": l.ts, "level": l.level, "msg": l.msg}
                    for l in self.logs[-tail:]]
            total = len(self.logs)
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "stage": self.stage,
            "progress": self.progress,
            "result": self.result,
            "error": self.error,
            "logs": logs,
            "log_total": total,
        }


# --------------------------------------------------------------------------- #
# 任务管理器（单工作者串行队列）                                              #
# --------------------------------------------------------------------------- #

_pipeline_main = None


def _get_main():
    global _pipeline_main
    if _pipeline_main is None:
        import main as m
        _pipeline_main = m
    return _pipeline_main


def _new_id():
    return "t" + datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:6]


def _build_args(opts):
    a = types.SimpleNamespace()
    a.dry_run = bool(opts.get("dry_run", True))
    a.debug = bool(opts.get("debug", False))
    a.limit = int(opts.get("limit") or 0)
    a.no_move = bool(opts.get("no_move", False))
    a.trash_dup = bool(opts.get("trash_dup", False))
    a.skip_vip = bool(opts.get("skip_vip", False))
    a.skip_fingerprint = bool(opts.get("skip_fingerprint", False))
    a.skip_tag_update = bool(opts.get("skip_tag_update", False))
    a.skip_check = bool(opts.get("skip_check", False))
    a.skip_organize = bool(opts.get("skip_organize", False))
    a.fix = bool(opts.get("fix", False))
    a.report_dir = opts.get("report_dir") or None
    a.month = opts.get("month") or None
    return a


def _resolve_month(opts, args):
    m = opts.get("month")
    if m and utils.validate_month_format(str(m)):
        return str(m)
    # 跳过 VIP 解密时不需要月份
    if args.skip_vip:
        return None
    return utils.get_current_month()


def _dispatch(kind, args, month):
    m = _get_main()
    if kind == "pipeline":
        return m.flow_pipeline(month, args)
    if kind == "check":
        return m.flow_check(args)
    if kind == "decrypt":
        return m.flow_decrypt(month, args)
    if kind == "dedupe":
        return m.flow_dedupe(args, with_temp=True)
    if kind == "dedupe-report":
        return m.flow_dedupe_report(args)
    if kind == "manual-archive":
        return m.flow_manual_archive(args)
    raise ValueError("unknown kind: " + kind)


def _capture_result(res):
    if res is None:
        return None
    summary_attr = getattr(res, "summary", None)
    if isinstance(summary_attr, list):
        # core.report.Report
        return {"type": "report", "title": getattr(res, "title", ""),
                "summary": [list(x) for x in summary_attr]}
    if callable(summary_attr):
        try:
            return {"type": "text", "text": str(summary_attr())}
        except Exception:  # noqa: BLE001
            pass
    if isinstance(res, list):
        items = []
        for r in res:
            items.append({
                "name": getattr(r, "name", str(r)),
                "ok": getattr(r, "ok", None),
                "encrypted": getattr(r, "encrypted", None),
                "produced": getattr(r, "produced", None),
                "message": getattr(r, "message", ""),
            })
        return {"type": "decrypt", "items": items}
    return {"type": "text", "text": str(res)}


class TaskManager:
    def __init__(self):
        self._queue: "queue.Queue" = queue.Queue()
        self._tasks: Dict[str, Task] = {}
        self._order: List[str] = []
        self._lock = threading.Lock()
        self._worker: Optional[threading.Thread] = None
        self._started = False
        self._max_keep = 20
        self._sentinel = object()

    def _ensure_worker(self):
        if self._started:
            return
        with self._lock:
            if self._started:
                return
            self._worker = threading.Thread(target=self._loop, daemon=True)
            self._worker.start()
            self._started = True

    def submit(self, kind, opts=None):
        _get_main()  # 提前确认流水线入口可用，不可用立即报错
        task = Task(_new_id(), kind, opts)
        with self._lock:
            self._tasks[task.id] = task
            self._order.append(task.id)
            while len(self._order) > self._max_keep:
                old = self._order.pop(0)
                self._tasks.pop(old, None)
        self._ensure_worker()
        self._queue.put(task)
        return task

    def get(self, task_id):
        with self._lock:
            return self._tasks.get(task_id)

    def list(self):
        with self._lock:
            return [self._tasks[tid] for tid in reversed(self._order)]

    def _loop(self):
        while True:
            task = self._queue.get()
            if task is None:
                self._queue.task_done()
                break
            try:
                self._run(task)
            finally:
                self._queue.task_done()

    def _run(self, task):
        task.status = "running"
        task.started_at = time.time()
        task.stage = "启动"
        args = _build_args(task.opts)
        month = _resolve_month(task.opts, args)
        logger = utils.main_logger
        handler = _TaskHandler(task)
        handler.setLevel(logging.DEBUG)
        try:
            logger.addHandler(handler)
            if not args.dry_run:
                try:
                    utils.ensure_dirs()
                except Exception:  # noqa: BLE001
                    pass
            try:
                raw = _dispatch(task.kind, args, month)
            except Exception as exc:  # noqa: BLE001
                task.error = f"{type(exc).__name__}: {exc}"
                logger.exception("任务执行异常")
                task.status = "error"
                return
            task.result = _capture_result(raw)
        finally:
            logger.removeHandler(handler)
            handler.close()
        task.status = "done"
        task.progress = 100
        task.stage = "完成"
        task.finished_at = time.time()


manager = TaskManager()
