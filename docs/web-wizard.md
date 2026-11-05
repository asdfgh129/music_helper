# Web 向导（六步）

> 本文负责：向导六步各自做什么、判定规则落在哪个模块、跳过/回退的语义、接口与文件清单，
> 以及「um 能不能跨盘解密」的核实结论与建议。
> 本文不负责：单条判定规则（见 [rules.md](rules.md)）、CLI 参数（见 [usage.md](usage.md)）、
> 配置项全表（见 [configuration.md](configuration.md)）。

前端是 `web/static/` 下的 Vue 3 应用（**无构建链**，Vue 运行时随仓库分发在
`web/static/vendor/vue.global.prod.js`），后端是 `web/api.py` + `web/tasks.py`。
业务编排在 `services/steps.py`，判定在 `core/`——`web/` 里没有任何文件操作。

> 随仓库分发的 `vue.global.prod.js` 是 Vue **3.5.13** 的 production 全局构建
> （MIT 许可，取自 npm 包 `vue` 的 dist 目录同名文件）。选它而不是 CDN，
> 是为了断网也能打开向导、也避免每次加载都依赖外网。升级时直接替换该文件即可，
> 页面无需改动。

```
浏览器（Vue 3）──HTTP──> web/api.py ──> services/steps.py ──> core/*（判定 + Plan）
                                   └──> web/tasks.py（串行队列，逐条进度）
旧版仪表盘：/legacy（web/index.html，仍可用）
```

## 0. 流程总览

| 步骤 | 页面 | 执行主体 | 产物 |
|---|---|---|---|
| 1 | 目录设置 | `services/settings_store.py` | 写入 `config.ini [paths]` |
| 2 | 操作类型 | `core/library.py` 判定 + 前端互斥逻辑 | 决定下一步去 a / b / c |
| 2a | 初始化（做完回第 2 步） | `steps.init_library` | 目录结构 + 声纹库 |
| 2b | 自检（做完回第 2 步） | `main.flow_check` | `log/reports/*.md` + `review-*.csv` |
| 3 | 拷贝 | `steps.run_copy` → `core.ops.copy_items` | 工作区里的普通音频 |
| 4 | 解密 | `steps.run_decrypt` → `services.decrypt.decrypt_direct` | 工作区里的明文音频 |
| 5 | 标签歌词 | `steps.run_fill_tags` → `tagger.Tagger` | 标签 / 封面 / `.lrc` |
| 6 | 归档 | `steps.run_archive` → `core.organize` + `core.ops.Plan` | `<年代>/<年份>/` |

步骤条上只出现 1–6；2a/2b 是第 2 步的子页面，做完自动回到第 2 步。

## 1. 目录设置

八项设置，键名与 `config.py` 的常量一一对应：

| 页面名称 | `[paths]` 键 | 常量 |
|---|---|---|
| 库目录 | `library_dir` | `LIBRARY_DIR` |
| 工作区目录 | `workspace_dir` | `WORKSPACE_DIR` |
| 待确认目录 | `incomplete_dir` | `INCOMPLETE_DIR` |
| 重复文件临时目录 | `duplicate_dir` | `DUPLICATE_DIR` |
| 网易云目录 | `netease_dir` | `NETEASE_DIR` |
| 网易云 VIP 目录 | `netease_vip_dir` | `NETEASE_VIP_DIR` |
| QQ 音乐目录 | `qq_dir` | `QQ_DIR` |
| QQ 音乐 VIP 目录 | `qq_vip_dir` | `QQ_VIP_DIR` |

**持久化**：保存即写 `config.ini` 的 `[paths]`，然后 `config.reload()`，CLI 与 Web 读到的是同一份值。
不另存一份 JSON，避免「配置有两个真相」。

- 值写空 = 删除该键，回落到 `config.py` 的默认值（默认值只维护一份）。
- VIP 目录留空表示「跟随下载目录 + `/VipSOngsDownload`」；页面会显示跟随后的实际路径。
  与默认值相同的值不会落盘，ini 保持干净。
- 被环境变量覆盖的项，页面标注「环境变量」；保存不改变实际生效值（优先级固定为
  环境变量 > config.ini > 默认值）。
- 保存失败（校验不过、磁盘错误）不写坏原文件：先写 `config.ini.tmp` 再 `os.replace`。

校验规则（`services/settings_store.validate`）：

| 检查 | 原因 |
|---|---|
| 必填项非空、必须是绝对路径 | 相对路径按项目根解析，用户以为指别处 |
| 路径已存在但不是目录 | 后面所有步骤都会以「目录不存在」失败 |
| 任意两项指向同一目录 | 移动会变成「自己移到自己」 |
| 库/工作区/待确认/重复四者互相嵌套 | 移动会把目录搬进自己的子目录 |

## 2. 操作类型

### 2.1 初始化判定（`core/library.status`）

