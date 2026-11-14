# Web 向导（八步）

> 本文负责：向导八步各自做什么、判定规则落在哪个模块、跳过/回退的语义、接口与文件清单，
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
| 2b | 库自检（做完回第 2 步） | `main.flow_check` | `log/reports/*.md` + `review-*.csv` |
| 3 | 拷贝 | `steps.run_copy` → `core.ops.copy_items` | 工作区里的普通音频 |
| 4 | 解密 | `steps.run_decrypt` → `services.decrypt.decrypt_direct` | 工作区里的明文音频 |
| 5 | 标签歌词 | `steps.run_fill_tags` → `tagger.Tagger` | 标签 / 封面 / `.lrc` |
| 6 | 查重 | `steps.dedupe_preview` → `core.dedupe` + `core.quality` | 重复的移走；库里音质更低或更占地方的旧版本让位 |
| 7 | 工作区自检 | `steps.workspace_check` → `core.check` | 只出报告，不动文件 |
| 8 | 归档 | `steps.run_archive` → `core.organize` + `core.ops.Plan` | `<年代>/<年份>/` |

步骤条上只出现 1–8；2a/2b 是第 2 步的子页面，做完自动回到第 2 步。

顺序上的因果：**先查重再自检，最后归档**。查重负责「这份库里有没有」，
自检负责「这份本身合不合格」，两者都过了才值得往库目录里放。

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
| 非 Windows 上出现盘符路径 | 该路径在本机不存在 |

## 2. 操作类型

### 2.1 初始化判定（`core/library.status`）

