# 公共功能清单

与解密途径无关、所有平台/所有内核共用的功能。各解密途径（内核）独有的能力见
[kernel-features.md](kernel-features.md)。条目格式：功能 — 主要实现位置。

## 1. 流水线（CLI 入口 `python main.py`）

| 功能 | 实现位置 |
|---|---|
| 完整流水线：解密 → 声纹去重 → 标签补全 → 检查 → 待补全分流 → 年份归档 | `main.flow_pipeline` |
| 最终库检查 `--check`（可 `--fix` 执行修复） | `main.flow_check` |
| 手动归档入库 `--manual-archive`（工作区 → 按年份并入库） | `main.flow_manual_archive` |
| 单一动作：`--only-decrypt` / `--only-update-tag` / `--only-check-file-name` / `--only-archive` | `main.main` |
| 声纹库维护：`--init`（建库）/ `--checkdb`（一致性）/ `--soundalike`（去重）/ `--soundalike-report`（只列候选） | `services/soundalike.py` |
| 试运行 `--dry-run`：所有破坏性动作先出计划不落盘 | `core/ops.py` |
| 调试开关 `--debug`、限量 `--limit`、报告目录 `--report-dir`、重复直删 `--trash-dup`、跳步 `--skip-*` | `main.build_parser` |
| 检查六维度：文件名格式 / 标签完整性 / 文件名↔标签一致性 / 重复 / 缺歌词 / 孤立歌词 | `core/check.py` |
| 入库就绪判定（缺歌曲名/歌手/专辑/年份/封面、年份可解析、文件名不矛盾；歌词不参与） | `core.check.readiness_problems` |
| 去重双规则：标签（歌手+歌名+时长容差）与文件名（去下载序号+时长），保留策略「无损优先、同格式留小者」 | `core/dedupe.py` |
| 版本标记保护：Live/Remix/伴奏/翻唱 等不同版本不自动判重 | `core/naming.version_markers` |
| 年份归档：`<年代>/<年份>/` 结构，无法归档的进 `unknown/` 转人工 | `core/organize.py` |
| 按标签规范化文件名（只在标签可信时） | `core/check.plan_fixes` |

## 2. 执行安全

| 功能 | 实现位置 |
|---|---|
| 破坏性动作唯一出口 `Plan`（move / rename / trash），逐条带 reason、写 journal（JSONL） | `core/ops.py` |
| 删除 = 移入 `log/_trash/`，永不 `os.remove` 用户文件 | `core/ops.py` |
| rename 撞车直接失败留痕，绝不静默加 `_1` 造重复 | `core/ops._apply` |
| 同盘 `os.replace` 原子改名；跨盘先复制到 `.part`、校验大小再落盘，不留截断文件 | `core/ops._move_file` |
| 音频移动时同步搬走同名 `.lrc`（失败记日志不影响主文件） | `core/ops._move_companion_lrc` |
| 重复目标自动加 `_1/_2`（仅 move/trash；rename 不适用） | `core/ops._unique_path` |
| 加密原文件去向三模式：`return` 归还 VIP / `trash` 回收站 / `keep` 留暂存区；只处理本次移入的文件 | `services/decrypt.py` + `ENCRYPTED_SOURCE_MODE` |

## 3. 标签与元数据

| 功能 | 实现位置 |
|---|---|
| 一次打开读三件事（tags / duration / has_cover） | `core/tags.read_meta` |
| 九种音频格式读写标签（mp3/flac/wav/ape/ogg/opus/m4a/wma/dsf） | `core/tags._READERS` / `_WRITERS` |
| 内嵌封面读 / 写 / 探测（六种容器各一套） | `core/tags._COVER_READERS` 等 |
| 在线补标签：AcoustID 声纹匹配 → QQ 音乐 / 网易云搜索，按 `tag_score` 择优；只填空缺不覆盖 | `tagger/` + `core/scoring.py` |
| 封面下载（stream 模式 + `MAX_COVER_SIZE` 上限拦截） | `tagger.download_cover` |
| 歌词下载与写入（QQ base64 解码、双语合并） | `tagger.fetch_qq_lyric` 等 |
| 可选繁简转换（opencc 缺失自动降级） | `fingerprint/textconv.py` |
| 音质规格读取与比较（无损/有损、采样率、位深、码率；格式偏好 FLAC>WAV） | `core/tags.read_quality` + `core/quality.py` |

## 4. 声纹查重（入库必要前置）

| 功能 | 实现位置 |
|---|---|
| fpcalc 现场指纹（`-raw -json -length N -algorithm 2`） | `services/soundalike.fingerprint_of` |
| 只读声纹库 music.db（全表 JOIN 一次读出 + 进程内缓存；写库只经 Go 程序 `refresh_db`） | `services/soundalike.library_fingerprints` |
| 16 位截断倒排筛选 → 大整数逐位精算（与 Go 实现同一公式） | `core/dedupe.py` |
| 跨集合判定四态：unique / duplicate / upgrade / unknown；upgrade 分 quality / format 两种依据 | `core.dedupe.match_against` |
| 缺库 / 空库 / 参数冲突 / fpcalc 不可用 → 拦下入库，绝不静默放行 | `services/soundalike.fingerprint_status` |
| 库内索引缓存与失效（目录变化 / 配置重载 / 归档后补录） | `services/steps.invalidate_library_cache` |
| fpcalc 参数与库锁定一致性预检（不一致给重建指引） | `services/soundalike.settings_problem` |

