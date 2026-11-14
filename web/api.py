# -*- coding: utf-8 -*-
"""
music_helper Web UI —— FastAPI 后端

前端是 `web/static/` 下的 Vue 3 八步向导（无构建，Vue 运行时随仓库分发）。
本模块只做三件事：读配置 / 给出每一步的预览 / 提交后台任务，业务逻辑全部在
`services.steps`，判定规则全部在 `core/`，破坏性动作只走 `core.ops.Plan`。

向导接口（八步）：
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
  POST /api/tags/run          第 5 步执行（可限定写入字段）→ 后台任务
  GET  /api/track             第 5 步单曲详情
  POST /api/track/save        第 5 步单曲保存（不改文件名）
  POST /api/track/fetch       第 5 步在线取标签（只预览，不写盘）
  GET  /api/dedupe/preview    第 6 步预览：工作区 vs 库目录
  POST /api/dedupe/run        第 6 步执行（重复的移走；库里音质更低的旧版本让位）→ 后台任务
  GET  /api/selfcheck/preview 第 7 步：工作区自检（只读）
  POST /api/selfcheck/run     第 7 步自检 → 后台任务（文件多时用）
  GET  /api/archive/preview   第 8 步预览：按 <年代>/<年份> 分组
  POST /api/archive/run       第 8 步执行 → 后台任务
  GET  /api/workspace/files   工作区文件列表（拷贝/解密页右栏）

试听旁路（不属于八步，也不进后台任务队列；不改音乐库、不生成 Plan）：
  GET       /api/media/info    音频元数据 + 浏览器可播判定
  GET|HEAD  /api/media/stream  Range 206 字节流（transcode=1 时读派生 mp3 缓存）
  GET       /api/media/lyric   结构化 LRC（编码探测 / 时间戳 / 双语）
  GET       /api/media/cover   内嵌封面字节（无封面 404）
  POST      /api/media/lyric/parse   纯文本 -> 结构化歌词（抽屉实时预览，不写盘）
  POST      /api/media/lyric/offset  改写 [offset:] 后的全文（不写盘，落盘走 track/save）
  POST      /api/media/open    用系统默认播放器打开不可播格式
  GET       /api/media/transcode     查询本机解码状态（前端轮询）
  POST      /api/media/transcode     启动本机解码（唯一写 log/_media_cache 的入口）

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

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# 源码模式先把仓库根放进 sys.path（从任意 CWD 启动都能 import config）；
# 冻结模式下 sys._MEIPASS 已在其中，config.PROJECT_DIR 由 runtime_paths 指向 exe 所在目录。
_SOURCE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SOURCE_ROOT not in sys.path:
    sys.path.insert(0, _SOURCE_ROOT)

import config  # noqa: E402
import core.check as checker  # noqa: E402
import core.ops as ops  # noqa: E402
import core.scan as scanner  # noqa: E402
import utils  # noqa: E402
from services import media as media_service  # noqa: E402  顶层导入，PyInstaller 才扫得到
from services import steps  # noqa: E402
from services import transcode as transcode_service  # noqa: E402  同上，P2 解码子进程
from web.tasks import manager, supported_actions  # noqa: E402

PROJECT_DIR = config.PROJECT_DIR
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# 初始化日志（供解密等需要 logger 的流程使用；失败也降级，不阻塞启动）
try:
    utils.setup_logging()
except Exception:  # noqa: BLE001
    pass

# 冻结后 __file__ 指向 _internal/，静态资源实际在 exe 旁的 web/ 目录
WEB_DIR = os.path.join(PROJECT_DIR, "web")
STATIC_DIR = os.path.join(WEB_DIR, "static")
LEGACY_INDEX = os.path.join(WEB_DIR, "index.html")

app = FastAPI(title="music_helper Web UI", version="0.4")
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
    fields: Optional[list] = None       # 允许写入的标签键；None = 全部


class TrackFetchReq(BaseModel):
    path: str = ""
    fields: Optional[list] = None


class TrackSaveReq(BaseModel):
    path: str = ""
    tags: dict = {}                     # 只写传入的键；空字符串表示不改
    lyric: Optional[str] = None         # None = 不动歌词；字符串 = 覆盖写入


class DedupeRunReq(BaseModel):
    paths: list = []                    # 空 = 全部可处理的
    action: str = "move"                # move（移入重复目录）| trash（进回收站）
    refresh: bool = False               # 重新扫描库目录
    statuses: list = ["duplicate"]      # duplicate（移工作区）/ upgrade（移库里旧版本）
    # {工作区路径: [库内路径, ...]}：一个工作区文件对上库里多份时，只动勾选的那几个。
    # 不传表示该文件命中的库内旧版本全部替换。
    replaces: dict = {}


class ArchiveRunReq(BaseModel):
    into_library: bool = True           # True 直接入库，False 在工作区内整理
    move_incomplete: bool = True        # 不可归档的移入待确认目录
    write_fingerprints: bool = True     # 入库成功后补录声纹库


class MkdirReq(BaseModel):
    path: str = ""


class MediaOpenReq(BaseModel):
    path: str = ""


class MediaTranscodeReq(BaseModel):
    path: str = ""


class LyricParseReq(BaseModel):
    text: str = ""


class LyricOffsetReq(BaseModel):
    text: str = ""
    offset: int = 0


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
    """向导初始状态：一次请求拿到八步需要的静态信息"""
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
                            "write_lyrics": req.write_lyrics,
                            "fields": req.fields})


# ---------------- 单曲编辑（第 5 步的「编辑」抽屉） ----------------

@app.get("/api/track")
def api_track(path: str = ""):
    """单曲详情：标签、封面/歌词状态、文件名 ↔ 标签逐项比对"""
    try:
        return {"ok": True, **steps.track_detail(path)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/track/save")
def api_track_save(req: TrackSaveReq):
    """手工保存单曲标签 / 歌词（不改文件名）"""
    try:
        return steps.save_track(req.path, tags=req.tags, lyric=req.lyric)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/track/fetch")
def api_track_fetch(req: TrackFetchReq):
    """在线取标签（只填空缺、不写盘），返回结果供用户确认后再保存"""
    try:
        return steps.fetch_track_online(req.path, fields=req.fields)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# --------------------------------------------------------------------------- #
# 第 6 步：查重（工作区 ↔ 库目录）                                            #
# --------------------------------------------------------------------------- #

@app.get("/api/dedupe/preview")
def api_dedupe_preview(refresh: bool = False):
    return {"ok": True, **steps.dedupe_preview(refresh=refresh)}


@app.post("/api/dedupe/run")
def api_dedupe_run(req: DedupeRunReq):
    if req.action not in ("move", "trash"):
        raise HTTPException(status_code=400, detail="action 只能是 move 或 trash")
    unknown = [item for item in req.statuses if item not in ("duplicate", "upgrade")]
    if unknown:
        raise HTTPException(status_code=400,
                            detail=f"statuses 只接受 duplicate / upgrade，收到 {unknown}")
    if not req.statuses:
        raise HTTPException(status_code=400, detail="至少要选一类要处理的情况")
    if "upgrade" in req.statuses and not req.paths:
        raise HTTPException(status_code=400,
                            detail="替换库内旧版本必须逐条指定 paths，不支持全量处理")
    # replaces 只能落在本次明确指定的 paths 上，避免绕过「逐条确认」这道闸门
    stray = [key for key in req.replaces if key not in set(req.paths)]
    if stray:
        raise HTTPException(status_code=400,
                            detail=f"replaces 里的文件必须同时在 paths 中：{stray}")
    bad = [key for key, value in req.replaces.items() if not isinstance(value, list)]
    if bad:
        raise HTTPException(status_code=400,
                            detail=f"replaces 的值必须是路径数组：{bad}")
    return _submit("dedupe-cross", {"paths": req.paths, "action": req.action,
                                    "refresh": req.refresh,
                                    "statuses": req.statuses,
                                    "replaces": req.replaces})


# --------------------------------------------------------------------------- #
# 第 7 步：工作区自检                                                         #
# --------------------------------------------------------------------------- #

@app.get("/api/selfcheck/preview")
def api_selfcheck_preview():
    """同步返回自检结果（工作区文件数通常不大；文件特别多时改走任务）"""
    if not os.path.isdir(config.WORKSPACE_DIR):
        raise HTTPException(status_code=400,
                            detail=f"工作区目录不存在: {config.WORKSPACE_DIR}")
    return {"ok": True, **steps.workspace_check()}


@app.post("/api/selfcheck/run")
def api_selfcheck_run():
    return _submit("selfcheck", {})


# --------------------------------------------------------------------------- #
# 第 8 步：归档                                                               #
# --------------------------------------------------------------------------- #

@app.get("/api/archive/preview")
def api_archive_preview(into_library: bool = True):
    return {"ok": True, **steps.archive_preview(into_library=into_library)}


@app.post("/api/archive/run")
def api_archive_run(req: ArchiveRunReq):
    return _submit("archive", {"into_library": req.into_library,
                               "move_incomplete": req.move_incomplete,
                               "write_fingerprints": req.write_fingerprints})


# --------------------------------------------------------------------------- #
# 试听旁路（只读媒体层；契约见 docs/media-player.md）                          #
# --------------------------------------------------------------------------- #

def _media_target(path):
    """所有带 path 的媒体接口共用同一套白名单校验"""
    try:
        return media_service.resolve_media(path)
    except media_service.MediaError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/media/info")
def api_media_info(path: str = ""):
    return {"ok": True, **media_service.media_info(_media_target(path))}


@app.api_route("/api/media/stream", methods=["GET", "HEAD"])
def api_media_stream(request: Request, path: str = "", transcode: int = 0):
    """自行实现 Range：Starlette 各版本 FileResponse 的行为不一致，指望不上。

    只返回单段 206；多段 Range 由 services.media.parse_range 取第一段。
    HEAD 只回响应头，不读文件体。流式响应不打逐块日志。

    ``transcode=1`` 时读的是本机解码落盘的派生 MP3：路径仍由白名单校验原文件，
    缓存路径完全由服务端按 cache_key 计算，前端无法指定任意文件。
    """
    target = _media_target(path)
    if transcode:
        ext = os.path.splitext(target)[1].lower()
        if ext not in transcode_service.NEEDS_TRANSCODE:
            raise HTTPException(status_code=400,
                                detail='该格式浏览器可以直接播放，无需转码')
        source = transcode_service.ready_path(target)
        if not source:
            return JSONResponse(
                {'detail': '派生 MP3 尚未就绪，请先完成解码',
                 'transcode': transcode_service.status(target)},
                status_code=409)
        mime = 'audio/mpeg'
    else:
        source = target
        mime = media_service.mime_for(target)
    size = os.path.getsize(source)
    headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "no-store",
        "Content-Type": mime,
    }
    if request.method == "HEAD":
        return Response(status_code=200,
                        headers={**headers, "Content-Length": str(size)})
    try:
        start, end, partial = media_service.parse_range(
            request.headers.get("range"), size)
    except media_service.RangeError as exc:
        return JSONResponse(
            {"detail": str(exc)}, status_code=416,
            headers={"Accept-Ranges": "bytes",
                     "Content-Range": f"bytes */{size}"})
    body_headers = {**headers, "Content-Length": str(end - start + 1)}
    if partial:
        body_headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return StreamingResponse(
        media_service.iter_chunks(source, start, end),
        status_code=206 if partial else 200,
        headers=body_headers,
    )


@app.get("/api/media/lyric")
def api_media_lyric(path: str = ""):
    return media_service.lyric_payload(_media_target(path))


@app.get("/api/media/cover")
def api_media_cover(path: str = ""):
    """内嵌封面字节；无封面 / 读不出时 404，前端显示占位图"""
    data, mime = media_service.cover_payload(_media_target(path))
    if not data:
        raise HTTPException(status_code=404, detail='该文件没有内嵌封面')
    return Response(content=data, media_type=mime,
                    headers={'Cache-Control': 'no-store'})


@app.post("/api/media/lyric/parse")
def api_media_lyric_parse(req: LyricParseReq):
    """编辑抽屉实时预览：只解析前端传来的文本，不读盘、不写盘"""
    return media_service.parse_lyric_text(req.text)


@app.post("/api/media/lyric/offset")
def api_media_lyric_offset(req: LyricOffsetReq):
    """偏移微调：返回改写后的 LRC 全文；落盘由前端调 POST /api/track/save 完成"""
    return media_service.lyric_with_offset(req.text, req.offset)


@app.post("/api/media/open")
def api_media_open(req: MediaOpenReq):
    """把不可播格式交给本机系统播放器；路径已由白名单校验，且必须用户点击触发"""
    target = _media_target(req.path)
    try:
        utils.open_with_default_app(target)
    except OSError as exc:
        raise HTTPException(status_code=502, detail=f"打不开系统播放器: {exc}")
    return {"ok": True, "launched": True, "path": target}


@app.get("/api/media/transcode")
def api_media_transcode_status(path: str = ""):
    """查询本机解码状态（前端轮询）；纯查询，不启动子进程"""
    return {"ok": True, **transcode_service.status(_media_target(path))}


@app.post("/api/media/transcode")
def api_media_transcode_start(req: MediaTranscodeReq):
    """启动本机解码，幂等：同一文件已有 running 任务时直接返回它的状态

    试听链路里唯一的写盘入口，且只写 ``log/_media_cache/`` 下的派生 MP3；
    不碰原文件、不进音乐库、不生成 ``Plan``。
    """
    return {"ok": True,
            **transcode_service.status(_media_target(req.path), start=True)}


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
