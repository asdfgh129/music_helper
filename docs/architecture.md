# 架构说明

> 本文负责：分层边界、模块职责、数据流、`Plan` 机制、设计决策、扩展指南。
> 本文不负责：单条判定规则（见 [rules.md](rules.md)）、流程顺序（见 [workflow.md](workflow.md)）、
> 参数与配置（见 [usage.md](usage.md)、[configuration.md](configuration.md)）。

## 1. 分层

```
┌──────────────────────────────────────────────────────────────────┐
│ 编排入口（两种形态，都只复用 core/services，不改业务代码）          │
│ main.py   CLI：解析参数 → 串流程 → 汇总报告                       │
│ web/      HTTP：FastAPI 路由 → 触发 core/services/main.flow_*      │
└───────────────┬────────────────────────────┬─────────────────────┘
                │                            │
┌───────────────▼──────────────┐  ┌──────────▼───────────────┐
│ core/      纯逻辑，可单测     │  │ services/  有副作用       │
│ model scan naming tags        │  │ decrypt soundalike        │
│ lyrics dedupe organize        │  │                           │
│ check report ops scoring      │  │ tagger/    标签服务        │
└───────────────┬──────────────┘  └──────────┬───────────────┘
                │                            │ 外部世界
┌───────────────▼────────────────────────────▼───────────────┐
│ config.py 纯数据（不导入业务模块）                            │
│ utils.py  日志、目录创建、月份工具、跨平台工具预检            │
└────────────────────────────────────────────────────────────┘
```

### 各层职责

| 层 | 可以做 | 不可以做 | 判据 |
|---|---|---|---|
| `core/` | 读元信息、计算、生成 `Plan` | 网络、外部 exe、`os.remove`、直接 `shutil.move` | 「同样输入是否总得到同样输出」 |
| `services/`、`tagger/` | HTTP、调用 exe、写标签/封面/歌词 | 决定目录结构、决定哪些文件该删 | 「离开这台机器还能不能跑」 |
| `main.py` | 解析参数、决定顺序、汇总 | 实现判定规则 | 「换一个入口，这些逻辑还要不要再写一遍」 |
| `web/` | 路由、触发 `core`/`services`/`main.flow_*`、做展示 | 自己操作文件、绕过 `core.ops.Plan`、并发改配置 | 「换一个前端，这套接口还要不要再写一遍」 |
| `config.py` | 路径、字符串、数字常量 | `import core` / `import services` / `import tagger` | 「导入它会不会引发循环依赖」 |

## 2. 模块清单

### `core/`

| 模块 | 职责 | 关键接口 |
|---|---|---|
| `core/model.py` | 统一的 `Track` 抽象 | `Track(dirpath, ext, stem, key, year_int, has_lrc, tag())` |
| `core/scan.py` | 一次遍历建索引 | `scan(paths, month, with_tags, recursive, extensions)` |
| `core/naming.py` | 文件名规则（唯一实现） | `parse_filename`、`canonicalize`、`format_filename`、`version_key` |
| `core/tags.py` | 标签读写 + 封面 + 时长（唯一实现） | `read_meta`、`read_tags`、`write_tags`、`write_cover`、`has_cover`、`duration` |
| `core/lyrics.py` | 歌词缺失 / 孤立 | `missing_lrc`、`orphan_lrc` |
| `core/dedupe.py` | 本地重复判定 | `find_by_tag`、`find_by_filename`、`find_duplicates` |
| `core/organize.py` | 年代/年份归档 | `plan_organize(tracks, base_dir, plan)` |
| `core/check.py` | 检查、修复计划、入库判定 | `check_library`、`plan_fixes`、`report_into`、`readiness_problems` |
| `core/report.py` | 报告渲染 | `Report.add/add_summary/add_review/save` |
| `core/ops.py` | 破坏性动作唯一出口 | `Plan.add_move/add_rename/add_trash/execute`、`copy_items` |
| `core/scoring.py` | 在线标签相似度打分 | `tag_score` |

### `services/`

