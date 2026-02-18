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
# 安装fpcalc工具 (详见下方 fpcalc 安装说明)

# 音乐标签管理
pip install music-tag mutagen

# 网易云加密
pip install pycryptodome
```

### 2. 配置路径

编辑 `config.py` 中的目录配置:

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
NETEASE_TMP_DIR = r'G:\NeTmp'
TEMP_COMPLETED_DIR = r'G:\Temp'
TEMP_MOVE_DIR = r'G:\Tmp'
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

## 项目结构

```
music_helper/
├── main.py                 # 主程序入口
├── config.py              # 配置文件
├── utils.py               # 工具函数
├── metadata.py            # 元数据读写
├── soundalike.py          # 声纹去重
├── tag_fetcher.py         # 标签获取
├── vip_decrypt.py         # VIP解密
├── tag_updater.py         # 标签更新
├── file_operations.py      # 文件操作
├── archive.py             # 音乐文件归档工具
├── duplicate.py           # 重复文件检测工具
├── lrc.py                # 歌词文件管理工具
├── requirements.txt        # 项目依赖
├── Decrypto/             # QQ音乐解密模块
│   ├── __init__.py
│   ├── qq.py            # QQ音乐解密(Frida)
│   └── source_finder.py  # 歌曲URL查找
├── Fingerprint/          # 声纹识别模块
│   ├── __init__.py
│   └── musicbrainz_matcher.py  # MusicBrainz声纹匹配
├── music_tagger/         # 音乐标签管理模块
│   ├── __init__.py
│   ├── core.py          # 核心标签读写
│   ├── matcher.py       # 智能匹配算法
│   ├── encrypt.py      # 加密模块
│   └── platforms/      # 音乐平台API
│       ├── __init__.py
│       ├── netease.py   # 网易云音乐
│       ├── qqmusic.py   # QQ音乐
│       ├── migu.py      # 咪咕音乐
│       ├── kugou.py     # 酷狗音乐
│       ├── kuwo.py      # 酷我音乐
│       └── acoustid.py  # AcoustID声纹识别
├── Fingerprint/         # 外部工具目录
│   └── soundalike.exe   # 声纹对比工具
└── Doc/                 # 文档目录
    └── FEATURES.md      # 功能详细说明
```

## 模块说明

### 1. QQ音乐解密 (Decrypto/)

**功能**: 解密QQ音乐VIP下载的加密音频文件 (.mflac, .mgg)

**使用方法**:
```bash
# Windows快捷启动
Decrypto\qq.bat

# 命令行 - 列出默认目录歌曲
python Decrypto/qq.py -l

# 命令行 - 解密指定目录
python Decrypto/qq.py -i <input_dir> -o <output_dir>
```

**模块化导入**:
```python
from Decrypto import run_decrypt, list_download_songs, guess_song_url

# 解密文件
run_decrypt(
    input_dir="G:\\QQMusic\\VipSOngsDownload",
    output_dir="G:\\QQMusic\\Decrypted"
)

# 列出默认下载目录歌曲
list_download_songs()

# 猜测歌曲URL
url = guess_song_url("周杰伦 - 晴.flac")
```

**技术原理**:
- 使用Frida动态注入Hook脚本到QQMusic.exe进程
- 解密 `.mflac` 和 `.mgg` 加密格式
- 自动识别和转换为标准 `.flac` 和 `.ogg` 格式
- 自动查找和记录歌曲来源链接

**依赖**:
- `frida`: 动态二进制插桩框架
- `requests`: HTTP请求库

**注意事项**:
- 必须先启动QQMusic.exe进程
- Windows系统需要管理员权限
- 仅支持Windows平台的QQ音乐客户端

### 2. 声纹识别 (Fingerprint/)

**功能**: 通过音频指纹在MusicBrainz数据库中查找音乐元数据

**模块化导入**:
```python
from Fingerprint import FingerprintMatcher, format_recording_info

matcher = FingerprintMatcher()
result = matcher.match_file('song.mp3')

if result.success:
    for recording in result.recordings:
        print(f"{recording['title']} - {recording['artist']}")

# 格式化录音信息
info = format_recording_info(recording)
print(info)
```

**API**:
```python
class FingerprintMatcher:
    def match_file(self, audio_path: str) -> MatchResult:
        """通过音频文件匹配MusicBrainz录音"""

    def match_recording(self, track_id: str) -> MatchResult:
        """通过MusicBrainz track ID查询录音信息"""

    def format_recording_info(self, recording: dict) -> str:
        """格式化录音信息为易读字符串"""
