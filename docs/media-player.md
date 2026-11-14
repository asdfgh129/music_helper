# Web 试听与同步歌词

> 本文负责：本机 Web 向导里的**只读媒体层**、LRC 解析口径、播放器交互、格式矩阵与分期。
> 不负责：判定规则（见 [rules.md](rules.md)）、八步流程（见 [workflow.md](workflow.md)）、
> 向导操作细节（见 [web-wizard.md](web-wizard.md)）、未来纯服务器分支
> （见 [browser-local-roadmap.md](browser-local-roadmap.md)）。
> 权威来源：接口契约以本文为准，实现以 `services/media.py`、`core/lyrics.py`、
> `web/static/js/player.js` 为准；判定口径仍以 `core/` 与 [rules.md](rules.md) 为准。

| 项 | 值 |
|---|---|
| 状态 | P0 已实现：只读试听、Range 拖动、结构化歌词、同步高亮、不可播格式降级 |
| 日期 | 2026-11-14 |
| 适用分支 | `master`（主干） |
| 权威实现 | `services/media.py`、`core/lyrics.py`、`web/static/js/player.js`、`web/api.py` |

---

## 1. 部署口径：本机临时 Web 服务

主干是「**本机 Python 进程 + 本机浏览器开 localhost**」。`main.py --web` 起一个临时
FastAPI/uvicorn 服务，默认只监听 `127.0.0.1:8000`，Web 页面、音乐库、Python 进程都在
同一台机器上。`docs/architecture.md` §8 的定义即「本机跑服务、浏览器开 localhost」。

因此这里**没有「服务端 vs 浏览器」的机器边界，也不存在音频上传**。真实存在的只有一条
**进程 / 浏览器沙箱边界**：页面是 `http://127.0.0.1`，浏览器不允许 `<audio>` 直接读取
本地 `file://` 路径，字节必须由 Python 进程经回环 HTTP 送入浏览器。这是同机进程间拷贝。

由此得出两条结论：

1. `/api/media/stream` 与 HTTP Range 的必要性来自**沙箱限制**，不是网络传输。
2. **WASM 解码在主干没有立论**。它唯一的价值是「音频字节不上服务器」，而主干无服务器：
   文件本就在同一块磁盘，Python 进程本来就在读（解密、指纹、拷贝）。把几百 MB 音频再经
   localhost 塞进浏览器 WASM 的 32 位内存解码，是多一次全量拷贝、首播更慢、拖动要另做
   缓存，且默认 ffmpeg.wasm core 不含 APE/WMA/DSD 解码器。WASM 只属于
   `feat/browser-local` 那个「Ubuntu Server + 用户浏览器分处两台机器、要求音频字节零上行」
   的未来分支，见 [browser-local-roadmap.md](browser-local-roadmap.md) §7 / P-04。

> `--web-host` 允许改成非回环地址。只有那时上述边界才变成真实网络边界，也正因如此
> 媒体接口的路径白名单不能省。

## 2. 分层与不变量

| 层 | 新增职责 |
|---|---|
| `core/lyrics.py` | 纯解析：编码探测、LRC 结构化、同名歌词路径解析（**唯一实现**） |
| `core/tags.py` | 已有的 `duration()` / `has_cover()` 提供只读元数据，不改判定 |
| `services/media.py` | 文件读写：路径白名单、Range 参数解析、分块迭代、MIME 矩阵、系统播放器调用 |
| `web/api.py` | 只做参数校验、组装 `StreamingResponse`、序列化 JSON |
| `web/static/js/player.js` | 播放器组件与歌词同步，只消费后端结构化结果 |

硬约束（与 [AGENTS.md](../AGENTS.md) 一致）：

- **整条链路只读**：不新增写接口、不生成 `core.ops.Plan`、不移动/删除任何文件。
  歌词写回仍只走已有的 `POST /api/track/save`（它自己校验工作区）。
- **不进 `web/tasks.py` 串行队列**：试听与流式响应是同步短请求，塞进单工作者队列会让
  一首歌堵住八步流水线。
- **判定规则零改动**：歌词是否齐全、是否孤立、待补全判定都不受播放功能影响。
- **一个功能只有一处实现**：LRC 解析只在 `core/lyrics.py`，前端不再解析一遍；
  同名歌词路径只在 `core/lyrics.py`，`core/model.py` 与 `services/steps.py` 复用它。
- 媒体模块在 `web/api.py` **顶层 import**，保证 PyInstaller 能扫到；绿色版用
  `copytree` 整目录复制 `web/static/`，新增 JS 自动带入，无需改打包脚本。

## 3. 接口契约

`info` / `stream` / `lyric` 三个路径接受 `?path=<绝对路径>`（`stream` 另支持 `HEAD`），
`/api/media/open` 用 JSON body 传同一个字段；路径校验都由
`services/media.py:resolve_media()` 统一完成，返回值是 JSON 或字节流。