| 模块 | 职责 | 依赖 |
|---|---|---|
| `services/decrypt.py` | 网易云 / QQ 解密编排 | `tools/um`（三平台）、`decrypto`（Frida，仅 Windows） |
| `services/soundalike.py` | 声纹去重、库一致性 | `tools/soundalike`（Windows 为 `soundalike.exe`）、`fpcalc` |
### `tagger/`

| 模块 | 职责 | 依赖 |
|---|---|---|
| `tagger/__init__.py` | 声纹 + 在线标签、封面、歌词 | `fingerprint/`、`music_tagger/platforms/`、`requests` |

`music_tagger/` 只保留 `platforms/{qqmusic,netease}.py` 两个客户端，不含标签匹配或写盘逻辑；
匹配与择优的唯一实现是 `core/scoring.py` 与 `tagger/__init__.py`。

外部依赖一律**延迟导入 + 失败降级**：缺 `requests` 只是不下载封面，缺 `fpcalc` 只是跳过声纹，
缺 `mutagen` 只是读不到标签——主程序永远能启动。

### `web/`

| 模块 | 职责 | 关键接口 |
|---|---|---|
| `web/api.py` | FastAPI 应用：只读配置/扫描/报告 + 检查/计划/执行 + OS 感知解密 + 任务提交/查询 | 全部 `GET/POST /api/*` 路由（如 `GET /api/config`、`POST /api/check`、`GET /api/tasks/{id}`） |
| `web/tasks.py` | 单工作者串行任务队列，按任务捕获 `utils.main_logger` 日志并推断进度 | `TaskManager.submit` / `poll`、`run_action(kind, opts)` |
| `web/index.html` | 深色单文件仪表盘，原生 HTML/JS，无构建链 | — |

设计要点：
- **零业务代码改动**：`web/` 只 `import core` / `services` / `config` / `utils` 与 `main.flow_*`，从不自己操作文件；破坏性动作一律经 `core.ops.Plan` + `log/journal.jsonl`。
- **单进程串行**：`config.py` 是模块级全局态，`web/tasks.py` 用单个 daemon 线程逐条执行任务队列，避免并发改配置/库。
- **长任务异步化**：`POST /api/tasks` 立即返回 `task_id`，前端轮询 `GET /api/tasks/{id}` 拿状态 / `progress`（0–100）/ 实时日志 / 结果。
- **OS 感知解密**：`GET /api/platform` 返回运行平台与解密能力矩阵；Web 不做平台假设，解密动作交给 `services.decrypt` 按本机 OS 路由（Windows→Frida/um，macOS→um，纯服务器→仅离线可解）。

### 附属目录与脚本

| 目录 | 是什么 | 为什么不在 `core` / `services` |
|---|---|---|
| `decrypto/` | QQ 音乐解密的 Python 调用与来源检索；`qq_client.py` 负责客户端安装检测 / 启动 / 登录确认 | 半独立上游代码，自带 CLI；由 `services/decrypt.py` 调用 |
| `fingerprint/` | AcoustID / MusicBrainz 指纹匹配 | 自带 HTTP 客户端与解析，被 `tagger/` 借用 |
| `music_tagger/` | QQ 音乐 / 网易云平台客户端 | 上游项目名沿用；包内只剩客户端 |
| `tools/` | `um`（三平台）、`soundalike`（三平台）、`fpcalc`、Frida hook | 外部二进制与脚本，不参与 Python 分层 |
| `scripts/` | `check_docs.py`、`git_uplink.py` | 开发者工具，不参与运行时 |
| `tests/` | 单元测试 + `tests/manual/` 手工脚本 + `tests/fixtures/` 样本 | 不随程序分发 |

命名约定：自有代码目录一律小写（`core`、`services`、`tagger`、`decrypto`、`fingerprint`、
`music_tagger`、`scripts`、`tests`、`docs`）。外部程序文件名保持上游原样（`um.exe`、
`soundalike.exe`），改它会连带上游脚本失效。同一程序的多平台产物用 Go 的
`<名字>-<GOOS>-<GOARCH>` 后缀区分（`soundalike-darwin-arm64`），由 `config.py` 按平台挑选。

