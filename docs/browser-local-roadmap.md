# 纯服务器 Web + 浏览器本机实现：分支路线与可行性研究

> 本文负责：下一个分支（建议 `feat/browser-local`）的愿景、目标与非目标、现状基线、可行性结论、
> 问题清单与解决方案、技术选型、必须保持的行为契约、分期路线图、验收策略、风险与待决决策。
> 本文不负责：主干现有判定规则（见 [rules.md](rules.md)）、流程（见 [workflow.md](workflow.md)）、
> 算法与阈值（见 [algorithms.md](algorithms.md)）、配置（见 [configuration.md](configuration.md)）、
> 现有八步向导（见 [web-wizard.md](web-wizard.md)）、声纹原理（见 [fingerprint.md](fingerprint.md)）。
> 权威来源：本文是该分支的基石文档与可行性研究报告；涉及判定口径时以主干 `core/` 代码、
> `rules.md`、`algorithms.md` 为准，本文只规定「迁移时必须保持的契约」，不重新定义规则。

| 项 | 值 |
|---|---|
| 状态 | 可行性研究完成，**尚未实现**；本文是设计基线，不是已交付功能说明 |
| 日期 | 2026-11-09 |
| 建议分支 | `feat/browser-local`（从 `dev` 切出，与主干并行，不改主干行为） |
| 适用范围 | Ubuntu Server 只提供服务 + 用户浏览器在本机执行八步；音频文件不上传服务器 |
| 维护约定 | 设计决策变更先改本文，再改代码；每期完成后回填「状态」与验收结论，并同步 [CHANGELOG.md](../CHANGELOG.md) |

---

## 1. 为什么要做这个分支

主干是「本机 Python 后端 + 浏览器 UI」：`web/api.py` 与 `services/steps.py` 在**服务端进程**里
读写用户音乐库。把这套东西直接搬到 Ubuntu Server 上，会要求把音频文件上传到服务器、在服务器
落地目录结构与声纹库，还要在服务器上跑 QQ 客户端 / Frida——这与「服务器仅提供服务」的
部署预期冲突，也把用户的私有曲库暴露在服务器上。

本分支要验证并落地另一种形态：**服务器只做控制面与知识层，所有字节操作留在用户浏览器本机**。

### 1.1 目标

1. Ubuntu Server 只托管静态资源（PWA）、WASM 产物与一个**纯文本元数据代理**；不接收音频字节。
2. 用户通过浏览器完成八步：目录设置 → 操作类型 → 拷贝 → 解密 → 标签歌词 → 查重 → 工作区自检 → 归档。
3. 解密、拷贝、标签与内嵌封面写入、声纹计算与比对、查重、文件移动/删除全在用户本机执行。
4. 判定口径与主干一致：同样输入得到同样的 duplicate / upgrade / unknown / 可入库结论。
5. 保留现有 Vue 八步 UI 的交互骨架（无构建链），替换数据层而非重写产品。

### 1.2 非目标

- 不把整个 Python 项目编译成 WASM；不追求 `main.py`、`FastAPI`、`frida`、`subprocess` 的浏览器等价物。
- 不在服务器上运行 QQ 音乐 / 网易云客户端、扫码登录、Frida 注入或 GUI 安装向导。
- 不要求用户上传音频、封面之外的用户私有文件、`music.db` 或账号凭据。
- 不改变判定规则、阈值、目录命名与归档布局；不引入「浏览器版专用口径」。
- 不在本分支内解决多人协作、跨设备同步或服务器集中存储（列为待决决策）。

### 1.3 成功标准（可验收）

| 编号 | 标准 | 验证方式 |
|---|---|---|
| S-1 | 八步在 Chromium 桌面 + HTTPS 下可完整跑通 | 端到端脚本：从下载目录到年份目录 |
| S-2 | **音频字节零上行** | 浏览器 Network 面板 / 代理日志审计，断言无 `multipart`、无音频 content-type 请求体 |
| S-3 | 判定结果与主干一致 | 黄金用例集（见 §10.1）双端跑同一批输入，结论逐条比对 |
| S-4 | 故障可恢复 | 拷贝/移动中途刷新、权限被撤销、磁盘写入失败后，靠 journal 续跑或回滚，不留半拉子文件 |
| S-5 | 离线可用核心链路 | 断网后仍能解密、读标签、本地查重与归档；在线补全降级为「跳过」而非报错 |
| S-6 | 主干不受影响 | 分支内不修改主干行为；`python scripts/check_docs.py` 与主干测试基线保持通过 |

---

## 2. 讨论演进与关键结论