## 5. Web 八步向导（`main.py --web`）

| 功能 | 实现位置 |
|---|---|
| 第 1 步 目录设置（写 config.ini 热重载；同目录/嵌套/盘符/非目录四种拦截） | `services/settings_store.py` |
| 第 2 步 库状态与初始化（建目录 + 建声纹库，幂等） | `core/library.py` + `steps.init_library` |
| 第 3 步 拷贝下载文件到工作区（排除 VIP 子目录，逐条进度） | `steps.copy_candidates` / `run_copy` |
| 第 4 步 直解加密文件到工作区（不经暂存区，省两次跨盘复制） | `steps.run_decrypt` + `decrypt_direct` |
| 第 5 步 标签与歌词补全（字段开关 / 单曲编辑抽屉 / 在线预览不落盘 / 并发补全） | `steps.run_fill_tags` |
| 第 6 步 工作区↔库查重（两栏比对、逐条勾选替换、库内文件永不直接删除） | `steps.dedupe_preview` / `run_dedupe` |
| 第 7 步 工作区自检（只读；与库自检同一份 `core.check`） | `steps.workspace_check` |
| 第 8 步 按年份归档（入库闸门：声纹未就绪拒绝入库、重复/升级/待人工拦截） | `steps.run_archive` |
| 后台任务队列（单 worker 串行、逐条进度、阶段日志实时回传） | `web/tasks.py` |
| 目录浏览弹窗 / 新建目录 | `web/api.py /api/fs/*` |
| 跨站写请求防护（Origin 同源校验中间件） | `web/api._same_origin_guard` |
| 监听默认 `127.0.0.1:8000`，打包后 exe 同样可用 | `main.run_web` |

## 6. 试听与歌词（只读媒体层，不属于八步）

| 功能 | 实现位置 |
|---|---|
| 路径白名单四道闸：绝对路径 → realpath → 扩展名 → commonpath 允许目录 → 普通文件 | `services/media.resolve_media` |
| Range 流式播放（单段 206、HEAD、416 语义完备、1 MiB 分块） | `services/media.parse_range` / `iter_chunks` + `web/api.py` |
| 结构化 LRC 解析：编码探测 / 时间戳 / 双语 / 增强逐字（word timing） | `core/lyrics.parse_lrc` |
| 歌词偏移微调（±60 秒限幅，落盘仍走 track/save） | `services/media.lyric_with_offset` |
| 内嵌封面字节端点 | `services/media.cover_payload` |
| `.ape/.wma/.dsf` 本机 FFmpeg 解码 → 派生 MP3 缓存（原子落盘、超时看门狗、按 mtime 淘汰） | `services/transcode.py` |
| 不可播格式降级：系统默认播放器打开 | `utils.open_with_default_app` |

## 7. 配置 / 日志 / 报告 / 自检

| 功能 | 实现位置 |
|---|---|
| 配置三级优先：环境变量 > config.ini > 默认值；相对路径按项目根解析 | `config.py` |
| 项目根唯一判定（源码=仓库根；冻结=exe 所在目录） | `runtime_paths.project_dir` |
| 外部程序按平台挑默认路径（`<名字>-<GOOS>-<GOARCH>`）+ 三类故障预检（缺文件/缺执行位/平台不匹配） | `config._default_*` + `utils.tool_problem` |
| 日志单点初始化（文件 + 控制台双 handler 挂根 logger；可重复调用不叠加） | `utils.setup_logging` |
| 六份运行目录幂等创建（非 Windows 跳过盘符路径） | `utils.ensure_dirs` |
| 报告双格式输出（Markdown 正文限量行 + CSV 全量） | `core/report.py` |
| 配置校验（库/工作区不存在告警，不阻断） | `config.validate` |

## 8. 打包与运维

| 功能 | 实现位置 |
|---|---|
| 免 Python 绿色版（PyInstaller 组装；dist/config.ini 与 log/ 属用户数据永不覆盖删除） | `scripts/build_exe.py` |
| 文档站点生成（侧栏直达、状态看板、过期检查） | `scripts/build_docs_index.py` |
| 文档校验（链接 / 反引号路径 / python 命令是否真实存在） | `scripts/check_docs.py` |
| GitHub 推拉代理（网络受限环境） | `scripts/git_uplink.py` |
| 跨平台测试基线（584 项单元测试；不触碰真实库/网络/外部 exe） | `tests/` |

---
「内核」= 解密途径。各途径独有的能力见 [kernel-features.md](kernel-features.md)。