「已初始化」= 库目录存在，且（已有 `<年代>/<年份>` 结构 **或** 至少有一个音频文件）。
声纹库缺失不算未初始化——它是可单独补建的，所以在初始化状态里只作为建议列出；
但它是**入库查重的必要前置**：缺库时第 6 步所有 `archive_ok=False`、第 8 步拒绝执行，
必须先补建（见 [6. 查重](#6-查重工作区--库目录)）。

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

注意这一页的自检针对**库目录**（`LIBRARY_DIR`），与第 7 步的工作区自检不是一回事：
两者用的是同一份 `core.check` 判定，只是扫描范围不同。

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
无论哪条流程，加密原文件都只碰本次搬进暂存区的，或用户在左栏已选的那几个文件。

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

- 产物落点固定为 `WORKSPACE_DIR`（第 3、5、6、7 步都以工作区为舞台）。
- 网易云 `.ncm` 不需要凭据；QQ 新版 qmc（`qmc2` / `mflac1`）需要 mmkv + 16 位密钥，
  缺失时页面提示原因，不静默失败。
- Windows 上 QQ 优先 Frida：整批 attach 一次，逐文件结果按产物判定；环境不就绪
  （未安装 / 未启动 / 未登录）时在搬任何文件之前就返回。

## 5. 标签与歌词

表格列出工作区顶层文件：文件名 / 艺术家 / 歌名 / 专辑 / 年份 / 流派 / 时长 / 封面 / 歌词 / 状态。
数据来自 `steps.tag_candidates()`，与第 6、7 步共用同一个扫描口径（`_workspace_tracks()`：
只扫顶层、只扫音频），避免「这一步看到 36 个、下一步看到 38 个」。

### 5.1 选文件

- 打开时默认勾选「有问题的行」（不可入库、缺歌词或缺封面），省掉一次无意义的全选。
- 快捷选择只作用于**当前列表**：全选 / 全不选 / 仅缺标签 / 仅缺歌词 / 仅缺封面 / 仅文件名矛盾。
- 顶部实时显示「已选 N / 总数」。

### 5.2 选字段

七个开关：歌名 / 歌手 / 专辑 / 年份 / 流派 / 封面 / 歌词。

- 「开」只表示**允许写入**，实际仍遵守既有铁律：字段为空才填，已有值不覆盖
  （`Tagger._merge`）。所以「只补歌词」就是关掉其余六项。
- 传给后端的是 `fields` 白名单（`tagger.Tagger(fields=...)`），白名单外的字段既不填也不写。
- 「仅缺失项」按当前勾选行把空字段的开关打开；「全开」「全关」是批量动作。
- 声纹识别（MusicBrainz）是独立开关，慢但准；关掉只走在线平台。

### 5.3 排序

7 列可排：文件名 / 艺术家 / 歌名 / 专辑 / 年份 / 流派 / 时长，外加「状态」。

- 单击在**升序 → 降序 → 取消**之间循环（取消后回到默认的文件名升序）。
- Shift + 单击追加第二、第三排序键，例如「艺术家 → 专辑 → 时长」就是标准的专辑视图。
- 排序在前端完成（候选最多 2000 行），不让后端参与，避免每次点表头都发一次请求。
- 中文用 `localeCompare('zh-Hans-CN', {numeric: true})`，`第2首` 会排在 `第10首` 前面。

### 5.4 单曲编辑

行尾「编辑」打开右侧抽屉，不打断表格滚动位置。

- 打开时调 `GET /api/track`，拿到标签、封面/歌词状态、`.lrc` 全文与**文件名 ↔ 标签逐项比对**。
- 五个文本字段可直接改；「在线取标签」走 `POST /api/track/fetch`，用 `dry_run=True`
  只算不写，把合并后的值填回表单，用户确认后再保存。
- 歌词编辑框直接对应同名 `.lrc`：留空表示不写，填写则整体覆盖。
- 保存走 `POST /api/track/save`，只写传入的字段；空字符串不会被写入（`write_tags` 只写非空值），
  返回里用 `ignored` 告知哪些字段保留了原值。
- **不改文件名**。改名会牵动重复判定、归档路径与 journal，属于归档环节的事；
  手工编辑只负责把标签改对。
- 接口只接受工作区内的音频路径（`steps._audio_in_workspace`），越权直接 400。

### 5.4.1 试听与同步歌词

表格每行与编辑抽屉都提供「试听」：调根组件的 `playTrack(path, name)`，由挂在
`web/static/js/app.js` 根模板里的全局播放器接管，**切到第 6、7 步不会中断播放**。
播放器先取 `/api/media/info` 与 `/api/media/lyric`，再让 `<audio>` 指向 `/api/media/stream`；
歌词高亮由 `timeupdate` 驱动，点歌词行会发起新的 Range 请求跳转进度。

播放器本身**不写任何文件**：歌词偏移只存内存，写回仍走 `POST /api/track/save`，
因此库目录里的文件只能听、不能改。`.ape/.wma/.dsf` 在 `info` 里被标为
`browser_playable=false`，播放器明确提示并提供「用系统播放器打开」按钮，不静默失败。
详见 [media-player.md](media-player.md)。

### 5.5 判定来源

「是否可入库」仍是 `core.check.readiness_problems()`，没有第二套规则。
标签不全的文件不会留在这里挡路——第 7 步会把它标出来，第 8 步会把它移入待确认目录。

## 6. 查重（工作区 ↔ 库目录）

入库前必须确认「库里没有这一份」。库中已有一份的文件再归档一次，年份目录里会出现两条
相同记录，声纹库也会重复，而且第 8 步不会替你发现。

### 6.1 库索引为什么不读标签

库目录一万多首，逐个用 mutagen 打开读标签要十几分钟。但库里的文件是归档流程按
「歌手 - 歌名.ext」写进去的，**文件名本身就是可信的歌手/歌名来源**。所以
`steps._library_tracks()` 只做 `os.walk` + `os.stat` + `parse_filename()`：

| 做法 | 12433 首耗时 | 能拿到 |
|---|---|---|
| 读标签（`scanner.scan(with_tags=True)`） | 十几分钟 | artist / title / duration / cover |
| 只 stat + 解析文件名 | 约 8 秒 | artist / title / size |

查重只需要「歌手 + 歌名 + 大小」，没有理由付前者的代价。索引在进程内缓存，
目录改了或点「重新扫描库」才重建。

音质比较需要采样率/位深/码率，这些也确实要打开文件。但只在**命中候选之后**
才对那几个文件调用 `core.tags.read_quality`，不会退化成全库扫描。

### 6.2 判定规则（`core.dedupe.match_against`）

这是**两个集合之间**的比对，与 `find_duplicates()` 的「同一堆文件内部找重复」不同：
不只要回答「工作区这份是不是新的」，还要回答「库里那份该不该让位」。

命中候选有三个维度，第三条是**入库的必要前置**：

| 维度 | 命中条件 | 说明 |
|---|---|---|
| 歌手+歌名 | `version_key(artist)` + `version_key(title)` 相同 | `version_key` 保留 Live/Remix/伴奏/feat 标记，不同版本不会互判 |
| 文件名 | 去掉 `(1)`/`_1` 后同名，且原文含「 - 」结构 | `Intro.flac` 这类没有歌手结构的名字不跨目录比对 |
| 声纹 | `fpcalc -raw` 指纹与 `music.db` 中某条库指纹的逐位相似度 ≥ `fp_match_threshold`（0.95） | 不看文件名与标签，专治「换名/换标签的同一录音」；版本标记冲突转 `unknown` |

声纹信号由 `steps._fingerprint_pool()` 只读加载库指纹、`soundalike.fingerprint_of()`
现场算工作区指纹，判定仍在 `core.dedupe.match_against(fp_pool=...)` 一处。
预览返回 `fingerprint`（`status` / `count` / `reason`）与 `fingerprint_ready`；
每条结果带 `fingerprint_ok` / `blocked_reason`。**声纹库未就绪时所有
`archive_ok` 都是 False**，查重页会显示 `fingerprint.status` 与 `reason` 并提示
先在第 2 步补建声纹库；就绪时显示参与判定的库内指纹数。

第 8 步 `run_archive()` 会再复核一次：库未就绪直接报错，`duplicate`/`unknown`/
`upgrade` 的文件留在工作区（升级档要先在第 6 步让库里旧版本移走）；
归档成功后把新文件指纹增量写入 `music.db`（返回结果里的 `fingerprint_db`），
试运行不写库。

命中之后先确认是不是同一录音：

| 情况 | 判断 |
|---|---|
| 两边大小完全相同 | 同一录音（同一文件的复制/移动，字节数一定相同） |
| 大小不同，但时长都在且相差 ≤ `DURATION_TOLERANCE` | 同一录音（不同码率转码） |
| 两边时长都拿不到 | 判不了，转人工 |

时长从哪来：库索引不读标签（见 6.1），所以 `match_against` 接受一个 `probe` 回调，
**只在命中候选之后**才补读这一个文件的规格（`core.tags.read_quality`）。通常只有
个位数文件，不影响索引那 8 秒。

### 6.3 音质比较（`core.quality`）

确认同一录音之后，比的是**声音**，不是文件大小：

| 比较 | 规则 |
|---|---|
| 无损 vs 有损 | 无损胜（`.flac` `.ape` `.wav` `.dsf` `.dff` `.aif` `.alac` 计为无损） |
| 都无损 | 比「采样率 × 位深」 |
| 都有损 | 比码率；容器不报码率时用 `大小 ÷ 时长` 估算，相差 10% 以内算同一水平 |
| 同规格但容器不同 | 压缩无损（FLAC/APE/ALAC）胜未压缩（WAV/AIFF），这是**省磁盘**不是音质 |
| 任一侧读不出规格 | `unknown` |

> 不按大小比是刻意的：WAV 未压缩，体积一定比同源 FLAC 大，但两者音质完全等同；
> 反过来 128k MP3 也可能比高压缩的 FLAC 大。按大小比会两头出错。

最后一条单独由 `quality.storage_preference()` 判断，只在 `compare()` 已判 `same` 之后
才调用：此时两者解码出来是同一串 PCM，唯一差别是容器。命中时结论仍是 `upgrade`，
但带 `basis='format'`，页面上写「同音质更省磁盘」，不写「音质升级」。

同一录音 + 音质比较，得到四种结论：

| 结论 | 含义 | 处理 |
|---|---|---|
| `unique` | 库里没有 | 照常归档 |
| `duplicate` | 库里有同等或更好的 | 移走**工作区**这份 |
| `upgrade` | 库里有但更差 | 移走**库里**那份，工作区这份留给第 8 步归档 |
| `unknown` | 判不出来 | 交人工，不自动处理 |

一条兜底：规格读不出来但**格式相同**时降级为 `same`（同格式同录音没有可靠的
升级依据，保守不动库）；格式不同又读不出规格，才算 `unknown`。这样「损坏文件」
和「mutagen 不认的容器」不会被误判成升级。

实测 36 个文件：`unique` 31、`duplicate` 1、`upgrade` 4、`unknown` 0。
4 个 `upgrade` 里 3 个是 `basis='format'`（FLAC 对库里同规格的 WAV），
1 个是 `basis='quality'`（FLAC 48kHz/24bit 对库里 320kbps MP3）。

### 6.4 页面与执行

页面是**两栏比对**，左栏工作区、右栏库内，右栏是 1:N：

- 左栏点一行，右栏列出库里与它对应的**全部**副本（`MATCHED_LIMIT` = 50，超出在
  `matched_total` 里计数）；行上有状态与音质描述。
- 右栏每行一个复选框：只有 `relation='better'` 的（即库里这份更差）才能勾选，
  其余标「保留」。勾选结果通过 `replaces` 提交。
- 默认勾选规则：`duplicate` 默认勾（只动工作区），`upgrade` 默认**不勾**（动库，需逐项确认）。
- 两个执行按钮，落点不同：
  - 「移入重复目录」→ `action='move'`，工作区那份进 `DUPLICATE_DIR`；
  - 「删除所选」→ `action='trash'`，工作区那份进 `log/_trash`，**不进重复目录**。
  两者都会先弹**两栏摘要确认框**（工作区将删除 / 移走几个，库内将移出几个）。
- `upgrade` 无论 `action` 选什么，库内那份都移入 `DUPLICATE_DIR` 而不是回收站——
  动的是库里的存量文件，留一份可对照的副本比进回收站稳妥。
- **不接受全量替换**：`statuses` 含 `upgrade` 而 `paths` 为空时直接 400；
  `replaces` 的 key 必须在 `paths` 里、值必须落在预览列出的可替换清单内，否则 400。
- 库内文件全被取消勾选的 `upgrade` 项整项不做处理，结果里计入 `skipped`。
- 还有未处理项时点「下一步」→ 二次确认（列出「N 个库中已有、M 个可替换库内、
  K 个需人工确认」），确认后照常前进，但会提示「归档时这些文件会一起入库」。

## 7. 工作区自检

只读，不动任何文件。检查项与库自检**完全一致**（同一份 `core.check.check_library`），
区别是扫描范围限在工作区顶层，并且把文件名 ↔ 标签的比对结果结构化返回。

| 检查项 | 常量 | 说明 |
|---|---|---|
| 文件名格式 | `KIND_FILENAME` | 是否「歌手 - 歌名」，不规范的可给出建议名 |
| 标签不完整 | `KIND_TAGS` | 缺歌曲名/歌手/专辑/年份/内嵌封面都算 `severe` |
| 文件名与标签不一致 | `KIND_MISMATCH` | 见 7.1 |
| 重复文件 | `KIND_DUP` | 工作区内部的重复（跨库的重复由第 6 步负责） |
| 缺少歌词 | `KIND_NO_LRC` | 没有同名 `.lrc` |
| 孤立歌词 | `KIND_ORPHAN_LRC` | 有 `.lrc` 但没有对应音频 |

### 7.1 文件名 ↔ 标签比对

这一步原本就存在（`core.check._consistency_problem`），但它只返回「矛盾/不矛盾」一个值，
页面拿不到逐项结果，而且只有库自检在用。现在收敛为 `core.check.consistency_report(track)`：

```text
{
  ok: bool, problem: str|None,
  file: {artist, title},          # 从文件名解析
  tag:  {artist, title},          # 从标签读取
  items: [{field, label, file, tag, state, reason}, ...]
}
```

`state` 有三种，不是两种：

| state | 含义 | 算不算问题 |
|---|---|---|
| `ok` | 一致（歌手按 token 交集/子串，歌名归一化后允许互相包含） | 否 |
| `mismatch` | 明确矛盾 | **是**，文件无法入库 |
| `skipped` | 这一维不可比：文件名没有「歌手 - 歌名」结构、标签为空、群星/未知歌手 | 否 |

`skipped` 单独列出来，是为了避免把「标签根本没填」误报成「标签写错了」——
前者去第 5 步补，后者才需要改。`_consistency_problem()` 保留为它的薄包装，
两者的结论逐字一致（有回归用例）。

页面对每行显示两个小标签（歌手 ✓/✗/—、歌名 ✓/✗/—），悬停看具体值或跳过原因。

### 7.2 页面

- 统计卡：文件数 / 可入库 / 文件名与标签矛盾 / 标签不完整 / 文件名不规范 / 缺歌词 / 孤立歌词 / 工作区内重复。
- 「只看有问题的文件」开关，默认关闭（保留全量视图，便于对照）。
- 主表四列：文件名 / 文件名解析 / 标签 / 一致性，末尾是问题汇总。
- 「其他检查项」按 kind 分组，点击展开明细。
- 本步不需要「执行」按钮：查到的问题由第 5 步（改标签）或第 8 步（未达标进待确认）处理。

## 8. 归档

- 目标二选一：**直接入库**（`LIBRARY_DIR`，推荐）或**只在工作区整理**
  （`WORKSPACE_DIR` 内建 `<年代>/<年份>`，先不入库）。
- 预览按 `<年代>/<年份>` 分组（`1980-1989/1985`），另列「无法归档」（缺年份/缺歌手/文件名与标签矛盾）。
- 执行走 `core.ops.Plan`：可归档的进年份目录；可按勾选把不可归档的移入 `INCOMPLETE_DIR`。
- 所有移动写 `log/journal.jsonl`；删除一律进 `log/_trash/`。
- 完成后弹结果（已移动 / 失败 / 转待确认），点「完成」回到第 2 步处理下一批。
- 归档不判断「库里是否已有」——那是第 6 步的职责，页面上也写明了这一点。

## 9. 状态、回退与「跳过」

- 步骤条只允许回到**访问过**的步骤（`maxStep`）；2a/2b 高亮为第 2 步。
- 「上一步」按 目录 → 操作 → 拷贝 → 解密 → 标签 → 查重 → 自检 → 归档 的线性顺序回退；
  2a/2b 的「上一步」直接回第 2 步。
- 「下一步」的落点按当前视图查表决定（`app.js` 的 `forward`），不在各步里硬编码，
  避免同名事件互相串台。
- 每页刷新都会重新拉取预览，因此回退后看到的是当前真实状态，不是缓存。
- 「跳过」在 3、4 两步需要显式确认；第 6 步在有未处理项时也会二次确认。
- 任务在跑时：不能改目录（接口 409）、不能重复提交、不能前进/后退按钮。

## 10. 接口与文件

| 文件 | 职责 |
|---|---|
| `web/static/index.html`、`web/static/css/app.css`、`web/static/js/*.js` | Vue 3 前端（每步一个组件，`web/static/js/app.js` 是状态机） |
| `web/api.py` | 路由：向导八步 + 保留的旧接口 |
| `web/tasks.py` | 单工作者串行队列；`Task.set_progress()` 记录 `done/total/item` |
| `services/steps.py` | 八步编排（CLI 与 Web 共用），不新增判定规则 |
| `services/settings_store.py` | `config.ini [paths]` 的唯一写入点 |
| `core/library.py` | 「库是否已初始化」的唯一判据 |
| `core/check.py` | 检查规则；`consistency_report()` 是文件名 ↔ 标签比对的唯一实现 |
| `core/dedupe.py` | 库内查重（`find_duplicates`）与跨集合查重（`match_against`） |
| `core/scan.py` | `month_from` / `month_to` |
| `core/ops.py` | `copy_items(on_item=…)` 逐条回调 |
| `services/decrypt.py` | `encrypted_candidates()` / `decrypt_direct()` |
| `decrypto/qq.py` | `run_decrypt(files=…)`：只解密指定文件 |
| `tagger/__init__.py` | `Tagger(write_cover=…, write_lyrics=…, fields=…)` |

向导接口（前缀 `/api`）：

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/wizard/state` | 目录 + 库状态 + 平台能力 + 月份列表 |
| POST | `/wizard/dirs` | 保存目录设置 |
| GET | `/fs/list`、POST `/fs/mkdir` | 目录浏览与新建 |
| GET | `/library/status`、POST `/library/init` | 库状态与初始化 |
| GET/POST | `/copy/preview`、`/copy/run` | 第 3 步 |
| GET/POST | `/decrypt/preview`、`/decrypt/run` | 第 4 步 |
| GET/POST | `/tags/preview`、`/tags/run` | 第 5 步批量补全 |
| GET | `/track` | 第 5 步单曲详情 |
| POST | `/track/save`、`/track/fetch` | 第 5 步保存 / 在线取标签 |
| GET/POST | `/dedupe/preview`、`/dedupe/run` | 第 6 步 |
| GET/POST | `/selfcheck/preview`、`/selfcheck/run` | 第 7 步 |
| GET/POST | `/archive/preview`、`/archive/run` | 第 8 步 |
| GET | `/workspace/files` | 工作区文件列表（拷贝/解密页右栏） |
| GET | `/media/info`、`/media/lyric` | 试听前的只读元数据与结构化歌词 |
| GET/HEAD | `/media/stream` | 音频字节流（支持 Range 206） |
| POST | `/media/open` | 用系统默认播放器打开不可播格式 |

媒体接口不属于八步，全部只读（`/media/open` 只启动本机播放器，不改文件），也不进
`web/tasks.py` 串行队列。契约与格式矩阵见 [media-player.md](media-player.md)。

## 11. 边界（明确不做）

- 不做多用户/多库：`config.py` 是模块级全局态，服务只绑 `127.0.0.1`，一个进程一个配置。
- 不做并发任务：队列串行，避免两条流程同时改同一批文件。
- 不在浏览器里删文件：向导只调用已有的 `Plan`，删除仍等于移入 `log/_trash/`。
- 不做「批量跳过失败再重试」：失败就留在原处，下一轮预览会重新列出来。
- 单曲编辑不改文件名：只写标签与 `.lrc`。
- 查重不自动处理 `unknown`：大小与时长的证据不足时交给人。
- 查重不跨格式**猜**音质：跨格式但规格读不出来（如 `.dff`）仍然是 `unknown`，
  只有无损/有损、采样率、位深、码率这些可比证据齐全时才给结论。
