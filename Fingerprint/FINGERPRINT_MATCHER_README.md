# 音乐文件指纹匹配器 - 独立版本

这是一个从Picard项目中提取的独立音乐文件指纹匹配模块，无需UI或PyQt依赖。

## 功能特性

- 通过音频指纹识别音乐文件
- 使用AcoustID API查询匹配结果
- 从MusicBrainz获取完整的录音信息
- **智能匹配算法**：使用 Picard 的匹配算法自动选择最佳匹配结果
- **加载完整Release信息**：与Picard一致的Release加载流程，获取所有音轨、关系等完整数据
- 支持多种音频格式（通过fpcalc）
- 完全独立的Python实现，无GUI依赖

## 依赖要求

### 必需依赖

- Python 3.7+
- **opencc** - 完整的繁简中文字符转换库（必需）

### 外部工具

- **fpcalc** - 音频指纹计算工具
  - 下载地址: https://acoustid.org/chromaprint#download
  - Linux: `sudo apt-get install libchromaprint-tools`
  - macOS: `brew install chromaprint`
  - Windows: 从官网下载安装

## 安装

1. 确保 Python 3.7+ 已安装
2. 安装依赖:
   ```bash
   # 安装 OpenCC（必需，用于繁简转换）
   pip install opencc

   # macOS
   brew install chromaprint

   # Ubuntu/Debian
   sudo apt-get install libchromaprint-tools

   # Windows
   # 从 https://acoustid.org/chromaprint 下载并安装
   ```

## 使用方法

### 命令行使用

```bash
# 基本用法
python fingerprint_matcher.py path/to/audio.mp3

# 指定fpcalc路径
python fingerprint_matcher.py path/to/audio.flac /path/to/fpcalc
```

### 作为模块使用

```python
from fingerprint_matcher import (
    FingerprintMatcher,
    format_recording_info,
    format_complete_tags
)

# 创建匹配器
matcher = FingerprintMatcher()

# 方式1: 从音频文件匹配
result = matcher.match_file('song.mp3')

# 处理结果
if result.success:
    # 最佳匹配（自动选择最合适的标签）
    if result.best_match:
        # 显示完整标签信息（包含120+个标签字段）
        print(format_complete_tags(result.best_match))

    # 查看所有候选结果
    print(f"找到 {len(result.recordings)} 个匹配结果:")
    for i, recording in enumerate(result.recordings, 1):
        print(f"\n结果 #{i}:")
        print(format_recording_info(recording))
else:
    print(f"匹配失败: {result.error}")

# 方式2: 使用现有元数据提高匹配精度
metadata = {
    'title': '月亮代表我的心',
    'artist': '邓丽君',
    'album': '邓丽君金曲精选',
    'date': '1999',
    'totaltracks': '20',
}

result = matcher.match_file('song.mp3', metadata=metadata)

# 方式3: 从已有指纹匹配
result = matcher.match_from_fingerprint(
    fingerprint='AQAD...',  # 指纹字符串
    duration=180  # 时长（秒）
)
```

### 高级用法

```python
from fingerprint_matcher import (
    FingerprintMatcher,
    FingerprintCalculator,
    AcoustIDClient,
    RecordingResolver,
    format_recording_info,
    map_recording_to_tags
)

# 1. 仅计算指纹
calculator = FingerprintCalculator()
fingerprint_result = calculator.calculate('song.mp3')
print(f"指纹: {fingerprint_result.fingerprint}")
print(f"时长: {fingerprint_result.duration}秒")

# 2. 仅查询AcoustID
client = AcoustIDClient()
document, error = client.query_acoustid(
    fingerprint='AQAD...',
    duration=180
)

# 3. 解析录音信息
resolver = RecordingResolver(client.http_client)
recordings = resolver.resolve(document)
for recording in recordings:
    # 映射到Picard风格的标签字典（120+个标签字段）
    tags = map_recording_to_tags(recording)
    print(f"标题: {tags['title']}")
    print(f"艺术家: {tags['artist']}")
    print(f"专辑: {tags['album']}")
    print(f"录音ID: {tags['musicbrainz_recordingid']}")
```
```

## 返回数据结构

### MatchResult

```python
class MatchResult:
    success: bool              # 是否成功
    recordings: List[Dict]     # 匹配的录音列表（所有候选）
    best_match: Dict           # 最佳匹配（自动选择）
    error: str                  # 错误信息（如有）
