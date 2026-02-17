# Music Helper - 音乐文件管理工具集

一个功能完善的 Python 音乐文件管理工具集，包含解密、标签管理、归档、重复检测等多个实用功能。

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
│   ├── hook_qq_music.js    # Frida注入脚本
│   ├── qq.bat             # Windows快捷启动
│   └── um.bat             # Windows快捷启动
├── Fingerprint/            # 声纹识别模块
│   └── musicbrainz_matcher.py  # MusicBrainz声纹匹配
├── music_tagger/          # 音乐标签管理模块
│   ├── __init__.py         # 包入口
│   ├── core.py            # 核心标签读写
│   ├── matcher.py         # 智能匹配算法
│   ├── platforms/         # 音乐平台API
│   │   ├── __init__.py
│   │   ├── netease.py    # 网易云音乐
│   │   ├── qqmusic.py    # QQ音乐
│   │   ├── migu.py       # 咪咕音乐
│   │   ├── kugou.py      # 酷狗音乐
│   │   ├── kuwo.py       # 酷我音乐
│   │   └── acoustid.py   # AcoustID声纹识别
│   └── crypto/           # 加密模块
│       └── encrypt.py     # AES/RSA加密
└── Doc/                  # 文档目录
    ├── README.md           # 本文档
    ├── feature.md          # 功能详细说明
    ├── FINGERPRINT_MATCHER_README.md  # 声纹匹配文档
    ├── TAG_UPDATE_README.md          # 标签更新文档
    ├── QUICKSTART.md       # 快速开始指南
    └── PROJECT_STRUCTURE.md # 旧项目结构(已废弃)
```

## 功能模块

### 1. QQ音乐解密 (Decrypto)

**功能**: 解密QQ音乐VIP歌曲的加密音频文件

**使用方法**:
```bash
# Windows
cd Decrypto
qq.bat

# 命令行
python main.py -i <input_dir> -o <output_dir>
```

**技术**:
- 使用Frida动态注入Hook脚本到QQMusic.exe进程
- 解密 `.mflac` 和 `.mgg` 加密格式
- 自动识别和转换为标准 `.flac` 和 `.ogg` 格式

**依赖**:
- `frida`: 动态二进制插桩框架
- `requests`: HTTP请求库

**模块**:
- `qq.py`: 主解密逻辑
- `source_finder.py`: 歌曲信息查找
- `hook_qq_music.js`: Frida注入脚本

### 2. 声纹识别 (Fingerprint)

**功能**: 通过音频指纹在MusicBrainz数据库中查找音乐元数据

**使用方法**:
```python
from Fingerprint.musicbrainz_matcher import FingerprintMatcher

matcher = FingerprintMatcher()
result = matcher.match_file('song.mp3')

if result.success:
    for recording in result.recordings:
        print(f"{recording['title']} - {recording['artist']}")
```

**API**:
```python
class FingerprintMatcher:
    def match_file(self, audio_path: str) -> MatchResult
    def match_recording(self, track_id: str) -> MatchResult
    def format_recording_info(self, recording: dict) -> str
```

**依赖**:
- `fpcalc`: Chromaprint声纹计算工具(需单独安装)
- `requests`: API请求
- `acoustid`: AcoustID API客户端

### 3. 音乐标签管理 (music_tagger)

**功能**: 读写和更新音乐文件的元数据标签

#### 3.1 核心标签读写 (core.py)

**类**: `MusicTagger`

```python
from music_tagger.core import MusicTagger

tagger = MusicTagger('song.mp3')
print(tagger.title)      # 歌曲标题
print(tagger.artist)     # 艺术家
print(tagger.album)      # 专辑

# 更新标签
tagger.update_tags({
    'title': '新标题',
    'artist': '新艺术家',
    'year': '2024'
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
class PlatformClient:
    def fetch_id3_by_title(self, title: str) -> list[dict]
    def fetch_lyric(self, song_id: str) -> str
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

**公钥来源**: 从网易云音乐 core.js 中提取(详见 NETEASE_KEY_EXTRACTION.md)

### 4. 主程序功能 (main.py)

**功能整合**:
1. QQ音乐VIP文件解密
2. 声纹匹配更新标签(优先)
3. 在线音乐平台查询(备选)
4. 文件归档整理

**标签更新策略**:
```
声纹匹配 (MusicBrainz)
    ↓ 成功?
    ├── 是 → 更新标签 → 下载封面
    └── 否 ↓
在线查询 (QQ音乐/网易云音乐)
    ↓ 找到?
    ├── 是 → 更新标签 → 下载封面
    └── 否 → 跳过
```

**依赖检查**:
```python
fingerprint_matcher_available = False  # Fingerprint.musicbrainz_matcher
music_tagger_available = False       # music_tagger.core
qq_music_available = False           # Decrypto.qq
```

### 5. 归档工具 (archive.py)

**功能**: 按年份组织音乐文件目录结构

```bash
python archive.py
```

**功能**:
- 从音乐文件元数据提取年份
- 按年份创建子目录
- 移动文件到对应年份目录
- 生成归档日志

### 6. 重复检测 (duplicate.py)

**功能**: 查找重复的音乐文件

```bash
python duplicate.py
```

**检测规则**:
- 文件名包含 `(1)`, `(2)`, `(3)` 等标记
- 支持自定义匹配模式

### 7. 歌词管理 (lrc.py)

**功能**: 查找缺失或孤立的 `.lrc` 歌词文件

```bash
python lrc.py
```

**功能**:
- 检测没有歌词的音频文件
- 检测没有对应音频的歌词文件
- 生成报告

## 安装依赖

```bash
# 基础依赖
pip install -r requirements.txt

# QQ音乐解密
pip install frida requests

# 声纹识别
pip install acoustid

# 音乐标签管理
pip install music-tag mutagen

# 网易云加密
pip install pycryptodome
```

## 配置

主程序在 `main.py` 中配置目录:

```python
# 主目录
MAIN_DIR = r'D:\music'

# 网易云音乐目录
NETEASE_DIR = r'G:\Neteasymusic'
NETEASE_VIP_DIR = r'G:\Neteasymusic\VipSOngsDownload'
NETEASE_TMP_DIR = r'G:\NeTmp'
TEMP_COMPLETED_DIR = r'G:\Temp'

# QQ音乐目录
QQ_DIR = r'G:\QQMusic'
QQ_VIP_DIR = r'G:\QQMusic\VipSOngsDownload'
QQ_TMP_DIR = r'G:\QQTmp'

# 外部程序路径
UM_EXE = r'um.exe'
SOUNDALIKE_EXE = r'soundalike.exe'
```

**重要**: 根据实际环境修改这些路径配置!

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
from Fingerprint.musicbrainz_matcher import FingerprintMatcher

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

## 模块化设计

### 导入路径规则

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

### 模块间依赖关系

```
main.py
    ├── Decrypto (QQ解密)
    ├── Fingerprint (声纹匹配)
    └── music_tagger (标签管理)
            ├── platforms (音乐平台API)
            │   └── crypto (加密)
            ├── matcher (智能匹配)
            └── core (标签读写)
```

## 注意事项

### 1. QQ音乐解密

- 需要先启动QQMusic.exe进程
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
