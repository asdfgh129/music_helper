# Debug 模式实现总结

## 实施日期
2026-03-08

## 项目范围
- **music_helper**: Python 音乐文件管理系统
- **soundalike**: Go 语言的音频文件重复检测工具

## 实现概述

为两个项目添加了完整的 Debug 模式支持，可以详细记录运行过程中的各种变量信息、查询值、计算值等中间信息，便于问题排查和性能分析。

---

## music_helper 项目

### 1. 主程序 (main.py)

**修改内容**:
- 添加 `--debug` 命令行参数
- 将 debug 模式传递给子模块
- 记录命令行参数和工作目录信息

**使用方式**:
```bash
python main.py --debug
python main.py --debug --check
python main.py --debug --month 202406
```

### 2. 日志系统 (utils.py)

**修改内容**:
- `setup_logging()` 函数添加 `debug_mode` 参数
- Debug 模式下设置 DEBUG 级别日志
- 同时输出到文件和控制台

**输出内容**:
- DEBUG 级别的详细日志
- 时间戳精确到毫秒
- 更详细的错误堆栈信息

### 3. 声纹识别模块 (soundalike.py)

**修改内容**:
- `run_soundalike_fingerprinting()` 和 `run_soundalike_fingerprinting_without_temp()` 添加 `debug_mode` 参数
- Debug 模式下自动添加 `-log-sec=1` 参数

### 4. 标签更新模块 (tag_updater.py)

**修改内容**:
- `update_tags_from_fingerprint()` 添加 `debug_mode` 参数
- 传递 debug 模式给 FingerprintMatcher

### 5. MusicBrainz 匹配器 (Fingerprint/musicbrainz_matcher.py)

#### 5.1 FingerprintMatcher 类

**修改内容**:
- 添加 `debug_mode` 参数到 `__init__()`
- 记录初始化参数
- `match_file()` 方法添加详细日志：
  - 文件路径和存在状态
  - 文件大小
  - 指纹计算结果（指纹值前50字符、时长、错误信息）
  - AcoustID 查询结果数量
  - 最佳匹配分数
  - 完整的匹配过程追踪

#### 5.2 AcoustIDClient 类

**修改内容**:
- 添加 `debug_mode` 参数到 `__init__()`
- 传递 debug 模式给 HTTPClient、RecordingResolver、ReleaseLoader
- `query_acoustid()` 方法添加详细日志：
  - 请求 URL
  - 指纹长度和时长
  - meta 参数
  - 请求体长度
  - 响应状态
  - 返回结果数量
  - 第一个结果的部分内容
- `match_fingerprint()` 方法添加详细日志：
  - 录音解析过程
  - 最佳匹配算法过程

#### 5.3 RecordingResolver 类

**修改内容**:
- 添加 `debug_mode` 参数到 `__init__()`
- `resolve()` 方法添加详细日志：
  - 结果数量
  - 每个结果的 acoustid、result_score、recordings 数量
  - 每个录音的 MBID、sources、title

#### 5.4 ReleaseLoader 类

**修改内容**:
- 添加 `debug_mode` 参数到 `__init__()`
- `load_release_by_id()` 方法添加详细日志：
  - Release ID
  - inc 参数（显示前5项）
  - 完整 URL
  - 缓存状态

#### 5.5 HTTPClient 类

**修改内容**:
- 添加 `debug_mode` 参数到 `__init__()`
- `post()` 方法添加详细日志：
  - 方法、URL、headers
  - 数据类型和长度
  - 编码后数据长度
  - 响应接收时间
  - 状态码和响应内容长度
  - JSON 解析状态
- `get()` 方法添加相同详细日志

### 6. 测试文件 (test/test_musicbrainz_connection.py)

**修改内容**:
- `test_musicbrainz_connection()` 添加 `debug_mode` 参数
- `main()` 函数支持 `--debug` 命令行参数
- Debug 模式下设置 DEBUG 日志级别

---

## soundalike 项目

### 1. 主程序 (main.go)

**修改内容**:
- 添加 `-debug` 命令行标志
- Debug 模式下自动设置 `opts.logSec = 1`
- 输出 Debug 模式启用提示

**使用方式**:
```bash
./soundalike --debug /path/to/music
./soundalike --debug -move-interactive /dup_dir /path/to/music
./soundalike --debug -temp /temp_dir /path/to/music
```

### 2. 扫描选项 (scan.go)

