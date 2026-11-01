# SoundAlike 功能详细说明

SoundAlike 是一个基于音频指纹的重复音乐文件检测工具，通过比较音频文件的声纹特征来识别重复歌曲。

## 目录

- [核心功能](#核心功能)
- [音频指纹技术](#音频指纹技术)
- [匹配算法](#匹配算法)
- [数据库管理](#数据库管理)
- [文件操作](#文件操作)
- [命令行参数](#命令行参数)
- [性能特性](#性能特性)
- [使用场景](#使用场景)

---

## 核心功能

### 1. 音频指纹生成

SoundAlike 使用 Chromaprint 库的 `fpcalc` 工具生成音频文件的声纹指纹。

**功能特点**:
- 支持多种音频格式：AIFF, FLAC, M4A, MP3, OGA, OGG, OPUS, WAV, WMA, APE
- 基于 FFT（快速傅里叶变换）提取音频特征
- 生成 32 位无符号整数序列作为指纹
- 可配置处理时长和算法参数

**技术原理**:
```
音频文件 → 分帧 → FFT 变换 → 特征提取 → 指纹生成
  ↓           ↓        ↓         ↓          ↓
PCM 数据   短时帧   频谱特征   整数序列
```

**配置参数**:
- `-fpcalc-length`: 最大处理时长（默认 120 秒，MusicBrainz 标准长度）
- `-fpcalc-chunk`: 音频块分割时长
- `-fpcalc-algorithm`: 指纹算法（默认 2）
- `-fpcalc-overlap`: 是否重叠音频块

### 2. 相似度检测

**两层检测机制**:

**第一层：快速查找表**
- 将 32 位指纹截断为 16 位
- 建立哈希表快速定位潜在匹配
- 检查匹配值数量是否达到阈值（`-lookup-threshold`，默认 0.25）

**第二层：精确位对比**
- 对齐两个指纹的所有可能位置
- 计算相同位数的比例
- 达到阈值则判定为重复（`-match-threshold`，默认 0.95）

**匹配示例**:
```go
// 指纹 A: [0x1234, 0x5678, 0x9ABC, 0xDEF0]
// 指纹 B: [0x1234, 0x5678, 0x9ABC, 0xDEF1]

// 查找表匹配: 4/4 (100%)
// 位对比结果: 31/32 bits (96.875%)
// 判定: 重复（超过 0.95 阈值）
```

### 3. 重复分组

使用无向图算法将相似文件分组：

**分组算法**:
```
文件对判定为重复 → 添加边到图
  ↓
构建无向图
  ↓
查找连通分量
  ↓
每个连通分量 = 一组重复文件
```

**示例**:
```
文件: A, B, C, D
关系: A~B (重复), B~C (重复), C~D (重复)

图结构:
A ── B ── C ── D

分组结果: [A, B, C, D] (一组）
```

**排除对处理**:
- 支持标记文件对不应被视为重复（`-exclude`）
- 排除对在分组时自动跳过
- 便于处理误报或特殊版本（如混音/原曲）

### 4. 交互式文件清理

**智能格式优先级**:
```
FLAC (4) > WAV (3) > APE (2) > MP3 (1) > OGG (0) > 其他 (-1)
```

**自动清理逻辑**:
1. 按格式优先级分类
2. 低优先级格式自动移动到 `-move-interactive` 目录
3. 高优先级格式中，较大文件优先保留
4. 同格式同大小：用户手动选择

**交互流程**:
```
1. 显示所有重复文件信息
2. 标记自动删除的文件（低优先格式）
3. 等待用户输入选择保留文件
4. 移动其他文件到指定目录
5. 从数据库删除已移动文件的记录
```

**自动重命名**:
目标文件已存在时自动添加序号：
```
song.mp3 → song(1).mp3 → song(2).mp3
```

### 5. 数据库持久化

使用 SQLite 数据库存储文件信息和指纹，加速重复扫描。

**数据库结构**:

```sql
-- 设置表（存储指纹参数）
CREATE TABLE Settings (
    Desc STRING PRIMARY KEY NOT NULL
);

-- 目录表
CREATE TABLE Directories (
    DirectoryID INTEGER PRIMARY KEY AUTOINCREMENT,
    Path STRING UNIQUE NOT NULL
);

-- 文件表
CREATE TABLE Files (
    Path STRING NOT NULL,
    DirectoryID INTEGER NOT NULL,
    Duration FLOAT NOT NULL,
    Size INTEGER NOT NULL,
    ModTime INTEGER NOT NULL,
    Fingerprint BLOB NOT NULL,
    PRIMARY KEY (DirectoryID, Path),
    FOREIGN KEY (DirectoryID) REFERENCES Directories(DirectoryID)
);

-- 排除对表
CREATE TABLE ExcludedPairs (
    PathA STRING NOT NULL,
    PathB STRING NOT NULL,
    PRIMARY KEY (PathA, PathB)
);
```

**存储内容**:
- 文件路径（相对路径，基于目录）
- 文件大小（字节）
- 文件修改时间（Unix 时间戳）
- 音频时长（秒）
- 音频指纹（32 位整数数组，二进制存储）

**数据库版本管理**:
- 支持版本升级（PRAGMA user_version）
- 自动迁移旧版本数据库
- 版本 0 → 1: 添加 ModTime 列
- 版本 1 → 2: 分离目录和文件表

**增量更新**:
- 检查文件大小和修改时间
- 未变化：复用现有指纹
- 已变化：重新计算指纹
- 新文件：插入记录

### 6. 临时目录处理

支持 `-temp` 参数扫描临时目录，不保存到数据库。

**临时文件标识**:
- 使用负数 ID 标识（-1, -2, -3, ...）
- 存储在内存中，不写入数据库
- 扫描完成后自动清理

**使用场景**:
```
主目录 (数据库保存)           临时目录 (不保存)
├── music/                  ├── temp_downloads/
│   ├── song1.mp3         │   ├── new_song.mp3
│   └── song2.flac         │   └── temp_song.flac
│                           └── sorting/
└── duplicates/                 └── to_check/

命令: soundalike -temp temp_downloads music
```

**跨目录匹配**:
- 临时文件与数据库文件可以匹配
- 临时文件之间也可以匹配
- 重复判定包含所有文件类型

---

## 音频指纹技术

### Chromaprint 工作原理

**音频特征提取**:
```
1. 音频预处理（重采样、归一化）
2. 分帧（每帧约 0.1 秒）
3. FFT 变换获取频谱
4. 提取特征点（频谱峰值、能量）
5. 编码为 32 位指纹
```

**指纹特点**:
- 长度与音频时长成正比（120 秒 ≈ 800 个值）
- 每个值代表约 0.1-0.2 秒音频
- 对音质变化有鲁棒性（不同比特率、编码）
- 对音量变化不敏感

### 指纹对比算法

**查找表优化**:
```
原始: 32 位指纹直接比较 → O(N²) 复杂度
优化: 截断为 16 位哈希表 → O(N) 预筛选

示例:
指纹: [0x12345678, 0x9ABCDEF0, ...]
截断: [0x1234, 0x9ABC, ...]
哈希: {0x1234: {file1: 2, file2: 1}, ...}
```

**位对比计算**:
```go
func compareFingerprints(a, b []uint32, minLength bool) float64 {
    best := 0
    // 尝试所有对齐方式
    for i := 1; i < len(a); i++ {
        cnt := countBits(a[i:], b)
        if cnt > best {
            best = cnt
        }
    }
    for i := 1; i < len(b); i++ {
        cnt := countBits(a, b[i:])
        if cnt > best {
            best = cnt
        }
    }
    // 计算相同位数比例
    return float64(best) / float64(32 * totalBits)
}
```

**位操作优化**:
使用 `bits.OnesCount32()` 计算异或结果中置 1 的位数：
```go
sameBits := 32 - bits.OnesCount32(a[i] ^ b[i])
```

### 准确性分析

**高准确率场景**:
- 相同歌曲的不同编码（MP3 320kbps vs FLAC）
- 相同格式不同比特率
- 轻微音量调整

**低准确率场景**:
- 人声 vs 伴奏版本（开头相同）
- 带静音开头的歌曲
- 相似旋律/和弦的电子音乐
- 采样率不同（需要较长指纹）

**解决方法**:
1. 增加 `-fpcalc-length` 处理更多音频内容
2. 调整 `-match-threshold` 平衡误报/漏报
3. 使用 `-exclude` 排除已知的误报

---

## 匹配算法

### 查找表阈值

`-lookup-threshold` 控制第一层筛选的严格程度。

**默认值**: 0.25（25% 指纹值匹配）

**影响分析**:
```
阈值 = 0.10: 更严格，减少候选对，提高速度
阈值 = 0.25: 默认值，平衡速度和准确性
阈值 = 0.50: 更宽松，增加候选对，可能降低速度
```

**计算示例**:
```
指纹长度: 100
阈值 0.25 → 需至少 25 个值匹配
阈值 0.50 → 需至少 50 个值匹配
```

### 匹配阈值

`-match-threshold` 控制第二层位对比的严格程度。

**默认值**: 0.95（95% 位相同）

**影响分析**:
```
阈值 = 0.90: 宽松，更多重复，可能误报
阈值 = 0.95: 默认值，平衡
阈值 = 0.98: 严格，减少误报，可能漏报
```

**位相同计算**:
```
A: 0x12345678 (0001 0010 0011 0100 0101 0110 0111 1000)
B: 0x12345679 (0001 0010 0011 0100 0101 0110 0111 1001)

XOR: 0x00000001 (0000 0000 0000 0000 0000 0000 0000 0001)
相同位数: 31/32 = 96.875%
```

### 最短长度对比

`-match-min-length` 控制对比时使用较短还是较长的指纹长度。

**默认行为**: 使用较长指纹（更严格）

**使用场景**:
- 检测截断的歌曲（末尾被剪裁）
- 检测带额外内容的歌曲（开头静音、尾奏）
- 不同编码版本（MP3 vs FLAC，时长略有差异）

**示例**:
```
歌曲 A: 120 秒（120 个指纹值）
歌曲 B: 119 秒（119 个指纹值，截断版本）

-min-length=false（默认）: 对比 120 vs 119 → 98% 匹配
-min-length=true: 对比 119 vs 119 → 100% 匹配
```

---

## 数据库管理

### 数据库初始化

**自动创建流程**:
```
1. 检查数据库文件是否存在
2. 不存在：创建新数据库，应用当前 schema
3. 存在：读取版本号，执行必要的迁移
4. 验证设置参数与数据库一致
```

**设置验证**:
数据库存储 `fpcalc` 参数（length, chunk, algorithm, overlap），不匹配时拒绝使用：
```
Error: database settings (length=120.000,chunk=0.000,algorithm=2,overlap=false)
don't match current settings (length=240.000,chunk=0.000,algorithm=2,overlap=false)
```

### 文件更新策略

**智能判断逻辑**:
```
文件在数据库中?
  ├─ 否 → 计算指纹，插入数据库
  └─ 是 → 文件大小变化?
              ├─ 是 → 重新计算，更新数据库
              └─ 否 → 忽略时间变化?
                      ├─ 是 (-ignore-mtimes) → 重新计算
                      └─ 否 → 修改时间变化?
                               ├─ 是 → 重新计算
                               └─ 否 → 跳过，复用指纹
```

**性能优化**:
- 大部分情况下无需重新计算指纹
- 只处理新增或修改的文件
- 显著加速重复扫描（>90% 时间节省）

### 目录结构

**相对路径存储**:
```
数据库存储:
DirectoryID: 1, Path: "music"
DirectoryID: 2, Path: "music/1980s"

完整路径重建:
file.dirPath + "/" + file.path
= "music/1980s/1986/01 - song.mp3"
```

**优势**:
- 目录移动时只需更新 `Directories` 表
- 减少存储空间
- 支持多目录扫描

### 数据库检查功能

`-check` 参数执行一致性检查：

**检查项目**:
1. 数据库中记录的文件是否实际存在
2. 实际文件是否在数据库中有记录
3. 文件信息是否一致（大小、修改时间）

**修复操作**:
```
删除不存在文件的记录:
  → DELETE FROM Files WHERE ...
添加新文件的记录:
  → INSERT INTO Files ... + fpcalc 计算
```

**输出示例**:
```
Checking database consistency...
Removed from database: /path/to/deleted_song.mp3
Added to database: /path/to/new_song.mp3
Database check complete: removed 1, added 1 files
```

---

## 文件操作

### 移动策略

**跨分区移动**:
```go
func moveFile(srcPath, dstPath string) error {
    // 尝试重命名（同分区）
    if os.Rename(srcPath, dstPath) == nil {
        return nil
    }
    // 跨分区：复制 + 删除
    return copyAndRemoveFile(srcPath, dstPath)
}
```

**自动重命名**:
```
目标目录已存在文件:
  song.mp3
  song(1).mp3
  song(2).mp3

尝试移动 song.mp3 → 自动命名为 song(3).mp3
```

### 格式优先级

**质量排序**:
```go
func formatPriority(path string) int {
    ext := strings.ToLower(filepath.Ext(path))
    switch ext {
    case ".flac": return 4  // 无损，首选
    case ".wav":  return 3  // 无损
    case ".ape":  return 2  // 无损
    case ".mp3":  return 1  // 有损
    case ".ogg":  return 0  // 有损
    default:      return -1
    }
}
```

**自动清理规则**:
```
场景 1: 同歌曲不同格式
  song.flac (优先级 4)
  song.mp3 (优先级 1)
  → 自动删除 MP3，保留 FLAC

场景 2: 同格式不同大小
  song(1).flac (5.2 MB)
  song(2).flac (4.8 MB)
  → 保留较大文件（5.2 MB）

场景 3: 同格式同大小
  song(1).flac (5.2 MB)
  song(2).flac (5.2 MB)
  → 用户手动选择
```

### 日志记录

**自动创建日志**:
```
文件名: SoundAlike-YYYYMMDD_HHMMSS.log
示例: SoundAlike-20260219_103045.log

内容:
  2026/02/19 10:30:45 Finished scanning 67 files
  1980s/song.mp3    3.07 MB  120.45 sec
  Moving /path/to/song.mp3 -> /path/to/duplicates/song(1).mp3
```

**双输出模式**:
- 标准输出：用户可见
- 日志文件：持久化存储
- 同时写入，便于排查问题

---

## 命令行参数

### 基本参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|---------|------|
| `-db` | string | "music.db" | SQLite 数据库文件路径 |
| `-file-regexp` | string | `(?i)\.(aiff\|flac\|...)$` | 音频文件匹配正则表达式 |
| `-print-file-info` | bool | true | 打印文件大小和时长 |
| `-print-full-paths` | bool | false | 打印绝对路径 |
| `-version` | bool | false | 打印版本并退出 |

### fpcalc 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|---------|------|
| `-fpcalc-length` | float | 120.0 | 最大处理时长（秒，MusicBrainz 标准长度） |
| `-fpcalc-chunk` | float | 0.0 | 音频块分割时长（秒） |
| `-fpcalc-algorithm` | int | 2 | 指纹算法 |
| `-fpcalc-overlap` | bool | false | 重叠音频块 |

### 扫描参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|---------|------|
| `-skip-bad-files` | bool | true | 跳过无法指纹的文件 |
| `-ignore-mtimes` | bool | false | 忽略文件修改时间 |
| `-log-sec` | int | 10 | 日志输出频率（秒） |

### 匹配参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|---------|------|
| `-lookup-threshold` | float | 0.25 | 查找表阈值 (0.0, 1.0] |
| `-match-threshold` | float | 0.95 | 位对比阈值 (0.0, 1.0] |
| `-match-min-length` | bool | false | 使用较短长度对比 |

### 操作参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|---------|------|
| `-temp` | string | 无 | 临时目录（不保存到数据库） |
| `-move-interactive` | string | 无 | 交互式移动重复文件到此目录 |
| `-move-smaller` | string | 无 | 自动移动较小重复文件到此目录 |
| `-exclude` | bool | false | 标记文件对不视为重复 |
| `-check` | bool | false | 检查数据库一致性 |

### 比较参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|---------|------|
| `-compare` | bool | false | 比较两个文件（代替扫描） |
| `-compare-interval` | int | 0 | 比较分数输出间隔（0=整体） |

---

## 性能特性

### 扫描性能

**性能基准**（Intel Core i5-8250U）:
```
文件数量 | 总大小 | 处理时间 | 指纹长度
--------|--------|---------|---------
99      | 266 MB | ~30 秒  | 120 秒
1,000   | ~2.7 GB | ~5 分钟 | 120 秒
20,000  | ~54 GB  | ~60 分钟 | 120 秒
```

**指纹长度影响**:
```
120 秒（默认）: 800 值/文件, ~3,000 首/小时
60 秒: 400 值/文件, ~5,000 首/小时
30 秒: 200 值/文件, ~10,000 首/小时
```

### 内存使用

**内存增长因素**:
- 文件数量
- 指纹长度
- 查找表大小

**实际测试**（20,000 MP3 文件，120 秒指纹）:
```
RSS（常驻集）: ~150,000 KB
峰值内存: ~180 MB
```

**查找表内存估算**:
```
文件数量: 20,000
平均指纹长度: 800
截断后键数: ~1,000
每个键的平均映射: 20

内存占用:
  查找表结构: ~2 MB
  指纹数据: ~8 MB
  总计: ~10 MB
```

### 数据库性能

**查询优化**:
```sql
-- 主键查询（快速）
SELECT * FROM Files WHERE DirectoryID = ? AND Path = ?

-- 索引字段
-- Path: 目录内快速查找
-- DirectoryID: 目录间快速切换
```

**批量操作**:
```sql
-- UPSERT 语法（SQLite 3.24+）
INSERT INTO Files (...) VALUES (...)
ON CONFLICT(DirectoryID, Path) DO UPDATE SET ...
```

**VACUUM 优化**:
升级后自动执行 VACUUM，回收空间：
```sql
VACUUM
```

---

## 使用场景

### 场景 1: 清理音乐库重复

**完整流程**:
```bash
# 1. 创建数据库（首次）
./soundalike -db music.db /path/to/music

# 2. 交互式清理
./soundalike -db music.db -move-interactive /path/to/duplicates /path/to/music

# 3. 检查数据库一致性
./soundalike -db music.db -check /path/to/music
```

### 场景 2: 处理新下载的文件

**临时目录扫描**:
```bash
./soundalike -temp /path/to/downloads -temp /path/to/temp \
  /path/to/music
```

**优势**:
- 不污染主数据库
- 快速识别新文件重复
- 便于批量导入前检查

### 场景 3: 精确比较两个文件

**直接比较**:
```bash
# 整体相似度
./soundalike -compare song_a.mp3 song_b.mp3

# 逐段相似度
./soundalike -compare -compare-interval 100 song_a.mp3 song_b.mp3
```

**输出分析**:
```
0.972  # 97.2% 相同，基本可以确定是同一首歌
0.854  # 85.4% 相同，可能是同一首歌的不同版本
0.512  # 51.2% 相同，可能相关但不同
0.203  # 20.3% 相同，不太可能是同一首歌
```

### 场景 4: 持续监控音乐库

**定期扫描**:
```bash
# 每周运行一次
crontab -e
# 0 2 * * 0 /usr/local/bin/soundalike -db ~/music.db /path/to/music
```

**增量更新**:
- 只处理新增/修改的文件
- 数据库自动复用
- 快速完成扫描

### 场景 5: 质量优先整理

**自动保留高质量版本**:
```bash
./soundalike -db music.db -move-interactive /path/to/duplicates \
  /path/to/music
```

**保留策略**:
1. FLAC > WAV > APE > MP3 > OGG
2. 同格式保留较大文件
3. 用户手动选择特殊情况

### 场景 6: 处理误报

**排除误报文件对**:
```bash
# 标记不是重复的文件
./soundalike -db music.db -exclude song_mix.mp3 song_remix.mp3

# 后续扫描将跳过这对文件
./soundalike -db music.db /path/to/music
```

**适用情况**:
- 原曲 vs 混音版
- 不同版本（如电台版 vs 专辑版）
- 误判（开头相似但完全不同的歌曲）

### 场景 7: 处理漏报

**调整参数提高检出率**:
```bash
# 降低匹配阈值
./soundalike -db music.db -match-threshold 0.90 /path/to/music

# 增加指纹长度（超过默认 120 秒）
./soundalike -db music.db -fpcalc-length 240 /path/to/music

# 使用最短长度对比
./soundalike -db music.db -match-min-length /path/to/music
```

### 场景 8: 大规模音乐库

**分批处理**:
```bash
# 分年份数据扫描
./soundalike -db 1980s.db /path/to/music/1980s
./soundalike -db 1990s.db /path/to/music/1990s
./soundalike -db 2000s.db /path/to/music/2000s
```

**优势**:
- 减少单次扫描内存占用
- 并行处理不同年份
- 更快的定位问题

---

## 技术亮点

### 1. 高效查找表

**设计理念**:
- 32 位指纹截断为 16 位，降低内存占用
- 哈希表索引，O(1) 查找复杂度
- 值计数，避免重复计数

**数据结构**:
```go
type lookupTable struct {
    m map[uint16]map[fileID]int16
}
// key: 截断后的指纹值
// value: 文件 ID → 匹配次数
```

### 2. 并行化潜力

**可并行部分**:
- fpcalc 指纹计算（I/O 密集）
- 查找表构建（CPU 密集）
- 位对比（CPU 密集）

**当前限制**:
- 单线程扫描
- 顺序文件处理
- SQLite 单连接写入

### 3. 错误处理

**优雅降级**:
```go
// 文件太短，跳过
if err == errEmptyFingerprint {
    return nil
}

// 损坏文件，可选择跳过
if opts.skipBadFiles {
    fmt.Println("Skipping:", path)
    return nil
}

// 解码错误，部分成功
if exitCode == 3 {
    // fpcalc 退出码 3 表示有错误但可生成指纹
    err = nil
}
```

### 4. 平台兼容性

**跨平台支持**:
- Windows: `fpcalc.exe`, 路径使用 `\`
- macOS/Linux: `fpcalc`, 路径使用 `/`
- 路径处理: `filepath.EvalSymlinks()`, `filepath.Rel()`

**编译目标**:
```
GOOS=linux GOARCH=amd64 go build
GOOS=windows GOARCH=amd64 go build
GOOS=darwin GOARCH=arm64 go build
```

---

## 限制与已知问题

### fpcalc 限制

1. **最短文件**: 无法处理 < 2-3 秒的文件
2. **损坏文件**: 某些编码错误会导致退出码 3
3. **格式支持**: 依赖 Chromaprint 支持的格式

### 匹配精度限制

1. **人声 vs 伴奏**: 默认 120 秒通常能更好区分
2. **开头相似**: 电子音乐或相同旋律开头
3. **静音检测**: 带静音的歌曲可能误报

### 数据库限制

1. **参数锁定**: 更改 `-fpcalc-*` 需要重建数据库
2. **路径依赖**: 目录移动需更新数据库
3. **并发限制**: SQLite 单进程写入

### 性能限制

1. **内存占用**: 大规模库需要足够内存
2. **I/O 密集**: 指纹计算受磁盘速度限制
3. **CPU 密集**: 位对比受 CPU 速度限制

---

## 最佳实践建议

### 1. 参数调优流程

```
1. 默认参数首次扫描
2. 根据结果调整阈值
3. 记录有效的参数组合
4. 定期维护数据库
```

### 2. 备份策略

```
操作前备份 → 重要！
├─ 完整备份（首次）
├─ 增量备份（定期）
└─ 检查点备份（大规模操作前）
```

### 3. 数据库维护

```
每周运行一次检查
├─ 清理不存在的文件
├─ 添加遗漏的文件
└─ VACUUM 回收空间
```

### 4. 分级处理策略

```
临时文件 → 临时数据库
└─ 确认无重复后
    → 导入主数据库
```

---

## 扩展性

### 添加新音频格式

修改 `-file-regexp` 参数：
```bash
./soundalike -file-regexp '(?i)\\.(mp3|flac|wav|dsd)$' /path/to/music
```

### 自定义格式优先级

修改 `formatPriority()` 函数：
```go
case ".dsd": return 5  // 最高优先级
```

### 集成到工作流

```bash
#!/bin/bash
# music_workflow.sh
# 1. 下载新音乐
download_music.sh /path/to/temp

# 2. 检查重复
./soundalike -temp /path/to/temp /path/to/music

# 3. 交互式整理
./soundalike -move-interactive /path/to/duplicates /path/to/music

# 4. 导入确认文件
mv /path/to/temp/* /path/to/music/
```

---

## 参考资源

### 技术文档

- [Acoustid Chromaprint](https://acoustid.org/chromaprint) - 指纹算法说明
- [Chromaprint 源码](https://github.com/acoustid/chromaprint) - 完整实现
- [Chromaprint 工作原理](https://oxygene.sk/2011/01/how-does-chromaprint-work/) - 详细解析

### 相关项目

- [MusicBrainz Picard](https://picard.musicbrainz.org/) - 音乐标签管理
- [Acoustid Web 服务](https://acoustid.org/) - 在线指纹查询

### 性能基准

- [Chromaprint 性能测试](https://github.com/acoustid/chromaprint#performance)
- [fpcalc 参数优化](https://acoustid.org/chromaprint#command-line-usage)

---

## 许可与版权

SoundAlike Copyright 2022-2024 Daniel Erat
基于 Chromaprint 库，遵循相关开源协议。

**重要**: 本工具仅供个人学习和使用。使用时请遵守相关音乐平台的版权条款。
