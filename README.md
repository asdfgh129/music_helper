# Music Helper - 音乐文件管理工具集

一个功能完善的 Python 音乐文件管理工具集，包含解密、标签管理、归档、重复检测等多个实用功能。

## 功能特性

### 核心功能
- 🔓 **QQ音乐解密**: 使用Frida技术解密VIP加密音频文件
- 🎵 **声纹识别**: 通过AcoustID API在MusicBrainz数据库中匹配音乐
- 🏷️ **标签管理**: 读写和更新音乐文件的元数据标签
- 📦 **归档整理**: 按年份自动组织音乐文件目录
- 🔍 **重复检测**: 查找重复的音乐文件
- 📝 **歌词管理**: 检测缺失或孤立的歌词文件

### 支持的音乐平台
| 平台 | 搜索 | 歌词 | 封面 | 加密 |
|------|------|------|------|------|
| 网易云音乐 | ✅ | ✅ | ✅ | AES+RSA |
| QQ音乐 | ✅ | ❌ | ✅ | 无 |
| 咪咕音乐 | ✅ | ✅ | ✅ | 无 |
| 酷狗音乐 | ✅ | ✅ | ✅ | MD5签名 |
| 酷我音乐 | ✅ | ✅ | ✅ | 无 |
| MusicBrainz | ✅ | ❌ | ✅ | 声纹匹配 |

### 支持的音频格式
- MP3 (.mp3)
- FLAC (.flac)
- OGG Vorbis (.ogg)
- WAV (.wav)
- APE (.ape)

## 快速开始

### 1. 安装依赖

```bash
# 基础依赖
pip install -r requirements.txt

# QQ音乐解密
pip install frida requests

# 声纹识别
pip install acoustid
# 安装fpcalc工具 (请参考 Doc/README.md)

# 音乐标签管理
pip install music-tag mutagen

# 网易云加密
pip install pycryptodome
```

### 2. 配置路径

编辑 `main.py` 中的目录配置:

```python
# 主目录
MAIN_DIR = r'D:\music'

# QQ音乐目录
QQ_DIR = r'G:\QQMusic'
QQ_VIP_DIR = r'G:\QQMusic\VipSOngsDownload'
QQ_TMP_DIR = r'G:\QQTmp'

# 网易云音乐目录
NETEASE_DIR = r'G:\Neteasymusic'
NETEASE_VIP_DIR = r'G:\Neteasymusic\VipSOngsDownload'
```

**重要**: 根据您的实际环境修改这些路径!

### 3. 基本使用

```bash
# 运行主程序
python main.py

# 或使用独立工具
python archive.py        # 文件归档
python duplicate.py      # 重复检测
python lrc.py           # 歌词管理
```

## 模块说明

### 1. QQ音乐解密 (Decrypto/)

解密QQ音乐VIP下载的加密音频文件 (.mflac, .mgg)。

**使用方法**:
```bash
# Windows快捷启动
Decrypto\qq.bat

# 命令行
python Decrypto/qq.py -i <input_dir> -o <output_dir>
```

**技术原理**: 使用Frida动态注入Hook脚本到QQMusic.exe进程

**依赖**: `frida`, `requests`

### 2. 声纹识别 (Fingerprint/)

通过音频指纹在MusicBrainz数据库中查找音乐元数据。

**使用方法**:
```python
from Fingerprint.musicbrainz_matcher import FingerprintMatcher

matcher = FingerprintMatcher()
result = matcher.match_file('song.mp3')

if result.success:
    for recording in result.recordings:
        print(f"{recording['title']} - {recording['artist']}")
```

**依赖**: `fpcalc`, `acoustid`, `requests`

### 3. 音乐标签管理 (music_tagger/)

#### 3.1 核心标签读写 (core.py)

```python
from music_tagger.core import MusicTagger

tagger = MusicTagger('song.mp3')
print(f"标题: {tagger.title}")
print(f"艺术家: {tagger.artist}")
print(f"专辑: {tagger.album}")

# 更新标签
tagger.update_tags({
    'title': '新标题',
    'artist': '新艺术家',
    'year': '2024'
})
```

#### 3.2 智能匹配 (matcher.py)

并行搜索多个音乐平台，智能评分排序。

```python
from music_tagger.matcher import SmartTagClient

client = SmartTagClient()
results = client.fetch_id3_by_title({
    'title': '歌曲名',
    'artist': '艺术家',
    'full_path': '文件路径'
})
```

#### 3.3 音乐平台API (platforms/)

统一接口:
```python
# 网易云音乐
from music_tagger.platforms.netease import NetEaseMusicClient
client = NetEaseMusicClient()
songs = client.fetch_id3_by_title("歌曲名")

# QQ音乐
from music_tagger.platforms.qqmusic import QQMusicApi
api = QQMusicApi()
songs = api.search("歌曲名")
```