```

**返回数据格式**:
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

**依赖**:
- `fpcalc`: Chromaprint声纹计算工具(需单独安装)
- `requests`: API请求

**安装fpcalc**:

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

**API密钥**:
本项目使用的AcoustID API密钥: `v8pQ6oyB`

**注意**: 此密钥仅供个人学习使用，请勿用于商业用途或滥用API。

### 3. 网易云解密 (vip_decrypt.py)

**功能**: 解密网易云音乐VIP下载的加密音频文件

**模块化导入**:
```python
from vip_decrypt import decrypt_netease_vip

# 解密网易云VIP文件
count = decrypt_netease_vip(month=None)
print(f"解密了 {count} 个文件")
```

**处理流程**:
1. 扫描网易云VIP目录中的音乐文件
2. 将文件移动到临时目录
3. 运行um.exe进行解密
4. 解密后的文件输出到完成目录

**配置** (在 `config.py` 中):
```python
# 网易云音乐目录
NETEASE_VIP_DIR = r'G:\Neteasemusic\VipSOngsDownload'
NETEASE_TMP_DIR = r'G:\NeTmp'
TEMP_COMPLETED_DIR = r'G:\Temp'
UM_EXE = r'um.exe'  # 解密工具路径
```

**依赖**:
- `um.exe`: 网易云解密工具（需单独配置）
- `pycryptodome`: 加密算法库

**注意事项**:
- 需要配置um.exe的路径
- 确保有足够的临时存储空间

### 4. 声纹去重 (soundalike.py)

**功能**: 使用 Soundalike 工具进行声纹识别，自动检测和移动重复的音乐文件

**模块化导入**:
```python
from soundalike import run_soundalike_fingerprinting, check_database_consistency

# 运行声纹识别去重
success = run_soundalike_fingerprinting()
if success:
    print("声纹去重完成")
else:
    print("声纹去重失败")

# 检查数据库一致性
success = check_database_consistency()
```

**工作原理**:
1. 扫描主目录中的所有音乐文件
2. 使用soundalike.exe计算声纹
3. 对比声纹特征，识别重复文件
4. 将重复文件移动到TEMP_MOVE_DIR（交互式确认）
5. 使用TEMP_COMPLETED_DIR作为临时工作目录

**配置** (在 `config.py` 中):
```python
# 主目录（扫描目标）
MAIN_DIR = r'D:\music'

# 临时目录（工作目录）
TEMP_COMPLETED_DIR = r'G:\Temp'

# 重复文件移动目录（交互式确认）
TEMP_MOVE_DIR = r'G:\Move'
```

**依赖**:
- `soundalike.exe`: 声纹对比工具

**返回值**:
- `True`: 声纹识别成功完成
- `False`: 声纹识别失败

**注意事项**:
- 必须确保 `soundalike.exe` 在系统PATH中或放在项目根目录
- 声纹识别需要一定时间，取决于文件数量和大小
- 交互模式下需要手动确认文件移动操作
- 建议在操作前备份重要文件

### 5. 音乐标签管理 (music_tagger/)

#### 3.1 核心标签读写 (core.py)

**类**: `MusicTagger`

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

# 支持模板语法
tagger.update_tags({
    'title': '${artist} - ${title}',  # 使用现有标签值
    'filename': '${year} - ${artist} - ${title}'  # 文件名模板
})
```

**支持的标签字段**:
- title: 歌曲标题
- artist: 艺术家
- album: 专辑
- year: 年份
- genre: 流派
- tracknumber: 音轨号
- discnumber: 碟片号
- lyrics: 歌词
- comment: 评论
- artwork: 封面图片
- album_img: 封面URL(会自动下载)

#### 3.2 智能匹配 (matcher.py)

**类**: `SmartTagClient`

并行搜索多个音乐平台，智能评分排序返回最佳匹配。

```python
from music_tagger.matcher import SmartTagClient

client = SmartTagClient()
results = client.fetch_id3_by_title({
    'title': '歌曲名',
    'artist': '艺术家',
    'full_path': '文件路径'
})

for song in results:
    print(f"{song['name']} - {song['artist']}")
```

**评分算法**:
- 标题匹配度: 2(完全匹配) | 1(包含匹配) | 0(不匹配)
- 艺术家匹配度: 相同算法
- 支持繁简体中文转换

#### 3.3 音乐平台API (platforms/)

支持以下音乐平台:

| 平台 | 模块 | 特殊要求 |
|------|--------|---------|
| 网易云音乐 | `netease.py` | AES+RSA加密 |
| QQ音乐 | `qqmusic.py` | 无 |
| 咪咕音乐 | `migu.py` | 无 |
| 酷狗音乐 | `kugou.py` | MD5签名 |
| 酷我音乐 | `kuwo.py` | 无 |
| AcoustID | `acoustid.py` | 声纹识别 |

