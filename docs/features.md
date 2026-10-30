# 功能规则详解

本文只讲**规则与边界**：每个检查/动作到底怎么判定、什么情况不触发、坑在哪里。
想改行为先看这里，改完记得同步更新。

---

## 1. 文件名规则（`core/naming.py`）

全项目唯一的命名规则实现，其他模块必须复用。

### 解析 `parse_filename`

优先级：

1. 含 ` - `（空格-空格）→ 在**第一个** ` - ` 处切成 `(艺术家, 歌名)`；
2. 否则含 `-` → 在第一个 `-` 处切；
3. 都没有 → 艺术家为空，整串当歌名。

```python
parse_filename('Taylor Swift - Love Story.mp3')   # ('Taylor Swift', 'Love Story')
parse_filename('AC-DC - Back In Black.flac')       # ('AC-DC', 'Back In Black')
parse_filename('小城故事.flac')                     # ('', '小城故事')
```

### 合规判断 `is_canonical`

要求：能切出非空艺术家 + 非空歌名，**且**文件名部分含 ` - `。
所以 `AC-DC - Back.flac` 合规，`AC-DC-Back.flac` 不合规。

### 规范化 `canonicalize`

只在**恰好一个 `-` 且不含 ` - `** 时改写，其余返回 `None`：

| 输入 | 输出 | 原因 |
|---|---|---|
| `Taylor Swift-Love Story.mp3` | `Taylor Swift - Love Story.mp3` | 单个连字符，典型漏空格 |
| `AC-DC-Back.flac` | `None` | 两个连字符，改了就毁掉乐队名 |
| `AC-DC - Back.flac` | `None` | 已含 ` - `，无需处理 |
| `-abc.flac` / `abc-.flac` | `None` | 一侧为空，不猜 |

> 这是刻意保守的取舍：宁可漏改，也不要把 `AC-DC` 改成 `AC - DC`。
> 旧实现按「第一个 `-`」无脑切分，会把这类文件名改坏。

### 生成 `format_filename`

去掉 Windows 非法字符 `\ / : * ? " < > |` 与换行制表符，替换为 `_`；
艺术家为空时退化为 `歌名.扩展名`。

### 工具函数

- `normalize_text`：去掉所有空白并转小写，用于一致性比较。
- `normalize_key`：在 `normalize_text` 基础上再去掉括号内容（`(1)`、`[无损]`、`（伴奏）`），
  用于宽松比对。
- `split_artist`：按 `; ；, ，& / 、 • · | ｜ + ＋` 拆分多艺术家。
- `is_audio`：扩展名属于 `.flac .mp3 .wav .ape .ogg`。

---

## 2. 元数据一致性（`core/check.py: _consistency_problem`）

比较「文件名解析结果」与「音频标签」，只在**两者都有值**时比较：

- **歌手**：两侧各自 `split_artist` 后做集合比较，有交集即视为一致
  （`A feat. B` 对 `A` 不算矛盾）。无交集报 `歌手: 文件名「X」≠ 标签「Y」`。
- **歌名**：`normalize_text` 后比较；若一方是另一方的子串也视为一致
  （处理 `小城故事` vs `小城故事 (Live)`）。
- 任一侧为空则跳过，不报错——缺标签由「标签完整性」单独报告。

矛盾属于**必须人工处理**（`severe=True`），`--fix` 会把文件移入
`review/文件名与标签不一致/`，不做自动改写——因为无法判断是文件名错还是标签错。

---

## 3. 标签完整性（`core/tags.py`）

### 检查字段

| 字段 | 标签键 | 缺失后果 |
|---|---|---|
| 歌曲名 | `title` | **严重**，无法归档，`--fix` 会移入待处理目录 |
| 歌手 | `artist` | **严重**，同上 |
| 专辑 | `album` | 仅报告 |
| 年份 | `year` | 仅报告（归档需要，缺了进 `unknown/`） |
| 封面 | 文件内嵌 | 仅报告 |

`missing_tag_fields(track)` 返回缺失项中文名列表。

### 读写实现

- 读取用 `mutagen.File` 统一入口，返回小写键的 dict：`title/artist/album/year/genre/lyrics`。
- 写入按格式分派：MP3/WAV 用 ID3（`TIT2/TPE1/TALB/TDRC/TCON`），FLAC/OGG 用 Vorbis
  Comment（`TITLE/ARTIST/ALBUM/DATE`），APE 用 APEv2。