**平台选择只有两处实现**：`config.py` 的 `_default_*()` 负责「默认路径按 `sys.platform` +
`platform.machine()` 挑」，`utils.tool_problem()` 负责「这份产物在本机能不能跑」。业务模块
（`services/soundalike.py`、`decrypto/um.py`）不许自己再判断 `sys.platform`，只调这两处；
唯一的例外是 `decrypto/qq.py` 的 `decrypt_backend()`——它选的是**方案**（Frida / um），
不是路径。

## 3. 数据流

```
磁盘
 │  core.scan.scan()
 ▼
[Track, ...] ──────────────► core.check.check_library()
 │                                   │
 │                                   ├─► CheckResult.findings ─► report_into() ─► Report ─► .md / .csv
 │                                   └─► CheckResult.groups   ─┐
 │                                                             │
 ├─► core.organize.plan_organize() ─┐                          │
 ├─► tagger.update()                │                          ▼
 ├─► services.decrypt                └────────────► core.ops.Plan ─► execute() ─► 磁盘 + journal.jsonl
 │                                                        ▲
 │                                     --dry-run ─────────┘（只 describe，不执行）
 └─► core.check.readiness_problems() ─► 完整文件留在 WORKSPACE_DIR，其余进 INCOMPLETE_DIR
```

关键点：**检查阶段永不改文件**，它只产出 `Finding`；所有改动集中到 `Plan.execute()`。
这让「报告」和「执行」可以分别验证，也让 `--dry-run` 天然成立。

## 4. 操作计划 `Plan`

```python
plan = Plan('最终库检查-修复', dry_run=False,
            journal_path='log/journal.jsonl', trash_dir='log/_trash')
plan.add_move(src, dst, reason)
plan.add_rename(src, new_name, reason)
plan.add_trash(src, reason)
result = plan.execute()      # PlanResult(done, skipped, failed)
```

约定：

- `src == dst` 的操作会被忽略（规范化后比较）；
- `move` 目标已存在时自动加 `_1/_2` 后缀，**永不覆盖**；
- `rename` 目标已存在时**直接失败**并写入 journal，不会加后缀造出重复文件名；
- `move` 移动同盘用 `os.replace`（原子改名），跨盘先写 `.part`、校验大小、再改名、最后删源；
- `trash` 不是删除，是把文件移到 `TRASH_DIR`，保留文件名；
- 音频移动/改名时同步搬运同名 `.lrc`；
- 单条失败不中断整批，失败原因进 `journal.jsonl` 的 `error` 字段；
- `dry_run=True` 时全部进 `skipped`，不创建任何目录。

## 5. 设计决策

### 5.1 为什么 `config.py` 不许导入业务模块

旧版 `config.py` 是「导入中转站」，把 `MusicTagger`、`FingerprintMatcher`、`QQMusicApi`
从 config 导出。后果：

1. 任一可选依赖缺失，`from config import X` 直接 `ImportError`，主程序起不来；
2. `config → fingerprint → config` 循环导入，`FPCALC_LENGTH` 永远读到回退值。

现在 config 只依赖标准库，读取顺序为环境变量 → `config.ini` → 默认值。

### 5.2 为什么删除都要走回收站

旧实现在重名时直接 `os.remove(filepath)`，连 `.lrc` 一起删，仅凭文件名判断重复。
一次误判就是不可逆的数据丢失。现在 `core/` 层没有任何 `os.remove`，删除一律
`shutil.move` 到 `log/_trash/`。

### 5.3 为什么一个功能只留一处实现

重构前同一功能最多有四份实现，规则互相矛盾：

| 功能 | 旧实现 | 矛盾点 |
|---|---|---|
| 归档 | `archive.py`、`file_operations.organize_by_year`、`lrc.py` | 支持的格式不同、重名处理不同 |
| 歌词 | `lrc.py`、`file_operations`、`archive.py` | 扩展名集合三套 |
| 元数据 | `metadata.py`、`archive.generate_music_metadata` | 字段映射不同 |
| 重复 | `duplicate.py`、`file_operations` | 两套都不比较时长 |

现在收敛到 `core/{organize,lyrics,tags,dedupe}.py`，旧文件已删除，git 历史可追溯。

### 5.4 为什么扫描只遍历一次

