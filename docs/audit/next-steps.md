# 下一步开发建议（2026-11 审计产出）

来源：[2026-11-audit.md](2026-11-audit.md) 的遗留清单。按「收益 / 风险」排序，
每项标注行为影响与验收方式。执行时遵循 `AGENTS.md`：改判定规则同步 `docs/rules.md`，
改流程同步 `docs/workflow.md`，改配置同步 `docs/configuration.md`。

## 第一梯队：性能（判定行为不变，收益立竿见影）

### 1. 消除工作区的重复扫描（预计省 30–90 秒/千文件）

- `run_archive` 里 `archive_preview`、`dedupe_preview`（入库闸门）、执行体各扫一遍工作区
  （`services/steps.py`）。给 `archive_preview` / `dedupe_preview` 加可选的
  `tracks=` 参数，入口扫一次传下去。
- `run_fill_tags` 中 `tag_candidates` 与逐文件 `build_track` 重复读标签：
  让 `tag_candidates` 返回的 items 带上 Track，按 path 复用。
- `flow_manual_archive` 三次扫描（rename 前后标签不变，只更新路径）+
  每文件 4 次 `readiness_problems`：一次遍历分桶 + 结果存 dict。

### 2. 孤立歌词检查复用扫描结果

`core/check.py` 的 `orphan_lrc` 独立 walk 一遍全部目录。`core/scan.scan()` 本来就
enumerate 了每个目录的全部文件，让它顺带收集 `.lrc` 路径（或返回目录文件清单），
`orphan_lrc` 从扫描结果推导，省一次全库 walk。**判定口径不变**（tests/test_lyrics.py
是回归保障）。

### 3. 封面接口加缓存

`/api/media/cover` 每次请求重新 mutagen 解析且 `Cache-Control: no-store`。
建议：进程内按 `(path, mtime)` LRU 缓存封面字节（上限如 64 张），响应加
`ETag` + `Cache-Control: private, max-age=3600`。**注意**：响应头变化需在
`docs/media-player.md` 与 `tests/test_media_api.py` 同步。

### 4. 声纹池改 bytes 存储

`services/soundalike.library_fingerprints()` 把 BLOB 解成 int tuple（万首 ≈ 100 MB 常驻）。
配合本轮 P0-2 的大整数方案：池里存原始 bytes，比较时 `int.from_bytes` 一次成型，
内存降到 ≈ 10 MB。缓存键与失效逻辑不变。

### 5. 直接解密批量调用 um

`decrypt_direct` 的 um 路径逐文件起子进程（每文件 100–300 ms 进程开销）。
网易云（.ncm 免凭据）可整目录一次调用后按产物 `_find_output` 回填逐条进度；
qmc 需凭据的保持逐文件（失败隔离优先）。进度粒度从实时变分批，需在
`docs/web-wizard.md` 注明。

## 第二梯队：Web 层收尾

### 6. 可选访问令牌

现状：默认 127.0.0.1、Origin 中间件拦截跨站写；绑定 `--web-host 0.0.0.0` 时同网段
设备仍可调用读接口（含 `/api/fs/list` 任意目录浏览）。建议：

- `--web-token <随机串>` 或配置项 `web_token`；设置后所有 `/api/*` 要求
  `Authorization: Bearer <token>` 或 `?token=`（首页注入 sessionStorage）；
- 未设置时在启动横幅打印「仅限本机使用」提醒；
- `/api/fs/list` 在远程监听（非 127.0.0.1）时收敛为只列配置目录与它们的父级。

### 7. 任务队列可观测性与取消

`web/tasks.py` 是单 worker 串行队列，长任务（流水线）无法取消，失败只能看日志。
建议：给 Task 加 `cancel_requested` 标志 + 各步骤在逐条循环里检查；
再加一个 `DELETE /api/tasks/{id}`。属于纯增强，不动 `core/`。

### 8. `_last_check` 失效机制

`web/api.py` 的检查结果缓存无失效：归档/改名后 `/api/plan/preview` 可能基于过期
结果。最低成本方案：缓存值带上扫描时的工作区文件数与最大 mtime，复用时比对，
不一致就重算。

## 第三梯队：功能增强（按价值排序）

### 9. 试听增强的收尾

`docs/media-player.md` 的分期表里剩余项：播放列表持久化（记住上次队列）、
音量均衡（ReplayGain/EBU R128 标签）、`.ape` 以外的探针式时长缓存。
建议先做「播放队列持久化」——纯前端 + 一条 localStorage，风险最低。

### 10. 报告的机器可读导出

`core/report.py` 已产出 md + csv。查重/自检结果可再加 JSON 导出（结构对齐
`/api/selfcheck/preview`），便于外部脚本消费，不必爬 Web 接口。

### 11. 待补全区的人工闭环

INCOMPLETE_DIR 里的文件目前只能人工改标签后重跑。向导第 5 步已能编辑工作区文件，
把同一套单曲编辑抽屉复用到待补全目录（只读→编辑→保存→提示重新归档），
即可闭环「补全→回流」。

## 暂不做的（评估结论）

- **删除旧接口 / legacy 仪表盘**：保留。CLI 时代脚本仍引用，删除收益低于回归风险。
- **`qq.py` 独立 CLI 与 `--only-decrypt` 合并**：保留。它是 Frida 通道的最小复现
  环境，`--no-ensure` 等调试参数在排错时不可替代。
- **`opencc` 转为必选依赖**：维持可选。繁简转换只影响匹配精度，缺失时降级路径
  已有测试覆盖。
- **`browser-local-roadmap.md` 的纯服务器分支**：按该文档自己的节奏推进；本轮的
  Origin 中间件与媒体白名单正好是它的前置地基。

## 工程健康

- 测试覆盖缺口：`web/tasks.py` 的 `_dispatch_wizard` 各分支只有提交层测试，
  建议补「任务执行 → result 结构」的端到端用例（mock 业务函数即可）。
- CI 已有 lint job；建议把 `scripts/check_docs.py` 加入 CI（当前只在本地约定执行）。
- 依赖：frida 上限钉死的注释（17.25.0 TLS 崩溃）很有价值，升级前先在 Win10 21H2
  验证；`ruff==0.17.3` 与 CI 锁定的做法保持不变。