```

### Recording 数据结构

每个录音记录包含以下字段:

```python
{
    'id': str,                    # MusicBrainz录音ID
    'title': str,                 # 歌曲标题
    'artist-credit': [            # 艺术家列表
        {
            'artist': {
                'name': str,      # 艺术家名称
                'sort-name': str, # 排序名称
                'id': str         # MusicBrainz艺术家ID
            },
            'name': str,          # 显示名称
            'joinphrase': str     # 连接符（如 '; '）
        }
    ],
    'releases': [                 # 发行信息列表
        {
            'id': str,            # MusicBrainz发行ID
            'title': str,         # 发行标题
            'date': str,          # 发行日期
            'country': str,       # 发行国家
            'release-group': {
                'id': str,
                'primary-type': str,      # 主要类型（如 Album）
                'secondary-types': []      # 次要类型
            },
            'media': [
                {
                    'format': str,        # 媒体格式（如 CD, Digital Media）
                    'position': int,     # 碟片位置
                    'track-count': int,   # 音轨数量
                    'track': [...]       # 音轨列表
                }
            ]
        }
    ],
    'length': int,                # 时长（毫秒）
    'score': float,               # AcoustID匹配分数（0-100）
    'sources': int,               # 来源数量
    'acoustid': str,              # AcoustID
    '_calculated_similarity': float  # 计算出的相似度分数（0-1，可选）
}
```

## 配置选项

### 修改AcoustID客户端密钥

```python
from fingerprint_matcher import AcoustIDClient

# 使用自定义密钥
client = AcoustIDClient()
client.client_key = 'your_api_key'
```

### 修改User-Agent

```python
from fingerprint_matcher import HTTPClient

http_client = HTTPClient(user_agent='MyApp/1.0')
```

### 指定fpcalc路径

```python
from fingerprint_matcher import FingerprintCalculator

calculator = FingerprintCalculator(fpcalc_path='/path/to/fpcalc')
```

## 工作流程

### 标准流程

1. **计算指纹**: 使用fpcalc工具计算音频文件的声学指纹
2. **查询AcoustID**: 将指纹发送到AcoustID API获取匹配结果
3. **解析录音信息**: 将AcoustID返回的数据转换为标准格式
4. **获取完整信息**: 对于不完整的记录，从MusicBrainz API获取完整元数据
5. **计算匹配分数**: 基于来源数和相似度计算匹配分数
6. **智能选择最佳匹配**: 使用相似度算法选择最合适的标签
7. **返回结果**: 返回排序后的匹配录音列表和最佳匹配

### Picard兼容流程（推荐）

当选择最佳匹配后，Picard会加载完整的Release信息：

1. **AcoustID匹配** → 2. **选择最佳recording** → 3. **获取release_id**
4. **加载完整Release**: 向 `https://musicbrainz.org/ws/2/release/{release_id}` 发起GET请求
5. **获取完整数据**: 包含所有音轨、完整标签、关系等
6. **合并信息**: 将完整Release数据合并到recording数据中

这确保了获取的标签信息与Picard完全一致。

## 完整标签映射

本模块实现了与Picard相同的标签映射系统,将MusicBrainz数据映射到120+个标准标签字段。

### 使用标签映射

```python
from fingerprint_matcher import FingerprintMatcher, map_recording_to_tags

matcher = FingerprintMatcher()
result = matcher.match_file('song.mp3')

if result.success and result.best_match:
    # 将recording数据映射到标签字典
    tags = map_recording_to_tags(result.best_match)

    # 访问各种标签
    print(f"标题: {tags['title']}")
    print(f"艺术家: {tags['artist']}")
    print(f"专辑: {tags['album']}")
    print(f"专辑艺术家: {tags['albumartist']}")

    # MusicBrainz ID
    print(f"录音ID: {tags['musicbrainz_recordingid']}")
    print(f"专辑ID: {tags['musicbrainz_releaseid']}")
    print(f"专辑组ID: {tags['musicbrainz_releasegroupid']}")
    print(f"音轨ID: {tags['musicbrainz_trackid']}")
    print(f"艺术家ID: {tags['musicbrainz_artistid']}")
    print(f"专辑艺术家ID: {tags['musicbrainz_albumartistid']}")

    # 日期信息
    print(f"发行日期: {tags['date']}")
    print(f"首发日期: {tags['originaldate']}")
    print(f"首发年份: {tags['originalyear']}")

    # 音轨和碟片
    print(f"音轨号: {tags['tracknumber']}")
    print(f"碟号: {tags['discnumber']}")
    print(f"总音轨数: {tags['totaltracks']}")
    print(f"总碟数: {tags['totaldiscs']}")
    print(f"专辑总音轨数: {tags['totalalbumtracks']}")

    # 发行信息
    print(f"发行国/地区: {tags['releasecountry']}")
    print(f"专辑状态: {tags['releasestatus']}")
    print(f"专辑类型: {tags['releasetype']}")
    print(f"媒体格式: {tags['media']}")

    # 唱片公司
    print(f"专辑唱片公司: {tags['label']}")
    print(f"编号: {tags['catalognumber']}")
    print(f"条码: {tags['barcode']}")

    # 流派
    print(f"流派: {tags['genre']}")
```