- 封面：MP3 用 `APIC`，FLAC 用 `Picture`，OGG 用 `metadata_block_picture`。
- `mutagen` 未安装时 `MUTAGEN_AVAILABLE=False`，所有读写降级为「读不到/写不进」，
  程序**照常启动**，检查全部走「标签缺失」分支。

> 注意：`year` 读取时做了四位数字提取，`2004-05-01` 与 `2004` 都得到 `2004`。

---

## 4. 重复判定（`core/dedupe.py`）

两套策略，同一文件只会落进一个组。

### 策略 A：标签维度

键为 `(标准化歌手, 标准化歌名)`，同一键下再按**时长聚类**。

### 策略 B：文件名维度

键为「去掉结尾 `(1) (2) （1）` 后的文件名主干」，同样按时长聚类。
只用于策略 A 没覆盖到的文件（例如标签全空、只剩文件名）。

### 时长聚类

- 把时长升序排列，相邻差值 ≤ `DURATION_TOLERANCE`（默认 3 秒）归为一簇；
- 时长读到 0（读取失败）的文件并进第一簇，但组上标记 `duration_unknown=True`，
  报告里写「时长未知」，提醒人工复核。

> 这是「相近」而非「两两比较」的实现——避免 A≈B、B≈C 时把 A 和 C 也判成一组。

### 保留策略 `pick_keep`

按 `(格式质量分, 文件大小)` 取最大：

| 格式 | 分 |
|---|---|
| `.flac` | 5 |
| `.wav` / `.ape` | 4 |
| `.ogg` | 3 |
| `.mp3` | 2 |

即优先无损，同格式留体积大的（通常码率更高）。其余进 `drop`。

### 处置

默认**只报告**。`--trash-dup` 进回收站；流程中未加 `--no-move` 时移入
`review/重复文件/`。

---

## 5. 歌词检查（`core/lyrics.py`）

| 检查 | 规则 | 报告类型 |
|---|---|---|
| 缺失 | 音频同目录下没有同名 `.lrc` | `缺少歌词` |
| 孤立 | `.lrc` 同目录下没有同名 `.flac/.mp3/.wav/.ape/.ogg` | `孤立歌词` |

两边都不移动文件，只进报告与 CSV 清单。歌词写入只在标签更新阶段、且文件本来没有 `.lrc` 时发生。

---

## 6. 归档规则（`core/organize.py`）

### 必要条件

`title`、`artist`、`year` 三者齐全且年份可解析为整数，否则进 `unknown/`。

### 目录结构

```
<归档根>/<年代>/<年份>/<文件名>
```

`decade_label`：

| 年份 | 目录 |
|---|---|
| ≤ 1979 | `1950-1979` |
| 1980–1989 | `1980-1989` |
| 1990–1999 | `1990-1999` |
| … | 依此类推 |

`1950-1979` 用合并区间是因为早期文件稀少、单独分年代意义不大。

### 冲突处理

目标已存在同名文件时，`Plan` 自动加 `_1`、`_2` 后缀，**不覆盖、不删除**。

### 归档根

- `--only-archive` / 流水线：归档进临时目录内部（`TEMP_COMPLETED_DIR/<年代>/<年份>/`）
- `--manual-archive`：归档根是 `MAIN_DIR`，源是临时目录，一步完成「移动 + 分类」

---

## 7. 检查报告（`core/report.py`）

每次 `--check` 或流水线结束生成两份文件到 `log/reports/`：

| 文件 | 内容 |
|---|---|
| `report-YYYYmmdd_HHMMSS.md` | 摘要 + 各问题类型的明细表 |
| `review-YYYYmmdd_HHMMSS.csv` | `类型,路径,说明`，UTF-8 BOM，Excel 可直接打开 |

- 摘要固定列出 6 类计数：文件名格式、标签不完整、文件名与标签不一致、重复文件、
  缺少歌词、孤立歌词——**即使为 0 也会显示**，避免「没看到 = 没问题」的误判。
- Markdown 里每个类型都有一张明细表；重复文件额外有一张「待处理文件 / 说明」表，
  说明里写明「重复于哪个文件」。