| 轮次 | 提出的问题 | 结论（本分支据此设计） |
|---|---|---|
| 1 | 把项目拷到服务器、浏览器远程访问，八步哪些能做 | 业务逻辑已 100% Web 化；卡点是「文件怎么进服务器」「凭据」「安全边界」「GUI 客户端前置」 |
| 2 | 全部下沉浏览器、文件不上传（um-react / WASM 思路） | 整体 WASM 化不可行；应只把**本地操作** WASM 化；解密算法已有上游 Web 版验证 |
| 3 | Frida/QQ 客户端可否让用户先装、只检查环境；补标签能否服务器流式输出；声纹库是否一次性；比对能否上服务器；跨目录移动与 um-react 写不同目录 | ① WASM 离线解密**不需要**客户端与 Frida，只需引导用户准备文件与凭据；② 服务器可流式下发元数据/封面 bytes，但内嵌标签必须本地改写；③ 声纹库需每次入库增量补录；④ 比对是纯计算，放服务器不划算；⑤ um-react 证明的是「写到不同目录」= copy 语义，不是 move |
| 4 | 审计主干：库目录声纹库是否参与入库查重 | **审计发现缺漏并已落地修复**：向导第 6 步原本不读 `music.db`、第 8 步不补录指纹、归档可绕过查重；现已改为三条信号 + 入库闸门 + 归档后补录（见 §3.2） |
| 5 | 内嵌标签/封面写入、本地目录文件操作、本地声纹库匹配，能否用 PWA/WASM/本机文件接口实现 | 三项均可实现，但需三者组合；纯浏览器的硬边界是跨目录原子移动、后台长任务与全浏览器支持（见 §5、§6） |

---

## 3. 现状基线（主干，本分支的出发点）

### 3.1 架构与可复用资产

| 资产 | 位置 | 浏览器分支的处置 |
|---|---|---|
| 分层与唯一实现原则 | [architecture.md](architecture.md) | 保持不变：判定只在 `core`、副作用只在 `services` |
| 八步编排 | `services/steps.py` | 逻辑迁移为 TS 编排层；CLI/Web 共用的口径作为契约 |
| 八步 UI | `web/static/js/` 下 12 个 Vue 组件 | **保留骨架**，把 `MH.api.*` 换成 Worker 引擎调用 |
| 纯判定规则 | `core/naming.py`、`core/dedupe.py`、`core/quality.py`、`core/check.py`、`core/organize.py` | 纯函数可翻成 TS 或在 Pyodide 中直接跑；黄金用例对齐 |
| 文件执行层 | `core/ops.py` 的 `Plan`（`.part` 两段式、journal、回收站） | 语义照搬，实现换成 FS Access API 两段式提交 |
| 标签与封面 | `core/tags.py` 的 9 种读/写、`write_cover` | 迁移到 TagLib-Wasm / Pyodide+mutagen，见 §6.2 |
| 外部程序 | `tools/um*`、`tools/soundalike*`、`tools/fpcalc*` | 浏览器侧替换为 WASM 组件；主干产物不动 |

### 3.2 必须迁移的行为契约（上一轮审计后落地的口径）