#### 3.4 加密模块 (crypto/)

用于网易云音乐API请求加密:

```python
from music_tagger.crypto import weEncrypt, linuxEncrypt

# AES+RSA混合加密
data = weEncrypt({"s": "搜索关键词"})

# AES-ECB加密
data = linuxEncrypt({"id": "123"})
```

### 4. 主程序 (main.py)

整合所有功能，提供统一的命令行接口。

**标签更新策略**:
```
1. 声纹匹配 (MusicBrainz)
   └─ 成功? → 更新标签 → 下载封面

2. 在线查询 (QQ音乐/网易云音乐)
   └─ 找到? → 更新标签 → 下载封面
```

**依赖检查**: 自动检测各模块是否可用，跳过不可用功能。

### 5. 其他工具

- **archive.py**: 按年份组织音乐文件目录
- **duplicate.py**: 查找重复的音乐文件
- **lrc.py**: 检测缺失或孤立的歌词文件

## 项目结构

```
music_helper/
├── main.py                 # 主程序入口
├── archive.py              # 音乐文件归档工具
├── duplicate.py             # 重复文件检测工具
├── lrc.py                  # 歌词文件管理工具
├── requirements.txt          # 项目依赖
├── Decrypto/               # 解密模块
│   ├── qq.py              # QQ音乐解密(Frida)
│   ├── source_finder.py     # 歌曲URL查找
│   └── hook_qq_music.js    # Frida注入脚本
├── Fingerprint/            # 声纹识别模块
│   └── musicbrainz_matcher.py  # MusicBrainz声纹匹配
├── music_tagger/          # 音乐标签管理模块
│   ├── __init__.py
│   ├── core.py            # 核心标签读写
│   ├── matcher.py         # 智能匹配算法
│   ├── platforms/         # 音乐平台API
│   │   ├── netease.py
│   │   ├── qqmusic.py
│   │   ├── migu.py
│   │   ├── kugou.py
│   │   ├── kuwo.py
│   │   └── acoustid.py
│   └── crypto/           # 加密模块
│       └── encrypt.py
└── Doc/                  # 文档目录
    ├── README.md           # 主文档
    ├── FEATURES.md         # 功能详细说明
    ├── FINGERPRINT_MATCHER_README.md
    ├── TAG_UPDATE_README.md
    └── QUICKSTART.md
```

## 模块化导入

```
Decrypto模块:
    from Decrypto.qq import run_decrypt, guess_song_url
    from Decrypto.source_finder import guess_song_url

Fingerprint模块:
    from Fingerprint.musicbrainz_matcher import FingerprintMatcher, format_recording_info

music_tagger模块:
    from music_tagger.core import MusicTagger
    from music_tagger.matcher import SmartTagClient, match_score, match_artist
    from music_tagger.platforms import MusicResource
    from music_tagger.platforms.netease import NetEaseMusicClient
    from music_tagger.platforms.qqmusic import QQMusicApi
    from music_tagger.crypto import weEncrypt, linuxEncrypt
```

## 文档

- **[Doc/README.md](Doc/README.md)** - 详细项目结构和API文档
- **[Doc/FEATURES.md](Doc/FEATURES.md)** - 功能详细说明
- **[Doc/FINGERPRINT_MATCHER_README.md](Doc/FINGERPRINT_MATCHER_README.md)** - 声纹匹配文档
- **[Doc/TAG_UPDATE_README.md](Doc/TAG_UPDATE_README.md)** - 标签更新文档
- **[Doc/QUICKSTART.md](Doc/QUICKSTART.md)** - 快速开始指南

## 注意事项

1. **QQ音乐解密**: 需要先启动QQMusic.exe进程，需管理员/root权限
2. **声纹识别**: 需要安装fpcalc工具，API有频率限制
3. **音乐标签**: 更新前建议备份文件
4. **平台API**: 注意控制请求频率，避免被封
5. **编码问题**: 统一使用UTF-8编码
6. **Python版本**: 需要Python 3.7+

## 扩展开发

### 添加新的音乐平台

1. 在 `music_tagger/platforms/` 创建新文件
2. 实现 `fetch_id3_by_title` 和 `fetch_lyric` 方法
3. 在 `platforms/__init__.py` 中注册

### 添加新的加密算法

1. 在 `music_tagger/crypto/encrypt.py` 添加函数
2. 遵循命名规范: `xxxEncrypt`
3. 在 `crypto/__init__.py` 中导出

## 许可证

本项目仅供学习和个人使用。使用音乐平台API请遵守相应平台的服务条款。

## 更新日志

### v2.0.0 (当前版本)
- 重构项目结构，模块化设计
- 集成声纹匹配功能
- 优化QQ音乐解密为直接模块导入
- 添加多平台标签更新支持
- 完善文档体系

### v1.0.0
- 初始版本
- 基础QQ音乐解密
- 简单归档功能