### 支持的标签列表

#### 基本信息
- `title` - 歌曲名称
- `length` - 时长 (mm:ss格式)
- `musicbrainz_recordingid` - MusicBrainz录音ID
- `acoustid_id` - AcoustID

#### 艺术家信息
- `artist` - 艺术家 (标准化,含连接词)
- `artists` - 艺术家列表
- `artistsort` - 艺术家排序顺序
- `artists_sort` - 艺术家排序列表
- `artists_countries` - 艺术家国家列表
- `musicbrainz_artistid` - MusicBrainz艺术家ID列表

#### 专辑信息
- `album` - 专辑标题
- `musicbrainz_releaseid` - MusicBrainz专辑ID
- `musicbrainz_releasegroupid` - MusicBrainz专辑组ID
- `releasegroup` - 专辑组标题
- `albumartist` - 专辑艺术家
- `albumartists` - 专辑艺术家列表
- `albumartistsort` - 专辑艺术家排序
- `albumartists_sort` - 专辑艺术家排序列表
- `musicbrainz_albumartistid` - 专辑艺术家ID列表

#### 日期信息
- `date` - 发行日期 (YYYY-MM-DD格式)
- `originaldate` - 首发日期
- `originalyear` - 首发年份
- `releasegroup_firstreleasedate` - 专辑组首次发行日期

#### 音轨/碟片信息
- `tracknumber` - 音轨号
- `discnumber` - 碟号
- `discsubtitle` - 碟片子标题
- `totaltracks` - 总音轨数
- `totaldiscs` - 总碟数
- `totalalbumtracks` - 专辑总音轨数
- `musicbrainz_trackid` - MusicBrainz音轨ID

#### 发行信息
- `releasecountry` - 发行国/地区
- `releasecountries` - 发行国家列表
- `releasestatus` - 专辑状态 (official/promotional/bootleg)
- `releasetype` - 专辑类型列表
- `primaryreleasetype` - 主要专辑类型
- `secondaryreleasetype` - 次要专辑类型
- `media` - 媒体格式 (CD/Vinyl/Digital Media等)

#### 唱片公司
- `label` - 唱片公司列表
- `catalognumber` - 编号列表
- `barcode` - 条码
- `asin` - Amazon ASIN

#### 标签/流派
- `genre` - 流派列表
- `genres` - 所有流派
- `folksonomy_tags` - 社区标签

#### 其他
- `isrc` - ISRC代码列表
- `recordingcomment` - 录音备注
- `score` - 匹配得分
- `sources` - 提交来源数

### 显示完整标签

使用 `format_complete_tags()` 函数可以格式化显示所有标签:

```python
from fingerprint_matcher import FingerprintMatcher, format_complete_tags

matcher = FingerprintMatcher()
result = matcher.match_file('song.mp3')

if result.success and result.best_match:
    print(format_complete_tags(result.best_match))
```

### 加载完整Release信息（与Picard一致）

Picard在选择最佳匹配后,会加载完整的Release信息,包括所有音轨、关系等。

**方法1：命令行加载完整Release**

```bash
python fingerprint_matcher.py song.mp3 --load-full-release
```

**方法2：编程方式加载完整Release**