| 接口 | 方法 | 返回 |
|---|---|---|
| `/api/media/info` | GET | `ok / path / name / ext / mime / size / duration / browser_playable / playable_reason / has_lrc / has_cover` |
| `/api/media/stream` | GET / HEAD | `200` 或 `206`，带 `Accept-Ranges`、`Content-Range`、`Content-Length` |
| `/api/media/lyric` | GET | `ok / exists / encoding / has_timing / offset / meta / lines / plain` |
| `/api/media/open` | POST | `{ok, launched, path}`，用系统默认播放器打开该文件 |

`info` 的 `duration` 来自 `core.tags.duration()`（mutagen 不可用或读不出时降级为 `0`），
`has_cover` 来自 `core.tags.has_cover()`，两者都只是展示信息，不参与可入库判定。

**路径白名单**：只允许 `config` 声明的库目录、工作区、待补全、重复文件、下载目录及其
VIP / 暂存子目录。归档后文件位于库目录的 `<年代>/<年份>` 子目录，用 `commonpath` 递归
覆盖。校验顺序：`abspath` → `realpath`（防符号链接逃逸）→ 扩展名必须属于
`config.AUDIO_EXTENSIONS` → `commonpath` 落在白名单内 → 必须是普通文件。
白名单的主要作用是防前端传错路径与路径穿越；若有人把 `--web-host` 改成 `0.0.0.0`，
它同时是防「任意路径读文件」的防线。

**`/api/media/open` 的安全边界**：这是唯一有副作用的接口——启动一个外部播放器进程。
它复用同一套白名单，且必须由用户点击触发（POST）；不接受目录、不接收命令参数，
`os.startfile` / `open` / `xdg-open` 只拿到一个已校验的文件路径。

## 4. Range 流式

浏览器拖动进度条依赖 `206 Partial Content`，Starlette 各版本 `FileResponse` 的 Range 行为
不一致，所以自行实现，不用它。

| 请求头 | 行为 |
|---|---|
| 无 `Range` | `200` 全文 |
| `bytes=start-end` | `206`，`end` 钳制到 `size-1` |
| `bytes=start-` | `206`，从 `start` 到文件末尾 |
| `bytes=-N` | `206`，末尾 `N` 字节；`N >= size` 时退化为全文 |
| `start >= size` / `start > end` | `416` + `Content-Range: bytes */<size>` |
| 多段 `bytes=a-b,c-d` | 只取第一段（单流播放不需要 multipart） |
| 语法不合法（非 `bytes=` / 空区间 / `start > end`） | `416` + `Content-Range: bytes */<size>` |
| `HEAD` | 只回响应头，不读文件体 |

- 用 1 MiB 同步生成器 + `StreamingResponse`，Starlette 会在线程池迭代，几百 MB 的 FLAC
  不会进内存，也不阻塞事件循环。
- 响应头固定带 `Accept-Ranges: bytes`、`Cache-Control: no-store`；流式响应逐块不打日志，
  避免一次拖动刷出几百行。
- `services/media.py` 只返回 `(start, end, partial)` 与块迭代器，不依赖 Web 框架；
  组装 `StreamingResponse` 是 `web/api.py` 的事。

## 5. LRC 解析口径

`core/lyrics.py` 是 LRC 解析的唯一实现，前端只渲染 `parse_lrc()` 的输出。

- **编码探测**（`read_lrc_text()`）：带 UTF-8 BOM 时直接用 `utf-8-sig` 解码；否则依次
  尝试 `utf-8` 严格解码 → `gb18030` → `utf-8 errors=replace` 兜底，并返回实际采用的
  `encoding`。修掉旧
  `services/steps.py:_read_lrc()` 用 `utf-8 errors=replace` 造成 GBK 中文歌词乱码的问题。
- **时间戳**：`[mm:ss.xx]` / `[mm:ss:xx]` / `[mm:ss]`，一行允许多个时间戳（合唱叠句），
  全部展开成独立行；结果按时间稳定排序。
- **元数据**：`[ti:]` / `[ar:]` / `[al:]` / `[by:]` 进 `meta`；`[offset:±毫秒]` 进 `offset`，
  前端把 `offset / 1000` 加到播放时间上。
- **双语歌词**：同一时间戳重复出现的第二行作为 `translation` 合并进该行；遇独立的
  `[翻译]` / `[trans]` 分段标记时，之后的时间戳行按时间合并为译文。
- **无时间戳**：`has_timing=false`、`lines=[]`，非空行进 `plain`，前端显示静态全文，
  不显示进度同步与点击跳转。
- **同名歌词路径**（`lrc_path_for()`）：同目录、同主文件名，扩展名大小写不敏感；
  优先精确小写 `.lrc`，否则在实际目录项里找 `.LRC` 等变体。这修掉
  `Track.lrc_path` 只认小写 `.lrc`、而 `orphan_lrc()` 认 `.LRC` 的口径不一致。

`parse_lrc(text)` 只返回 5 个解析字段：