**修改内容**:
- `scanOptions` 结构体添加 `debugMode` 字段
- `scanFiles()` 函数添加详细日志：
  - 初始化参数（lookup threshold、match threshold）
  - 数据库加载信息
  - 每个文件的处理过程：
    - 文件路径
    - 文件大小和修改时间
    - 是否需要重新计算指纹
    - fpcalc 执行结果（时长、指纹长度、压缩指纹长度）
    - 保存到数据库的 ID
    - Lookup 阈值计算（位数、百分比）
    - 查找匹配的过程

### 3. 测试文件 (test/test_musicbrainz.go)

**修改内容**:
- 添加 `-debug` 命令行标志
- Debug 模式下输出详细信息：
  - 请求 URL 和 Headers
  - 响应头信息
  - 响应内容前 500 字符
  - 总记录数
  - 每个结果的 ID

---

## 文档

### 1. 新增文档

- **DEBUG_MODE_GUIDE.md**: Debug 模式完整使用指南
  - 概述
  - music_helper 和 soundalike 的启用方式
  - Debug 输出内容详解
  - 输出示例
  - 日志文件位置
  - 使用建议和注意事项

### 2. 更新文档

- **README.md** (music_helper): 添加 Debug 模式说明
- **README.md** (soundalike): 添加 Debug 模式使用示例
- **CHANGELOG.md**: 记录版本 0.6 的所有改进

---

## Debug 输出示例

### music_helper 输出

```
DEBUG: ============================================================
DEBUG: 运行模式: 调试
DEBUG: 日志文件: /path/to/log/Music-20260308_123456.log
DEBUG: 音乐文件管理系统启动
DEBUG: ============================================================
DEBUG: 调试模式已启用
DEBUG: ============================================================
DEBUG: 命令行参数: {'debug': True, 'month': None, ...}
DEBUG: 工作目录: /Users/bemin/Code/music_helper
DEBUG: ============================================================
DEBUG: FingerprintMatcher 初始化
DEBUG:   debug_mode = True
DEBUG:   fpcalc_path = None
DEBUG:   client_version = 1.0
DEBUG: ============================================================
DEBUG: 开始匹配音频文件
DEBUG: ============================================================
DEBUG: audio_file_path = /Users/bemin/Code/music_helper/1.flac
DEBUG: metadata = None
DEBUG: 文件存在: True
DEBUG: 文件大小: 12345678 bytes
DEBUG: 指纹计算结果:
DEBUG:   success = True
DEBUG:   fingerprint = AQAAh...（前50字符）
DEBUG:   duration = 245
DEBUG:   error = None
DEBUG: 开始查询 AcoustID API...
DEBUG: AcoustID 查询参数:
DEBUG:   url = https://api.acoustid.org/v2/lookup
DEBUG:   fingerprint length = 120
DEBUG:   duration = 245s
...
```

### soundalike 输出

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

---

## 使用场景

### 1. 问题排查
- API 查询失败时查看详细的请求和响应
- 指纹计算错误时查看中间变量值
- 数据库操作失败时查看 SQL 语句

### 2. 性能分析
- 通过时间戳分析各步骤耗时
- 识别性能瓶颈
- 优化查询和计算流程

### 3. 数据验证
- 确认计算过程是否正确
- 验证 API 返回的数据格式
- 检查数据转换过程

### 4. 开发调试
- 新功能开发时的快速调试
- 集成测试时的详细日志
- 回归测试时的对比分析

---

## 注意事项

1. **性能影响**: Debug 模式会产生大量日志输出，可能影响性能
2. **磁盘空间**: 长时间运行会生成大日志文件，注意监控磁盘空间
3. **隐私保护**: Debug 输出包含完整的文件路径和内容，确保安全
4. **生产环境**: 不建议在生产环境使用 Debug 模式
5. **日志管理**: 定期清理旧日志文件

---

## 测试

### music_helper 测试
```bash
# 基本功能测试
python test/test_musicbrainz_connection.py

# Debug 模式测试
python test/test_musicbrainz_connection.py --debug

# 完整流程测试
python main.py --debug --check
```

### soundalike 测试
```bash
# 基本功能测试
go run test/test_musicbrainz.go

# Debug 模式测试
go run test/test_musicbrainz.go --debug

# 完整流程测试
./soundalike --debug /path/to/test/music
```

---

## 总结

成功为两个项目添加了完整的 Debug 模式支持，包括：
- ✅ 命令行参数支持
- ✅ 详细的日志输出
- ✅ 所有关键模块的 Debug 信息
- ✅ 测试脚本的 Debug 支持
- ✅ 完整的使用文档

这将大大提高问题排查和开发调试的效率。