- CSV 收所有需要人工处理的行。凡是进了 CSV 的段落，Markdown 正文只留一句
  `共 N 条，明细见同目录下的 review-*.csv`，不在两处重复列同一批路径。

---

## 8. VIP 解密（`services/decrypt.py`）

### 流程

```
扫描 VIP 下载目录（仅当层，不递归）→ 移入解密临时目录 → 调用外部程序
  → 对比产出目录前后快照，算出本次新增文件 → 处理加密原文件
```

### 关键点

1. **只认加密扩展名**：网易云 `.ncm`，QQ `.mflac/.mgg`；`--month` 按文件修改月份过滤。
2. **产出判定靠快照差集**，不看外部程序返回码——外部程序常返回 0 却没产出。
3. **失败必还原**：任何异常都把本次移入的加密文件原样搬回 VIP 目录。
4. **加密原文件去向**由 `ENCRYPTED_SOURCE_MODE` 决定，默认 `return` 搬回 VIP 下载目录
   （见 [configuration.md](configuration.md#加密原文件去向)）。
5. **超时**：`SUBPROCESS_TIMEOUT`，超时按失败处理并还原。

> 旧实现会把 `TEMP_COMPLETED_DIR` 顶层**所有**文件搬进 VIP 目录——执行一次解密，
> 整条流水线的产物都会被搬走。现在只操作本次移入的那几个文件。

---

## 9. 声纹去重与库一致性（`services/soundalike.py`）

### 去重 `run(with_temp)`

```bash
soundalike.exe -move-interactive <TEMP_MOVE_DIR> [-temp <TEMP_COMPLETED_DIR>] <MAIN_DIR> [-log-sec=1]
```

- `-move-interactive`：重复项交互式确认后移到 `TEMP_MOVE_DIR`；
- `-temp`：把临时目录也纳入比对（流水线用）；
- `-log-sec=1`：`--debug` 时追加，每秒输出一行进度。

### 库一致性 `check()`

```bash
soundalike.exe -check <MAIN_DIR>
```

比对数据库记录与磁盘实际文件，退出码 0 视为一致。

### 注意

- `soundalike.exe` 会在**当前工作目录**生成 `music.db`，已加入 `.gitignore`；
  从别的目录启动会生成在别处，找不到「库」时先确认这一点。
- 外部程序返回非 0 不会抛异常，只体现在 `ToolResult.ok`。

---

## 10. 标签更新（`services/tagger.py`）

### 顺序

```
声纹（MusicBrainz/AcoustID） → 成功则结束
  ↓ 失败或未达阈值
在线平台（QQ 音乐 + 网易云并行查询，按 tag_score 择优）
  ↓
只填补空缺字段（已有标签优先）
  ↓
封面（仅当文件无封面）→ 歌词（仅当无 .lrc）
```

### 规则

- **已有标签永不覆盖**，只填空缺。要强制刷新请先手动清空对应标签。
- 声纹结果需 `score >= FINGERPRINT_THRESHOLD`（默认 50）才采用；在线结果无硬门槛，
  靠 `core/scoring.py: tag_score` 打分择优。
- 歌手匹配做集合交集校验，避免「同名不同曲」错配。
- 封面超过 `MAX_COVER_SIZE`（5 MB）直接放弃。
- `--dry-run` 下只计算不写入，`UpdateResult` 仍会标出「将会变更哪些字段」。

### 结果字段

`UpdateResult.fields`（写入的标签键）、`cover`、`lyric`、`source`（`MusicBrainz(87)` /
`QQ音乐` / `网易云音乐`）、`error`。

---

## 11. 日志

| 日志 | 位置 | 用途 |
|---|---|---|
| 主日志 | `log/Music-YYYYmmdd_HHMMSS.log` | 每次运行一个，同时输出到控制台 |
| 操作日志 | `log/<操作名>-*.log` | `create_operation_log()` 创建，返回 `Logger` |
| 操作流水 | `log/journal.jsonl` | 每条动作一行 JSON：时间/计划名/动作/源/目标/原因/成败/错误 |

`--debug` 把主日志级别降到 DEBUG，并把计划全文打印出来（`plan.describe()`）。

`journal.jsonl` 的用途是**事后追责与手工回滚**：知道哪个文件什么时候被谁搬到哪，
就能反着搬回来。目前没有自动 `--rollback`，需要按记录人工操作。
