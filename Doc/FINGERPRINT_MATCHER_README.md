# 音乐文件指纹匹配器 - 独立版本

这是一个从Picard项目中提取的独立音乐文件指纹匹配模块，无需UI或PyQt依赖。

## 功能特性

- 通过音频指纹识别音乐文件
- 使用AcoustID API查询匹配结果
- 从MusicBrainz获取完整的录音信息
- 支持多种音频格式（通过fpcalc）
- 完全独立的Python实现，无GUI依赖

## 依赖要求

### 必需依赖

- Python 3.7+

### 外部工具

- **fpcalc** - 音频指纹计算工具
  - 下载地址: https://acoustid.org/chromaprint#download
  - Linux: `sudo apt-get install libchromaprint-tools`
  - macOS: `brew install chromaprint`
  - Windows: 从官网下载安装

## 安装

1. 确保 Python 3.7+ 已安装
2. 安装 fpcalc:
   ```bash
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
from fingerprint_matcher import FingerprintMatcher, format_recording_info

# 创建匹配器
matcher = FingerprintMatcher()

# 方式1: 从音频文件匹配
result = matcher.match_file('song.mp3')

# 方式2: 从已有指纹匹配
result = matcher.match_from_fingerprint(
    fingerprint='AQAD...'  # 指纹字符串
    duration=180  # 时长（秒）
)

# 处理结果
if result.success:
    print(f"找到 {len(result.recordings)} 个匹配结果:")
    for i, recording in enumerate(result.recordings, 1):
        print(f"\n结果 #{i}:")
        print(format_recording_info(recording))
else:
    print(f"匹配失败: {result.error}")
```

### 高级用法

```python
from fingerprint_matcher import (
    FingerprintMatcher,
    FingerprintCalculator,
    AcoustIDClient,
    RecordingResolver,
    format_recording_info
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
    print(format_recording_info(recording))
```

## 返回数据结构

### MatchResult

```python
class MatchResult:
    success: bool              # 是否成功
    recordings: List[Dict]     # 匹配的录音列表
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
    'score': float,               # 匹配分数（0-100）
    'sources': int,               # 来源数量
    'acoustid': str               # AcoustID
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

1. **计算指纹**: 使用fpcalc工具计算音频文件的声学指纹
2. **查询AcoustID**: 将指纹发送到AcoustID API获取匹配结果
3. **解析录音信息**: 将AcoustID返回的数据转换为标准格式
4. **获取完整信息**: 对于不完整的记录，从MusicBrainz API获取完整元数据
5. **计算匹配分数**: 基于来源数和相似度计算匹配分数
6. **返回结果**: 返回排序后的匹配录音列表

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

- `format_recording_info(recording)`: 格式化录音信息用于显示

## 许可证

本代码从Picard项目提取，遵循GNU General Public License v2.0或更高版本。

## 相关链接

- Picard项目: https://picard.musicbrainz.org/
- AcoustID: https://acoustid.org/
- MusicBrainz: https://musicbrainz.org/
- Chromaprint: https://acoustid.org/chromaprint
