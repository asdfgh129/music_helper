# Debug 模式使用指南

## 概述

两个项目（music_helper 和 soundalike）都已添加 Debug 模式支持，可以详细记录运行过程中的各种变量信息、查询值、计算值等中间信息。

## music_helper Debug 模式

### 启用方式

```bash
# 在 main.py 中使用 --debug 标志
python main.py --debug

# 结合其他参数使用
python main.py --debug --check
python main.py --debug --month 202406
```

### Debug 输出内容

Music Helper 的 Debug 模式会在以下位置输出详细信息：

#### 1. 主程序 (main.py)
- 命令行参数解析结果
- 工作目录信息
- 各步骤的执行状态

#### 2. 日志系统 (utils.py)
- DEBUG 级别的日志输出到文件和控制台
- 更详细的时间戳和日志信息

#### 3. 声纹识别模块 (soundalike.py)
- 调用 SoundAlike 时的命令参数
- `-log-sec=1` 参数（每秒记录一次日志）

#### 4. 标签更新模块 (tag_updater.py)
- 每个文件的处理过程
- 指纹匹配器的初始化状态

#### 5. MusicBrainz 匹配器 (Fingerprint/musicbrainz_matcher.py)

**FingerprintMatcher 类:**
- 初始化参数
- 文件路径和元数据信息
- 指纹计算结果（指纹值前50字符、时长、错误信息）
- AcoustID 查询结果（返回结果数、最佳匹配分数）
- 完整的匹配过程追踪

**AcoustIDClient 类:**
- API 查询参数（URL、指纹长度、时长、meta 参数）
- 请求体长度
- HTTP 响应状态
- 解析出的结果数量
- 最佳匹配算法的详细过程

**RecordingResolver 类:**
- 每个结果的处理过程
- 录音信息的详细解析
- MBID、sources、title 等字段的值

**ReleaseLoader 类:**
- Release ID 和 inc 参数
- API 请求 URL
- 缓存状态

**HTTPClient 类:**
- HTTP 请求详细信息（方法、URL、headers、数据长度）
- 响应接收时间
- 状态码和响应内容长度
- JSON 解析状态

### 测试文件中的 Debug 模式

```bash
# MusicBrainz 连接测试（带 debug）
python test/test_musicbrainz_connection.py --debug

# 直接 API 测试
python test/test_musicbrainz_direct.py
```

## soundalike Debug 模式

### 启用方式

```bash
# 使用 --debug 标志
./soundalike --debug /path/to/music

# 结合其他参数
./soundalike --debug -move-interactive /duplicate_dir /path/to/music
./soundalike --debug -temp /temp_dir /path/to/music
```

### Debug 输出内容

SoundAlike 的 Debug 模式会输出：

#### 1. 主程序 (main.go)
- Debug 模式启用提示
- 自动设置 `-log-sec=1`（如果没有设置）

#### 2. 扫描选项 (scan.go)
**scanFiles 函数:**
- 初始化时的参数（lookup threshold、match threshold）
- 数据库加载信息
- 每个文件的处理过程：
  - 文件路径
  - 文件大小和修改时间
  - 是否需要重新计算指纹
  - fpcalc 执行结果（时长、指纹长度、压缩指纹长度）
  - 保存到数据库的 ID
  - Lookup 阈值计算（位数、百分比）
  - 查找匹配的过程

#### 3. 数据库操作 (db.go)
- SQL 查询语句
- 数据加载和保存过程

#### 4. 日志输出
所有 DEBUG 信息会同时输出到：
- 控制台（stdout）
- 日志文件（`SoundAlike-YYYYMMDD_HHMMSS.log`）

## Debug 输出示例

### music_helper 输出示例

```
DEBUG: ============================================================
DEBUG: FingerprintMatcher 初始化
DEBUG: ============================================================
DEBUG:   debug_mode = True
DEBUG:   fpcalc_path = None
DEBUG:   client_version = 1.0
DEBUG: ============================================================
DEBUG: ============================================================
DEBUG: 开始匹配音频文件
DEBUG: ============================================================
DEBUG: audio_file_path = /Users/bemin/Code/music_helper/1.flac
DEBUG: metadata = None
DEBUG: 文件存在: True
DEBUG: 文件大小: 12345678 bytes
...
```

### soundalike 输出示例

```
[DEBUG] scanFiles started
[DEBUG] lookup threshold: 0.25
[DEBUG] match threshold: 0.95
[DEBUG] Loading fingerprints from database...
Loaded 1000 fingerprint(s) from database
[DEBUG] Loaded 1000 fingerprints into lookup table
[DEBUG] Processing: 1980-1989/1986/1.mp3
[DEBUG]   Size: 4567890 bytes
[DEBUG]   MTime: 1234567890
[DEBUG]   Needs fingerprint: true
[DEBUG]   Running fpcalc...
[DEBUG]   Duration: 245.30s
[DEBUG]   Fingerprint length: 120
[DEBUG]   Compressed fingerprint length: 96
[DEBUG]   Saved to database with ID: 1001
[DEBUG]   Lookup threshold: 30 bits (0.25% of 120)
...
```

## Debug 日志文件位置

### music_helper
- 主日志文件: `log/Music-YYYYMMDD_HHMMSS.log`
- 包含 DEBUG 级别的所有详细信息

### soundalike
- 日志文件: `SoundAlike-YYYYMMDD_HHMMSS.log`（在运行目录下）
- 包含所有输出（包括 DEBUG 信息）

## 使用建议

1. **问题排查**: 当遇到匹配失败、查询错误等问题时，使用 `--debug` 查看详细信息
2. **性能分析**: 通过时间戳和响应时间分析各步骤的耗时
3. **数据验证**: 查看中间变量值，确认计算过程是否正确
4. **API 调试**: 查看 HTTP 请求和响应的详细信息

## 注意事项

- Debug 模式会产生大量日志输出，建议只在排查问题时使用
- 长时间运行的项目会生成大日志文件，注意磁盘空间
- 包含完整的查询参数和响应，注意隐私保护
- Debug 输出包含文件路径和内容，确保安全
