# -*- coding: utf-8 -*-
"""
music_helper Web UI —— FastAPI 实现（阶段 0 → 阶段 3）

能力一览（全部复用既有 core / services / config，不修改业务代码；破坏性动作只走 core.ops.Plan）：

  GET  /api/config        配置校验（config.validate）+ 外部程序预检（utils.tool_problem）
  GET  /api/platform      运行机器 OS + 解密能力矩阵（★OS 感知：解密随运行平台分支）
  GET  /api/scan          音乐库 / 工作区扫描统计（core.scan.scan，可选读标签）
  POST /api/check         运行检查，返回 findings，并缓存 CheckResult 供预览/执行复用
  POST /api/plan/preview  基于检查结果生成 dry-run 计划，返回将执行的操作清单
  POST /api/plan/execute  执行计划（走 Plan.execute），返回 done/skipped/failed + journal
  GET  /api/reports       历史报告列表（log/reports）
  GET  /api/reports/view  单份报告预览（.md / .csv）
  POST /api/decrypt       按 OS 路由的解密动作（默认 dry_run 预览；复用 services.decrypt）
  GET  /api/tasks         近期任务列表 + 支持的动作清单（阶段 4）
  POST /api/tasks         提交后台任务（流水线/检查/解密/去重…），立即返回 task_id
  GET  /api/tasks/{id}    轮询任务：状态 / 阶段进度 / 实时日志 / 结果（阶段 4）

运行：
    python -m uvicorn web.api:app --host 127.0.0.1 --port 8000
浏览器打开 http://127.0.0.1:8000/
"""

import os
import sys
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import config
import utils
import core.scan as scanner
import core.check as checker
import core.ops as ops
from web.tasks import manager, supported_actions

# 初始化日志（供解密等需要 logger 的流程使用；失败也降级，不阻塞启动）
try:
    utils.setup_logging()
except Exception:  # noqa: BLE001
    pass

app = FastAPI(title="music_helper Web UI", version="0.2")

# 单进程内缓存最近一次检查结果：target -> CheckResult（供预览/执行复用，避免重复扫描大库）
_last_check = {}

INDEX_PATH = os.path.join(os.path.dirname(__file__), "index.html")


# --------------------------------------------------------------------------- #
# 请求模型                                                                    #
# --------------------------------------------------------------------------- #

class CheckReq(BaseModel):
    target: str = "workspace"          # library | workspace
    check_tags: bool = True
    check_lyrics: bool = True
    check_duplicates: bool = True


class PlanReq(BaseModel):
    target: str = "workspace"
    move_bad: bool = False             # 把严重缺失/矛盾文件移入待补全目录
    delete_duplicates: bool = False    # 重复文件直接进回收站（默认只报告）
    rename_by_tags: bool = True        # 文件名缺结构时按标签全名重写
    dry_run: bool = True               # 仅预览用；execute 接口会强制 False


class DecryptReq(BaseModel):
    target: str = "netease"           # netease | qq
    dry_run: bool = True


class TaskReq(BaseModel):
    kind: str                           # pipeline | check | decrypt | dedupe | dedupe-report | manual-archive
    opts: dict = {}                     # dry_run / month / skip_* / no_move / trash_dup / fix / limit ...


# --------------------------------------------------------------------------- #
# 序列化（core 对象是 dataclass，转成前端友好的纯字典）                          #
# --------------------------------------------------------------------------- #

def _serialize_finding(item):
    return {
        "kind": item.kind,
        "path": item.path,
        "detail": item.detail,
        "fixable": item.fixable,
        "severe": item.severe,
    }


def _serialize_group(group):
    keep = group.keep
    return {
        "kind": group.kind,
        "key": str(group.key),
        "keep": keep.path if keep else "",
        "keep_name": keep.filename if keep else "",
        "duration_unknown": group.duration_unknown,
        "drop": [{"path": t.path, "name": t.filename} for t in group.drop],
    }


def _serialize_result(result):
    return {
        "counts": result.counts(),
        "findings": [_serialize_finding(f) for f in result.findings],
        "groups": [_serialize_group(g) for g in result.groups],
    }


# --------------------------------------------------------------------------- #
# 业务封装（只读 / 计划 / 解密）                                               #
# --------------------------------------------------------------------------- #

def _target_dir(target):
    return config.LIBRARY_DIR if target == "library" else config.WORKSPACE_DIR


def _get_or_run(target, opts):
    """取缓存的 CheckResult；没有则按完整检查重新跑一次"""
    cached = _last_check.get(target)
    if cached is not None:
        return cached
    directory = _target_dir(target)
    if not os.path.isdir(directory):
        return None
    tracks = scanner.scan([directory], with_tags=True, recursive=True)
    return checker.check_library(
        tracks, directories=[directory],
        check_tags=opts.get("check_tags", True),
        check_lyrics=opts.get("check_lyrics", True),
        check_duplicates=opts.get("check_duplicates", True),
    )