「已初始化」= 库目录存在，且（已有 `<年代>/<年份>` 结构 **或** 至少有一个音频文件）。
声纹库缺失不算未初始化——它是可单独补建的，只作为建议列出。

| 状态 | 页面表现 |
|---|---|
| 未初始化 | 「初始化」可选且必须选；「自检」与「完整流程」禁用；日期范围禁用 |
| 已初始化 | 「初始化」禁用；「自检」「完整流程」可选 |

初始化是幂等的三件事：建库目录、建 `unknown/` 与流水线所需目录、按需建/刷新声纹库
（`soundalike` 只扫描写指纹，**不移动任何文件**；`-move-interactive` 不参与）。
「补建声纹库」在已初始化时也单独提供了一个入口（状态卡片里的链接），因为去重需要它。

### 2.2 自检是排它选项

勾上「只做库目录自检」后：初始化不可选、日期范围不可用、点「下一步」直接进自检页；
自检做完回到第 2 步，不会自动进入拷贝。自检默认只出报告，页面上另有一个
「顺便执行可自动修复项」的勾选（等价 `--check --fix`），默认关闭。

### 2.3 月份范围

按月选择，默认当月；可以单月，也可以区间（闭区间，`YYYYMM` 字符串比较）。
它只作用于第 3 步拷贝与第 4 步解密——这两个动作按文件**修改时间**筛选（与 `--month` 同一语义）。
自检不使用月份范围（它检查整个库）。

`core.scan.scan()` 为此新增 `month_from` / `month_to`；`month` 仍优先，避免两个条件冲突时
行为不确定。

## 3. 拷贝

左栏按**原目录**分组的待拷贝文件，右栏是工作区当前文件（栏头显示目录路径）。

- 来源：`NETEASE_DIR`、`QQ_DIR` 递归扫描得到的普通音频，**排除各 VIP 子目录**；
  这条规则只有一处实现：`steps.copy_candidates`（CLI 的 `_copy_normal_files` 也调它）。
- 每组可勾选（默认全选），只有被选中的文件会被拷贝。
- 「工作区已有同名」只是提示，不跳过——真拷贝时 `core.ops._unique_path` 会加 `_1` 后缀。
- 拷贝成功/失败逐条回填到左栏（`已拷贝` 标记），右栏重新拉取。
- 结束后弹结果框：成功数 / 失败数 / 失败清单（含原因）；确认后留在本页。
- 没拷贝就点「下一步」→ 弹「跳过拷贝」确认框，确认才进第 4 步。

拷贝不是破坏性动作，因此不进 `Plan`（走 `core.ops.copy_items`），但同样处理同名与伴随 `.lrc`。

## 4. 解密（直解，不经过暂存区）

左栏是 VIP 目录里的加密文件（`.ncm` / `.mflac` / `.mgg`），右栏是工作区。点「解密」后：

1. 逐文件调外部程序解密，产物直接写工作区；
2. 进度按 `已完成 / 总数` 显示，当前文件名与实时日志同步；
3. 结束后弹结果框（每个来源的加密数 / 产出数 / 失败原因），右栏刷新；
4. 没解密就点「下一步」→ 弹确认框，确认才进第 5 步。

与旧流程（`main.flow_decrypt` → `services.decrypt._decrypt`）的差别只有一处：**不再把加密文件
搬进 `DECRYPT_STAGING_DIR`**。旧流程是「搬进暂存区 → 解密 → 按 `ENCRYPTED_SOURCE_MODE`
把原文件归还/入回收站/留下」，直接解密省掉了第一步和随之而来的归还动作。

### 4.1 关于「um 不能跨盘解密」

**结论：um 本身支持跨盘，不构成限制。** 依据（`third_party/um-cli`，v0.2.12）：

| 关注点 | 源码位置 | 事实 |
|---|---|---|
| 计算输出相对路径 | `cmd/um/main.go:421` `filepath.Rel(p.inputDir, filepath.Dir(inputFile))` | 两端都在源文件所在盘，`Rel` 不会跨盘 |
| 写产物 | `cmd/um/main.go:441` `os.OpenFile(outPath, O_CREATE|O_WRONLY|O_TRUNC)` + `io.Copy` | 逐字节拷贝，不含 rename |
| 全仓库 rename | `grep -rn "os.Rename"` | **没有**匹配 |

`io.Copy` 写另一个盘符与写同盘没有区别（Windows 上是两次系统调用，不是 rename）。
所以「VIP 在 D:、工作区在 G:」这种直解是安全的。

真正的跨盘成本在**旧流程**里：

1. `services.decrypt._decrypt` 先把加密文件 `Plan.add_move` 进暂存区；VIP 与工作区不同盘时，
   `core.ops._move_file` 走 EXDEV 分支——复制到 `.part`、校验大小、再删源（一次完整读+写）；
2. 解密再读一遍；
3. `ENCRYPTED_SOURCE_MODE=return`（默认）还要把加密文件搬回 VIP 目录（又一次完整读+写）。

