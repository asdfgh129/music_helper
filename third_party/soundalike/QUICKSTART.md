# SoundAlike 快速开始指南

SoundAlike 是一个命令行工具，通过比较音频指纹来查找相似的音频文件，主要用于识别音乐收藏中的重复歌曲。

## 目录

- [安装](#安装)
- [基本使用](#基本使用)
- [常用场景](#常用场景)
- [高级用法](#高级用法)
- [常见问题](#常见问题)

---

## 安装

### 1. 安装 fpcalc

SoundAlike 依赖 Chromaprint 库的 `fpcalc` 工具来生成音频指纹。

**Linux (Debian/Ubuntu)**:
```bash
sudo apt install libchromaprint-tools
```

**Linux (CentOS/RHEL)**:
```bash
sudo yum install chromaprint-tools
```

**macOS**:
```bash
brew install chromaprint
```

**Windows**:
1. 访问 [Chromaprint Releases](https://github.com/acoustid/chromaprint/releases)
2. 下载适用于 Windows 的预编译版本
3. 将 `fpcalc.exe` 放到系统 PATH 中（例如 `C:\Windows\System32`）

### 2. 获取 SoundAlike

**从源码编译**:
```bash
cd /path/to/soundalike
go install
```

编译后的可执行文件将位于 `$GOPATH/bin/soundalike`（或 `~/go/bin/soundalike`）

**使用预编译版本**:
从项目的 [Releases 页面](https://codeberg.org/derat/soundalike/releases) 下载适用于您操作系统的可执行文件。

### 3. 验证安装

```bash
# 检查 fpcalc 是否可用
fpcalc -version

# 检查 soundalike 是否可用
./soundalike --version
```

---

## 基本使用

### 扫描目录查找重复文件

最简单的用法是指定要扫描的目录：

```bash
# 扫描当前目录
./soundalike .

# 扫描指定目录
./soundalike /path/to/music

# 扫描多个目录
./soundalike /path/to/music /path/to/other_music
```

输出示例：
```
2026/02/19 10:30:45 Finished scanning 67 files
1980s/1986/01 - song.mp3    3.07 MB  120.45 sec
1980s/1986/01 - song (1).mp3  1.84 MB  120.46 sec
```

### 查看完整路径

默认情况下，显示相对于扫描目录的路径。使用 `-print-full-paths` 显示绝对路径：

```bash
./soundalike -print-full-paths /path/to/music
```

### 使用数据库加速重复扫描

使用 `-db` 参数可以保存指纹到 SQLite 数据库，后续扫描时复用：

```bash
# 首次扫描，创建数据库
./soundalike -db music.db /path/to/music

# 后续扫描，复用数据库（只处理新增/修改的文件）
./soundalike -db music.db /path/to/music
```

---

## 常用场景

### 场景 1: 交互式清理重复文件

使用 `-move-interactive` 参数，自动移动重复文件到指定目录，交互式选择保留的文件：

```bash
./soundalike -move-interactive /path/to/duplicates /path/to/music
```

**智能选择逻辑**:
- 自动优先保留高质量格式（FLAC > WAV > APE > MP3 > OGG）
- 同质量格式下，自动保留较大文件
- 多个相同格式/大小的文件需要用户手动选择

**交互提示示例**:
```
Auto-removing lower priority format files:
1980s/song.mp3    3.07 MB  120.45 sec

1. 1980s/song.flac    5.12 MB  120.45 sec
2. 1980s/song (1).flac  5.08 MB  120.45 sec
File to keep [1-2, empty to keep all]: 1
```

### 场景 2: 自动移动较小文件

使用 `-move-smaller` 参数，自动保留最大的文件，移动其他重复文件：

```bash
./soundalike -move-smaller /path/to/duplicates /path/to/music
```

**注意**: 此操作会自动执行，无交互确认。请务必先备份数据！

### 场景 3: 只扫描临时目录

使用 `-temp` 参数扫描临时目录但不保存到数据库：

```bash
./soundalike -temp /path/to/temp -temp /path/to/temp2 /path/to/music
```

**适用场景**:
- 临时下载目录
- 待整理的文件
- 不想纳入主数据库的文件

### 场景 4: 比较两个文件

使用 `-compare` 参数直接比较两个文件的相似度：

```bash
./soundalike -compare file1.mp3 file2.mp3
```

输出相似度分数（0.000 - 1.000）：
```
0.972
```

- 1.000 = 完全相同
- 0.950+ = 可能相同（默认匹配阈值）
- 0.500+ = 可能相关
- < 0.500 = 可能不同

**详细对比**（使用 `-compare-interval`）:
```bash
# 每对比 100 个值输出一次分数
./soundalike -compare -compare-interval 100 instrumental.mp3 vocals.mp3

# 输出示例
 100: 0.983
 200: 0.984
 300: 0.983
 400: 0.989
 500: 0.819  # 从这里开始差异变大
 600: 0.757
 700: 0.751
```

---

## 高级用法

### 调整匹配阈值

**查找更严格的重复**（减少误报）:
```bash
./soundalike -match-threshold 0.98 /path/to/music
```

**查找更多潜在重复**（可能增加误报）:
```bash
./soundalike -match-threshold 0.90 /path/to/music
```

### 调整指纹长度

默认只处理每首歌的前 15 秒。增加处理时长可以提高准确性，但会降低性能：

```bash
# 处理前 30 秒
./soundalike -fpcalc-length 30 /path/to/music

# 处理整首歌（用于精确比较）
./soundalike -compare -fpcalc-length 7200 song1.mp3 song2.mp3
```

**性能影响**:
- 15 秒（默认）: 约 20,000 首/小时
- 30 秒: 约 10,000 首/小时
- 60 秒: 约 5,000 首/小时

### 跳过损坏的文件

某些音频文件可能损坏，fpcalc 无法处理。使用 `-skip-bad-files` 跳过这些文件（默认启用）：

```bash
./soundalike -skip-bad-files /path/to/music
```

### 忽略文件修改时间

默认情况下，只有文件大小或修改时间变化时才重新计算指纹。使用 `-ignore-mtimes` 强制重新扫描：

```bash
./soundalike -ignore-mtimes /path/to/music
```

### 自定义音频文件匹配模式

使用 `-file-regexp` 自定义匹配的音频文件扩展名：

```bash
# 只扫描 FLAC 文件
./soundalike -file-regexp '(?i)\\.flac$' /path/to/music

# 扫描无损格式
./soundalike -file-regexp '(?i)\\.(flac|wav|ape)$' /path/to/music
```

### 排除误报的文件对

使用 `-exclude` 参数标记某些文件对不应被视为重复：

```bash
# 标记 file1.mp3 和 file2.mp3 不是重复
./soundalike -db music.db -exclude file1.mp3 file2.mp3

# 后续扫描将跳过这对文件
./soundalike -db music.db /path/to/music
```

### 检查数据库一致性

使用 `-check` 参数检查数据库与实际文件的一致性：

```bash
./soundalike -db music.db -check /path/to/music
```

输出示例：
```
Checking database consistency...
Removed from database: /path/to/deleted_song.mp3
Added to database: /path/to/new_song.mp3
Database check complete: removed 1, added 1 files
```

---

## 常见问题

### Q: 为什么某些文件没有被扫描？

**A**: 可能的原因：
1. 文件扩展名不在默认匹配列表中
2. 文件太短（少于 2-3 秒），fpcalc 无法生成指纹
3. 文件已损坏，fpcalc 无法处理（如启用了 `-skip-bad-files`）

**解决方案**:
```bash
# 跳过损坏的文件检查
./soundalike -skip-bad-files=false /path/to/music

# 自定义文件匹配模式
./soundalike -file-regexp '(?i)\\.(mp3|flac|wav|m4a|ogg|ape)$' /path/to/music
```

### Q: 为什么出现误报（非重复文件被识别为重复）？

**A**: 常见原因：
1. 歌曲开头相同（静音、相似旋律、相同鼓点）
2. 电子音乐有相似的合成器音色
3. 默认匹配阈值（0.95）对于您的音乐库来说太低

**解决方案**:
```bash
# 提高匹配阈值
./soundalike -match-threshold 0.98 /path/to/music

# 增加指纹长度以捕获更多音乐内容
./soundalike -fpcalc-length 30 /path/to/music

# 排除误报的文件对
./soundalike -db music.db -exclude file1.mp3 file2.mp3
```

### Q: 为什么漏报（重复文件未被识别）？

**A**: 常见原因：
1. 音质/编码差异（MP3 320kbps vs 128kbps）
2. 歌曲被截断或添加了开头/结尾静音
3. 人声和伴奏版本
4. 匹配阈值过高

**解决方案**:
```bash
# 降低匹配阈值
./soundalike -match-threshold 0.90 /path/to/music

# 使用较短的指纹长度进行比较
./soundalike -match-min-length /path/to/music

# 增加指纹长度捕获更多内容
./soundalike -fpcalc-length 60 /path/to/music
```

### Q: 数据库可以复用吗？

**A**: 只有在使用相同的 `-fpcalc-*` 参数时才能复用数据库。如果更改了这些参数，需要删除或重新创建数据库。

```bash
# 删除旧数据库
rm music.db

# 使用新参数重新扫描
./soundalike -db music.db -fpcalc-length 30 /path/to/music
```

### Q: 移动文件后如何清理数据库？

**A**: 使用 `-check` 参数会自动清理不存在的文件记录，或手动删除数据库重新扫描：

```bash
# 方法 1: 检查数据库一致性（推荐）
./soundalike -db music.db -check /path/to/music

# 方法 2: 删除数据库重新扫描
rm music.db
./soundalike -db music.db /path/to/music
```

### Q: 如何查看扫描日志？

**A**: SoundAlike 会自动在当前目录创建日志文件：

```
SoundAlike-20260219_103045.log
```

日志包含所有输出信息，便于排查问题。

### Q: 支持哪些音频格式？

**A**: 默认支持的格式：AIFF, FLAC, M4A, MP3, OGA, OGG, OPUS, WAV, WMA, APE

可以通过 `-file-regexp` 参数添加更多格式。

### Q: 性能如何优化？

**A**:
1. 使用数据库（`-db`）加速重复扫描
2. 调整指纹长度（`-fpcalc-length`）平衡准确性和性能
3. 跳过损坏的文件（`-skip-bad-files`）
4. 使用 `-log-sec` 控制日志输出频率

---

## 最佳实践

1. **首次使用前备份数据**
   ```bash
   # 创建备份
   cp -r /path/to/music /path/to/music_backup
   ```

2. **先使用默认参数扫描**
   ```bash
   ./soundalike /path/to/music
   ```

3. **根据结果调整参数**
   - 误报多: 提高 `-match-threshold`
   - 漏报多: 降低 `-match-threshold`

4. **使用数据库加速重复扫描**
   ```bash
   ./soundalike -db music.db /path/to/music
   ```

5. **使用临时目录处理待整理文件**
   ```bash
   ./soundalike -temp /path/to/temp /path/to/music
   ```

6. **定期检查数据库一致性**
   ```bash
   ./soundalike -db music.db -check /path/to/music
   ```

---

## 更多信息

- **完整功能说明**: 参见 [FEATURES.md](FEATURES.md)
- **技术文档**: 参见 [README.md](README.md)
- **Acoustid Chromaprint**: https://acoustid.org/chromaprint
- **源代码**: https://codeberg.org/derat/soundalike