```python
from fingerprint_matcher import FingerprintMatcher, map_recording_to_tags

matcher = FingerprintMatcher()
result = matcher.match_file('song.mp3')

if result.success and result.best_match:
    # 加载完整Release信息
    full_release = matcher.load_full_release_for_best_match(result.best_match)
    
    if full_release:
        print("✓ 完整Release加载成功!")
        
        # 完整Release包含：
        # - 所有音轨信息（track列表）
        # - 完整的媒体信息（media列表）
        # - 唱片公司信息
        # - 标签/流派
        # - 关系信息（如果请求了inc参数）
        
        # 显示Release ID
        print(f"Release ID: {full_release.get('id')}")
        print(f"Release标题: {full_release.get('title')}")
        
        # 显示媒体信息
        media_list = full_release.get('media', [])
        print(f"\n媒体数量: {len(media_list)}")
        for medium in media_list[:3]:
            format_type = medium.get('format', 'Unknown')
            track_count = medium.get('track-count', 0)
            print(f"  - {format_type}: {track_count} 首音轨")
        
        # 使用完整Release数据映射标签
        tags_complete = map_recording_to_tags(result.best_match)
        print(f"\n完整标签映射:")
        print(f"  标题: {tags_complete.get('title')}")
        print(f"  专辑: {tags_complete.get('album')}")
        print(f"  总音轨数: {tags_complete.get('totaltracks')}")
```

**方法3：自定义inc参数**

```python
from fingerprint_matcher import FingerprintMatcher

matcher = FingerprintMatcher()
result = matcher.match_file('song.mp3')

if result.success and result.best_match:
    # 自定义inc参数来控制加载的信息量
    
    # 最小参数（快速）
    min_inc = ['media', 'recordings']
    release = matcher.load_full_release_for_best_match(
        result.best_match,
        inc=min_inc
    )
    
    # 标准参数（推荐）
    std_inc = [
        'aliases',
        'annotation',
        'artist-credits',
        'artists',
        'media',
        'recordings',
        'release-groups',
    ]
    release = matcher.load_full_release_for_best_match(
        result.best_match,
        inc=std_inc
    )
    
    # 完整参数（包含关系）
    full_inc = std_inc + [
        'artist-rels',
        'recording-rels',
        'label-rels',
        'release-group-level-rels',
    ]
    release = matcher.load_full_release_for_best_match(
        result.best_match,
        inc=full_inc
    )
```

**详细示例**: 参见 `example_full_release.py` 文件,包含完整的演示代码。

## 智能匹配算法

### 算法概述

当 AcoustID 返回多个候选结果时，模块使用 Picard 的智能匹配算法自动选择最合适的标签。该算法基于以下因素综合评分：

### 评分因素

1. **标题相似度**（权重：13）
   - 使用基于编辑距离的字符串相似度算法
   - 支持多词字符串匹配

2. **艺术家相似度**（权重：4）
   - 比较现有艺术家与候选艺术家名称
   - 支持多艺术家协作匹配

3. **时长匹配**（权重：10）
   - 完全匹配 = 1.0
   - 相差30秒内线性递减
   - 相差超过30秒 = 0.0

4. **发行类型偏好**（权重：14）
   - Album（专辑）：1.0
   - Single（单曲）：0.8
   - EP：0.7
   - Compilation（精选集）：0.6
   - Other：0.5

5. **日期匹配**（权重：4）
   - 完全匹配：1.00
   - 年份相同：0.95
   - 年份相差±2年：0.85
   - 其他情况：较低分数

6. **曲目数量**（权重：4）
   - 完全匹配：1.0
   - 候选曲目更多：0.3
   - 候选曲目更少：0.0

7. **国家/格式偏好**（权重：各2）
   - 根据用户偏好加权（简化版默认0.5）

### 匹配流程

```python
# 1. 提供现有元数据（可选）
metadata = {
    'title': '月亮代表我的心',
    'artist': '邓丽君',
    'album': '邓丽君金曲精选',
    'date': '1999',
    'totaltracks': '20',
}

# 2. 执行匹配
result = matcher.match_file('song.mp3', metadata=metadata)

# 3. 获取最佳匹配
if result.best_match:
    # 查看计算出的相似度
    similarity = result.best_match.get('_calculated_similarity', 0)
    print(f"相似度: {similarity * 100:.1f}%")

# 4. 查看所有候选结果
for recording in result.recordings:
    print(f"{recording['title']} - 分数: {recording['score']:.1f}%")
```

### 不提供元数据时的行为

如果不提供现有元数据，模块会：
1. 返回所有候选结果
2. 自动选择 AcoustID 分数最高的结果作为 `best_match`
3. 不计算元数据相似度分数