也就是说跨盘时旧流程对同一批加密文件做了**三次跨盘 IO**，而直解只有一次读 + 一次写。
这就是第 4 步改成直解的主要动机。

顺带核实：`soundalike -temp` 确实**不能跨盘**（`filepath.Rel` 在 Windows 上跨盘直接报错），
`services/soundalike.same_volume()` 已提前判断并降级为只比对音乐库——这与 um 无关，别混为一谈。

### 4.2 落点与凭据

- 产物落点固定为 `WORKSPACE_DIR`（第 3、5、6 步都以工作区为舞台）。
- 网易云 `.ncm` 不需要凭据；QQ 新版 qmc（`qmc2` / `mflac1`）需要 mmkv + 16 位密钥，
  缺失时页面提示原因，不静默失败。
- Windows 上 QQ 优先 Frida：整批 attach 一次，逐文件结果按产物判定；环境不就绪
  （未安装 / 未启动 / 未登录）时在搬任何文件之前就返回。

## 5. 标签与歌词

表格列出工作区顶层文件：文件名 / 艺术家 / 歌名 / 专辑 / 年份 / 时长 / 封面 / 歌词 / 状态。

- 勾选：全选、全不选、仅缺标签、仅缺歌词、仅缺封面。
- 选项：声纹识别（MusicBrainz，慢但准）、写封面、写歌词（对应 `tagger.Tagger` 新增的
  `write_cover` / `write_lyrics` 参数，关掉只补文本标签）。
- 补全只填空缺，不覆盖已有值（`Tagger._merge` 的既有语义）。
- 每行就地更新，状态列显示 `+title/artist +封面 +歌词`；失败行显示原因。
- 这一步不影响「下一步」：标签不全的文件会在第 6 步被移入待确认目录，而不是留在这里。
- 判定「是否可入库」用的仍是 `core.check.readiness_problems()`，没有第二套规则。

## 6. 归档

- 目标二选一：**直接入库**（`LIBRARY_DIR`，右键推荐）或**只在工作区整理**
  （`WORKSPACE_DIR` 内建 `<年代>/<年份>`，先不入库）。
- 预览按 `<年代>/<年份>` 分组（`1980-1989/1985`），另列「无法归档」（缺年份/缺歌手/文件名与标签矛盾）。
- 执行走 `core.ops.Plan`：可归档的进年份目录；可按勾选把不可归档的移入 `INCOMPLETE_DIR`。
- 所有移动写 `log/journal.jsonl`；删除一律进 `log/_trash/`。
- 完成后弹结果（已移动 / 失败 / 转待确认），点「完成」回到第 2 步处理下一批。

## 7. 状态、回退与「跳过」

- 步骤条只允许回到**访问过**的步骤（`maxStep`）；2a/2b 高亮为第 2 步。
- 「上一步」按拷贝 ← 解密 ← 标签 ← 归档的线性顺序回退；2a/2b 的「上一步」直接回第 2 步。
- 每页刷新都会重新拉取预览，因此回退后看到的是当前真实状态，不是缓存。
- 「跳过」只在 3、4 两步存在，且必须显式确认；已执行过一次的来源不会重复提示。
- 任务在跑时：不能改目录（接口 409）、不能重复提交、不能前进/后退按钮。

## 8. 接口与文件

| 文件 | 职责 |
|---|---|
| `web/static/index.html`、`web/static/css/app.css`、`web/static/js/*.js` | Vue 3 前端（每步一个组件，`web/static/js/app.js` 是状态机） |
| `web/api.py` | 路由：向导 + 保留的旧接口 |
| `web/tasks.py` | 单工作者串行队列；`Task.set_progress()` 记录 `done/total/item` |
| `services/steps.py` | 六步编排（CLI 与 Web 共用），不新增判定规则 |
| `services/settings_store.py` | `config.ini [paths]` 的唯一写入点 |
| `core/library.py` | 「库是否已初始化」的唯一判据 |
| `core/scan.py` | `month_from` / `month_to` |
| `core/ops.py` | `copy_items(on_item=…)` 逐条回调 |
| `services/decrypt.py` | `encrypted_candidates()` / `decrypt_direct()` |
| `decrypto/qq.py` | `run_decrypt(files=…)`：只解密指定文件 |
| `tagger/__init__.py` | `Tagger(write_cover=…, write_lyrics=…)` |

## 9. 边界（明确不做）

- 不做多用户/多库：`config.py` 是模块级全局态，服务只绑 `127.0.0.1`，一个进程一个配置。
- 不做并发任务：队列串行，避免两条流程同时改同一批文件。
- 不在浏览器里删文件：向导只调用已有的 `Plan`，删除仍等于移入 `log/_trash/`。
- 不做「批量跳过失败再重试」：失败就留在原处，下一轮预览会重新列出来。
