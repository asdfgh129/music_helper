# -*- coding: utf-8 -*-
"""
music_helper Web UI —— FastAPI 后端

前端是 `web/static/` 下的 Vue 3 六步向导（无构建，Vue 运行时随仓库分发）。
本模块只做三件事：读配置 / 给出每一步的预览 / 提交后台任务，业务逻辑全部在
`services.steps`，判定规则全部在 `core/`，破坏性动作只走 `core.ops.Plan`。

向导接口（六步）：
  GET  /api/wizard/state      向导初始状态：目录设置 + 库状态 + 平台能力 + 默认月份
  POST /api/wizard/dirs       保存目录设置（写入 config.ini 并热重载）
  GET  /api/fs/list           目录浏览（选目录弹窗）
  POST /api/fs/mkdir          新建目录
  GET  /api/library/status    库是否已初始化
  POST /api/library/init      初始化（建目录 + 建声纹库）→ 后台任务
  GET  /api/copy/preview      第 3 步预览：待拷贝文件（按源目录分组）
  POST /api/copy/run          第 3 步执行 → 后台任务
  GET  /api/decrypt/preview   第 4 步预览：待解密文件
  POST /api/decrypt/run       第 4 步执行（VIP 目录直解到工作区）→ 后台任务
  GET  /api/tags/preview      第 5 步预览：工作区文件与标签/歌词缺失情况
  POST /api/tags/run          第 5 步执行 → 后台任务
  GET  /api/archive/preview   第 6 步预览：按 <年代>/<年份> 分组
  POST /api/archive/run       第 6 步执行 → 后台任务
  GET  /api/workspace/files   工作区文件列表（拷贝/解密页右栏）

保留的旧接口（CLI 时代的仪表盘与脚本仍可用）：
  GET  /api/config /api/platform /api/scan /api/reports /api/reports/view
  POST /api/check /api/plan/preview /api/plan/execute /api/decrypt
  GET|POST /api/tasks、GET /api/tasks/{id}

运行：
    python -m uvicorn web.api:app --host 127.0.0.1 --port 8000
浏览器打开 http://127.0.0.1:8000/
"""

import os
import sys
from datetime import datetime
from typing import Optional  # noqa: F401  （保留给旧接口的类型注解）

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import config  # noqa: E402
import core.check as checker  # noqa: E402
import core.ops as ops  # noqa: E402
import core.scan as scanner  # noqa: E402
import utils  # noqa: E402
from services import steps  # noqa: E402
from web.tasks import manager, supported_actions  # noqa: E402

# 初始化日志（供解密等需要 logger 的流程使用；失败也降级，不阻塞启动）
try:
    utils.setup_logging()
except Exception:  # noqa: BLE001
    pass

WEB_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(WEB_DIR, "static")
LEGACY_INDEX = os.path.join(WEB_DIR, "index.html")

app = FastAPI(title="music_helper Web UI", version="0.3")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# 单进程内缓存最近一次检查结果：target -> CheckResult（供预览/执行复用，避免重复扫描大库）
_last_check = {}


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
    kind: str                           # pipeline | check | copy | tags | archive ...
    opts: dict = {}                     # dry_run / month / paths / into_library ...


class DirsReq(BaseModel):
    values: dict = {}                   # {library_dir: 'D:\\music', ...}


class InitReq(BaseModel):
    make_db: bool = True                # 是否同时建立声纹库


class CopyRunReq(BaseModel):
    paths: list = []                    # 空 = 全部候选
    month: str = ""                     # 单月优先（YYYYMM）
    month_from: str = ""
    month_to: str = ""


class DecryptRunReq(BaseModel):
    paths: list = []
    month_from: str = ""
    month_to: str = ""


class TagsRunReq(BaseModel):
    paths: list = []
    with_fingerprint: bool = True
    write_cover: bool = True
    write_lyrics: bool = True


class ArchiveRunReq(BaseModel):
    into_library: bool = True           # True 直接入库，False 在工作区内整理
    move_incomplete: bool = True        # 不可归档的移入待确认目录


class MkdirReq(BaseModel):
    path: str = ""


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