def _build_plan(result, req: PlanReq, dry_run: bool):
    plan = ops.Plan(
        f"WebUI-修复-{req.target}",
        dry_run=dry_run,
        journal_path=config.JOURNAL_PATH,
        trash_dir=config.TRASH_DIR,
    )
    checker.plan_fixes(
        result, plan,
        review_dir=config.INCOMPLETE_DIR,
        rename_canonical=True,
        move_bad=req.move_bad,
        delete_duplicates=req.delete_duplicates,
        dup_dir=config.DUPLICATE_DIR,
        rename_by_tags=req.rename_by_tags,
    )
    return plan


def _platform_info():
    """运行机器 OS + 解密能力矩阵（解密随平台分支，不假设只在 Windows）"""
    is_win = os.name == "nt"
    is_mac = sys.platform == "darwin"
    um_ok = utils.tool_problem(config.UM_EXE, "um") == ""

    netease = {
        "available": um_ok,
        "backend": "um（三平台通用，.ncm 免密钥）",
        "vip_dir": config.NETEASE_VIP_DIR,
    }
    if is_win:
        qq_backend = ("Frida 注入（需 QQ 音乐客户端已安装/启动/登录）" if um_ok
                      else "Frida 注入 或 um 离线解密")
    elif is_mac:
        qq_backend = "um 离线（旧版 qmc 免密钥；新版 qmc2 需 mmkv+key）"
    else:
        qq_backend = "um 离线（需本机存在加密文件；新版 qmc2 可能需凭据）"

    return {
        "ok": True,
        "os": utils.platform_label(),
        "is_windows": is_win,
        "is_macos": is_mac,
        "um_available": um_ok,
        "netease": netease,
        "qq": {"backend": qq_backend, "vip_dir": config.QQ_VIP_DIR},
        "note": ("解密随运行平台分支：Windows 优先 Frida、其余走 um；"
                 "macOS 走 um（8.8.0 客户端旧版 qmc 免密钥）。"
                 "无图形客户端的环境（如纯服务器）仅能处理离线可解的文件。"),
    }


# --------------------------------------------------------------------------- #
# 路由                                                                        #
# --------------------------------------------------------------------------- #

@app.get("/api/config")
def api_config():
    tools = []
    for name, path in (
        ("声纹去重", config.SOUNDALIKE_EXE),
        ("fpcalc", config.FPCALC_EXE),
        ("um 解密", config.UM_EXE),
    ):
        problem = utils.tool_problem(path, name)
        tools.append({"name": name, "path": path, "ok": not problem,
                      "detail": problem or "可用"})
    return {"ok": True, "config": config.as_dict(),
            "problems": config.validate(), "tools": tools}


@app.get("/api/platform")
def api_platform():
    return _platform_info()


