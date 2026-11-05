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
    # 向导六步（第 2a/2b 步单独成任务，方便复用同一条进度通道）
    "init": "初始化库目录",
    "copy": "拷贝下载文件到工作区",
    "decrypt-direct": "直接解密到工作区",
    "tags": "标签与歌词补全",
    "archive": "按年份归档",
}

_SUPPORTED = [
    {"kind": "init", "label": "初始化库目录",
     "desc": "建目录结构 + 建声纹库（幂等，不动文件）", "default_dry_run": False},
    {"kind": "copy", "label": "拷贝下载文件",
     "desc": "下载目录（非 VIP）→ 工作区", "default_dry_run": False},
    {"kind": "decrypt-direct", "label": "直接解密",
     "desc": "VIP 目录 → 工作区，不经过暂存区", "default_dry_run": False},
    {"kind": "tags", "label": "标签与歌词补全",
     "desc": "声纹/在线平台补标签、封面、歌词", "default_dry_run": False},
    {"kind": "archive", "label": "按年份归档",
     "desc": "工作区 → <年代>/<年份>/（可入库）", "default_dry_run": False},
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

# 走 services.steps 的向导任务（有逐条进度，结果直接是 JSON 字典）
_WIZARD_KINDS = ("init", "copy", "decrypt-direct", "tags", "archive")


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
        # 逐条进度：向导需要「第几个文件 / 一共几个 / 当前在做什么」
        self.total = 0
        self.done = 0
        self.current = ""
        self.items: List[dict] = []
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

    def set_progress(self, done, total, item=None):
        """业务回调：更新条数进度（比按日志关键字猜阶段准确得多）"""
        self.done = int(done or 0)
        self.total = int(total or 0)
        if self.total:
            self.progress = min(99, int(self.done / self.total * 100))
        item = item or {}
        name = item.get("name") or item.get("message") or ""
        if name:
            self.current = str(name)
            self.stage = f"{self.done}/{self.total}"
        if item:
            self.items.append(item)
            if len(self.items) > 2000:
                del self.items[: len(self.items) - 2000]

    def progress_cb(self):
        return self.set_progress

    def to_dict(self, tail=200):
        with self._logs_lock:
            logs = [{"ts": line.ts, "level": line.level, "msg": line.msg}
                    for line in self.logs[-tail:]]
            total_logs = len(self.logs)
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
            "total": self.total,
            "done": self.done,
            "current": self.current,
            "items": self.items[-tail:],
            "result": self.result,
            "error": self.error,
            "logs": logs,
            "log_total": total_logs,
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


def _dispatch_wizard(task):
    """向导逐步任务：直接调 services.steps，进度走 task.set_progress"""
    from services import steps

    kind, opts = task.kind, task.opts
    progress = task.progress_cb()
    if kind == "init":
        return steps.init_library(make_db=bool(opts.get("make_db", True)),
                                  progress=progress)
    if kind == "copy":
        return steps.run_copy(paths=opts.get("paths") or None,
                              month=opts.get("month") or None,
                              month_from=opts.get("month_from") or None,
                              month_to=opts.get("month_to") or None,
                              progress=progress)
    if kind == "decrypt-direct":
        months = (opts.get("month_from") or None, opts.get("month_to") or None)
        return steps.run_decrypt(months=months, paths=opts.get("paths") or None,
                                 progress=progress)
    if kind == "tags":
        return steps.run_fill_tags(paths=opts.get("paths") or None,
                                   with_fingerprint=bool(opts.get("with_fingerprint", True)),
                                   write_cover=bool(opts.get("write_cover", True)),
                                   write_lyrics=bool(opts.get("write_lyrics", True)),
                                   progress=progress)
    if kind == "archive":
        return steps.run_archive(into_library=bool(opts.get("into_library", True)),
                                 move_incomplete=bool(opts.get("move_incomplete", True)),
                                 progress=progress)
    raise ValueError("unknown wizard kind: " + kind)


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

    def busy(self):
        """有没有排队/执行中的任务（向导里禁止在跑任务时改配置）"""
        return any(task.status in ("queued", "running") for task in self.list())

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
        logger = utils.main_logger
        handler = _TaskHandler(task)
        handler.setLevel(logging.DEBUG)
        wizard = task.kind in _WIZARD_KINDS
        args = None if wizard else _build_args(task.opts)
        try:
            logger.addHandler(handler)
            # 向导步骤自己负责建目录（init 就是干这个的）；CLI 流程沿用老规矩：
            # 只有真执行（非试运行）才建目录
            if args is not None and not args.dry_run:
                try:
                    utils.ensure_dirs()
                except Exception:  # noqa: BLE001 - 建目录失败交给具体步骤报错
                    pass
            try:
                if wizard:
                    task.result = _dispatch_wizard(task)
                else:
                    month = _resolve_month(task.opts, args)
                    task.result = _capture_result(_dispatch(task.kind, args, month))
            except Exception as exc:  # noqa: BLE001
                task.error = f"{type(exc).__name__}: {exc}"
                logger.exception("任务执行异常")
                task.status = "error"
                task.finished_at = time.time()
                return
        finally:
            logger.removeHandler(handler)
            handler.close()
        task.status = "done"
        task.progress = 100
        task.stage = "完成"
        task.finished_at = time.time()


manager = TaskManager()