**统一接口**:
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

**返回格式**:
```python
{
    "id": "歌曲ID",
    "name": "歌曲标题",
    "artist": "艺术家",
    "album": "专辑",
    "year": "年份",
    "album_img": "封面URL",
    "lyrics": "歌词",
}
```

#### 3.4 加密模块 (crypto/)

用于网易云音乐API请求加密:

```python
from music_tagger.crypto import weEncrypt, linuxEncrypt, eEncrypt

# 网易云网页API加密
data = weEncrypt({"s": "搜索关键词"})

# 网易云Linux API加密
data = linuxEncrypt({"id": "123"})

# 网易云E-API加密
data = eEncrypt("url", "params")
```

**加密方式**:
- `weEncrypt`: AES + RSA混合加密(2048位)
- `linuxEncrypt`: AES-ECB加密
- `eEncrypt`: MD5 + AES加密

**公钥来源**: 从网易云音乐 core.js 中提取(详见 Doc/EXTRACTION_SUMMARY.md)

### 4. 主程序 (main.py)

整合所有功能，提供统一的命令行接口。

**标签更新策略**:
```
1. 声纹匹配 (MusicBrainz)
   └─ 成功且分数≥50%? → 更新标签 → 下载封面

2. 在线查询 (QQ音乐/网易云音乐)
   └─ 找到? → 更新标签 → 下载封面

3. 检查标签完整性
   └─ 记录缺失信息
```

**配置选项**:
```python
# 声纹匹配阈值 (0-100)
FINGERPRINT_THRESHOLD = 50

# 在线查询优先级
PLATFORM_PRIORITY = ['qq', 'netease']

# 是否自动下载封面
AUTO_DOWNLOAD_COVER = True

# 封面尺寸限制
MAX_COVER_SIZE = 1024 * 1024  # 1MB
```

**依赖检查**: 自动检测各模块是否可用，跳过不可用功能。

### 5. 其他工具

#### archive.py - 文件归档

**功能**: 按年份组织音乐文件目录结构

```bash
python archive.py
```

**归档规则**:
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

**功能**:
- 从音乐文件元数据提取年份
- 按年份创建子目录
- 移动文件到对应年份目录
- 生成归档日志

#### duplicate.py - 重复检测

**功能**: 查找重复的音乐文件

```bash
python duplicate.py
```

**检测规则**:
- 文件名包含 `(1)`, `(2)`, `(3)` 等数字标记
- 例如: `song.mp3`, `song (1).mp3`, `song (2).mp3`

#### lrc.py - 歌词管理

**功能**: 查找缺失或孤立的 `.lrc` 歌词文件

```bash
python lrc.py
```

**功能**:
- 检测没有歌词的音频文件
- 检测没有对应音频的歌词文件
- 生成报告

## 模块化导入

```
Decrypto模块:
    from Decrypto import run_decrypt, guess_song_url, list_download_songs, parse_filename_to_artist_title

Fingerprint模块:
    from Fingerprint import FingerprintMatcher, format_recording_info

核心模块（根目录）:
    # 配置
    from config import MAIN_DIR, QQ_DIR, QQ_VIP_DIR, NETEASE_VIP_DIR, TEMP_COMPLETED_DIR

    # 工具函数
    from utils import setup_logging, create_operation_log, get_current_month, main_logger

    # 元数据操作
    from metadata import get_music_metadata, set_music_metadata

    # VIP解密
    from vip_decrypt import decrypt_netease_vip, decrypt_qq_vip

    # 声纹去重
    from soundalike import run_soundalike_fingerprinting, check_database_consistency

    # 标签获取
    from tag_fetcher import parse_musicbrainz_recording, fetch_qq_music_tags, fetch_netease_tags, fetch_album_cover

    # 标签更新
    from tag_updater import update_tags_from_fingerprint

    # 文件操作
    from file_operations import scan_music_files, move_files_to_temp, organize_by_year, check_filename_consistency

music_tagger模块:
    from music_tagger.core import MusicTagger
    from music_tagger.matcher import SmartTagClient, match_score, match_artist
    from music_tagger.platforms import MusicResource
    from music_tagger.platforms.netease import NetEaseMusicClient
    from music_tagger.platforms.qqmusic import QQMusicApi
    from music_tagger.crypto import weEncrypt, linuxEncrypt
```

## 模块依赖关系