旧 `check_filename_consistency` 对每个目录 `os.walk` 四遍。`core.scan.scan()` 一次遍历产出
`Track` 列表，后续全部基于内存数据，大库上省掉 3/4 的磁盘遍历。

## 6. 扩展指南

### 新增一项检查

1. 在 `core/check.py` 加 `KIND_XXX` 常量；
2. 在 `check_library()` 里产出 `Finding`（`severe=True` 表示需要人工处理）；
3. 在 `report_into()` 的渲染顺序里加进去；
4. 如需修复，在 `plan_fixes()` 加分支，保持「先重复、后移动、最后改名」的顺序；
5. 补 `tests/` 用例，更新 [rules.md](rules.md)。

### 新增一个外部工具

1. 在 `services/` 下新建模块，参考 `services/soundalike.py`：`subprocess.run` 必带
   `timeout` 与 `check=False`，自行判断 `returncode`；
2. 路径放 `config.py`，同时支持 `config.ini` 与环境变量覆盖；只按 `PATH` 找同目录依赖的
   程序（如 `soundalike` 找 `fpcalc`），在 `subprocess.run(env=...)` 里把 `TOOLS_DIR` 前置进
   `PATH`，不要要求用户自己配；
3. 失败返回结构化结果，不要把异常抛到 `main`。

### 新增 CLI 开关

