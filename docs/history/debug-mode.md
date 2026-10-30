# 历史归档：Debug 模式设计

> **归档说明**：本文合并自 `DEBUG_MODE_GUIDE.md` 与 `DEBUG_MODE_SUMMARY.md`。
> Debug 模式在 `0.2.0` 重构后基本保留（`--debug` 仍然有效），但文中提到的
> `soundalike.py`、`tag_updater.py` 等文件已不存在，对应能力现在位于
> `services/soundalike.py` 与 `services/tagger.py`。
> 排查现代码时以 [../troubleshooting.md](../troubleshooting.md) 为准。

## 设计目标

为 `music_helper` 与 `soundalike`（Go）两个项目提供统一的调试输出：记录运行中的参数、
查询值、中间计算结果与 HTTP 往返，用于排查匹配失败、性能瓶颈与数据异常。

启动方式：`--debug`（Go 侧是 `--debug` 或 `-debug`）。

---

## music_helper

### 启用

```bash
python main.py --debug
python main.py --debug --check
python main.py --debug --month 202406
```

### 输出位置与内容

| 位置 | 内容 |
|---|---|
| `main.py` | 命令行参数、工作目录、各步骤状态、`Plan` 全文 |
| `utils.py` | DEBUG 级日志，同时写文件与控制台 |
| `services/soundalike.py` | 调用命令与参数，追加 `-log-sec=1`（每秒一行进度） |
| `services/tagger.py` | 每个文件的处理过程、指纹匹配器初始化状态、命中的来源与分数 |
| `Fingerprint/musicbrainz_matcher.py` | 见下 |

### FingerprintMatcher 的调试信息

- **FingerprintMatcher**：初始化参数、文件路径与元数据、指纹结果（前 50 字符、时长、错误）、
  AcoustID 返回条数与最佳分数、完整匹配过程。
- **AcoustIDClient**：请求参数（URL、指纹长度、时长、`meta`）、请求体长度、HTTP 状态、
  解析出的结果数、最佳匹配选择过程。
- **RecordingResolver**：每个候选的处理、MBID、`sources`、`title`。
- **ReleaseLoader**：release id、`inc` 参数、请求 URL、缓存状态。
- **HTTPClient**：方法/URL/headers/数据长度、响应耗时、状态码与内容长度、JSON 解析结果。

### 日志文件

- 主日志：`log/Music-YYYYmmdd_HHMMSS.log`（DEBUG 级全量）

### 示例输出

```
DEBUG: ============================================================
DEBUG: FingerprintMatcher 初始化
DEBUG: ============================================================
DEBUG:   debug_mode = True
DEBUG:   fpcalc_path = None
DEBUG:   client_version = 1.0
DEBUG: ============================================================
DEBUG: 开始匹配音频文件
DEBUG: audio_file_path = /path/to/1.flac
DEBUG: 文件存在: True
DEBUG: 文件大小: 12345678 bytes
```

---

## soundalike（Go）

### 启用

```bash
./soundalike --debug /path/to/music
./soundalike --debug -move-interactive /duplicate_dir /path/to/music
./soundalike --debug -temp /temp_dir /path/to/music
```

`--debug` 若未显式设置，会自动补上 `-log-sec=1`。

### 输出内容

- **main.go**：Debug 启用提示、自动设置的参数。
- **scan.go**：初始化的 lookup/match 阈值、数据库加载、逐文件处理（路径、大小、mtime、
  是否需要重算指纹、`fpcalc` 结果、入库 ID、lookup 阈值位数与百分比、匹配过程）。
- **db.go**：SQL 语句、加载与保存过程。
- **日志**：同时输出到 stdout 与 `SoundAlike-YYYYMMDD_HHMMSS.log`（运行目录下）。

### 示例输出

```
[DEBUG] scanFiles started
[DEBUG] lookup threshold: 0.25
[DEBUG] match threshold: 0.95
[DEBUG] Loading fingerprints from database...
Loaded 1000 fingerprint(s) from database
[DEBUG] Processing: 1980-1989/1986/1.mp3
[DEBUG]   Size: 4567890 bytes
[DEBUG]   Needs fingerprint: true
[DEBUG]   Running fpcalc...
[DEBUG]   Duration: 245.30s
[DEBUG]   Fingerprint length: 120
[DEBUG]   Saved to database with ID: 1001
[DEBUG]   Lookup threshold: 30 bits (0.25% of 120)
```

---

## 使用建议与注意事项

- **问题排查**：匹配失败、查询异常时首选 `--debug`。
- **性能分析**：靠时间戳与响应耗时定位瓶颈。
- **数据验证**：核对中间变量，确认计算与映射正确。
- **注意**：输出量大，只在小样本上开（配合 `--limit`）；日志会含完整路径与查询参数，
  分享前请脱敏。