```
main.py
    ├── config.py (配置)
    ├── utils.py (工具函数)
    ├── metadata.py (元数据读写)
    ├── soundalike.py (声纹去重)
    ├── tag_fetcher.py (标签获取)
    ├── vip_decrypt.py (VIP解密)
    ├── tag_updater.py (标签更新)
    ├── file_operations.py (文件操作)
    ├── Decrypto (QQ解密)
    ├── Fingerprint (声纹匹配)
    └── music_tagger (标签管理)
            ├── platforms (音乐平台API)
            ├── encrypt (加密)
            ├── matcher (智能匹配)
            └── core (标签读写)
```

## 使用示例

### 示例1: 解密QQ音乐VIP歌曲

```bash
# Windows: 直接运行bat文件
Decrypto\qq.bat

# 手动指定目录
python main.py -d qq -i G:\QQMusic\VipSOngsDownload -o G:\QQMusic\Decrypted
```

### 示例2: 智能更新音乐标签

```python
from music_tagger.core import MusicTagger
from music_tagger.matcher import SmartTagClient

# 读取标签
tagger = MusicTagger('song.mp3')
print(f"当前标签: {tagger.artist} - {tagger.title}")

# 在线查询
client = SmartTagClient()
results = client.fetch_id3_by_title(tagger.to_dict())

if results:
    # 更新最佳匹配
    tagger.update_tags(results[0])
    print(f"已更新标签: {tagger.artist} - {tagger.title}")
```

### 示例3: 声纹匹配

```python
from Fingerprint import FingerprintMatcher

matcher = FingerprintMatcher()
result = matcher.match_file('unknown_song.mp3')

if result.success:
    recording = result.recordings[0]
    print(f"匹配成功!")
    print(f"歌曲: {recording['title']}")
    print(f"艺术家: {recording['artist']}")
    print(f"专辑: {recording['album']}")
    print(f"年份: {recording['year']}")
```

## 注意事项

### 1. QQ音乐解密
- 必须先启动QQMusic.exe进程
- Frida需要管理员/root权限
- 仅支持Windows平台的QQ音乐客户端

### 2. 声纹识别
- 需要安装 `fpcalc` 命令行工具
- AcoustID API有请求频率限制
- 指纹匹配准确率受音频质量影响

### 3. 音乐标签
- `music_tag` 库需要正确安装
- 更新标签前建议备份文件
- 封面下载需要网络连接

### 4. 平台API
- 网易云需要正确的加密公钥
- 注意控制请求频率避免被封
- API接口可能随时变化

### 5. 编码问题
- 统一使用 UTF-8 编码
- 文件名建议避免特殊字符
- 歌词文件使用 `.lrc` 扩展名

## 扩展开发

### 添加新的音乐平台

1. 在 `music_tagger/platforms/` 创建新文件
2. 实现 `fetch_id3_by_title` 和 `fetch_lyric` 方法
3. 在 `platforms/__init__.py` 中注册

### 添加新的加密算法

1. 在 `music_tagger/crypto/encrypt.py` 添加函数
2. 遵循命名规范: `xxxEncrypt`
3. 在 `crypto/__init__.py` 中导出

## 故障排除

### 常见问题

**Q: QQ音乐解密失败**
A: 检查QQMusic.exe是否运行，Frida是否正确安装

**Q: 声纹匹配无结果**
A: 确认fpcalc已安装，音频质量是否良好

**Q: 标签更新无效**
A: 检查文件权限，music_tag库是否正确安装

**Q: 网易云API请求失败**
A: 检查加密公钥是否正确，网络连接是否正常

## 文档

- **[Doc/FEATURES.md](Doc/FEATURES.md)** - 功能详细说明
- **[Doc/FINGERPRINT_MATCHER_README.md](Doc/FINGERPRINT_MATCHER_README.md)** - 声纹匹配详细文档
- **[Doc/TAG_UPDATE_README.md](Doc/TAG_UPDATE_README.md)** - 标签更新详细文档
- **[Doc/QUICKSTART.md](Doc/QUICKSTART.md)** - 快速开始指南
- **[Doc/EXTRACTION_SUMMARY.md](Doc/EXTRACTION_SUMMARY.md)** - 公钥提取总结

## 许可证

本项目仅供学习和个人使用。使用音乐平台API请遵守相应平台的服务条款。

## 更新日志

### v2.1.0 (当前版本)
- 添加 Decrypto 和 Fingerprint 模块的 `__init__.py` 文件
- 优化模块导入路径，支持简洁导入方式
- 合并文档，统一在根目录 README.md

### v2.0.0
- 重构项目结构，模块化设计
- 集成声纹匹配功能
- 优化QQ音乐解密为直接模块导入
- 添加多平台标签更新支持
- 完善文档体系

### v1.0.0
- 初始版本
- 基础QQ音乐解密
- 简单归档功能