1. `main.py: build_parser()` 加参数；
2. 在 `main()` 的单一动作区按优先级插入（顺序敏感，见 [usage.md](usage.md#4-参数优先级)）；
3. 更新 `EPILOG` 与 [usage.md](usage.md)。

## 7. 已知坑

| 现象 | 原因 | 处理 |
|---|---|---|
| 声纹库「找不到记录」 | 旧版把 `music.db` 建在启动目录 | 0.6.0 起固定 `-db DB_PATH` 且 CWD 设为库目录 |
| 解密「成功但没产出」 | 外部程序返回 0 却没写文件 | 用前后快照差集判定产出，不看返回码 |
| 归档把文件搬进自己的子目录 | 边 `os.walk` 边在树内建年份目录 | 先扫描成列表再建计划 |
| 标签改了不生效 | 读到的 `FPCALC_LENGTH` 是循环导入的回退值 | 已修复；新增配置项时不要反向依赖 |
| `--fix` 把半库搬空 | 曾把缺封面/缺专辑也判为需移动 | 只有 `severe` 才移动 |
| 结果目录被重复扫描 | `INCOMPLETE_DIR`、`DUPLICATE_DIR` 嵌在 `WORKSPACE_DIR` 内 | 默认放在 `WORKSPACE_DIR` 同级，见 [configuration.md](configuration.md) |
| 合辑整张被搬进待补全 | 标签歌手是 `Various Artists`、文件名是具体歌手，曾被判「歌手矛盾」 | 占位歌手不参与一致性判定，见 [rules.md](rules.md#31-歌手维度是宽松的) |
| 库里凭空多出 `xxx_1.flac` | 改名撞车时静默加后缀 | 改名撞车改为失败留痕，见 [rules.md](rules.md#72-改名撞车一律失败) |
| 检查报告全是 0 | 目标目录配错，扫描空目录得到空结果 | `--check` 目录不存在时直接以退出码 1 结束 |
| 每首歌被解析三遍 | `read_tags` + `duration` + `has_cover` 各开一次文件 | `read_meta()` 一次读完，扫描阶段专用 |
| 新格式整类「缺标签」 | 只在 `config.py` 加了扩展名，`core/tags.py` 没有读取器 | `tests/test_tags.py` 检查每个扩展名都有读取器 |

## 8. Web UI

Web UI 是 `main.py` 之外的第二个编排入口，形态为「本机跑服务、浏览器开 `localhost`」。它**不复制任何业务逻辑**，只把 `core` / `services` / `main.flow_*` 包装成 HTTP 接口。

### 8.1 为什么单进程串行

`config.py` 是模块级全局可变状态，且整套流水线假设「一台机器一个配置」。`web/` 因此只起一个 daemon 工作者线程逐条消费任务队列，天然串行——不做多租户、不并发改同一个库。需要并发时，正确做法是起多个进程各绑定不同 `MUSIC_HELPER_*` 环境变量，而非在单进程内并行。

### 8.2 任务与日志

长时操作（打标签联网、声纹跑外部二进制）通过任务队列处理：`POST /api/tasks` 入队即返 `task_id`；`GET /api/tasks/{id}` 轮询状态、`progress`（按阶段关键字从执行的 `utils.main_logger` 日志推断 0–100）、`log`（实时捕获的日志行）、`result`。任务运行时临时给根 logger 挂一个缓冲 Handler，结束后摘掉，因此多个任务不会串日志。

### 8.3 安全边界

Web 端没有自己的删除/移动实现，所有破坏性动作都走 `core.ops.Plan`：`/api/plan/execute` 与任务里的各 `flow_*` 都先生成计划、写 `log/journal.jsonl`，再执行。接口默认 `dry_run`，非 dry-run 前会 `utils.ensure_dirs()` 保证目录存在。

### 8.4 解密随运行机器 OS 分支

Web 不假设「只有 Windows 能解密」。`/api/platform` 返回运行平台（macOS / Windows / 其它）与对应解密能力；`/api/decrypt` 把动作交给 `services.decrypt`，由 `decrypto/qq.py:decrypt_backend()` 按本机 OS 选 Frida（Windows，需客户端已登录）或 um（macOS 离线免密钥）。纯服务器环境只处理离线可解的文件。
| 声纹去重「跑到一半就失败」 | `-temp` 用第一个音乐目录推算相对路径，跨盘时 `filepath.Rel` 报错 | 调用前用 `services.soundalike.temp_supported()` 判断同盘，不同盘退化为只比对音乐库 |
| 声纹去重「卡住不动」 | 外部程序 stdout 被 `capture_output` 吞掉，提示语又不带换行 | 交互式运行（有 TTY）时不捕获输出，直接交给终端 |
| 声纹库改了长度打不开 | `Settings` 表锁定了 `-fpcalc-length` / `-algorithm` | 参数必须来自 `config.FPCALC_LENGTH`；改参数要删 `music.db` 重建 |
| macOS 上声纹工具「Exec format error」 | 只有 `soundalike.exe`，且 `fpcalc` 不在 PATH | `tools/soundalike-darwin-*` + 调用时注入 `tools/` 到 PATH |
| 预览过一遍就再也查不出重复 | 预览（`--soundalike-report`）也会把指纹写进库，而扫描只比对「新文件/变化过的文件」 | 预览统一走 `-dry-run`：复用库里指纹但不写库 |
| 未知扩展名被当成「最差的格式」 | 老 `formatPriority` 对不认识的扩展名返回 `-1`，`.dsf` 因此被判成比 mp3 还差 | 改成层级表 + 未知格式不参与自动判断，整组退回人工 |
| 跨盘移动「另一个程序正在使用此文件」 | `copyAndRemoveFile` 用 `defer sf.Close()`，`os.Remove` 时源句柄还开着 | 显式关句柄后再删；`moveFile` 还拒绝覆盖已有文件 |
| macOS 上「可执行文件却跑不起来」 | 配置指向了别的平台的产物，或克隆后丢了 exec 位 | 统一用 `utils.tool_problem()` 预检（缺文件 / 缺 `chmod +x` / PE 与 Mach-O 不匹配），并在报错里写清怎么修 |
| QQ 解密在 mac 上「找不到进程」 | Frida 方案只认 `QQMusic.exe` + `QQMusicCommon.dll` | `decrypt_backend()` 按平台选方案，macOS 固定走 `decrypto/um.py`；Frida 起不来时自动退回 um |
| 拿源文件路径直接调 `EncAndDesMediaFile::Open`，文件被清成 0 字节 | `Open` 会截断/重写传入路径，不是只读 | 一律先复制到暂存副本，只对副本 Open；探针脚本同理（`tests/manual/manual_frida_openprobe.py` 已强制走副本） |
| 只配 mmkv 没配密钥，连旧版 qmc 也解不开 | `um` 只要拿到 `--qmc-mmkv` 就会去开 vault，缺 key 直接 `unexpected EOF` | `um.run()` 只在 mmkv 与 key **同时存在**时才传这两个参数 |