```json
{
  "has_timing": true, "offset": 0,
  "meta": {"ti": "晴天", "ar": "周杰伦", "al": "", "by": ""},
  "lines": [{"time": 1.0, "text": "晴天", "translation": "Sunny"}],
  "plain": ""
}
```

`GET /api/media/lyric` 由 `services/media.py:lyric_payload()` 在上面结果之外再包
`ok`（恒 true）、`exists`（同名 `.lrc` 是否存在）、`encoding`（实际采用的编码）。
三者属于接口层，不是 `parse_lrc()` 的返回值。

## 6. 格式矩阵

| 扩展名 | MIME | 浏览器原生解码 |
|---|---|---|
| `.mp3` | `audio/mpeg` | 是 |
| `.flac` | `audio/flac` | 是 |
| `.wav` | `audio/wav` | 是 |
| `.m4a` | `audio/mp4` | 是 |
| `.ogg` | `audio/ogg` | 是 |
| `.opus` | `audio/ogg` | 是 |
| `.ape` | `audio/x-ape` | **否** |
| `.wma` | `audio/x-ms-wma` | **否** |
| `.dsf` | `audio/dsf` | **否** |

MIME 表必须覆盖 `config.AUDIO_EXTENSIONS` 全集，`tests/test_media.py` 有断言，防止重演
「只加扩展名、漏读取器」那类事故。三种不可播格式**明确提示**，不静默失败：
`info` 返回 `browser_playable=false` 与 `playable_reason`，播放器不设置 `audio.src`，
直接给出「浏览器无法解码，请用本地播放器」和「用系统播放器打开」按钮。

P2 若要内嵌播放，走**本机解码子进程**：Python 进程调用随 `tools/` 分发的精简
FFmpeg，把结果落成临时 mp3 再复用同一套 Range 接口（管道流没有可映射的字节范围，
浏览器拖不动进度条）。绝不回写原文件，缓存不进音乐库目录、不进 `Plan`。加二进制要遵守
[AGENTS.md](../AGENTS.md) 第 9 条：`config.py` 的平台默认路径、`utils.tool_problem()`
预检、`third_party` 下的构建配方与 LGPL 说明、同步打包工具清单。

## 7. 前端播放器

**`<audio>` 必须挂在 `web/static/js/app.js` 的根组件模板里**。向导用 `<component :is>`
切换步骤组件，播放器若放在第 5 步组件内，切到第 6 步就被卸载、播放中断。

- `web/static/js/player.js` 暴露 `MH.Player` 组件：音频对象、播放/暂停、进度与音量、
  歌词面板、错误降级。挂载在 `.shell` 底部，是全局底部条而非抽屉。
- 根组件全局 mixin 增加 `playTrack(path, name)`，通过 `mh-play` 事件通知播放器；
  第 5 步表格每行与编辑抽屉都能直接调用。
- 同步逻辑只消费后端结构化歌词：`activeIndex = upperBound(lines, currentTime + offset/1000) - 1`，
  由 `timeupdate` 驱动高亮与自动居中滚动；用户手动滚动时暂停自动跟随；点击歌词行设
  `audio.currentTime`，由浏览器发起新的 Range 请求。
- **前端不写回歌词**。`[offset:]` 只用于显示与同步高亮，不落盘；要改歌词必须走已有的
  `POST /api/track/save`，而它只允许工作区内文件，库目录里的文件只能听、不能改。
  P1 才会提供偏移微调按钮与写回入口。

降级路径必须在 UI 里说清楚：`browser_playable=false`（提示用本地播放器）、
`exists=false`（显示「无歌词」）、`has_timing=false`（静态全文）、`audio` 的 `error`
事件（解码失败而非网络问题）。

## 8. 分期与验收

- **P0（本轮）**：`services/media.py` + 4 个媒体接口、`core/lyrics.py` 解析与编码回退、
  全局播放器与同步歌词、第 5 步试听入口、系统播放器降级、顺带修 GBK 与 `.LRC` 口径。
- **P1**：内嵌封面接口、第 6 步查重试听、歌词偏移写回、播放列表与上下曲、
  编辑抽屉内实时预览。
- **P2（需决策）**：本机 ffmpeg 解码子进程覆盖 `.ape/.wma/.dsf`、逐字歌词、桌面歌词。

测试用 `tempfile`，不碰真实音乐库、网络与外部程序：`tests/test_lyrics.py` 覆盖多时间戳、
翻译段、offset、GBK、BOM、无时间戳、大小写路径；`tests/test_media.py` 覆盖白名单越界、
Range 三种写法与 416、MIME 表覆盖扩展名全集；`tests/test_steps.py` 回归歌词读取。
验收跑 `pytest -q`、`ruff check .`、`compileall`、`scripts/check_docs.py`、
`scripts/build_docs_index.py --check`，再手工验：拖动进度条、大文件流式、切步骤不中断、
GBK 歌词、`.ape` 提示。