def _fmt_time(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def _month_options(months=120):
    """月份下拉：最近 N 个月，新的在前"""
    today = datetime.now()
    year, month = today.year, today.month
    items = []
    for _ in range(months):
        items.append(f"{year:04d}{month:02d}")
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return items


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


def _submit(kind, opts):
    """提交向导任务并返回前端需要的字段"""
    if not any(action["kind"] == kind for action in supported_actions()):
        raise HTTPException(status_code=400, detail=f"不支持的动作: {kind}")
    try:
        task = manager.submit(kind, opts)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"任务提交失败: {exc}")
    return {"ok": True, "task_id": task.id, "kind": task.kind,
            "label": task.label, "status": task.status}


# --------------------------------------------------------------------------- #
# 引导 / 目录 / 库状态（向导第 1、2 步）                                       #
# --------------------------------------------------------------------------- #

@app.get("/api/wizard/state")
def api_wizard_state():
    """向导初始状态：一次请求拿到六步需要的静态信息"""
    return {
        "ok": True,
        "version": config.__version__,
        "dirs": steps.directories(),
        "library": steps.library_status(),
        "platform": _platform_info(),
        "problems": config.validate(),
        "month": utils.get_current_month(),
        "months": _month_options(),
        "busy": manager.busy(),
        "ini_path": config.ini_path(),
    }


@app.post("/api/wizard/dirs")
def api_wizard_dirs(req: DirsReq):
    """保存目录设置：写 config.ini → config.reload() → 返回最新状态"""
    if manager.busy():
        raise HTTPException(status_code=409, detail="有任务正在运行，先等它结束再改目录")
    problems, dirs = steps.save_directories(req.values)
    if problems:
        return JSONResponse({"ok": False, "problems": problems, "dirs": dirs},
                            status_code=400)
    return {"ok": True, "problems": [], "dirs": dirs,
            "library": steps.library_status()}


@app.get("/api/library/status")
def api_library_status():
    return {"ok": True, "library": steps.library_status()}


@app.post("/api/library/init")
def api_library_init(req: InitReq):
    return _submit("init", {"make_db": req.make_db})


@app.get("/api/fs/list")
def api_fs_list(path: str = ""):
    """目录浏览（给「选择目录」弹窗用）

    只列目录，不读文件内容；路径越权由操作系统权限兜底（这是本机工具，
    服务默认只监听 127.0.0.1）。
    """
    target = (path or "").strip()
    drives = []
    shortcuts = []
    for label, value in (("库目录", config.LIBRARY_DIR), ("工作区", config.WORKSPACE_DIR),
                         ("网易云", config.NETEASE_DIR), ("QQ音乐", config.QQ_DIR),
                         ("待确认", config.INCOMPLETE_DIR), ("重复文件", config.DUPLICATE_DIR)):
        if value and os.path.isdir(value):
            shortcuts.append({"label": label, "path": value})

    if not target:
        if os.name == "nt":
            import string
            for letter in string.ascii_uppercase:
                root = f"{letter}:\\"
                if os.path.exists(root):
                    drives.append({"name": root, "path": root})
        else:
            target = os.path.expanduser("~")

    dirs = []
    parent = ""
    if target and os.path.isdir(target):
        target = os.path.abspath(target)
        parent = os.path.dirname(target.rstrip("\\/")) or target
        try:
            for name in sorted(os.listdir(target)):
                full = os.path.join(target, name)
                if os.path.isdir(full):
                    dirs.append({"name": name, "path": full})
        except PermissionError:
            raise HTTPException(status_code=403, detail=f"没有权限读取: {target}")
        except OSError as exc:
            raise HTTPException(status_code=400, detail=f"读取失败: {exc}")
    elif target:
        raise HTTPException(status_code=404, detail=f"目录不存在: {target}")

    return {"ok": True, "path": target, "parent": parent, "dirs": dirs,
            "drives": drives, "shortcuts": shortcuts,
            "exists": os.path.isdir(target) if target else False}


@app.post("/api/fs/mkdir")
def api_fs_mkdir(req: MkdirReq):
    """新建目录（选择器里「不存在就建一个」）"""
    path = (req.path or "").strip()
    if not path or not config.is_absolute_path(path):
        raise HTTPException(status_code=400, detail="请填写绝对路径")
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"创建失败: {exc}")
    return {"ok": True, "path": os.path.abspath(path)}


# --------------------------------------------------------------------------- #
# 第 3 步：拷贝                                                               #
# --------------------------------------------------------------------------- #