@app.get("/api/scan")
def api_scan(target: str = "workspace", with_tags: bool = False):
    directory = _target_dir(target)
    if not os.path.isdir(directory):
        return JSONResponse({"ok": False, "error": f"目录不存在: {directory}"},
                            status_code=400)
    tracks = scanner.scan([directory], with_tags=with_tags, recursive=True)
    ext_counts = {}
    total_bytes = 0
    missing_title = missing_artist = missing_cover = 0
    for t in tracks:
        ext_counts[t.ext] = ext_counts.get(t.ext, 0) + 1
        total_bytes += t.size
        if with_tags:
            if not t.title:
                missing_title += 1
            if not t.artist:
                missing_artist += 1
            if t.has_cover is False:
                missing_cover += 1
    return {
        "ok": True, "target": target, "directory": directory,
        "count": len(tracks), "total_bytes": total_bytes,
        "ext_counts": dict(sorted(ext_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "with_tags": with_tags,
        "missing_title": missing_title, "missing_artist": missing_artist,
        "missing_cover": missing_cover,
    }


@app.post("/api/check")
def api_check(req: CheckReq):
    directory = _target_dir(req.target)
    if not os.path.isdir(directory):
        raise HTTPException(status_code=400, detail=f"目录不存在: {directory}")
    tracks = scanner.scan([directory], with_tags=True, recursive=True)
    result = checker.check_library(
        tracks, directories=[directory],
        check_tags=req.check_tags, check_lyrics=req.check_lyrics,
        check_duplicates=req.check_duplicates,
    )
    _last_check[req.target] = result
    payload = {"ok": True, "target": req.target, "directory": directory,
               "scanned": len(tracks)}
    payload.update(_serialize_result(result))
    return payload


@app.post("/api/plan/preview")
def api_plan_preview(req: PlanReq):
    result = _get_or_run(req.target, req.model_dump())
    if result is None:
        raise HTTPException(status_code=400, detail="目录不存在，无法生成计划")
    plan = _build_plan(result, req, dry_run=True)
    return {"ok": True, "dry_run": True, "count": len(plan),
            "actions": [op.describe() for op in plan.operations],
            "describe": plan.describe()}


@app.post("/api/plan/execute")
def api_plan_execute(req: PlanReq):
    result = _get_or_run(req.target, req.model_dump())
    if result is None:
        raise HTTPException(status_code=400, detail="目录不存在，无法执行")
    plan = _build_plan(result, req, dry_run=False)
    if plan.is_empty:
        return {"ok": True, "dry_run": False, "count": 0,
                "summary": "无需处理", "done": [], "skipped": [], "failed": [],
                "journal": config.JOURNAL_PATH}
    pres = plan.execute()
    return {
        "ok": True, "dry_run": False, "count": pres.total,
        "summary": pres.summary(),
        "done": [op.describe() for op in pres.done],
        "skipped": [op.describe() for op in pres.skipped],
        "failed": [op.describe() for op in pres.failed],
        "journal": config.JOURNAL_PATH,
    }


@app.get("/api/reports")
def api_reports():
    directory = config.REPORT_DIR
    items = []
    if os.path.isdir(directory):
        for name in os.listdir(directory):
            if not (name.endswith(".md") or name.endswith(".csv")):
                continue
            path = os.path.join(directory, name)
            if not os.path.isfile(path):
                continue
            st = os.stat(path)
            items.append({
                "name": name,
                "type": "markdown" if name.endswith(".md") else "csv",
                "size": st.st_size, "mtime": st.st_mtime,
                "mtime_str": _fmt_time(st.st_mtime),
            })
    items.sort(key=lambda i: i["mtime"], reverse=True)
    return {"ok": True, "directory": directory, "reports": items}


@app.get("/api/reports/view")
def api_reports_view(name: str = ""):
    directory = config.REPORT_DIR
    if not name or not (name.endswith(".md") or name.endswith(".csv")):
        raise HTTPException(status_code=400, detail="非法文件名")
    safe = os.path.basename(name)
    path = os.path.normpath(os.path.join(directory, safe))
    if not path.startswith(os.path.normpath(directory)) or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="文件不存在或越界")
    with open(path, "r", encoding="utf-8") as handle:
        content = handle.read()
    return {"ok": True, "name": safe,
            "type": "markdown" if safe.endswith(".md") else "csv",
            "content": content}


@app.post("/api/decrypt")
def api_decrypt(req: DecryptReq):
    """按 OS 路由的解密动作（复用 services.decrypt，其已按平台选后端）"""
    try:
        import services.decrypt as dec
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"解密模块不可用: {exc}")
    logger = getattr(utils, "main_logger", None)
    if req.target == "netease":
        res = dec.decrypt_netease(month=None, dry_run=req.dry_run, logger=logger)
    elif req.target == "qq":
        res = dec.decrypt_qq(month=None, dry_run=req.dry_run, logger=logger)
    else:
        raise HTTPException(status_code=400, detail="未知 target（netease/qq）")
    return {"ok": True, "target": req.target, "dry_run": req.dry_run,
            "name": res.name, "encrypted": res.encrypted,
            "produced": res.produced, "result_ok": res.ok,
            "message": res.message}


@app.get("/api/tasks")
def api_tasks():
    """列出近期任务 + 支持的动作清单"""
    items = [t.to_dict(tail=0) for t in manager.list()]
    return {"ok": True, "tasks": items, "supported": supported_actions()}


@app.post("/api/tasks")
def api_task_submit(req: TaskReq):
    """提交一个后台任务（串行执行），立即返回 task_id 供前端轮询"""
    if not any(a["kind"] == req.kind for a in supported_actions()):
        raise HTTPException(status_code=400, detail=f"不支持的动作: {req.kind}")
    try:
        task = manager.submit(req.kind, req.opts)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"任务提交失败: {exc}")
    return {"ok": True, "task_id": task.id, "kind": task.kind, "label": task.label,
            "status": task.status}


@app.get("/api/tasks/{task_id}")
def api_task_get(task_id: str):
    """轮询单个任务：状态 / 阶段进度 / 日志 / 结果"""
    task = manager.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"ok": True, **task.to_dict()}


@app.get("/", response_class=HTMLResponse)
def index():
    try:
        with open(INDEX_PATH, "r", encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return "<h1>index.html 未找到</h1>"


def _fmt_time(ts):
    from datetime import datetime
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
