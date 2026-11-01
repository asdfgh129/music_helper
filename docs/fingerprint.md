# 指纹匹配（AcoustID / MusicBrainz）

> 本文负责：指纹原理、AcoustID / MusicBrainz 匹配、声纹查重（soundalike）的流程与算法、
> 同曲不同版本的碰撞策略、声纹相关的外部程序与已知缺陷。
> 本文不负责：本地标签/文件名查重（见 [rules.md](rules.md#4-重复判定)）、流水线顺序
> （见 [workflow.md](workflow.md)）、配置项默认值（见 [configuration.md](configuration.md)）。

`fingerprint/` 回答一个问题：**这个音频文件在 MusicBrainz 里是哪一首？**
答案用来补标签——不依赖文件名，也不依赖已有标签，所以对「文件名乱、标签空」的库最有效。

「声纹」在本项目里是**两件事**，用同一个 `fpcalc` 指纹但目的不同：

| 用途 | 模块 | 判据 | 结果 |
|---|---|---|---|
| 补标签 | `fingerprint/` + `tagger/` | AcoustID 分数 ≥ `FINGERPRINT_THRESHOLD` | 写入 title/artist/album/year |
| 查重 | `services/soundalike.py` + `tools/soundalike` | 位相似度 ≥ 0.95 | 移入 `DUPLICATE_DIR` |

两套阈值互不干涉，见第 4 节与第 8.5 节。

## 1. 工作原理

```
音频文件 ──fpcalc──► 声学指纹 + 时长
                        │
                        ▼
              AcoustID API（按指纹模糊查找）
                        │  返回候选 recording + 相似度分数
                        ▼
              MusicBrainz（补全 release / artist / 年份）
                        │
                        ▼
              打分排序 → 最优结果 → 标签字段
```

- **指纹**是音频信号本身的特征，跟文件格式、码率、文件名无关；
- `fpcalc` 采样长度为 `FPCALC_LENGTH`（默认 120 秒），**必须与声纹库一致**，否则比对失效；
- AcoustID 负责「像不像」，MusicBrainz 负责「是哪张专辑、哪一年」。

## 2. 依赖

| 依赖 | 用途 | 缺失后果 |
|---|---|---|
| `fpcalc`（Chromaprint） | 计算指纹（补标签与查重都用它） | 声纹匹配降级为在线平台查询；声纹去重整步失败 |
| `acoustid` / `requests` | 调用 API | 同上（本模块内部用 `urllib`，不强制 `requests`） |
| `opencc` | 繁简转换 | 繁体标题不转换，匹配率略降 |
| 网络 | 访问 acoustid.org / musicbrainz.org | 查询失败，返回 `MatchResult(success=False)` |

`fpcalc` 的查找顺序：`config.FPCALC_EXE`（`tools.fpcalc_exe` / `MUSIC_HELPER_FPCALC_EXE`）
指向的文件存在就用它，否则退回系统 `PATH`。

- 仓库自带两份，都是 Chromaprint **1.6.2**（指纹算法没变，与旧版库兼容）：
  `tools/fpcalc`（macOS 通用二进制：arm64 + x86_64）、`tools/fpcalc.exe`（Windows x86_64）；
- Windows 早期只有 `C:\Windows\System32\fpcalc.exe`（1.6.0）在用；现在 `tools/fpcalc.exe`
  存在就优先用它，PATH 退居兜底；
- 想换版本就覆盖 `tools/fpcalc` / `tools/fpcalc.exe`，或设 `MUSIC_HELPER_FPCALC_EXE`。

其他安装方式（可选）：

```bash
# macOS（brew，注意与仓库自带的 1.6.2 可能不同版本）
brew install chromaprint
# Ubuntu / Debian
sudo apt install libchromaprint-tools
```

> **指纹参数与声纹库绑定**：`soundalike` 把 `-fpcalc-length` / `-algorithm` 写进
> `Settings` 表，参数与库不一致会直接报 `database settings (...) don't match`。
> 改 `fpcalc_length` 等于换了一套指纹，必须删掉 `music.db` 重新 `--init`。

## 3. 作为库使用

```python
from fingerprint import FingerprintMatcher

matcher = FingerprintMatcher()                 # fpcalc 不在 PATH 时传 fpcalc_path=...
result = matcher.match_file('song.flac')

if result.success and result.recordings:
    best = max(result.recordings, key=lambda r: r.get('score', 0))
    print(best['score'], best.get('title'), best.get('artist'))
else:
    print('未匹配:', result.error)
```

常用成员：

| 成员 | 说明 |
|---|---|
| `FingerprintMatcher(fpcalc_path=None, client_version=None, debug_mode=False)` | 主入口 |
| `.match_file(path, metadata=None)` | 返回 `MatchResult` |
| `MatchResult.success / recordings / best_match / error` | `recordings` 是按分数排好序的 dict 列表 |
| `format_recording_info(recording)` | 把一条 recording 格式化成可读文本 |
| `FingerprintCalculator(fpcalc_path)` | 只算指纹，不查网络 |
| `AcoustIDClient` | 只查 AcoustID，不算指纹 |

在项目里不需要直接调用——`tagger/__init__.py` 已经封装好降级与阈值判断：

```python
# tagger/__init__.py 内部
match = matcher.match_file(track.path)
if match.success and match.recordings:
    best = max(match.recordings, key=lambda r: r.get('score', 0))
    if float(best.get('score') or 0) >= config.FINGERPRINT_THRESHOLD:
        ...  # 只填补空缺标签
```

## 4. 评分与阈值

- AcoustID 的原始分数是 0–1 的概率值；`fingerprint/` 在合并多个来源后会归一化为
  **0–100 的百分制**，`tagger/` 直接与 `config.FINGERPRINT_THRESHOLD`（默认 50）比较；
- 多个候选时取分数最高的一条；
- 低于阈值视为「没匹配上」，转由在线平台查询（`tagger/__init__.py` 第二步）。

阈值调低会补更多标签，但也更容易张冠李戴；调高则宁可留空。默认 50 是「能补上、又不至于
把现场版当成录音室版」的折中。

> `FINGERPRINT_THRESHOLD` **只用于标签匹配**，不参与查重。查重是否执行由
> `--skip-fingerprint` 控制，移动目标由 `soundalike` 的交互确认决定。

## 5. 已知限制

| 限制 | 说明 |
|---|---|
| AcoustID 密钥是内置的公共 key | `AcoustIDConfig.ACOUSTID_KEY = 'v8pQ6oyB'`，有速率限制；高频使用请自行申请 |
| 只有网络请求、没有本地缓存 | 同一文件重复查询会重复请求；批量处理时建议先用 `FINGERPRINT_THRESHOLD` 过滤 |
| SSL | 代码对 macOS 使用了 `ssl._create_unverified_context()` 规避证书问题，安全性上属于妥协 |
| 中文匹配 | 依赖 `opencc` 做繁简统一，未安装时繁体标题匹配率下降 |
| 时长偏差 | 现场版、混音版与原版指纹可能相近，最终仍要看分数 |

## 6. 同曲不同版本的碰撞

结论：**声纹会误判，但场景可枚举。指纹只能证明「音频很像」，不能证明「是同一版本」。**
因此查重不能只看指纹，必须叠加时长、版本标记与元数据。

### 6.1 常见误判场景

| 场景 | 指纹表现 | 处理 |
|---|---|---|
| 同一录音换格式/码率 | 几乎相同 | 判重复（期望行为） |
| 同一录音收在不同专辑 | 几乎相同 | 判重复 |
| Remaster（重新母带） | 高度相似 | 倾向判重复 |
| 现场版 vs 录音室版 | 可能高度相似 | 版本标记不同 → 人工 |
| 伴奏版 / instrumental | 可能相似 | 版本标记不同 → 人工 |
| 不同歌手同一伴奏（翻唱/KTV） | 可能相似 | 版本标记不同 → 人工 |
| feat. 版本（加一段 verse） | 大部分相同 | 版本标记不同 → 人工 |
| 短片段、纯音乐、重复节奏 | 易碰撞 | 时长过滤 + 人工 |

### 6.2 判定矩阵

| 指纹 | 版本标记 | 时长差 | 结论 |
|---|---|---|---|
| 高相似 | 同类 | ≤ `DURATION_TOLERANCE` | 重复，保留质量最高者 |
| 高相似 | 不同类 | 任意 | 疑似不同版本 → 人工复核 |
| 高相似 | 一方缺失标记 | ≤ `DURATION_TOLERANCE` | 重复候选 → 人工复核 |
| 低相似 | 同类 | ≤ `DURATION_TOLERANCE` | 疑似同名不同版 → 人工复核 |
| 低相似 | 不同类 | 任意 | 不同文件，保留 |

关键一条：**「指纹像 + 版本标记不同」永远不自动移入 `DUPLICATE_DIR`。**

### 6.3 现有实现

- 本地查重键由 `core/naming.py: version_key()` 生成，保留 Live/Remix/伴奏等标记。
  `晴天 (Live)` 与 `晴天` 不会进入同一个标签桶；
- `core/dedupe.py` 在键相同后再按时长聚类，时长未知的候选会被标注；
- `soundalike` 是外部黑盒，项目无法读取它的相似度分数，只能通过
  `-move-interactive` 由人工确认每一次移动；
- `soundalike` 的移动目标固定为 `DUPLICATE_DIR`，不会进入回收站；
  `--trash-dup` 只作用于本地查重阶段。

### 6.4 提高准确率的做法

1. 声纹查重前先按「版本感知的去重键」分桶，只对同桶做比对；
2. 版本标记不同的候选写进报告，不自动移动；
3. 重复清单保留「指纹来源 / 时长差 / 版本标记 / 保留理由」，便于回滚；
4. 两个阈值不要混用：`FINGERPRINT_THRESHOLD` 只决定标签匹配，
   `DURATION_TOLERANCE` 只决定查重聚类。

## 7. 调试

```bash
# 提高日志级别看每一步请求与响应
python -c "
from fingerprint import FingerprintMatcher
m = FingerprintMatcher(debug_mode=True)
print(m.match_file('tests/fixtures/1.flac').recordings[:1])
"
```

`tests/manual/manual_musicbrainz.py` 是现成的手工验证脚本（需要真实网络与 AcoustID key）：
`--mode match` 跑全链路，`--mode api` 只打裸接口用来区分网络问题与匹配链路问题，
用法见 [troubleshooting.md](troubleshooting.md)。

## 8. 声纹查重（soundalike）

### 8.1 在流程里的位置

流水线第 2 步（[workflow.md](workflow.md#24-声纹去重)），**早于**补标签与检查：

```
解密 → 声纹去重 → 补标签 → 检查/修复 → 待补全分流 → 年代归档
```

它和本地查重（`core.dedupe`，见 [rules.md](rules.md#4-重复判定)）是**两条独立信号**：

| | 声纹查重 | 本地查重 |
|---|---|---|
| 判据 | 音频波形指纹相似度 | 标签/文件名 + 时长 |
| 覆盖 | 换格式、换码率、换专辑、文件名完全不通 | 同名同曲不同副本 |
| 何时跑 | 流水线第 2 步、`--soundalike` | 每次检查（`--check` / 流水线检查阶段） |
| 谁能移文件 | 外部程序自己移（人工确认） | `core.ops.Plan`（可 `--dry-run`、写 journal） |
| 结果去处 | `DUPLICATE_DIR` | `DUPLICATE_DIR/<重复文件>/` 或 `log/_trash/` |

### 8.2 调用与参数

```text
soundalike -db <DB_PATH> -fpcalc-length <FPCALC_LENGTH> -file-regexp <RE> \
           -move-interactive <DUPLICATE_DIR> [-dry-run] -temp <WORKSPACE_DIR> <LIBRARY_DIR>
```

| 参数 | 本项目取值 | 作用 |
|---|---|---|
| `-db` | `config.DB_PATH` | 声纹库；进程工作目录设到库所在目录，避免「库建在启动目录」 |
| `-fpcalc-length` | `config.FPCALC_LENGTH`（默认 120） | 采样长度，**必须**与库里的 Settings 一致（见 8.5） |
| `-file-regexp` | `services.soundalike.file_regexp()` | 参与扫描的扩展名：`config.AUDIO_EXTENSIONS` ∪ soundalike 内置格式。**必须显式传**，内置正则不含 `.dsf` |
| `-move-interactive` | `config.DUPLICATE_DIR` | 把重复文件移到该目录；音质分得出高下时不询问 |
| `-dry-run` | `--dry-run` 时追加 | 只打印「将移动谁」，不动文件、不写库 |
| `-temp` | `config.WORKSPACE_DIR` | 只比对、不写库的工作区 |
| `-log-sec=1` | `--debug` 时追加 | 每秒一行进度 |
| `-check` | `--checkdb` / `--check` 第 1 步 | 校验库与文件系统一致性 |

环境变量里会临时把 `tools/` 前置到 `PATH`：soundalike 只按 PATH 找 `fpcalc`，而 macOS 的
`fpcalc` 随仓库放在 `tools/`，不注入就会报 `fpcalc not in path`。

四种用法：

| 命令 | 行为 | 动文件 | 写库 |
|---|---|---|---|
| `python main.py` | 流水线内调用：音质差的自动移走，音质相同才问 | 是 | 是 |
| `python main.py --soundalike` | 同上，单独跑 | 是 | 是 |
| `python main.py --soundalike-report` | 只列候选组（等同下一行） | 否 | 否 |
| `python main.py --dry-run` | 试运行：打印「将移动谁」，含自动移走的那部分 | 否 | 否 |

**预览不能写库**，这点以前是错的：`--soundalike-report` 早期是「正经扫描、只是不带移动参数」，
副作用是把指纹写进 `Files` 表；而扫描只比对「新文件/变化过的文件」，于是下一轮正式运行会把
它们当成「已经处理过」，重复**再也报不出来**。现在预览统一走 `-dry-run`：能复用库里已有的
指纹（不用重算），但一份都不写，所以先预览几次再正式跑，结果一样。

### 8.3 数据流

```
LIBRARY_DIR  ──walk──┐
WORKSPACE_DIR ───────┘（仅 -temp，不写库）
        │
        ▼  文件大小 / mtime 与库里记录比对
   ┌──────────────┴───────────────┐
   │ 没变                          │ 新文件 / 变了
   ▼                              ▼
只入查重表                fpcalc -raw -length 120  ──►  []uint32 指纹
（不再比对）                          │
                                     ├─► 写 Files 表（下次不用再算）
                                     ├─► 16 位截断倒排索引查候选
                                     └─► 候选逐位比较，≥ 0.95 记一条边
                                                  │
                          ┌───────────────────────┘
                          ▼
                 边表 → 连通分量 → 一组一组的重复候选
                          ▼
       按音质排序：差的自动移走（不询问）/ 一样好才问
                          ▼
       目标 DUPLICATE_DIR（重名加 (1)(2)），移动成功后才删库记录
```

### 8.4 算法

1. **指纹**：`fpcalc -algorithm 2 -raw -length 120`，算法 2 每秒输出约 8 个 32 位整数，
   120 秒约 970 个值，即一首歌的指纹约 3.9 KB（库里以 BLOB 存）。
2. **候选筛选**：把每个 32 位值截断成 16 位（`v >> 16`）建倒排表，记录「值 → 文件」。
   查询时统计与目标文件共享的截断值个数，超过 `0.25 × 指纹长度` 才进入精算
   （120 秒的歌约 240 个）。这一步把 O(n²) 全库比较压到「只跟长得像的比」。
3. **精算**：两个指纹在所有偏移上逐位对齐（向前、向后各滑一遍），
   相似度 = 相同位数 / (32 × 较长者长度)，取最高分。`≥ 0.95` 视为同一条录音。
4. **分组**：命中的文件两两连边，取**连通分量**。注意这是传递闭包：
   A≈B、B≈C 时 A、B、C 同组，即使 A 与 C 并不像。
5. **决策（按音质取舍，不按大小）**：
   1. 每个文件算一个 `quality`：`tier`（格式层级）+ `bitrate`（`size*8/duration` 估算）；
   2. 逐个比，留下「最好的」：层级不同比层级，同层级比码率（差 ≥2% 才算更好）；
   3. 比它差的一律移入 `DUPLICATE_DIR`，**不询问**；
   4. 只有「音质完全一样」的几个才列出来问保留哪个，回车 = 全部保留；
   5. 组里有**认不出的扩展名**时不敢判断，整组退回人工，避免误移。

   格式层级（`move.go: formatTier`）：

   | 层级 | 扩展名 | 说明 |
   |---|---|---|
   | 6 | `.dsf` `.dff` | DSD |
   | 5 | `.wav` `.aif` `.aiff` `.aifc` | 未压缩 PCM |
   | 4 | `.flac` `.ape` `.wv` `.tta` `.tak` | 无损压缩 |
   | 3 | `.m4a` `.aac` | AAC / ALAC（只看扩展名分不出，同层级内按码率比） |
   | 2 | `.mp3` `.ogg` `.oga` `.opus` | 有损压缩 |
   | 1 | `.wma` | WMA 有损 |
   | 未知 | 其他 | 不参与自动判断，整组交给人工 |

   为什么旧版会丢音质：老实现只有 `flac(4) > wav(3) > ape(2) > mp3(1) > ogg(0) > 其他(-1)`，
   `.dsf` 落在 `-1`，也就是「比谁都差」——同曲的 DSF + MP3 会被判定移走 DSF、留下 MP3。
   现在 DSF 是最高层级，且未知扩展名不再被当成最差的一类。

   码率怎么估：`size*8/duration`，duration 取自 fpcalc 输出的**整首**时长。同一首歌
   128 kbps 与 320 kbps 的 mp3 差 2.5 倍，闸门定在 2% 足以区分码率阶梯，又不会因为
   VBR 的细微差别把同级文件判成「更差」。

### 8.5 阈值

| 参数 | 默认 | 位置 | 作用 |
|---|---|---|---|
| `-lookup-threshold` | 0.25 | soundalike | 倒排表命中比例，决定「要不要精算」 |
| `-match-threshold` | 0.95 | soundalike | 位相似度阈值，决定「像不像同一录音」 |
| `-fpcalc-length` | 120 秒 | 本项目传 `config.FPCALC_LENGTH` | 只比前 2 分钟 |
| `FINGERPRINT_THRESHOLD` | 50 | 本项目 config | **只用于补标签**，与查重无关 |

**指纹长度是库的一部分**：soundalike 把 `length / chunk / algorithm / overlap` 写进
`Settings` 表，打开库时逐字比对，不一致直接报
`database settings (...) don't match current settings (...)` 并退出。

历史情况要知道：`tools/soundalike.exe`（0.1.4，go1.25 构建）自己的默认长度是 **15 秒**，
而源码默认与 `config.FPCALC_LENGTH` 都是 120 秒。本项目现在**显式**传 120，于是：

- 新建库 → 全部 120 秒指纹，补标签与查重口径一致；
- 老库（15 秒建的，例如 `G://Tools//music.db`）→ 开跑前就会被拦下，并给出两条出路：
  删库 `--init` 重建，或把 `fpcalc_length` 改回 15。

改小的代价：全库要重新算指纹，扫描时间按倍数增加（解码 15 秒 vs 120 秒）；改小则反之，
但 15 秒指纹对「同前奏不同版本」更不敏感，误判会变多。

0.95 意味着「32 位字里最多 5% 的位不同」，同一录音换格式/换码率通常在 0.98 以上；
现场版、伴奏版因为前 2 分钟可能一致，也能冲过 0.95——这是第 6 节讨论的碰撞场景。

### 8.6 声纹库

SQLite，四张表：`Settings`（指纹参数，改了就拒绝打开）、`Directories`（绝对目录）、
`Files`（相对路径 + 大小 + mtime + 指纹 + 压缩指纹）、`ExcludedPairs`（人工标记「这俩不是重复」）。

- 记录键是「绝对目录 + 相对路径」，文件在库内移动/改名后按新路径重算指纹；
- `--checkdb` 做双向同步：库里有磁盘没有 → 删记录；磁盘有库没有 → 算指纹补进去；
- 每次运行还会在库文件所在目录写一份 `SoundAlike-<时间戳>.log`（便于事后追查移动了什么）。

### 8.7 平台

| 平台 | 程序 | 说明 |
|---|---|---|
| Windows | `tools/soundalike.exe` | 0.1.5，纯 Go 构建（modernc sqlite 驱动），库文件格式与历史 cgo 版互通 |
| macOS | `tools/soundalike-darwin-arm64`、`tools/soundalike-darwin-amd64` | 0.1.5，与 Windows 版同源同参数 |
| 两者都要 | `tools/fpcalc` / `PATH` 里的 `fpcalc` | 5.4 MB 通用二进制，arm64 + x86_64 |

三平台产物都由 `G://soundalike` 源码编出：`CGO_ENABLED=0` 时走纯 Go 驱动
（`dbdriver_nocgo.go`），需要 cgo 时才切回 `mattn/go-sqlite3`（`dbdriver_cgo.go`）。
同一份源码编出的 Windows 版与仓库内 exe 行为一致（分组、移动、库格式都验过）。

`config.SOUNDALIKE_EXE` 按 `sys.platform` + `platform.machine()` 自动挑，可用
`MUSIC_HELPER_SOUNDALIKE_EXE` 覆盖。

macOS 上首次使用先补可执行位（仓库在 Windows 上克隆时不会记录 exec 位）：

```bash
chmod +x tools/fpcalc tools/soundalike-darwin-*
# 若是通过浏览器/网盘拷贝的，还要去掉隔离标记
xattr -d com.apple.quarantine tools/fpcalc tools/soundalike-darwin-* 2>/dev/null || true
```

## 9. 审核结论

**算法不用换**：倒排筛选 + 位比对 + 连通分量是 Chromaprint 生态的标准做法，阈值也合理。
要改的是「工程边界」，以及「谁保留谁移走」的判据。

### 9.1 第一轮（2026-10-31）：调用链

| 问题 | 现象 | 处理 |
|---|---|---|
| 指纹长度没传给外部程序 | 补标签用 `fpcalc_length`，声纹库却按 exe 内置的 15 秒建库，两边口径不一致 | 固定传 `-fpcalc-length config.FPCALC_LENGTH`；开跑前读 `Settings` 比对，不一致就给出重建/改配置的具体做法 |
| `fpcalc` 找不到 | macOS 上 `fpcalc` 在 `tools/` 不在 PATH，声纹去重直接退出 | 调用时把 `tools/` 前置进 `PATH`；`tagger` 优先用 `config.FPCALC_EXE` |
| 跨盘 `-temp` 必失败 | `WORKSPACE_DIR` 与 `LIBRARY_DIR` 不同盘时 `filepath.Rel` 报错，整次扫描失败（默认配置就是 D: + G:） | 调用前判断同盘，不同盘退化为只比对音乐库并告警 |
| 交互提示看不见 | 外部程序 stdout 被 `capture_output` 吞掉，提示语又没有换行，用户只看到「卡住」 | 有终端时不再捕获，直接把提示交给用户 |
| macOS 无法运行 | 只有 `soundalike.exe` | 提供 arm64 / amd64 二进制 + `tools/fpcalc` |

### 9.2 第二轮（2026-11-01）：取舍规则

用户的要求很明确：**同一首歌存在不同音质时，移走音质差的那份不需要确认，谁留谁走以音质为准。**
按这个口径重写了决策部分，并顺手修掉一轮实测暴露的问题。

| 问题 | 现象 | 处理 |
|---|---|---|
| 只按格式分档，且不认识的格式一律最低 | `.dsf` 是 `-1`：DSD 会被当成「比 mp3 还差」自动移走，留下有损 | 层级扩到 `.dsf/.dff`(6) → PCM(5) → 无损(4) → AAC/ALAC(3) → 有损(2) → wma(1)；**未知格式不再参与自动判断**，整组退回人工 |
| 格式相同就看不出高下 | 128 kbps 与 320 kbps 的 mp3 只能人工挑 | 同层级用 `size*8/duration` 估码率，差 ≥2% 判为「更好」，自动取舍 |
| 扫描范围漏格式 | 内置 `-file-regexp` 不含 `.dsf`，DSD 连指纹都不算 | 由 `config.AUDIO_EXTENSIONS` ∪ soundalike 内置格式生成，显式传给外部程序 |
| 预览会污染库 | `--soundalike-report` 写指纹，下一轮正式运行就「查不出重复」 | 新增 `-dry-run`：复用库里指纹但一份不写；`report()` 改为它的别名 |
| 试运行没有预览能力 | `--dry-run` 整步跳过 | `--dry-run` 现在跑试运行，打印含自动移走部分的完整计划 |
| 跨盘移动在 Windows 上删不掉源文件 | `copyAndRemoveFile` 用 `defer sf.Close()`，`os.Remove` 时句柄还开着 → 「另一个程序正在使用此文件」，副本留下、原件留着 | 显式关句柄后再删；顺带给 `moveFile` / `copyAndRemoveFile` 加「目标已存在 / 源与目标是同一文件」的拒绝 |
| 移动失败会丢库记录 | 先删库记录再移文件 | 反过来：移成功才删，删失败只告警 |
| 目标目录平铺 + 重名 `(1)(2)` | 与「改名撞车一律失败」的约定不一致 | **保留现状**：`DUPLICATE_DIR` 是暂存区，加后缀不会让库里出现查不出来的重复；`moveFile` 本身已拒绝覆盖 |

实测（真实 flac 复本，非交互 stdin）：

| 场景 | 结果 |
|---|---|
| `song.dsf` + `song.flac` + `song.mp3` | 保留 dsf，flac/mp3 自动移走，全程无提示 |
| 两个同码率 `song.flac` | 列出 1/2 让人选，空输入 = 都保留（不乱删） |
| `--dry-run` 连续跑两次 | 两次都能列出同一组，第二次正式运行照常移走（库没被污染） |
| 源在 D:、`DUPLICATE_DIR` 在 C: | 复制 + 删除成功（修好句柄问题前是失败的） |

### 9.3 仍然待改

| 优先级 | 问题 | 影响 | 建议 |
|---|---|---|---|
| P1 | 每个文件跑两次 `fpcalc`（`fpcalc.go`：先 `-raw` 再取压缩指纹），压缩指纹存了却从不参与比对 | 扫描耗时 ≈ ×2，库体积 +30% | 默认只算 `-raw`，压缩指纹做成可选 |
| P1 | 组是传递闭包，「保留的那个」与某个被移走的文件可能根本不像 | 误移风险 | 移动前对「保留者 vs 待移者」再两两比一次 |
| P1 | 没有时长闸门：只比前 120 秒，且不比总时长 | 现场版/伴奏/同前奏的不同版本容易同组 | 精算前加 `\|Δduration\| ≤ DURATION_TOLERANCE` 预筛，与本地查重口径一致 |
| P2 | 「全部保留」不写 `ExcludedPairs` | 本轮跳过 = 以后每轮都会再问一次（不会再被静默吞掉，因为预览不写库了） | 保留时写入 `ExcludedPairs` |
| P2 | 移动只搬音频，不带同名 `.lrc` | 留下孤立歌词，下一轮检查报错 | 移动时同步搬运 `.lrc`（与 `Plan` 行为对齐） |
| P2 | 移动动作不受 `core.ops.Plan` 管，没有 journal | 想查「谁被搬走了」只能翻 `SoundAlike-<时间戳>.log` | 若要纳入统一审计，得改成「soundalike 只报告、Python 用 `Plan` 执行」 |

### 9.4 明确不改的

- **位相似度阈值 0.95**：调低会引入大量「同名不同版」，调高会漏掉重新编码的副本；
- **只比前 120 秒**：全长指纹让库和比对成本线性上升，收益主要在长尾；要更严就叠时长闸门，
  比加长指纹划算；
- **连通分量分组**：改成完全连接会让「A≈B、B≈C、A≉C」的链条漏报，宁可多问一次也不要漏；
- **同码率不自动挑一个**：音质分不出高下时自动选等于随机删，宁可停下来问。