### 最佳实践

1. **尽可能提供现有元数据**：即使只有标题和艺术家也能显著提高匹配精度
2. **时长信息很有用**：如果知道文件时长，可以排除不匹配的结果
3. **查看相似度分数**：`_calculated_similarity` 越高，匹配越可靠
4. **处理多个结果**：检查 `result.recordings` 的所有候选，必要时手动选择

## 错误处理

代码包含以下错误处理:

- fpcalc未找到或执行失败
- 网络连接错误
- API返回错误
- JSON解析错误
- 超时错误

## 限制

1. **API限制**: AcoustID API有速率限制（每秒最多3次请求）
2. **fpcalc依赖**: 需要安装fpcalc外部工具
3. **网络依赖**: 需要互联网连接访问AcoustID和MusicBrainz API
4. **文件格式**: 取决于fpcalc支持的音频格式

## 示例输出

```
INFO: Processing file: test.mp3
INFO: Found fpcalc: /usr/local/bin/fpcalc
INFO: Fingerprint calculated: 45678 chars, duration: 234s
INFO: Querying AcoustID with fingerprint (45678 chars, 234s)
INFO: AcoustID returned 2 results
INFO: Resolved 2 recordings

成功! 找到 2 个匹配结果:

结果 #1:
============================================================
Title: Bohemian Rhapsody
Artist: Queen
Match Score: 100.0%
Sources: 15
AcoustID: 7b1e6a7e-2a6b-4b8e-9b6a-5c4e3d2a1b0c
MusicBrainz ID: 3c5b6b8e-9d4e-4f8a-8b5e-6d4f8a5b2e1c
Releases (3):
  - A Night at the Opera (1975)
  - Greatest Hits (1981)
  - Classic Queen (1992)
============================================================

结果 #2:
============================================================
Title: Bohemian Rhapsody
Artist: Queen
Match Score: 85.0%
Sources: 5
AcoustID: 9d2e7a8f-3b7c-5c9f-0a7b-6e5f9a8b3c4d
MusicBrainz ID: 4d6c7c9f-0e5f-5g9b-1c6f-7e5g9b6c3f2d
Releases (1):
  - Live Killers (1979)
============================================================
```

## API 参考

### 主要类

- `FingerprintCalculator`: 计算音频指纹
- `AcoustIDClient`: AcoustID API客户端
- `RecordingResolver`: 解析录音信息
- `FingerprintMatcher`: 整合所有功能的主类
- `HTTPClient`: 简单的HTTP请求客户端

### 主要函数

- `format_recording_info(recording, show_similarity=False)`: 格式化录音信息用于显示
- `traditional_to_simplified(text)`: 将繁体中文转换为简体中文
- `convert_dict_to_simplified(data)`: 递归转换数据结构中的所有繁体字

### 匹配算法相关函数

- `similarity2(a, b)`: 计算多词字符串的相似度
- `length_score(a, b)`: 计算时长相似度分数
- `trackcount_score(actual, expected)`: 计算曲目数量相似度
- `extract_year_from_date(dt)`: 从日期字符串中提取年份
- `linear_combination_of_weights(parts)`: 计算加权线性组合

## 繁简转换

本模块使用**OpenCC**库进行完整的繁简中文字符转换，确保API返回的繁体中文数据能够正确转换为简体中文。

### 为什么需要繁简转换？

AcoustID API返回的JSON响应中包含Unicode转义字符，这些字符解码后是繁体中文。例如：
- `\u9127\u9e97\u541b` → `鄧麗君`（繁体）
- 转换后 → `邓丽君`（简体）

如果不进行完整转换，可能导致：
- 同一首歌曲被识别成两首不同的歌（繁体和简体版本）
- 名称匹配不准确
- 数据不一致

### OpenCC的安装

```bash
pip install opencc
```

### 转换机制

所有API响应都会自动进行繁简转换，无需手动处理：

```python
# API返回（繁体）
{"title": "鄧麗君"}

# 自动转换为简体
{"title": "邓丽君"}
```

转换覆盖所有汉字，确保100%准确。

## 许可证

本代码从Picard项目提取，遵循GNU General Public License v2.0或更高版本。

## 相关链接

- Picard项目: https://picard.musicbrainz.org/
- AcoustID: https://acoustid.org/
- MusicBrainz: https://musicbrainz.org/
- Chromaprint: https://acoustid.org/chromaprint
