# Music Helper 功能详细说明

## 目录
- [QQ音乐解密](#qq音乐解密)
- [声纹识别匹配](#声纹识别匹配)
- [音乐标签更新](#音乐标签更新)
- [文件归档](#文件归档)
- [重复检测](#重复检测)
- [歌词管理](#歌词管理)

---

## QQ音乐解密

### 功能概述

QQ音乐VIP下载的歌曲使用 `.mflac` (FLAC) 和 `.mgg` (OGG) 格式，这些文件经过加密无法直接播放。本项目使用 Frida 动态注入技术解密这些文件。

### 技术原理

**Frida Hook 流程**:
```
1. 启动QQMusic.exe进程
2. Frida附加到进程
3. 注入 hook_qq_music.js 脚本
4. Hook解密函数并拦截密钥
5. 使用密钥解密音频数据
6. 保存为标准格式文件
```

**加密格式**:
- `.mflac` → `*.flac` (无损格式)
- `.mgg` → `*.ogg` (有损格式)

### 使用方法

#### 方法1: 命令行

```bash
# 列出默认下载目录中的歌曲
python Decrypto/qq.py -l

# 解密指定目录
python Decrypto/qq.py -i "G:\QQMusic\VipSOngsDownload" -o "G:\QQMusic\Decrypted"
```

#### 方法2: 作为模块调用

```python
from Decrypto.qq import run_decrypt

run_decrypt(
    input_dir="G:\QQMusic\VipSOngsDownload",
    output_dir="G:\QQMusic\Decrypted"
)
```

#### 方法3: 通过主程序集成

编辑 `main.py` 中的目录配置，然后运行:
```bash
python main.py -d qq
```

### 依赖项

- `frida>=16.0.0`: 动态二进制插桩框架
- `requests>=2.31.0`: HTTP请求库

### 注意事项

- 必须先启动 QQMusic.exe 客户端
- Windows系统需要管理员权限
- 仅支持Windows平台的QQ音乐客户端
- 解密过程中请勿关闭QQMusic

---

## 声纹识别匹配

### 功能概述

通过计算音频文件的声纹特征，在MusicBrainz数据库中查找匹配的录音信息，无需依赖文件名或现有标签。

### 技术原理

**声纹计算**:
```
音频文件 → fpcalc工具 → Chromaprint指纹 (32位指纹字符串)
```

**匹配流程**:
```
1. 计算音频指纹和时长
2. 查询AcoustID API (api.acoustid.org)
3. 获取MusicBrainz录音ID
4. 从MusicBrainz API获取详细元数据
5. 评分排序返回最佳匹配
```

### 使用方法

#### 基本使用

```python
from Fingerprint.musicbrainz_matcher import FingerprintMatcher

# 初始化匹配器
matcher = FingerprintMatcher()

# 匹配单个文件
result = matcher.match_file('song.mp3')

if result.success:
    print(f"找到 {len(result.recordings)} 个匹配:")
    for recording in result.recordings:
        print(f"  {recording['title']} - {recording['artist']} ({recording['score']:.1f}%)")
else:
    print("未找到匹配")
```

#### 高级用法

```python
# 匹配特定track ID (MusicBrainz ID)
result = matcher.match_recording('track_id_here')

# 格式化显示匹配信息
info = matcher.format_recording_info(recording)
print(info)
```

### API接口

```python
class FingerprintMatcher:
    """MusicBrainz声纹匹配器"""

    def __init__(self, fpcalc_path='fpcalc'):
        """
        初始化匹配器

        Args:
            fpcalc_path: fpcalc可执行文件路径
        """

    def match_file(self, audio_path: str) -> MatchResult:
        """
        通过音频文件匹配MusicBrainz录音

        Args:
            audio_path: 音频文件路径

        Returns:
            MatchResult: 匹配结果对象
                - success: 是否成功
                - recordings: 匹配的录音列表
                - message: 错误消息(如果失败)
        """

    def match_recording(self, track_id: str) -> MatchResult:
        """
        通过MusicBrainz track ID查询录音信息

        Args:
            track_id: MusicBrainz track ID

        Returns:
            MatchResult: 匹配结果对象
        """

    def format_recording_info(self, recording: dict) -> str:
        """
        格式化录音信息为易读字符串

        Args:
            recording: 录音信息字典

        Returns:
            格式化的字符串
        """
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

### 依赖项

- `fpcalc`: Chromaprint指纹计算工具 (需单独安装)
- `requests`: HTTP请求库
- `acoustid`: AcoustID API客户端

### 安装fpcalc

**Windows**:
```bash
# 使用chocolatey
choco install chromaprint

# 或下载预编译二进制: https://acoustid.org/chromaprint
```

**macOS**:
```bash
brew install chromaprint
```

**Linux (Debian/Ubuntu)**:
```bash
sudo apt-get install libchromaprint-tools
```

**Linux (CentOS/RHEL)**:
```bash
sudo yum install chromaprint-tools
```

### API密钥

本项目使用的AcoustID API密钥: `v8pQ6oyB`

**重要**: 此密钥仅供个人学习使用，请勿用于商业用途或滥用API。

### 性能优化

- 缓存指纹计算结果
- 批量处理时重用API连接
- 限制并发请求数量

---

## 音乐标签更新

### 功能概述

音乐标签更新模块采用两级策略自动获取并更新音乐文件的元数据：

1. **声纹匹配 (优先)**: 通过AcoustID API查询MusicBrainz数据库
2. **在线查询 (备选)**: 从QQ音乐或网易云音乐获取元数据

### 标签更新流程

```
开始
    ↓
音频文件
    ↓
声纹匹配 (Fingerprint.musicbrainz_matcher)
    ├── 成功且分数≥50%
    │   ├── 更新标签 (MusicBrainz数据)
    │   ├── 下载封面 (多平台尝试)
    │   └── 结束
    └── 失败或分数<50%
        ↓
    在线查询 (QQ音乐/网易云音乐)
        ├── 找到匹配
        │   ├── 更新标签 (平台数据)
        │   ├── 下载封面
        │   └── 结束
        └── 未找到
            ↓
        检查标签完整性
        └── 记录缺失信息
```

### 模块依赖

```python
# 声纹匹配模块
from Fingerprint.musicbrainz_matcher import FingerprintMatcher

# 音乐平台API
from music_tagger.platforms.qqmusic import QQMusicApi
from music_tagger.platforms.netease import NetEaseMusicClient

# 标签读写模块
from music_tagger.core import MusicTagger
```

### 声纹匹配详细流程

#### 1. 计算音频指纹

```python
import subprocess
import hashlib

def calculate_fingerprint(audio_file):
    """使用fpcalc计算音频指纹"""

    cmd = ['fpcalc', '-json', audio_file]
    result = subprocess.run(cmd, capture_output=True, text=True)

    data = json.loads(result.stdout)
    return {
        'fingerprint': data.get('fingerprint'),
        'duration': data.get('duration')
    }
```

#### 2. 查询AcoustID API

```python
import requests

API_URL = "https://api.acoustid.org/v2/lookup"
API_KEY = "v8pQ6oyB"

def lookup_acoustid(fingerprint, duration):
    """查询AcoustID API"""

    params = {
        'client': API_KEY,
        'format': 'json',
        'meta': 'recordings+releasegroups+compress',
        'duration': int(duration),
        'fingerprint': fingerprint
    }

    response = requests.get(API_URL, params=params)
    return response.json()
```

#### 3. 解析MusicBrainz录音

```python
def parse_recording(recording_data):
    """解析MusicBrainz录音数据"""

    return {
        'id': recording_data.get('id'),
        'title': recording_data.get('title'),
        'artist': format_artist_credit(recording_data.get('artist-credit', [])),
        'album': get_album_name(recording_data),
        'year': get_release_year(recording_data),
        'tracknumber': get_track_number(recording_data),
        'duration': recording_data.get('duration') / 1000  # 转换为秒
    }
```

### 在线平台查询

#### QQ音乐

```python
from music_tagger.platforms.qqmusic import QQMusicApi

api = QQMusicApi()
songs = api.search("歌曲名 歌手名")

if songs:
    song = songs[0]
    print(f"{song['title']} - {song['artist']}")
    print(f"专辑: {song['album']}")
    print(f"年份: {song['year']}")
```

#### 网易云音乐

```python
from music_tagger.platforms.netease import NetEaseMusicClient

client = NetEaseMusicClient()
songs = client.fetch_id3_by_title("歌曲名 歌手名")

if songs:
    song = songs[0]
    print(f"{song['name']} - {song['artist']}")
    print(f"专辑: {song['album']}")
    print(f"年份: {song['year']}")
```

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
    'lyrics': '歌词内容',
    'comment': '备注信息',
    'album_img': 'https://example.com/cover.jpg',  # 封面URL
})

# 支持模板语法
tagger.update_tags({
    'title': '${artist} - ${title}',  # 使用现有标签值
    'filename': '${year} - ${artist} - ${title}'  # 文件名模板
})
```

### 封面下载

```python
def fetch_album_cover(qq_api, netease_api, title, artist, album):
    """从多个平台尝试下载封面"""

    # 尝试QQ音乐
    if qq_api:
        songs = qq_api.search(f"{title} {artist}")
        if songs and songs[0].get('album_img'):
            return songs[0]['album_img']

    # 尝试网易云音乐
    if netease_api:
        songs = netease_api.fetch_id3_by_title(f"{title} {artist}")
        if songs and songs[0].get('album_img'):
            return songs[0]['album_img']

    return None
```

### 配置选项

```python
# main.py 配置

# 声纹匹配阈值 (0-100)
FINGERPRINT_THRESHOLD = 50

# 在线查询优先级
PLATFORM_PRIORITY = ['qq', 'netease']

# 是否自动下载封面
AUTO_DOWNLOAD_COVER = True

# 封面尺寸限制
MAX_COVER_SIZE = 1024 * 1024  # 1MB
```

### 注意事项

1. **声纹匹配准确率**: 受音频质量、时长、数据库覆盖率影响
2. **API限制**: 注意各平台的请求频率限制
3. **网络连接**: 在线查询需要稳定的网络环境
4. **文件权限**: 更新标签前确保有文件写入权限
5. **备份**: 建议在批量更新前备份文件

---

## 文件归档

### 功能概述

按照音乐文件的元数据年份，自动将文件组织到按年份分类的目录结构中。

### 使用方法

```bash
# 运行归档工具
python archive.py
```

### 归档规则

```
输入目录/
    ├── song1.mp3  (年份: 2020)
    ├── song2.flac (年份: 2019)
    └── song3.wav  (无年份)

输出目录/
    ├── 2019/
    │   └── song2.flac
    ├── 2020/
    │   └── song1.mp3
    └── Unknown/
        └── song3.wav
```

### 支持的音频格式

- `.mp3`
- `.flac`
- `.wav`
- `.ape`
- `.ogg`

### 元数据来源

从音乐文件标签中提取年份信息:
- ID3v2: TDRC帧
- FLAC: YEAR标签
- Vorbis: YEAR标签
- APEv2: YEAR标签

---

## 重复检测

### 功能概述

查找具有重复模式的音乐文件。

### 使用方法

```bash
python duplicate.py
```

### 检测规则

- 文件名包含 `(1)`, `(2)`, `(3)` 等数字标记
- 例如: `song.mp3`, `song (1).mp3`, `song (2).mp3`

---

## 歌词管理

### 功能概述

检测和管理 `.lrc` 歌词文件。

### 使用方法

```bash
python lrc.py
```

### 功能

1. **缺失歌词**: 找出没有对应歌词文件的音频文件
2. **孤立歌词**: 找出没有对应音频文件的歌词文件
3. **生成报告**: 输出检测结果

---

## 附录

### 常见问题

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

### 性能建议

1. **批量处理**: 尽量批量处理文件，减少重复初始化开销
2. **并发控制**: 限制并发请求数，避免被API封禁
3. **缓存机制**: 使用缓存避免重复计算和请求
4. **进度显示**: 长时间操作显示进度条

### 扩展阅读

- [MusicBrainz API文档](https://musicbrainz.org/doc/MusicBrainz_API)
- [AcoustID API文档](https://acoustid.org/webservice)
- [Frida官方文档](https://frida.re/docs/)
- [mutagen文档](https://mutagen.readthedocs.io/)