@app.get("/api/copy/preview")
def api_copy_preview(month: str = "", month_from: str = "", month_to: str = ""):
    data = steps.copy_candidates(month=month or None,
                                 month_from=month_from or None,
                                 month_to=month_to or None)
    return {"ok": True, **data, "workspace": _workspace_files()}


@app.post("/api/copy/run")
def api_copy_run(req: CopyRunReq):
    opts = {"paths": req.paths, "month": req.month,
            "month_from": req.month_from, "month_to": req.month_to}
    return _submit("copy", opts)


# --------------------------------------------------------------------------- #
# 第 4 步：解密                                                               #
# --------------------------------------------------------------------------- #

@app.get("/api/decrypt/preview")
def api_decrypt_preview(month_from: str = "", month_to: str = ""):
    data = steps.decrypt_candidates(month_from=month_from or None,
                                    month_to=month_to or None)
    return {"ok": True, **data, "workspace": _workspace_files(),
            "platform": _platform_info()}


@app.post("/api/decrypt/run")
def api_decrypt_run(req: DecryptRunReq):
    return _submit("decrypt-direct", {"paths": req.paths,
                                      "month_from": req.month_from,
                                      "month_to": req.month_to})


# --------------------------------------------------------------------------- #
# 第 5 步：标签 / 歌词                                                        #
# --------------------------------------------------------------------------- #

@app.get("/api/tags/preview")
def api_tags_preview():
    return {"ok": True, **steps.tag_candidates()}


@app.post("/api/tags/run")
def api_tags_run(req: TagsRunReq):
    return _submit("tags", {"paths": req.paths,
                            "with_fingerprint": req.with_fingerprint,
                            "write_cover": req.write_cover,
                            "write_lyrics": req.write_lyrics})


# --------------------------------------------------------------------------- #
# 第 6 步：归档                                                               #
# --------------------------------------------------------------------------- #

@app.get("/api/archive/preview")
def api_archive_preview(into_library: bool = True):
    return {"ok": True, **steps.archive_preview(into_library=into_library)}


@app.post("/api/archive/run")
def api_archive_run(req: ArchiveRunReq):
    return _submit("archive", {"into_library": req.into_library,
                               "move_incomplete": req.move_incomplete})


# --------------------------------------------------------------------------- #
# 工作区文件（拷贝/解密页右栏）                                                #
# --------------------------------------------------------------------------- #

def _workspace_files(limit=2000):
    directory = config.WORKSPACE_DIR
    if not os.path.isdir(directory):
        return {"dir": directory, "exists": False, "files": [], "total": 0, "bytes": 0}
    tracks = scanner.scan([directory], with_tags=False, recursive=False)
    files = [{
        "name": track.filename,
        "size": track.size,
        "month": scanner.month_of(track.path),
        "ext": track.ext,
        "has_lrc": track.has_lrc,
    } for track in tracks[:limit]]
    return {"dir": directory, "exists": True, "files": files,
            "total": len(tracks), "truncated": len(tracks) > limit,
            "bytes": sum(track.size for track in tracks)}


@app.get("/api/workspace/files")
def api_workspace_files():
    return {"ok": True, **_workspace_files()}


# --------------------------------------------------------------------------- #
# 旧接口（保留：仪表盘与脚本还在用）                                          #
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
    return {"ok": True, "tasks": items, "supported": supported_actions(),
            "busy": manager.busy()}


@app.post("/api/tasks")
def api_task_submit(req: TaskReq):
    """提交一个后台任务（串行执行），立即返回 task_id 供前端轮询"""
    return _submit(req.kind, req.opts)


@app.get("/api/tasks/{task_id}")
def api_task_get(task_id: str):
    """轮询单个任务：状态 / 阶段进度 / 日志 / 结果"""
    task = manager.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"ok": True, **task.to_dict()}


# --------------------------------------------------------------------------- #
# 页面                                                                        #
# --------------------------------------------------------------------------- #

@app.get("/", response_class=HTMLResponse)
def index():
    path = os.path.join(STATIC_DIR, "index.html")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return "<h1>web/static/index.html 未找到</h1>"


@app.get("/legacy", response_class=HTMLResponse)
def legacy_index():
    """旧版仪表盘（配置状态 / 报告 / 任务日志），排查问题时仍然好用"""
    return FileResponse(LEGACY_INDEX)
