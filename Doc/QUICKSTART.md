# Music Tagger 快速开始指南

## 安装

### 1. 从源码安装

```bash
# 克隆或下载项目
cd music-tagger

# 安装依赖
pip install -r requirements.txt

# 或者使用 setup.py 安装
pip install -e .
```

### 2. 依赖说明

| 依赖包 | 用途 |
|--------|------|
| requests | HTTP请求 |
| mutagen | 音乐文件标签读写 |
| pycryptodomex | 加密算法(AES, RSA) |
| execjs | JavaScript执行(酷狗签名) |
| mako | 模板解析 |
| Pillow | 图片处理 |

### 3. 可选依赖

如果需要使用繁简转换功能，需要安装:

```bash
# 从原项目复制 component 目录到 Python 路径
# 或者安装相应的繁简转换库
```

## 快速使用

### 1. 作为Python库使用

```python
from music_tagger import MusicTagger, MusicResource

# 读取音乐文件
tagger = MusicTagger("song.mp3")
print(tagger.title)
print(tagger.artist)

# 在线搜索
songs = MusicResource("netease").fetch_id3_by_title("告白气球")
for song in songs:
    print(f"{song['name']} - {song['artist']}")
```

### 2. 作为命令行工具使用

```bash
# 查看音乐文件信息
python -m music_tagger.cli info /path/to/song.mp3

# 搜索音乐
python -m music_tagger.cli search "告白气球" --source netease

# 批量自动匹配
python -m music_tagger.cli auto-tag /path/to/music --source qmusic,netease --mode strict

# 智能搜索
python -m music_tagger.cli smart-search "告白气球" --file /path/to/song.mp3
```

### 3. 运行示例

```bash
python example.py
```

## 功能说明

### 支持的音乐平台

| 平台 | 标识符 | 搜索 | 歌词 | 封面 |
|------|--------|------|------|------|
| 网易云音乐 | `netease` | ✅ | ✅ | ✅ |
| QQ音乐 | `qmusic` | ✅ | ✅ | ✅ |
| 咪咕音乐 | `migu` | ✅ | ✅ | ✅ |
| 酷狗音乐 | `kugou` | ✅ | ✅ | ✅ |
| 酷我音乐 | `kuwo` | ✅ | ✅ | ✅ |
| 声纹识别 | `acoustid` | ✅ | ❌ | ❌ |
| 智能匹配 | `smart_tag` | ✅ | ✅ | ✅ |

### 标签字段说明

| 字段 | 说明 |
|------|------|
| title | 歌曲标题 |
| artist | 艺术家(支持多个, 逗号分隔) |
| album | 专辑名称 |
| albumartist | 专辑艺术家 |
| year | 年份 |
| genre | 流派/类型 |
| tracknumber | 音轨号 |
| discnumber | 碟片号 |
| lyrics | 歌词 |
| comment | 评论 |
| album_img | 专辑封面(URL或Base64) |
| filename | 文件名(支持模板) |

### 模板语法

支持 `${变量名}` 语法进行变量替换:

```python
tagger.update_tags({
    "filename": "${artist} - ${title}",  # 重命名文件
    "albumartist": "${artist}",
})
```

可用变量: `${title}`, `${artist}`, `${album}`, `${albumartist}`, `${tracknumber}`, `${discnumber}`, `${filename}`

### 匹配模式

- **strict (严格模式)**: 标题 + 艺术家 + 专辑 总分 >= 3 才匹配
- **simple (简单模式)**: 标题完全匹配即可

### 匹配算法

- **完全匹配**: 字符串完全相等 → 得分 2
- **包含匹配**: 一个字符串包含另一个 → 得分 1
- **不匹配**: 无关联 → 得分 0
- **艺术家降权**: 指定了艺术家但完全不匹配 → 得分 -2

## 使用场景

### 场景1: 批量整理音乐库

```python
from music_tagger import auto_tag

# 自动匹配整个文件夹
results = auto_tag(
    music_folder="./my_music",
    source_list=["qmusic", "netease"],
    select_mode="strict"
)

# 查看结果
for r in results:
    print(f"{r['file']}: {r['status']}")
```

### 场景2: 手动搜索并更新

```python
from music_tagger import MusicTagger, MusicResource

# 1. 读取本地文件
tagger = MusicTagger("song.mp3")
local_title = tagger.title

# 2. 搜索在线数据
songs = MusicResource("netease").fetch_id3_by_title(local_title)

# 3. 选择最佳匹配
if songs:
    best_match = songs[0]
    
    # 4. 更新标签
    tagger.update_tags({
        "title": best_match['name'],
        "artist": best_match['artist'],
        "album": best_match['album'],
        "lyrics": MusicResource("netease").fetch_lyric(best_match['id']),
        "album_img": best_match.get('album_img'),
    })
    print("更新成功!")
```

### 场景3: 使用智能匹配

```python
from music_tagger import MusicTagger, SmartTagClient

# 1. 读取本地文件
tagger = MusicTagger("song.mp3")

# 2. 智能搜索(多平台并行)
client = SmartTagClient()
results = client.fetch_id3_by_title({
    "title": tagger.title,
    "full_path": tagger.file_path
})

# 3. 查看匹配结果(已按得分排序)
for song in results:
    print(f"得分: {song['score']}, 歌曲: {song['name']} - {song['artist']}")

# 4. 选择最高分的结果更新
if results:
    tagger.update_tags(results[0])
```

## 注意事项

1. **备份重要文件**: 修改音乐文件标签前请先备份
2. **请求频率**: 批量处理时注意控制请求频率,避免被平台封禁
3. **fpcalc工具**: 声纹识别功能需要安装 fpcalc 工具
4. **网络连接**: 在线搜索功能需要网络连接
5. **编码格式**: 建议使用 UTF-8 编码处理中文

## 故障排除

### 问题1: ImportError: No module named 'component.music_tag'

**解决方案**: 需要从原项目复制 `component/music_tag` 目录到 Python 路径

### 问题2: 网易云音乐搜索失败

**解决方案**: 检查网络连接,部分接口可能有反爬限制

### 问题3: 酷狗音乐签名失败

**解决方案**: 确保已安装 `PyExecJS` 和 JavaScript 引擎

### 问题4: 中文乱码

**解决方案**: 确保文件使用 UTF-8 编码保存

## 扩展开发

### 添加新的音乐平台

1. 在 `music_tagger/platforms/` 下创建新文件
2. 实现以下方法:
   - `fetch_id3_by_title(title)`: 搜索音乐
   - `fetch_lyric(song_id)`: 获取歌词
3. 在 `music_tagger/platforms/__init__.py` 中注册

示例:

```python
class MyMusicClient:
    def fetch_id3_by_title(self, title):
        # 实现搜索逻辑
        return songs
    
    def fetch_lyric(self, song_id):
        # 实现歌词获取逻辑
        return lyric
```

## 许可证

MIT License