| 契约 | 主干实现 | 浏览器分支不得漂移的点 |
|---|---|---|
| 三条查重信号 | `core/dedupe.py: match_against(fp_pool=...)` | 歌手+歌名 / 文件名 / **声纹** 取并集；不同文件名、不同标签的同一录音必须命中 |
| 声纹阈值与公式 | `fingerprint_similarity` / `fingerprint_candidates`；`0.25` 倒排筛选、`0.95` 逐位精算 | 与 soundalike 同式：`max_offset Σ(32 − popcount(aᵢ⊕bᵢ)) / (32×max(len))`；阈值唯一来源，不另设一套 |
| 版本标记保护 | `version_markers_conflict()` | 指纹很像但 Live/Remix/伴奏标记不同 → `unknown` 转人工 |
| 声纹库是入库闸门 | `services/steps.py: dedupe_preview()` | 缺库 / 空库但库目录有文件（`stale`）/ 参数冲突 / `fpcalc` 不可用 → 所有 `archive_ok=False`，第 8 步拒绝执行 |
| 第 8 步复核 | `run_archive(enforce_dedupe=True)` | `duplicate`/`unknown`/`upgrade` 未在第 6 步处理完不得入库 |
| 入库后补录指纹 | `services/soundalike.py: refresh_db()` | 只有真正进 `LIBRARY_DIR` 的文件才写 `music.db`；试运行不写、待补全不算入库 |
| 入库标准 | `core/check.py: readiness_problems()` | 歌曲名/歌手/专辑/年份/**内嵌封面**齐全、年份可解析、文件名与标签不矛盾；只写外置封面不算达标 |
| 破坏性动作 | `core/ops.py: Plan` | 必须带 `reason`、支持 `dry_run`、删除 = 移入回收站；重命名撞车必须失败而非自动加 `_1` |
| 配置优先级 | `config.py` | 阈值与 `FPCALC_LENGTH`（120 秒）是单一事实来源，浏览器侧需显式声明同一组常量 |

### 3.3 主干的格式与依赖现状

- `config.AUDIO_EXTENSIONS` 9 种：`.flac .mp3 .wav .ape .ogg .opus .m4a .wma .dsf`。
- `core/tags.py` 的 `_READERS` / `_WRITERS` / `_COVER_READERS` 覆盖这 9 种；`write_cover` 实际实现
  含 `.mp3/.wav/.dsf/.m4a/.flac/.ogg/.opus` 共 7 种，`.ape/.wma` 只支持读封面。
  其 docstring 写的是 6 种，**与实现不一致**（本分支以代码为准，并在格式矩阵中显式记录）。
- 外部依赖：`um`（Go）、`soundalike`（Go）、`fpcalc`/chromaprint（C++）、mutagen（纯 Python）、
  requests、pycryptodomex、frida。浏览器侧只替换前四者的承载方式，frida 链路整体删除。

---

## 4. 目标架构

```text
Ubuntu Server（仅提供服务）
  ├─ HTTPS 静态托管：PWA manifest + Service Worker + WASM 产物 + Vue 组件
  ├─ 响应头：COOP same-origin / COEP require-corp（sqlite-wasm OPFS 需要 SharedArrayBuffer）
  ├─ /api/meta/*  纯文本元数据代理：只收歌名、指纹串、时长、封面 URL；绝不接收音频字节
  └─ 可选：共享标签/封面缓存（缓存公开元数据，不缓存用户文件）

用户浏览器（Chromium 桌面）
  ├─ Web Worker 引擎（串行任务队列 + 进度事件）
  ├─ File System Access API：单一授权根目录句柄（IndexedDB 持久化）
  ├─ um WASM：加密文件 → 明文 Blob
  ├─ TagLib-Wasm / Pyodide+mutagen：标签与内嵌封面读/写
  ├─ Chromaprint WASM + PCM 解码：现场算 120s / algorithm 2 指纹
  ├─ TS 化的 core 规则：命名、查重、音质、自检、归档计划
  ├─ sqlite-wasm(OPFS) / IndexedDB：music.db、journal、配置、任务状态
  └─ FileSystemWritableFileStream：copy / 两段式 move / 回收站

用户本机（浏览器之外，但同样不上传）
  └─ QQ 音乐 / 网易云客户端：只负责下载加密文件、产生 mmkv/ekey 凭据
```

### 4.1 数据流与信任边界

| 流向 | 内容 | 是否含音频字节 |
|---|---|---|
| Server → Browser | 静态资源、WASM、标签字段、歌词文本、封面图片 bytes、指令流 | 否 |
| Browser → Server | 歌名/歌手文本、chromaprint 指纹串、时长、封面 URL、AcoustID 查询 | 否 |
| Browser ↔ 本机目录 | 音频文件读写、拷贝、移动、解密产物、`.lrc` | 是，**不出本机** |
| 任何方向 | mmkv / 16 位密码 / 账号登录态 | **禁止上行** |

### 4.2 状态与存储映射

| 主干 | 浏览器分支 | 注意 |
|---|---|---|
| `config.ini` | IndexedDB / localStorage | 目录句柄必须存 IndexedDB；每会话通常需重新 `requestPermission` |
| `log/Music-*.log` | IndexedDB 日志 + 可导出诊断包 | 脱敏路径与凭据 |
| `log/journal.jsonl` | OPFS 追加日志 | 两段式提交与断点续跑的依据 |
| `log/_trash/` | 用户授权根目录下的 `_trash/` 子目录 | 仍遵守「删除 = 移入回收站」 |
| `music.db` | sqlite-wasm + OPFS VFS（或 IndexedDB 指纹索引） | 保持 `Settings/Directories/Files/ExcludedPairs` schema，便于与主干共存 |
| 内存任务队列 / 日志缓冲 | Worker 任务 + IndexedDB 状态 | 刷新后从 journal 恢复，不静默丢任务 |
| 库索引缓存 / 指纹池缓存 | 内存 + 显式失效 | 配置变更、归档补录后必须失效 |

---

## 5. 可行性结论总表

### 5.1 三种手段的能力边界

| 手段 | 能解决 | 不能解决 |
|---|---|---|
| **PWA** | 安装为应用、Service Worker 缓存 WASM/静态资源、离线启动、`navigator.storage.persist()` | **不增加任何文件系统权限**，不能读任意目录、不能绕过用户手势授权 |
| **WASM**（Emscripten / Pyodide / Go js-wasm） | 解密、标签编解码、Chromaprint 指纹、位比对、SQLite 查询等纯计算 | 无真实文件 IO、无子进程、无 socket（fetch 受 CORS）、WASI 的 FS 在浏览器里是虚拟的、内存受限 |
| **本机文件接口** | File System Access API（纯浏览器、Chromium）、OPFS（浏览器私有）、本机 agent / Native Messaging / Electron（完整能力） | 前两者受沙箱约束；后者需用户端安装一次 |

### 5.2 按八步

| 步骤 | 结论 | 关键条件 |
|---|---|---|
| 1 目录设置 | 可实现（语义重定义） | 一次授权根目录；句柄持久化；默认路径改 POSIX；VIP 子目录拼接不可硬编码反斜杠 |
| 2 初始化 / 自检 | 主体可实现 | 建目录、状态判定可搬；建声纹库依赖 Chromaprint WASM + sqlite-wasm；声纹库是入库闸门而非建议 |
| 3 拷贝 | 可实现 | copy 语义，um-react 已验证；注意保留 mtime（月份筛选依赖它） |
| 4 解密 | 算法可实现，凭据层受限 | um-react / Go 算法编 WASM；新版 qmc 需用户手工提供 mmkv+16 位密码；Frida 链路删除 |
| 5 标签歌词 | 可实现（工程量最大） | 内嵌标签/封面须本地整文件改写；在线查询需文本代理 |
| 6 查重 | 判定可实现，闸门必须保留 | 三条信号 + 0.25/0.95 + 版本标记；`fingerprint_ready=false` 一律不放行 |
| 7 自检 | 可实现，代价最小 | 纯只读规则 + 标签解析 |
| 8 归档 | 可实现但语义降级 | 跨目录移动非原子；两段式提交 + journal；或本机 agent 恢复原子性 |

### 5.3 三类归纳

- **可直接实现（不必改架构）**：八步 UI 骨架、纯判定规则、预览/确认/dry_run 语义、报告渲染、um WASM 解密 `.ncm`/旧版 qmc、拷贝、只读自检。
- **通过改造/补部署实现**：HTTPS + COOP/COEP + 认证/反代；目录句柄与上传替代；标签写入引擎；Chromaprint WASM + PCM 解码；sqlite-wasm；元数据文本代理；两段式文件事务；PWA 离线；试听与封面预览。
- **纯浏览器不能实现**：Frida 注入 / QQ 客户端安装与扫码登录 / 21.92 内存 ekey；凭空获得 mmkv 16 位密码；跨目录**原子**移动；后台静默长任务与断点续跑（只能近似）；Firefox/Safari 的目录级读写；在「零服务端代理」前提下完成在线补标签。

---

## 6. 问题清单与解决方案

| 编号 | 问题 | 影响 | 解决方案 | 验收 |
|---|---|---|---|---|
| P-01 | 文件如何进入/离开浏览器 | 第 3、4、8 步无米下锅 | 单一 `showDirectoryPicker()` 授权根目录，8 个目录作为子目录；`getFileHandle(...,{create:true})` + `createWritable()` 写新文件 | 八步无需任何 HTTP 上传接口 |
| P-02 | 内嵌标签/封面写入 | 不达标会进 `INCOMPLETE_DIR` | TagLib-Wasm 为主（浏览器 Emscripten，字节 buffer 进出，`setCoverArt`/`applyCoverArt`），Pyodide+mutagen 兜底 `.ape/.wma/.dsf`；服务器只下发字段与封面 bytes | 9 种容器读、7 种写封面的格式矩阵全绿 |
| P-03 | 跨目录移动非原子 | 归档/查重可能留半拉子文件 | 照搬 `core/ops.py` 的 `.part` 两段式：写临时 → 校验大小/哈希 → 同目录 `move()` 改名 → 删源 → 写 journal；Web Locks 防多标签；刷新后按 journal 续跑/回滚 | 故障注入测试（见 §10.3） |
| P-04 | 本地声纹库与指纹 | 不同名/不同标签的同一录音漏判 | Chromaprint WASM（如 `UniMusic-app/unimusic-chromaprint`，或纯 JS `chromaprint-fixed`）+ Web Audio / ffmpeg.wasm 解码；sqlite-wasm 读同一 `music.db` schema；直接移植 `core/dedupe.py` 两个纯函数 | 黄金用例集逐条一致；120s/algorithm 2 与 `Settings.Desc` 校验通过 |
| P-05 | 在线元数据 CORS | 第 5 步补不了标签 | 同源 `/api/meta/*` 文本代理（只传歌名/指纹/时长/URL）+ 浏览器端 WebCrypto 处理 weapi 签名；提供「完全离线模式」 | 代理日志断言无音频字节；断网时步骤降级不报错 |
| P-06 | 凭据与客户端前置 | 新版 qmc 解不开 | 引导页 + 用户自证 + 试解一个样本；旧版客户端下载（密钥内嵌）可零凭据；mmkv Bytes 由用户在浏览器中提供，绝不上传 | 凭据不上行的抓包验证 |
| P-07 | 浏览器支持矩阵 | Firefox/Safari 不可用 | 明确只支持 Chromium 桌面（Chrome/Edge 86+）；给出降级提示；若要求全浏览器，走 §9 P3 本机 agent | 支持矩阵文档与启动检测 |
| P-08 | 大文件内存与性能 | 几百 MB FLAC 可能 OOM | WASM 32 位内存约束下用分块 `slice()`、OPFS 中转、Worker 分任务；1.2 万首索引分批构建；进度可取消 | 性能基准（§10.4） |
| P-09 | 刷新/关闭中断长任务 | 任务状态丢失 | Worker + IndexedDB 任务状态 + OPFS journal + 幂等操作；恢复时提示「继续/回滚」 | 故障注入 |
| P-10 | 判定口径漂移 | 浏览器与主干结论不一致 | 黄金用例集 + 阈值单一来源常量表 + 双端回归；`core/` 纯函数优先直译而非重写 | S-3 |
| P-11 | 主干 Web 零鉴权 | 远程可达时风险极高 | 新分支静态页无写接口；元数据代理加认证/CSRF/限流/路径白名单；CSP + SRI 校验 WASM 完整性 | 安全评审清单 |
| P-12 | 指纹参数一致性 | 库与 AcoustID 不兼容 | 固定 `FPCALC_LENGTH=120`、`algorithm=2`；启动校验 `Settings.Desc`；参数版本与 WASM 版本绑定 | 混用旧库时明确报错并要求重建 |
| P-13 | mtime 语义 | 月份筛选失效 | 拷贝时显式保真/记录原始 mtime；浏览器写文件会改 mtime，索引以记录值为准 | 月份筛选用例 |
| P-14 | 并发/多设备 | 双标签页或两台设备写同一库 | Web Locks + 单设备单库约定；跨设备同步列为待决决策，不在首版承诺 | 并发冲突用例 |
| P-15 | 数据可恢复 | 清站点数据即丢 OPFS | 显式「导出/导入备份」（music.db + journal + 配置）；提示 OPFS 非永久存储 | 备份往返用例 |

---

## 7. 技术选型

| 领域 | 候选 | 推荐 | 理由 / 风险 |
|---|---|---|---|
| 解密 | 上游 Unlock Music Web（um-react）WASM 内核；`third_party/um-cli` Go 算法包编 `GOOS=js` | 直接复用上游 Web 内核，必要时给 Go 算法包加百行 WASM 入口 | 算法已验证；Go CLI 的 `os.Args`/`filepath.Walk`/`os.CreateTemp` 必须裁掉；许可证需核实 |
| 标签/封面 | TagLib-Wasm；Pyodide + mutagen；纯 JS 库拼装 | **TagLib-Wasm 主 + Pyodide/mutagen 兜底** | TagLib-Wasm 明确支持浏览器并提供 `setCoverArt`/`applyCoverArt`，覆盖主流格式，`.ape/.wma/.dsf` 仍需逐项实测；mutagen 是纯 Python，Pyodide 的 `micropip` 可装纯 Python wheel，口径与主干一致但体积大 |
| 指纹 | `fpcalc` CLI；Chromaprint WASM；纯 JS `chromaprint-fixed` | Chromaprint WASM + Web Audio，`.ape/.wma/.dsf` 用 ffmpeg.wasm 或专用解码器 | CLI 依赖 FFmpeg + 子进程，进不了浏览器；解码后的 PCM 采样率/声道必须与 fpcalc 一致（11025Hz 单声道），这一步由解码器或 WASM 封装承担 |
| 声纹库 | sqlite-wasm + OPFS；IndexedDB 指纹索引 | 优先 sqlite-wasm（schema 与主干共用），否则导出二进制索引 | OPFS VFS 需要 COOP/COEP 与 Worker；如服务器无法配响应头，退回 IndexedDB |
| 规则层 | TS 直译 `core/` 纯函数；Pyodide 直接跑 `core/` | **TS 直译**（首版），保留 Pyodide 作为一致性对照 | 避免 WASM 运行时体积；用黄金用例约束翻译正确性 |
| 文件 IO | FS Access API；OPFS；本机 agent | 单一授权根目录 + FS Access API；P3 视需求引入 agent | `move(destDir, name)` 对用户磁盘仍受 flag 限制，不能当原子移动用 |
| UI | 现有 Vue 无构建链组件；重写前端 | 保留 12 个组件，替换 `MH.api.*` 为 Worker 调用 | 产品交互与八步状态机已完成 |
| 服务 | 纯静态；静态 + 文本代理 | 静态 + 同源元数据代理 | 完全零代理则放弃在线补全，需在 UI 明示 |
| PWA | Service Worker 预缓存 | 采用 | 解决 WASM 体积与离线启动，不解决权限 |

---

## 8. 分期路线图

| 期 | 范围 | 交付物 | 退出条件 |
|---|---|---|---|
| **P0 骨架与只读** | HTTPS 静态站 + PWA、单一根目录授权、um WASM 解密、拷贝、目录/标签只读预览、元数据文本代理、声纹库状态展示 | 能在浏览器里完成 1/3/4（`.ncm`、旧版 qmc）/7 与只读查看；6/8 只出计划不执行 | S-2、S-6 通过；黄金用例的「预览」部分一致 |
| **P1 写入与匹配** | TagLib-Wasm 写标签/封面、Chromaprint WASM、sqlite-wasm 声纹库、三条查重信号与闸门、TS 化 `core` 规则、入库后补录指纹 | 第 2 步建库、第 5 步补全、第 6 步查重可用 | S-3 通过；格式矩阵 9 读 / 7 写封面；0.25/0.95 对齐 |
| **P2 事务与体验** | 两段式提交 + journal + Web Locks、归档执行与 `blocked`、试听/封面预览、任务恢复、PWA 离线、备份导出/导入 | 八步完整闭环 | S-1、S-4、S-5 通过；故障注入全绿 |
| **P3 完整能力（可选）** | 用户机本机 agent（localhost WS / Electron / Tauri）：真原子 `os.replace`、后台长任务、任意目录与全格式解码、任意浏览器 | 可靠性与兼容性补齐 | 仅当 §11 决策要求「全浏览器/真原子」时启动 |

每期完成回填：实际交付、验收结论、与本文的偏差及原因；偏差若改变契约，先改本文再改代码。

---

## 9. 验收与测试策略

### 9.1 黄金用例集（S-3）

从主干导出一批固定输入（文件名、标签、大小、时长、音质规格、指纹序列）与期望结论，
覆盖：同名同大小、大小不同无时长、不同文件名/不同标签但同指纹、指纹相同但 Live vs Remix、
声纹库缺失/空库/参数冲突、`upgrade`/`duplicate`/`unknown`、Vorbis/ID3/MP4/FLAC 封面。
浏览器实现必须对同一输入逐条产出相同 `status` / `basis` / `reason` 分类。

### 9.2 格式覆盖矩阵

9 种扩展名 ×（读标签 / 读封面 / 写标签 / 写封面 / 现场算指纹 / 解码 PCM），
逐格记录「通过 / 降级 / 不支持」，`.ape/.wma` 写封面按主干现状标注为不支持。

### 9.3 故障注入

拷贝中途刷新、目标写一半失败、权限被撤销、同名冲突、磁盘满、Worker 被终止、
`move` 失败、指纹计算超时、`music.db` 被外部改动。断言：不丢文件、不产生查不出的重复、
journal 可恢复、用户能看到明确原因。

### 9.4 性能基准

1.2 万首索引构建耗时、单文件 120s 指纹耗时、几百 MB FLAC 写回峰值内存、
批量解密吞吐、UI 在 Worker 忙碌时的响应性。设定上限并在 CI 中记录趋势。

### 9.5 隐私与安全验收

抓包确认无音频字节上行；元数据代理请求体白名单；mmkv/密码不出现在日志与诊断包；
CSP/SRI/COOP/COEP 生效；认证与 CSRF 用例；依赖（WASM 产物）完整性校验。

---

## 10. 讨论中未覆盖、本分支必须补充的事项

> 以下为本次讨论未充分展开、但会决定分支成败的补充项，按「必须处理 / 需决策」标注。

| 项 | 类别 | 说明 |
|---|---|---|
| 认证、鉴权与 CSRF | 必须 | 主干 `web/api.py` 零鉴权、`/api/fs/*` 可列任意目录，绝不能照搬到可远程访问的服务；新分支虽无写接口，元数据代理仍需认证、限流、Origin 校验与路径白名单 |
| HTTPS / CSP / SRI / HSTS | 必须 | FS Access API 要求安全上下文；WASM 产物建议 SRI；COOP/COEP 是 sqlite-wasm OPFS 的前提；部署清单需写进分支 README |
| 凭据与日志脱敏 | 必须 | mmkv、16 位密码只在浏览器内存中使用；诊断包导出前脱敏路径与凭据；明确「凭据永不上传」 |
| 隐私边界 | 必须 | 元数据代理会看到曲库查询、chromaprint 指纹可关联曲目；提供完全离线模式与隐私说明，默认不收集查询日志 |
| 许可证合规 | 必须 | TagLib（LGPL/MPL）、chromaprint、Unlock Music 上游、kissfft、Pyodide 及各 WASM 产物的许可证与静态链接/署名义务，需在引入前逐项确认；上游 um 有 DMCA 历史，源码获取方式要合规 |
| 数据迁移与共存 | 必须 | 是否与主干共用同一个 `music.db`？若共用，浏览器写入的 `Settings/Directories/Files` 必须与 Go 程序兼容并加锁；若不共用，需定义导入导出格式与版本迁移 |
| 备份与「清站点数据即丢」 | 必须 | OPFS/IndexedDB 不是可靠永久存储；必须提供导出/导入备份，并在首次授权时提示 |
| 时间与 mtime | 必须 | 第 3 步月份筛选依赖 mtime；浏览器 copy 会改写 mtime，需要显式保留原始值并写入索引 |
| 路径与编码 | 必须 | 中文/空格/emoji 路径、大小写敏感性差异、Windows 盘符与 UNC、路径长度上限、跨卷判定；主干 `commonpath` 校验要在句柄树上用 `resolve()` 复刻 |
| 后台与恢复 | 必须 | 页面关闭即中断；任务幂等、可取消、可恢复；Web Locks 防多标签；禁止「静默丢任务」 |
| 音频试听与封面预览 | 建议 | 第 6 步人工确认需要听；用 Blob URL + `<audio>` 本地试听，不外传；封面用本地 Blob 预览 |
| 可观测性 | 建议 | 本地结构化日志、错误码表、可导出诊断包、用户可读的失败原因（尤其是「声纹库未就绪」） |
| 可访问性与国际化 | 建议 | 键盘操作、授权流程的无障碍说明；沿用中文界面，错误提示保持中英标识符分离 |
| PWA 更新与版本绑定 | 必须 | Service Worker 缓存失效策略；WASM 版本、指纹参数版本、库 schema 版本三者绑定，避免旧缓存配新库 |
| 多用户/多设备 | 需决策 | 单设备单库为默认；跨设备同步、共享声纹库、并发写冲突不在首版承诺 |
| 版权与使用边界 | 必须 | 只处理用户自有文件，不内置密钥、不提供绕过 DRM 的通用能力；文档明确适用边界 |
| CI 与工程化 | 必须 | WASM 产物构建可复现、产物哈希校验、Playwright 浏览器自动化（Chromium 矩阵）、离线测试、黄金用例双端回归 |
| 运维成本 | 建议 | WASM 体积与带宽、自托管 vs CDN、代理服务日志脱敏、版本回滚与灰度 |
| 回滚与并行 | 必须 | 分支与主干并行、特性开关、用户数据不自动迁移；失败时可退回主干 Python 版，不破坏已有音乐库 |

---

## 11. 待决决策清单

| 编号 | 决策 | 选项 | 建议默认 | 影响 |
|---|---|---|---|---|
| D-01 | 是否允许「用户机本机 agent」 | 纯浏览器 / 允许 agent（P3） | 首版纯浏览器，P3 按需启用 | 决定能否有真原子移动、后台任务、全浏览器支持 |
| D-02 | 浏览器支持范围 | 仅 Chromium 桌面 / 全浏览器 | 仅 Chromium 桌面 + 其它浏览器明确提示 | 决定是否需要 agent |
| D-03 | 是否保留在线补标签 | 文本代理 / 完全离线 | 文本代理 + 离线开关 | 决定服务器是否「纯静态」 |
| D-04 | `music.db` 是否与主干共用 | 共用 schema / 独立索引 | 共用 schema（便于回退主干） | 决定 sqlite-wasm 与锁的复杂度 |
| D-05 | 标签写入引擎 | TagLib-Wasm / Pyodide+mutagen / 两者并存 | 两者并存、按扩展名分派 | 决定体积与格式覆盖 |
| D-06 | 声纹库归属 | 每用户本地一份 / 服务器共享知识库 | 每用户本地一份 | 决定隐私与同步设计 |
| D-07 | 规则层实现 | TS 直译 / Pyodide 跑 `core/` | TS 直译 + 黄金用例约束 | 决定运行时体积与一致性成本 |
| D-08 | 新版 qmc 凭据 | 引导用户旧版客户端 / 用户手工提供 mmkv / 不支持 | 引导 + 手工提供 | 决定第 4 步格式覆盖 |
| D-09 | 是否支持多人/多设备 | 否 / 是 | 首版否 | 决定是否要引入中心状态与冲突解决 |
| D-10 | 分支产物形态 | 仅新前端 / 与主干共存双栈 | 与主干共存、特性开关切换 | 决定回退路径与维护成本 |

决策变更记录在本文 §2 表格或新增 ADR，并在 [CHANGELOG.md](../CHANGELOG.md) 留痕。

---

## 12. 参考资料

### 12.1 内部文档

[architecture.md](architecture.md) · [rules.md](rules.md) · [algorithms.md](algorithms.md) ·
[fingerprint.md](fingerprint.md) · [workflow.md](workflow.md) · [web-wizard.md](web-wizard.md) ·
[web-guide.md](web-guide.md) · [self-check.md](self-check.md) · [configuration.md](configuration.md) ·
[usage.md](usage.md) · [troubleshooting.md](troubleshooting.md) · [README.md](README.md) ·
[CHANGELOG.md](../CHANGELOG.md) · [CONTRIBUTING.md](../CONTRIBUTING.md)

### 12.2 外部资料（本次评估核实）

| 主题 | 资料 |
|---|---|
| 浏览器文件访问 | [Chrome for Developers: File System Access API](https://developer.chrome.com/docs/capabilities/web-apis/file-system-access/) |
| 跨目录移动限制 | 同上文档：`move()` 已针对 OPFS 发布，源或目标在 OPFS 之外时位于 flag 后，且不支持目录 |
| 目录授权支持矩阵 | [MDN: showDirectoryPicker()](https://developer.mozilla.org/en-US/docs/Web/API/Window/showDirectoryPicker) 兼容性数据（Chromium 系为主） |
| 原子写入 | `FileSystemWritableFileStream.createWritable()` 写临时文件、`close()` 提交 |
| SQLite in browser | [SQLite WASM 文档](https://sqlite.org/wasm/doc/trunk/persistence.md)（OPFS VFS 需要 COOP/COEP 与 `SharedArrayBuffer`）、[Chrome 官方说明](https://developer.chrome.com/blog/sqlite-wasm-in-the-browser-backed-by-the-origin-private-file-system/) |
| Python in browser | [Pyodide](https://pyodide.org/) 与 [micropip API](https://micropip.pyodide.org/)（支持 PyPI 上的纯 Python wheel） |
| 标签/封面 WASM | [taglib-wasm (npm)](https://www.npmjs.com/package/taglib-wasm)、[TagLib-Wasm 源码](https://github.com/CharlesWiltgen/TagLib-Wasm)（`setCoverArt`/`applyCoverArt`） |
| 指纹 WASM | [unimusic-chromaprint](https://github.com/UniMusic-app/unimusic-chromaprint)（chromaprint + kissfft 编 WASM）、`chromaprint-fixed` |
| 浏览器解密 | Unlock Music Web Edition（um-react）及其 WASM 加速内核；本仓库 `third_party/um-cli` 的 Go 算法包 |
| 音频解码 | MDN Web Audio `decodeAudioData()`；ffmpeg.wasm |

> 外部链接不参与仓库文档校验；引入任何第三方产物前，先按 §10「许可证合规」逐项确认。

---

## 13. 术语表

| 术语 | 含义 |
|---|---|
| FS Access API | File System Access API，用户显式授权后可读写本机目录的浏览器 API |
| OPFS | Origin Private File System，浏览器私有文件存储，用户不可见 |
| COOP / COEP | 跨源隔离响应头，`SharedArrayBuffer` 与 sqlite-wasm OPFS 的前提 |
| Chromaprint / fpcalc | 声学指纹算法与官方 CLI；本分支用 WASM 版替代 CLI |
| `music.db` | soundalike 维护的 SQLite 声纹库；字段见 [fingerprint.md](fingerprint.md) |
| 两段式提交 | 写临时文件 → 校验 → 改名/提交 → 删源 → 写 journal 的事务近似 |
| journal | 记录每次破坏性动作的可恢复日志，主干为 `log/journal.jsonl` |
| 黄金用例集 | 主干与浏览器实现共用的固定输入/期望输出集合，用于防止判定口径漂移 |
| 控制面 / 数据面 | 服务器下发指令与元数据 / 浏览器本地处理音频字节 |

---

## 14. 文档维护

- 本文件是分支基石；设计决策变更先改本文，再改代码，并同步 [../CHANGELOG.md](../CHANGELOG.md)。
- 每期完成后回填 §1 状态表与 §8 验收结论；新增待决决策追加到 §11。
- 全仓文档的可浏览索引见 [index.html](index.html)，由 `scripts/build_docs_index.py` 生成；
  新增文档后重新生成并运行 `python scripts/check_docs.py`。
