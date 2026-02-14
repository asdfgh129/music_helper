# Music Tagger - 音乐文件标签管理工具

独立的音乐文件标签管理工具，用于查询、匹配、写入音乐文件的标签信息。

## 功能特性

- ✅ 读取音乐文件ID3标签（支持 MP3, FLAC, M4A, OGG 等多种格式）
- ✅ 在线搜索并匹配音乐标签（网易云音乐、QQ音乐、咪咕音乐、酷狗音乐、酷我音乐）
- ✅ 智能匹配算法（多维度评分、繁简转换、艺术家匹配）
- ✅ 批量处理音乐文件
- ✅ 支持歌词和封面图片下载
- ✅ 模板语法支持（${title}、${artist}等变量替换）
- ✅ 声纹识别（Acoustid）
- ✅ 文件重命名功能

## 依赖安装

```bash
pip install -r requirements.txt
```

## 使用示例

### 1. 查看音乐文件标签信息

```python
from music_tagger import MusicTagger

# 读取音乐文件
tagger = MusicTagger("song.mp3")

# 查看所有标签
info = tagger.to_dict()
print(info)

# 访问单个标签
print(f"标题: {tagger.title}")
print(f"艺术家: {tagger.artist}")
print(f"专辑: {tagger.album}")
```

### 2. 在线搜索音乐标签

```python
from music_tagger import MusicResource

# 从网易云音乐搜索
songs = MusicResource("netease").fetch_id3_by_title("告白气球")
for song in songs:
    print(f"{song['name']} - {song['artist']} - {song['album']}")

# 从QQ音乐搜索
songs = MusicResource("qmusic").fetch_id3_by_title("告白气球")
```

### 3. 智能匹配标签

```python
from music_tagger import SmartTagClient

# 智能匹配（并行搜索多个平台）
client = SmartTagClient()
results = client.fetch_id3_by_title({
    "title": "告白气球",
    "full_path": "/path/to/song.mp3"
})

# results 已按匹配度排序
for song in results:
    print(f"得分: {song['score']}, 歌曲: {song['name']} - {song['artist']}")
```

### 4. 批量自动匹配

```python
from music_tagger import auto_tag

# 批量匹配文件夹中的音乐文件
results = auto_tag(
    music_folder="/path/to/music",
    source_list=["qmusic", "netease", "migu", "kugou"],
    select_mode="strict"  # strict | simple
)

for result in results:
    print(f"{result['file']}: {result['status']}")
```

### 5. 更新音乐文件标签

```python
from music_tagger import MusicTagger

# 打开音乐文件
tagger = MusicTagger("song.mp3")

# 更新标签
tagger.update_tags({
    "title": "新标题",
    "artist": "周杰伦",
    "album": "周杰伦的床边故事",
    "year": "2016",
    "genre": "Pop",
    "lyrics": "歌词内容...",
    "album_img": "http://example.com/cover.jpg"
})

# 保存
tagger.save()
```

### 6. 批量更新标签

```python
from music_tagger import batch_update_tags

# 批量更新多个文件
batch_update_tags([
    {
        "file_full_path": "/path/to/song1.mp3",
        "title": "歌曲1",
        "artist": "艺术家1",
        "album": "专辑1"
    },
    {
        "file_full_path": "/path/to/song2.mp3",
        "title": "歌曲2",
        "artist": "艺术家2",
        "album": "专辑2"
    }
])
```

## 支持的音乐平台

| 平台 | 标识符 | 搜索 | 歌词 | 封面 |
|------|--------|------|------|------|
| 网易云音乐 | `netease` | ✅ | ✅ | ✅ |
| QQ音乐 | `qmusic` | ✅ | ✅ | ✅ |
| 咪咕音乐 | `migu` | ✅ | ✅ | ✅ |
| 酷狗音乐 | `kugou` | ✅ | ✅ | ✅ |
| 酷我音乐 | `kuwo` | ✅ | ✅ | ✅ |
| 声纹识别 | `acoustid` | ✅ | ❌ | ❌ |
| 智能匹配 | `smart_tag` | ✅ | ✅ | ✅ |

## 匹配算法说明

### 评分规则

- **完全匹配**: 字符串完全相等 → 得分 2
- **包含匹配**: 一个字符串包含另一个 → 得分 1
- **不匹配**: 无关联 → 得分 0
- **艺术家降权**: 指定了艺术家但完全不匹配 → 得分 -2

### 匹配模式

- **strict (严格模式)**: 标题 + 艺术家 + 专辑 总分 >= 3 才匹配
- **simple (简单模式)**: 标题完全匹配即可

## 命令行工具

```bash
# 查看音乐文件信息
python -m music_tagger info /path/to/song.mp3

# 搜索音乐
python -m music_tagger search "告白气球" --source netease

# 自动匹配
python -m music_tagger auto-tag /path/to/music --source qmusic,netease --mode strict
```

## 项目结构

```
music-tagger/
├── music_tagger/
│   ├── __init__.py
│   ├── core.py              # 核心标签读写
│   ├── matcher.py           # 匹配算法
│   ├── platforms/           # 各平台API
│   │   ├── __init__.py
│   │   ├── netease.py
│   │   ├── qqmusic.py
│   │   ├── migu.py
│   │   ├── kugou.py
│   │   ├── kuwo.py
│   │   └── acoustid.py
│   ├── crypto/              # 加密模块
│   │   ├── __init__.py
│   │   └── encrypt.py
│   └── utils.py            # 工具函数
├── requirements.txt
└── README.md
```

## 注意事项

1. 部分平台可能有反爬机制，建议合理使用
2. 批量处理时注意请求频率，避免被封禁
3. 修改音乐文件标签前建议先备份
4. 声纹识别需要安装 fpcalc 工具

## 许可证

MIT License
