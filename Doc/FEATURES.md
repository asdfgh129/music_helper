# Music Helper 功能详细说明

## 目录
- [一、功能模块](#一功能模块)
- [二、操作流程](#二操作流程)
- [附录](#附录)

---

# 一、功能模块

## 1. soundalike 声纹去重模块

### 功能概述
对音乐文件进行声纹分析，识别重复的音乐文件，并建立数据库记录已存在的音乐文件信息。

### 技术原理

**声纹计算与匹配流程**:
```
1. 扫描目录中的所有音乐文件
2. 使用soundalike.exe计算音频声纹特征
3. 对比声纹数据库，识别重复文件
4. 将重复文件移动到指定目录（交互式确认）
5. 建立数据库记录已存在的音乐文件信息
```

### 使用方法

#### 命令行调用

```python
from soundalike import (
    run_soundalike_fingerprinting, 
    run_soundalike_fingerprinting_without_temp, 
    check_database_consistency
)

# 运行声纹识别去重（使用--temp参数，适用于临时目录）
success = run_soundalike_fingerprinting()

# 运行声纹识别去重（不带--temp参数，适用于主目录）
success = run_soundalike_fingerprinting_without_temp()

# 检查数据库一致性
success = check_database_consistency()
```

#### 主程序集成

```bash
# 默认模式（处理临时目录）
python main.py

# check-master模式（处理主目录，不带--temp参数）
python main.py --check-master

# 仅检查数据库一致性
python main.py --checkdb
```

### 配置

编辑 `config.py` 中的目录配置：

```python
# 主目录（扫描目标）
MAIN_DIR = r'D:\music'

# 临时完成目录（工作目录）
TEMP_COMPLETED_DIR = r'G:\Temp'

# 重复文件移动目录（交互式确认）
TEMP_MOVE_DIR = r'G:\Tmp'

# 声纹识别工具
SOUNDALIKE_EXE = r'soundalike.exe'
```

### 命令行参数

Soundalike 工具的命令格式：

```bash
# 默认模式（带--temp参数）
soundalike.exe -move-interactive <移动目录> -temp <临时目录> <扫描目录>

# check-master模式（不带--temp参数）
soundalike.exe -move-interactive <移动目录> <扫描目录>
```

- `-move-interactive`: 交互式移动模式，需要用户确认
- `-temp`: 临时工作目录（check-master模式不使用此参数）
- `<扫描目录>`: 需要扫描的主目录

### 返回值

- `True`: 声纹识别成功完成
- `False`: 声纹识别失败

### 注意事项

- 必须确保 `soundalike.exe` 在系统PATH中或放在项目根目录
- 声纹识别需要一定时间，取决于文件数量和大小
- 交互模式下需要手动确认文件移动操作
- 建议在操作前备份重要文件
- 建立数据库后可进行快速的一致性检查

---

## 2. 文件名检查模块

### 功能概述
检查音乐文件的命名是否符合"[歌手] - [歌曲]"的格式，并提取歌手和歌曲信息。

### 功能特性

- 检查文件名是否包含正确的分隔符" - "
- **自动修复只有"-"分隔符的文件名，改为" - "**
- 处理重名情况（删除重复文件及其LRC文件）
- 同步重命名对应的LRC歌词文件
- 检查并记录孤立的LRC文件（只有歌词文件没有音乐文件）

### 使用方法

#### 命令行调用

```python
from file_operations import check_filename_consistency

# 检查文件名一致性
inconsistent_count, duplicate_count, missing_lrc_count = check_filename_consistency(
    check_master=True,   # 检查主目录
    check_temp=True       # 检查临时目录
)
```

#### 主程序集成

```bash
# 检查所有目录
python main.py

# 只检查主目录（check-master模式）
python main.py --check-master

# 只检查临时目录
python main.py --uncheck-temp

# 跳过文件检查
python main.py --skip-check
```

### 检查规则

**标准格式**:
```
[歌手名] - [歌曲名].扩展名
例如: Taylor Swift - Love Story.mp3
```

**自动修复**:
```
修复前: Taylor Swift-Love Story.mp3  (只有"-")
修复后: Taylor Swift - Love Story.mp3 (改为" - ")
```

**重名处理**:
- 如果修改后的文件名已存在，删除原文件
- 同步删除对应的LRC歌词文件
- 记录删除操作到日志

**孤立LRC检查**:
- 扫描所有.lrc文件
- 检查是否存在对应音乐文件（.mp3, .flac, .wav, .ape, .ogg）
- 记录孤立的LRC文件

### 实现细节

```python
from utils import parse_filename, check_filename_format

# 解析文件名
artist, title = parse_filename("Taylor Swift - Love Story.mp3")
# artist = "Taylor Swift"
# title = "Love Story"

# 检查文件名格式
is_valid = check_filename_format("Taylor Swift - Love Story.mp3")
# 返回 True
```

### 统计信息

函数返回三个统计值：
- `inconsistent_count`: 文件名不一致的文件数量
- `duplicate_count`: 重复文件组数量
- `missing_lrc_count`: 缺少歌词的文件数量
- `orphan_lrc`: 孤立LRC文件数量（记录在操作日志中）
- `files_renamed`: 文件名分隔符处理数量（记录在操作日志中）

---

## 3. 元数据检查模块

### 功能概述
检查音乐文件的歌手、歌曲名是否与文件名一致。

### 功能特性

- 从文件名解析歌手和歌曲信息
- 读取音乐文件的元数据标签
- 对比文件名和标签信息的一致性
- 支持多艺术家名称拆分和匹配
- 支持部分匹配（标题包含关系）
- 标准化文本比较（去除空格、转小写）

### 检查逻辑

```python
def check_metadata_consistency(file_info):
    """检查元数据一致性"""
    # 从文件名解析
    filename_artist, filename_title = parse_filename(file_info['filename'])
    
    # 从标签读取
    tag_artist = file_info['tags'].get('artist', '')
    tag_title = file_info['tags'].get('title', '')
    
    # 标准化比较
    filename_artists = set(split_artist(normalize_text(filename_artist)))
    tag_artists = set(split_artist(normalize_text(tag_artist)))
    
    # 检查艺术家是否有交集
    artist_match = bool(filename_artists & tag_artists) if filename_artists and tag_artists else True
    
    # 检查歌曲名
    norm_filename_title = normalize_text(filename_title)
    norm_tag_title = normalize_text(tag_title)
    title_match = (norm_filename_title in norm_tag_title or 
                   norm_tag_title in norm_filename_title) if (norm_filename_title and norm_tag_title) else True
    
    return artist_match and title_match
```

### 艺术家名称拆分

支持多种分隔符：
- 分号: `;` 或 `；`
- 逗号: `,` 或 `，`
- 连接符: `&`, `/`, `+`, `＋`
- 其他: `、`, `•`, `·`, `|`, `｜`

示例：
```python
from utils import split_artist

artists = split_artist("周杰伦；林俊杰，陈奕迅")
# 返回: ["周杰伦", "林俊杰", "陈奕迅"]
```

### 使用方法

```python
from file_operations import check_filename_consistency

# 执行检查（包含元数据一致性检查）
inconsistent, duplicate, missing = check_filename_consistency(
    check_master=True,
    check_temp=True
)

print(f"不一致文件: {inconsistent}")
print(f"重复文件: {duplicate}")
print(f"缺失歌词: {missing}")
```

---

## 4. 标签检查与更新模块

### 功能概述
检查音乐文件的标签是否齐全，主要包括歌手、歌曲名、专辑、年份、封面等信息，并根据需要自动更新标签。

### 检查的标签字段

| 字段 | 说明 | 必需 |
|------|------|------|
| title | 歌曲标题 | ✅ |
| artist | 艺术家 | ✅ |
| album | 专辑名称 | ✅ |
| year | 发行年份 | ✅ |
| cover | 专辑封面 | ✅ |
| genre | 音乐流派 | ❌ |
| tracknumber | 音轨号 | ❌ |
| discnumber | 碟片号 | ❌ |

### 标签更新策略

```
开始
    ↓
音频文件
    ↓
声纹匹配 (MusicBrainz)
    ├── 成功且分数≥50%
    │   ├── 更新标签 (MusicBrainz数据)
    │   ├── 尝试从QQ/网易云下载封面
    │   └── 结束
    └── 失败或分数<50%
        ↓
    在线查询 (QQ音乐/网易云音乐)
        ├── 优先尝试QQ音乐
        ├── 如果失败，尝试网易云音乐
        ├── 找到匹配
        │   ├── 更新标签 (平台数据)
        │   ├── 下载封面
        │   └── 结束
        └── 未找到
            ↓
        检查标签完整性
        └── 记录缺失信息
```

### 封面检查机制

支持检查的格式：
- **MP3**: 检查ID3v2 APIC帧
- **FLAC**: 检查PICTURE块

### 使用方法

#### 命令行调用

```python
from tag_updater import update_tags_from_fingerprint

# 更新标签（默认处理临时目录）
success, fail, tag_success = update_tags_from_fingerprint()

# 指定处理目录（支持主目录）
success, fail, tag_success = update_tags_from_fingerprint(target_dir=r'D:\music')
```

#### 主程序集成

```bash
# 默认模式（更新临时目录）
python main.py

# check-master模式（更新主目录）
python main.py --check-master

# 跳过标签更新
python main.py --skip-tag-update
```

### 返回值

函数返回三个统计值：
- `success_count`: 成功处理的文件数量
- `fail_count`: 处理失败的文件数量
- `tag_success`: 标签更新成功的文件数量（包括声纹匹配和在线查询）

### 操作日志

更新过程会生成详细的操作日志，包括：
- 每个文件的处理状态
- 声纹匹配结果（分数）
- 在线查询结果（来源：QQ音乐/网易云音乐）
- 封面下载结果
- 标签不完整的文件列表
- 更新失败的文件列表

### 标签更新实现

```python
from music_tagger.core import MusicTagger

# 初始化标签对象
tagger = MusicTagger('song.mp3')

# 更新标签
tagger.update_tags({
    'title': '新标题',
    'artist': '新艺术家',
    'album': '新专辑',
    'year': '2024',
    'genre': 'Pop',
    'tracknumber': '1',
    'discnumber': '1',
    'album_img': 'https://example.com/cover.jpg',  # 封面URL
})
```

### 模块可用性检测

系统会自动检测以下模块的可用性：
- `mutagen_available`: mutagen库是否可用
- `fingerprint_matcher_available`: 声纹匹配模块是否可用
- `music_tagger_available`: music_tagger库是否可用

如果模块不可用，会自动跳过相关功能并记录警告。

---

## 5. 重复检查模块

### 功能概述
根据歌手和歌曲名检查音乐文件是否存在重复。

### 检测规则

- 根据标签中的歌手和歌曲名进行比较
- 标准化文本进行比较（去除空格、转小写）
- 支持多艺术家名称拆分匹配
- 每组重复文件记录为一个重复组

### 检查逻辑

```python
def find_duplicate_files(music_info_list):
    """查找重复音乐文件"""
    artist_title_map = {}
    
    for info in music_info_list:
        tag_artist = info['tags'].get('artist', '')
        tag_title = info['tags'].get('title', '')
        
        if tag_artist and tag_title:
            # 标准化键
            key = (normalize_text(tag_artist), normalize_text(tag_title))
            
            if key not in artist_title_map:
                artist_title_map[key] = []
            artist_title_map[key].append(info)
    
    # 找出重复的
    duplicates = {k: v for k, v in artist_title_map.items() if len(v) > 1}
    return duplicates
```

### 使用方法

```python
from file_operations import check_filename_consistency

# 执行检查（包含重复文件检查）
inconsistent, duplicate, missing = check_filename_consistency(
    check_master=True,
    check_temp=True
)

print(f"重复文件组: {duplicate}")
```

### 操作日志

重复文件会记录到操作日志中，包括：
- 歌手名和歌曲名
- 所有重复文件的完整路径

---

## 6. 歌词文件检查模块

### 功能概述
检查同名歌词文件是否存在，并检查是否存在只有歌词文件的情况（孤立LRC文件）。

### 功能特性

- 检查音乐文件是否有对应的LRC歌词文件
- 检查是否存在孤立的LRC文件（没有对应音乐文件的歌词文件）
- 记录缺失歌词和孤立歌词的详细信息
- 支持多种音频格式（.mp3, .flac, .wav, .ape, .ogg）
- 文件名分隔符修复时同步重命名LRC文件

### 检查逻辑

```python
def check_lrc_files(directory):
    """检查歌词文件"""
    missing_lrc = []
    orphan_lrc = []
    
    # 扫描音乐文件，检查缺失歌词
    for music_file in scan_music_files(directory):
        lrc_path = os.path.splitext(music_file)[0] + '.lrc'
        if not os.path.exists(lrc_path):
            missing_lrc.append(music_file)
    
    # 扫描LRC文件，检查孤立歌词
    for lrc_file in scan_lrc_files(directory):
        name_without_ext = os.path.splitext(lrc_file)[0]
        has_music_file = False
        
        for ext in AUDIO_EXTENSIONS:
            music_path = name_without_ext + ext
            if os.path.exists(music_path):
                has_music_file = True
                break
        
        if not has_music_file:
            orphan_lrc.append(lrc_file)
    
    return missing_lrc, orphan_lrc
```

### 使用方法

```python
from file_operations import check_filename_consistency

# 执行检查（包含歌词文件检查）
inconsistent, duplicate, missing = check_filename_consistency(
    check_master=True,
    check_temp=True
)

print(f"缺失歌词: {missing}")
# orphan_lrc 会记录在操作日志中
```

### LRC文件处理规则

**文件名修改时同步处理LRC**:
```
音乐文件重命名: Taylor Swift-Love Song.mp3 → Taylor Swift - Love Song.mp3
LRC文件同步重命名: Taylor Swift-Love Song.lrc → Taylor Swift - Love Song.lrc
```

**重名删除时同步删除LRC**:
```
删除重复音乐文件: song.mp3
同步删除对应LRC: song.lrc
```

---

## 7. 文件归档模块

### 功能概述
按照音乐文件的元数据年份，自动将文件组织到按年份分类的目录结构中。

### 功能特性

- 按照音乐文件的元数据年份组织目录结构
- 将文件移动到对应的年份目录
- 支持十年分组（1950-1979, 1980-1989, 1990-1999等）
- 处理无年份标签的文件，移动到unknown目录
- 同步移动对应的LRC歌词文件
- 处理重名文件，自动添加序号

### 归档规则

```
输入目录/
    ├── song1.mp3  (年份: 2020)
    ├── song2.flac (年份: 2019)
    ├── song3.wav  (年份: 2005)
    └── song4.mp3  (无年份)

输出目录/
    ├── 1950-1979/
    │   └── (如果有1979年之前的文件)
    ├── 2000-2009/
    │   └── song3.wav
    ├── 2010-2019/
    │   └── song2.flac
    ├── 2020-2029/
    │   └── song1.mp3
    └── unknown/
        └── song4.mp3
```

### 年份分组规则

| 年份范围 | 目录名 |
|---------|--------|
| 1950-1979 | 1950-1979 |
| 1980-1989 | 1980-1989 |
| 1990-1999 | 1990-1999 |
| 2000-2009 | 2000-2009 |
| 2010-2019 | 2010-2019 |
| 2020-2029 | 2020-2029 |
| ... | ... |

### 使用方法

```bash
# 主程序集成
python main.py

# 跳过年份分类
python main.py --skip-organize

# 或者单独运行归档模块
python archive.py
```

### 重名处理

如果目标目录已存在同名文件，自动添加序号：
```
song.mp3 → song_1.mp3 → song_2.mp3
```

---

## 8. 检查报告生成模块

### 功能概述
将检查过程中发现的不一致文件移动到指定目录，并生成检查报告，供后续手动归档使用。

### 功能特性

- 记录所有检查操作到日志文件
- 操作日志同时输出到文件和控制台（WARNING级别）
- 生成详细的检查报告，包括：
  - 文件名不一致的文件
  - 重复文件
  - 缺失歌词的文件
  - 孤立LRC文件
  - 文件名分隔符处理记录
  - 标签不完整的文件

### 日志系统架构

```python
# 主日志系统
main_logger = logging.getLogger('music_manager')
# - 输出到文件: D:\music\Music-YYYYMMDD_HHMMSS.log
# - 输出到控制台: INFO级别

# 操作日志系统
op_logger, log_path = create_operation_log('OperationName')
# - 输出到文件: D:\music\OperationName-YYYYMMDD_HHMMSS.log
# - 输出到控制台: WARNING级别
```

### 日志级别

| 级别 | 说明 | 用途 |
|------|------|------|
| DEBUG | 调试信息 | 详细调试信息 |
| INFO | 一般信息 | 正常操作流程、统计信息 |
| WARNING | 警告信息 | 需要注意的问题（输出到控制台） |
| ERROR | 错误信息 | 操作失败 |

### 使用方法

```python
from utils import create_operation_log
from file_operations import check_filename_consistency

# 创建操作日志
op_logger, log_path = create_operation_log('Check')

# 执行检查
check_filename_consistency(check_master=True, check_temp=True)

# 日志会自动保存到 log_path
# WARNING级别的消息会输出到控制台
```

### 日志格式示例

```
2024-06-18 10:30:00 - INFO - 开始检查文件名一致性
2024-06-18 10:30:01 - INFO - 检查文件名与标签一致性
2024-06-18 10:30:01 - WARNING - 文件名不一致: song.mp3
2024-06-18 10:30:01 - WARNING -   文件名解析: Artist - Title
2024-06-18 10:30:01 - WARNING -   标签信息: Artist2 - Title2
2024-06-18 10:30:02 - INFO - 查找重复音乐文件
2024-06-18 10:30:03 - INFO - 发现重复文件: artist - song
2024-06-18 10:30:03 - WARNING -   - D:\music\artist - song.mp3
2024-06-18 10:30:03 - WARNING -   - D:\music\artist - song (1).mp3
2024-06-18 10:30:04 - INFO - 检查歌词文件
2024-06-18 10:30:05 - WARNING - 缺少歌词文件: artist - song.mp3
2024-06-18 10:30:05 - WARNING - 发现孤立LRC文件: orphan.lrc
2024-06-18 10:30:06 - INFO - 检查结果统计:
2024-06-18 10:30:06 - INFO - 文件名不一致: 1 个
2024-06-18 10:30:06 - INFO - 重复文件组: 1 组
2024-06-18 10:30:06 - INFO - 缺少歌词: 1 个
2024-06-18 10:30:06 - INFO - 孤立LRC: 1 个
```

---

## 9. 主目录检查模块

### 功能概述
检查主目录中的音乐文件是否与soundalike数据库中的记录一致。

### 功能特性

- 运行soundalike去重不带--temp参数，直接在主目录操作
- 检查数据库与目录文件的一致性
- 只检查主目录，不处理临时目录
- 跳过VIP文件解密和移动步骤

### 使用方法

```bash
# check-master模式
python main.py --check-master
```

### 执行流程

```
1. 确定目标目录为主目录 (D:\music)
2. 跳过VIP文件解密和移动
3. 运行声纹识别去重（不带--temp参数）
4. 更新主目录文件的标签
5. 检查主目录文件一致性
6. 不执行年份分类（只对临时目录操作）
```

### 与默认模式对比

| 特性 | 默认模式 | check-master模式 |
|------|---------|-----------------|
| VIP解密 | ✅ 执行 | ❌ 跳过 |
| 普通文件移动 | ✅ 执行 | ❌ 跳过 |
| 声纹识别 | 带--temp参数 | 不带--temp参数 |
| 标签更新 | 临时目录 | 主目录 |
| 文件检查 | 主+临时 | 仅主目录 |
| 年份分类 | 临时目录 | 不执行 |

---

## 10. VIP文件解密模块

### 功能概述
对QQ音乐和网易云音乐的VIP目录中的文件进行解密处理，确保能够进行后续的检查和归档操作。

### QQ音乐解密

#### 技术原理
使用Frida动态注入技术解密`.mflac`和`.mgg`格式文件。

#### 加密格式转换
- `.mflac` → `*.flac` (无损格式)
- `.mgg` → `*.ogg` (有损格式)

### 网易云解密

#### 技术原理
使用`um.exe`工具进行解密。

#### 处理流程
1. 扫描网易云VIP目录中的音乐文件
2. 将文件移动到临时目录
3. 运行um.exe进行解密
4. 解密后的文件输出到完成目录

### 使用方法

```bash
# 主程序集成（默认当前月份）
python main.py

# 指定月份
python main.py --month 202406

# 跳过VIP解密
python main.py --skip-vip

# check-master模式自动跳过
python main.py --check-master
```

### 配置

编辑 `config.py`：

```python
# 网易云音乐目录
NETEASE_DIR = r'G:\Neteasymusic'
NETEASE_VIP_DIR = r'G:\Neteasymusic\VipSOngsDownload'
NETEASE_TMP_DIR = r'G:\NeTmp'

# QQ音乐目录
QQ_DIR = r'G:\QQMusic'
QQ_VIP_DIR = r'G:\QQMusic\VipSOngsDownload'
QQ_TMP_DIR = r'G:\QQTmp'

# 网易云解密工具
UM_EXE = r'um.exe'

# 支持的加密格式
VIP_EXTENSIONS = {'.mflac', '.mgg'}
```

---

## 11. 普通文件移动模块

### 功能概述
将主目录中未被soundalike去重模块识别为重复的音乐文件移动到指定目录。

### 功能特性

- 根据文件修改时间筛选指定月份的文件
- 排除VIP目录中的文件
- 移动文件到临时完成目录
- 同步移动对应的LRC歌词文件
- 处理重名文件，自动添加序号

### 使用方法

```python
from file_operations import move_netease_normal_files, move_qq_normal_files

# 移动网易云普通文件（指定月份）
netease_count = move_netease_normal_files(month='202406')

# 移动QQ普通文件（当前月份）
qq_count = move_qq_normal_files()
```

### 主程序集成

```bash
# 主程序会自动执行
python main.py

# check-master模式会跳过
python main.py --check-master

# 跳过普通文件移动
python main.py --skip-vip
```

### 重名处理

如果目标目录已存在同名文件，自动添加序号：
```
song.mp3 → song_1.mp3 → song_2.mp3
```

---

## 12. 根据声纹从MusicBrainz数据库更新标签

### 功能概述
通过声纹识别从MusicBrainz数据库获取音乐文件的标签信息，并更新音乐文件的标签。

### 技术流程

```
音频文件 → fpcalc → Chromaprint指纹
    ↓
查询AcoustID API
    ↓
获取MusicBrainz录音ID
    ↓
从MusicBrainz API获取详细元数据
    ↓
匹配分数 >= 50%
    ↓
更新音乐文件标签
    ↓
尝试下载封面（QQ/网易云）
```

### 使用方法

```python
from Fingerprint import FingerprintMatcher

# 初始化匹配器
matcher = FingerprintMatcher()

# 匹配文件
result = matcher.match_file('song.mp3')

if result.success and result.recordings:
    # 选择最佳匹配（分数最高）
    best_recording = max(result.recordings, key=lambda x: x.get('score', 0))
    score = best_recording.get('score', 0)
    
    if score >= 50:
        # 更新标签
        update_file_tags('song.mp3', best_recording)
```

### 返回数据格式

```python
{
    "id": "MusicBrainz录音ID",
    "title": "歌曲标题",
    "artist": "艺术家",
    "artist_credit": ["艺术家1", "艺术家2"],  # 多艺术家
    "album": "专辑名称",
    "year": "发行年份",
    "duration": "时长(秒)",
    "score": 95.5,  # 匹配分数 0-100
    "releases": [
        {
            "id": "发行ID",
            "title": "专辑标题",
            "date": "发行日期",
            "country": "发行国家",
            "format": "格式"
        }
    ]
}
```

---

## 13. 根据文件名从QQ音乐和网易云音乐API更新标签

### 功能概述
根据文件名从QQ音乐和网易云音乐的API获取音乐文件的标签信息，并更新音乐文件的标签。

### 技术流程

```
文件名 → 提取歌手和歌曲名
    ↓
优先查询QQ音乐API
    ↓
找到匹配？
    ├─ 是 → 更新标签 → 下载封面
    └─ 否
        ↓
    查询网易云音乐API
        ↓
    找到匹配？
        ├─ 是 → 更新标签 → 下载封面
        └─ 否 → 记录失败
```

### 使用方法

```python
from music_tagger.platforms.qqmusic import QQMusicApi
from music_tagger.platforms.netease import NetEaseMusicClient

# QQ音乐
qq_api = QQMusicApi()
songs = qq_api.search("歌曲名 歌手名")
if songs:
    update_file_tags('song.mp3', songs[0])

# 网易云音乐
netease_api = NetEaseMusicClient()
songs = netease_api.fetch_id3_by_title("歌曲名 歌手名")
if songs:
    update_file_tags('song.mp3', songs[0])
```

### 返回数据格式

```python
{
    "id": "歌曲ID",
    "name": "歌曲标题",
    "artist": "艺术家",
    "album": "专辑",
    "year": "年份",
    "album_img": "封面URL",
    "lyrics": "歌词"
}
```

---

## 14. 日志记录模块

### 功能概述
记录程序运行过程中产生的日志信息，包括错误信息、警告信息、调试信息等。

### 日志系统架构

```python
# 主日志系统
main_logger = logging.getLogger('music_manager')
# - 输出到文件: D:\music\Music-YYYYMMDD_HHMMSS.log
# - 输出到控制台: INFO级别
# - 格式: %(levelname)s: %(message)s

# 操作日志系统
op_logger, log_path = create_operation_log('OperationName')
# - 输出到文件: D:\music\OperationName-YYYYMMDD_HHMMSS.log
# - 输出到控制台: WARNING级别
# - 格式: %(asctime)s - %(levelname)s - %(message)s
```

### 日志级别

| 级别 | 主日志 | 操作日志 | 用途 |
|------|--------|---------|------|
| DEBUG | ❌ | ❌ | 详细调试信息 |
| INFO | ✅ | ✅ | 正常操作流程、统计信息 |
| WARNING | ✅ | ✅（控制台） | 需要注意的问题 |
| ERROR | ✅ | ✅ | 操作失败 |

### 使用方法

```python
from utils import main_logger, create_operation_log

# 使用主日志
main_logger.info('处理完成: 100个文件')
main_logger.warning('发现孤立LRC文件: song.lrc')
main_logger.error('处理失败: song.mp3')

# 创建操作日志
op_logger, log_path = create_operation_log('Check')
op_logger.info('开始检查')
op_logger.warning('发现问题文件')
```

### 日志示例

**主日志**:
```
INFO: 使用当前月份: 202406
INFO: 使用 check-master 模式，只处理主目录: D:\music
INFO: 开始从声纹信息更新标签，目标目录: D:\music
WARNING: 标签不完整: song.mp3 - 缺少: 封面, 年份
INFO: 标签更新完成: 成功 50, 失败 2, 声纹 30, 在线 20
```

**操作日志**:
```
2024-06-18 10:30:00 - INFO - 开始检查文件名一致性
2024-06-18 10:30:01 - WARNING - 文件名不一致: song.mp3
2024-06-18 10:30:01 - WARNING -   文件名解析: Artist - Title
2024-06-18 10:30:02 - INFO - 发现孤立LRC文件: orphan.lrc
```

---

# 二、操作流程

## 1. 主目录检查 
### 参数 --check

### 概述
检查主目录中的音乐文件，不进行VIP文件解密和移动操作。

### 1.1 确定处理目录

```python
# check-master模式
target_dir = MAIN_DIR  # D:\music
```

### 1.2 跳过VIP文件解密和移动

**跳过的步骤**:
- 解密QQ音乐VIP文件
- 解密网易云VIP文件
- 移动普通文件

### 1.3 声纹识别去重（不带--temp参数）

```bash
soundalike.exe -move-interactive G:\Tmp D:\music
```

**执行内容**:
- 运行声纹识别去重（不带--temp参数）
- 识别重复文件并移动到 `G:\Tmp` 目录
- 建立数据库记录已存在的音乐文件信息

### 1.4 更新主目录文件的标签

```python
update_tags_from_fingerprint(target_dir=r'D:\music')
```

**更新策略**:
1. 优先使用声纹匹配MusicBrainz数据库
2. 如果失败或分数<50%，根据文件名从QQ音乐/网易云音乐API查询
3. 下载缺失的封面图片

### 1.5 检查主目录文件一致性

```python
check_filename_consistency(check_master=True, check_temp=False)
```

**检查内容**:
- 文件名格式检查（" - "分隔符）
- 文件名分隔符修复
- 元数据一致性检查
- 重复文件检查
- 歌词文件检查（缺失LRC、孤立LRC）

### 1.6 数据库一致性检查

### 概述
仅检查soundalike数据库与目录文件的一致性状态。

**执行内容**:
- 运行 `soundalike.exe -check D:\music`
- 检查数据库中的记录与实际文件是否一致
- 发现不一致时生成报告

### 1.7 生成检查报告

**报告内容**:
- 操作日志文件路径
- 文件名不一致数量
- 重复文件组数量
- 缺失歌词数量
- 孤立LRC数量
- 文件名分隔符处理数量

### 命令行执行

```bash
# 完整的主目录检查流程
python main.py --check-master

# 跳过某些步骤
python main.py --check-master --skip-fingerprint
python main.py --check-master --skip-tag-update
python main.py --check-master --skip-check
```

---

## 2. 临时目录归档 
### 参数  --archive

### 概述
将指定月份的音乐文件归档到临时目录，进行解密、去重、标签更新、年份分类等处理。

### 2.1 月份参数验证

```python
month = args.month or get_current_month()

if not validate_month_format(month):
    main_logger.error(f'月份格式错误: {month}')
    sys.exit(1)
```

**验证规则**:
- 格式: YYYYMM（6位数字）
- 年份: 1900-2099
- 月份: 01-12

### 2.2 拷贝QQ音乐VIP文件

```python
decrypt_qq_vip(month='202406')
```

**执行内容**:
- 扫描 `G:\QQMusic\VipSOngsDownload` 目录
- 根据文件修改时间筛选指定月份的文件（`.mflac`, `.mgg`）
- 拷贝文件到临时目录 `G:\QQTmp`
- 使用Frida解密为 `.flac` / `.ogg` 格式
- 输出到 `G:\Temp`

### 2.3 拷贝网易云音乐VIP文件

```python
decrypt_netease_vip(month='202406')
```

**执行内容**:
- 扫描 `G:\Neteasymusic\VipSOngsDownload` 目录
- 根据文件修改时间筛选指定月份的文件
- 拷贝文件到临时目录 `G:\NeTmp`
- 运行 `um.exe` 进行解密
- 输出到 `G:\Temp`

### 2.4 移动普通文件

```python
# 网易云普通文件
netease_normal_count = move_netease_normal_files(month='202406')

# QQ普通文件
qq_normal_count = move_qq_normal_files(month='202406')
```

**执行内容**:
- 扫描 `G:\Neteasymusic` 目录（排除VIP目录）
- 扫描 `G:\QQMusic` 目录（排除VIP目录）
- 根据文件修改时间筛选指定月份的文件（`.mp3`, `.flac`, `.wav`, `.ape`, `.ogg`）
- 移动文件到 `G:\Temp`
- 同步移动对应的LRC歌词文件

### 2.5 数据库一致性检查 

 - 仅检查soundalike数据库与目录文件的一致性状态。

**执行内容**:
- 运行 `soundalike.exe -check D:\music`
- 检查数据库中的记录与实际文件是否一致
- 发现不一致时生成报告

### 2.6 声纹识别去重

```bash
soundalike.exe -move-interactive G:\Tmp -temp G:\Temp D:\music
```

**执行内容**:
- 使用--temp参数运行声纹识别
- 扫描 `G:\Temp` 目录
- 识别并移动重复文件到 `G:\Tmp`
- 建立数据库记录

### 2.7 更新标签信息

```python
update_tags_from_fingerprint(target_dir=r'G:\Temp')
```

**更新策略**:
1. 优先使用声纹匹配MusicBrainz数据库（分数>=50%）
2. 如果失败，从QQ音乐API查询
3. 如果失败，从网易云音乐API查询
4. 下载缺失的封面图片

### 2.8 检查文件一致性

```python
check_filename_consistency(check_master=False, check_temp=True)
```

**检查内容**:
- 文件名格式检查和修复
- 元数据一致性检查
- 重复文件检查
- 歌词文件检查
- 孤立LRC检查

### 2.9 按年份归档

```python
organize_by_year()
```

**执行内容**:
- 扫描 `G:\Temp` 目录
- 读取音乐文件标签中的年份信息
- 按十年分组创建目录结构
- 移动文件到对应年份目录
- 处理无年份文件，移动到 `G:\Temp\unknown`
- 同步移动对应的LRC歌词文件

### 2.10 生成检查报告

**报告内容**:
- 操作日志文件路径
- VIP处理统计
- 普通文件移动统计
- 标签更新统计
- 文件检查统计
- 年份归档统计

### 命令行执行

```bash
# 完整的归档流程（默认当前月份）
python main.py

# 指定月份
python main.py --month 202406

# 跳过某些步骤
python main.py --skip-vip
python main.py --skip-fingerprint
python main.py --skip-tag-update
python main.py --skip-check
python main.py --skip-organize
```

---

## 3. 临时目录手动归档
### 参数 --archive-manual
 同 2.5-2.10 的步骤


---

# 附录

## 命令行参数

### 完整参数列表

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--month YYYYMM` | 指定扫描的月份 | 当前月份 |
| `--check` | 检查主目录D:\music的文件 | False |
| `--archive` | 归档临时目录G:\Temp | True |
| `--archive-manual` | 手动归档临时目录G:\Temp | False |
| `--checkdb` | 仅检查数据库和目录文件的一致性状态 | False |
| `--skip-vip` | 跳过VIP文件解密步骤 | False |
| `--skip-fingerprint` | 跳过声纹识别步骤 | False |
| `--skip-tag-update` | 跳过标签更新步骤 | False |
| `--skip-check` | 跳过文件检查步骤 | False |
| `--skip-organize` | 跳过年份分类步骤 | False |

### 使用示例

```bash
# 完整处理流程（默认）
python main.py

# 处理指定月份
python main.py --month 202406

# 仅检查主目录
python main.py --check

# 归档临时目录
python main.py --archive

# 手动归档临时目录
python main.py --archive-manual

# 检查数据库一致性
python main.py --checkdb

# 跳过某些步骤
python main.py --skip-vip
python main.py --skip-fingerprint --skip-tag-update
```

---

## 配置说明

### 目录配置 (config.py)

```python
# ==================== 目录配置 ====================

# 主目录
MAIN_DIR = r'D:\music'

# 网易云音乐目录
NETEASE_DIR = r'G:\Neteasymusic'
NETEASE_VIP_DIR = r'G:\Neteasymusic\VipSOngsDownload'
NETEASE_TMP_DIR = r'G:\NeTmp'

# QQ音乐目录
QQ_DIR = r'G:\QQMusic'
QQ_VIP_DIR = r'G:\QQMusic\VipSOngsDownload'
QQ_TMP_DIR = r'G:\QQTmp'

# 临时目录
TEMP_COMPLETED_DIR = r'G:\Temp'
TEMP_MOVE_DIR = r'G:\Tmp'

# 外部程序路径
UM_EXE = r'um.exe'
SOUNDALIKE_EXE = r'soundalike.exe'

# ==================== 文件扩展名配置 ====================

# 支持的所有音乐文件扩展名
MUSIC_EXTENSIONS = {'.flac', '.mp3', '.wav', '.ape', '.ogg', '.mflac', '.mgg'}

# 解压后的音频格式
AUDIO_EXTENSIONS = {'.flac', '.mp3', '.wav', '.ape', '.ogg'}

# VIP加密格式
VIP_EXTENSIONS = {'.mflac', '.mgg'}
```

---

## 常见问题

**Q: 声纹匹配为什么找不到结果?**
A: 可能原因:
- 音频文件太短或质量太差
- MusicBrainz数据库中没有收录
- fpcalc工具未正确安装

**Q: QQ音乐解密失败怎么办?**
A: 检查:
- QQMusic.exe是否正在运行
- Frida是否正确安装
- 是否有管理员权限

**Q: 网易云API请求失败?**
A: 可能是:
- 网络连接问题
- API接口变更
- 加密公钥不匹配
- um.exe工具未正确配置

**Q: check-master模式和默认模式的区别?**
A: check-master模式:
- 跳过VIP文件解密和移动
- 声纹识别不带--temp参数
- 只处理主目录，不处理临时目录
- 不执行年份分类

**Q: 月份格式错误怎么办?**
A: 正确格式为YYYYMM，如202406。年份范围1900-2099，月份范围01-12。

**Q: 如何跳过某个步骤?**
A: 使用对应的--skip-*参数，如--skip-vip跳过VIP解密。

---

## 性能建议

1. **批量处理**: 尽量批量处理文件，减少重复初始化开销
2. **并发控制**: 限制并发请求数，避免被API封禁
3. **缓存机制**: 使用缓存避免重复计算和请求
4. **进度显示**: 长时间操作显示进度信息（在日志中）
5. **备份**: 重要操作前务必备份文件
6. **分步骤执行**: 对于大量文件，可以分步骤执行，每步验证结果

---

## 扩展阅读

### 官方文档

- [MusicBrainz API文档](https://musicbrainz.org/doc/MusicBrainz_API)
- [AcoustID API文档](https://acoustid.org/webservice)
- [Frida官方文档](https://frida.re/docs/)
- [mutagen文档](https://mutagen.readthedocs.io/)

### 相关工具

- [Chromaprint/fpcalc](https://acoustid.org/chromaprint)
- [soundalike](https://github.com/soundalike/soundalike)
- [music-tag](https://pypi.org/project/music-tag/)
