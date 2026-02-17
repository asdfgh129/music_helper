# 音乐标签更新功能说明

## 概述

本项目实现了智能化的音乐文件标签更新功能，通过声纹识别和在线音乐数据库API自动获取和更新音乐文件的元数据。

## 主要特性

### 1. 双层查询策略

- **优先级1 - 声纹匹配**: 使用音频指纹查询MusicBrainz数据库，准确率高
- **优先级2 - 在线查询**: 使用QQ音乐和网易云音乐API，覆盖范围广

### 2. 自动封面下载

- 自动从在线平台获取专辑封面
- 支持高分辨率图片
- 自动压缩超大图片

### 3. 智能匹配

- 优先使用文件已有标签
- 支持文件名解析（"歌手 - 歌曲名"格式）
- 多歌手支持（分号分隔）

## 功能详解

### 声纹匹配流程

1. 计算音频文件指纹（使用fpcalc）
2. 通过AcoustID API查询MusicBrainz
3. 解析返回的录音信息
4. 匹配分数>=50%时接受结果
5. 更新标签并尝试下载封面

### 在线查询流程

1. 提取歌曲名和歌手（标签优先，文件名备选）
2. 优先查询QQ音乐API
3. 备选查询网易云音乐API
4. 匹配最佳结果并更新标签
5. 下载并嵌入封面

### 支持的标签字段

- 歌曲标题 (title)
- 歌手 (artist)
- 专辑 (album)
- 年份 (year)
- 流派 (genre)
- 封面 (album_img)

### 支持的文件格式

- MP3 (.mp3)
- FLAC (.flac)
- OGG (.ogg)
- WAV (.wav)
- APE (.ape)

## 使用方法

### 基本用法

```bash
# 完整处理流程（包含标签更新）
python main.py

# 跳过标签更新步骤
python main.py --skip-tag-update

# 处理指定月份
python main.py --month 202406
```

### 命令行参数

| 参数 | 说明 |
|------|------|
| `--month` | 指定扫描月份 (格式: YYYYMM) |
| `--skip-vip` | 跳过VIP文件解密 |
| `--skip-fingerprint` | 跳过声纹识别去重 |
| `--skip-tag-update` | 跳过标签更新 |
| `--skip-check` | 跳过文件检查 |
| `--skip-organize` | 跳过年份分类 |
| `--check-master` | 检查主目录 |
| `--uncheck-temp` | 不检查临时目录 |

## 依赖模块

标签更新功能需要以下模块：

### 可选依赖（声纹匹配和在线查询）

```bash
# 安装music_tagger模块（如果已有）
# music_tagger应包含以下子模块：
# - music_tagger.fingerprint_matcher
# - music_tagger.platforms.qqmusic
# - music_tagger.platforms.netease
# - music_tagger.core
```

### 基础依赖

```bash
pip install mutagen requests
```

### fpcalc工具

声纹匹配需要fpcalc命令行工具：

**macOS:**
```bash
brew install chromaprint
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get install chromaprint-tools
```

**Windows:**
下载并安装: https://acoustid.org/chromaprint

## QQ音乐解密优化

原实现使用外部程序调用，现已优化为直接导入模块：

**优化前:**
```python
cmd = [sys.executable, QQ_PY, '-i', QQ_TMP_DIR, '-o', TEMP_COMPLETED_DIR]
subprocess.run(cmd, ...)
```

**优化后:**
```python
import qq
qq.run_decrypt(QQ_TMP_DIR, TEMP_COMPLETED_DIR)
```

优势：
- 减少进程创建开销
- 更好的错误处理
- 更清晰的日志输出

## 日志输出

标签更新过程会生成以下日志文件：

1. **主日志**: `Music-{timestamp}.log`
   - 所有操作的汇总信息

2. **操作日志**: `UpdateTags-{timestamp}.log`
   - 详细的标签更新过程
   - 每个文件的处理结果
   - 失败原因和错误堆栈

### 日志包含的统计信息

- 处理总数
- 成功数量
- 失败数量
- 声纹匹配成功数量
- 在线查询成功数量
- 不完整标签文件列表

## 错误处理

- 每个文件独立处理，单个失败不影响其他文件
- 详细的错误日志记录
- 支持重试失败文件
- 网络错误自动超时处理

## 注意事项

1. **API限制**: 在线查询可能受到API调用频率限制
2. **网络连接**: 需要稳定的网络连接访问在线API
3. **fpcalc依赖**: 声纹匹配需要安装fpcalc工具
4. **模块可用性**: 如果music_tagger模块不可用，系统会跳过相应功能
5. **匹配准确性**: 声纹匹配准确率高于在线查询，建议优先使用

## 故障排查

### 声纹匹配不可用

**问题**: 日志显示 "声纹匹配模块不可用"

**解决**:
```bash
# 检查fpcalc是否安装
fpcalc --version

# 如果未安装，根据操作系统安装（见上方说明）
```

### 在线查询失败

**问题**: 日志显示 "音乐API客户端初始化失败"

**解决**:
- 检查网络连接
- 确认music_tagger模块正确安装
- 查看详细错误日志

### 封面未下载

**问题**: 日志显示 "下载封面失败"

**解决**:
- 检查网络连接
- 确认在线平台有该歌曲的封面
- 尝试手动指定封面URL

## 示例输出

```
2026-02-14 10:30:00 - INFO - 步骤 3/7: 更新标签信息
2026-02-14 10:30:00 - INFO - 声纹匹配器已初始化
2026-02-14 10:30:00 - INFO - 音乐API客户端已初始化
2026-02-14 10:30:01 - INFO - 处理文件: G:\Temp\周杰伦 - 夜曲.mp3
2026-02-14 10:30:03 - INFO -   尝试声纹查询: 周杰伦 - 夜曲.mp3
2026-02-14 10:30:05 - INFO -   声纹匹配成功 (分数: 95.2%)
2026-02-14 10:30:05 - INFO -   标签已从MusicBrainz更新: 周杰伦 - 夜曲
2026-02-14 10:30:06 - INFO -   已下载封面: http://y.qq.com/music/photo_new/T002R300x300M000003...
2026-02-14 10:30:06 - INFO - 处理完成: 周杰伦 - 夜曲.mp3
```

## 更多信息

详细的功能说明请查看 `feature.md` 文件。
