# Music Tagger 项目结构说明

```
music-tagger/
├── music_tagger/              # 主包
│   ├── __init__.py           # 包入口,导出主要类和函数
│   ├── core.py               # 核心标签读写模块
│   ├── matcher.py            # 智能匹配算法模块
│   ├── cli.py               # 命令行工具
│   ├── utils.py             # 工具函数
│   ├── platforms/           # 音乐平台API
│   │   ├── __init__.py     # 平台统一入口
│   │   ├── netease.py     # 网易云音乐
│   │   ├── qqmusic.py     # QQ音乐
│   │   ├── migu.py        # 咪咕音乐
│   │   ├── kugou.py       # 酷狗音乐
│   │   ├── kuwo.py        # 酷我音乐
│   │   └── acoustid.py    # 声纹识别
│   └── crypto/              # 加密模块
│       ├── __init__.py     # 加密模块入口
│       └── encrypt.py      # AES/RSA加密实现
├── example.py               # 使用示例
├── requirements.txt          # 依赖列表
├── setup.py                # 安装脚本
├── README.md               # 项目说明
├── QUICKSTART.md           # 快速开始指南
└── PROJECT_STRUCTURE.md     # 本文件
```

## 模块说明

### 1. core.py - 核心标签读写模块

**主要类**:
- `MusicTagger`: 音乐文件标签读写类
  - 读取: title, artist, album, year, genre等所有标签
  - 更新: update_tags() 方法
  - 转换: to_dict(), var_dict() 方法

**主要函数**:
- `match_song()`: 单平台精确匹配
- `auto_tag()`: 批量自动标签匹配
- `batch_update_tags()`: 批量更新标签

### 2. matcher.py - 智能匹配模块

**主要类**:
- `SmartTagClient`: 智能标签匹配客户端
  - 并行搜索多个平台
  - 智能评分排序
  - 返回最佳匹配结果

**主要函数**:
- `match_score()`: 字符串匹配评分算法
- `match_artist()`: 艺术家匹配算法(支持多艺术家)

### 3. platforms/ - 音乐平台API

每个平台实现两个方法:
- `fetch_id3_by_title(title)`: 搜索音乐
- `fetch_lyric(song_id)`: 获取歌词

**支持的平台**:
- `netease`: 网易云音乐(需要加密)
- `qqmusic`: QQ音乐
- `migu`: 咪咕音乐
- `kugou`: 酷狗音乐(需要MD5签名)
- `kuwo`: 酷我音乐
- `acoustid`: 声纹识别

### 4. crypto/ - 加密模块

**主要函数**:
- `weEncrypt()`: 网易云网页API加密(AES+RSA)
- `linuxEncrypt()`: 网易云Linux API加密(AES)
- `eEncrypt()`: 网易云E-API加密
- `MD5()`: MD5哈希计算

### 5. utils.py - 工具函数

**主要类**:
- `ConstantTemplate`: 模板解析器(支持${变量}语法)

**主要函数**:
- `timestamp_to_dt()`: 时间戳转日期时间
- `match_score()`: 字符串匹配评分

## 数据流

### 读取标签流程

```
MusicTagger(file_path)
    ↓
load_file() [来自 component/music_tag]
    ↓
访问属性: tagger.title, tagger.artist, etc.
    ↓
to_dict() → 转换为字典
```

### 在线搜索流程

```
MusicResource(platform)
    ↓
对应的平台客户端 (NetEaseMusicClient / QQMusicApi / etc.)
    ↓
fetch_id3_by_title(title)
    ↓
发送HTTP请求到音乐平台API
    ↓
解析返回结果
    ↓
返回标准化格式的歌曲列表
```

### 智能匹配流程

```
SmartTagClient()
    ↓
fetch_id3_by_title({title, full_path})
    ↓
ThreadPoolExecutor 并行搜索多个平台
    ↓
对每个结果评分:
    - 标题匹配度
    - 艺术家匹配度
    - 专辑匹配度
    ↓
按总分降序排序
    ↓
返回前15个结果
```

### 更新标签流程

```
MusicTagger(file_path)
    ↓
update_tags(tag_info)
    ↓
解析模板变量 (${title}, ${artist}等)
    ↓
设置各个标签字段
    ↓
下载封面图片 (如果提供URL)
    ↓
保存歌词文件 (如果需要)
    ↓
file.save() 写入文件
    ↓
可选: 重命名文件
```

## API设计

### 输入格式

#### fetch_id3_by_title() 返回格式

```python
[
    {
        "id": "歌曲ID",
        "name": "歌曲标题",
        "artist": "艺术家",
        "artist_id": "艺术家ID",
        "album": "专辑",
        "album_id": "专辑ID",
        "album_img": "封面URL",
        "year": "年份",
        "score": "匹配度(仅智能匹配)",  # 可选
        "resource": "来源平台"          # 可选
    },
    ...
]
```

#### update_tags() 输入格式

```python
{
    "title": "标题",
    "artist": "艺术家",
    "album": "专辑",
    "albumartist": "专辑艺术家",
    "year": "年份",
    "genre": "流派",
    "tracknumber": "音轨号",
    "discnumber": "碟片号",
    "lyrics": "歌词",
    "comment": "评论",
    "album_img": "封面URL或Base64",
    "filename": "新文件名(支持模板)",
    "is_save_lyrics_file": False,  # 是否保存歌词到文件
    "is_save_album_cover": False,  # 是否保存封面到文件
    "album_type": "专辑类型",      # 可选
    "language": "语言"             # 可选
}
```

## 依赖关系

```
music_tagger/
├── core.py
│   ├── platforms/ (在线搜索)
│   ├── matcher.py (智能匹配)
│   └── utils.py (工具函数)
├── matcher.py
│   ├── platforms/ (多平台搜索)
│   └── utils.py (匹配算法)
└── platforms/
    ├── netease.py
    │   └── crypto/ (加密)
    ├── kugou.py
    │   └── execjs (签名)
    └── acoustid.py
        └── component.mz (声纹识别)
```

## 扩展点

### 1. 添加新平台

位置: `music_tagger/platforms/new_platform.py`

实现:
```python
class NewPlatformClient:
    def fetch_id3_by_title(self, title):
        # 搜索逻辑
        return songs
    
    def fetch_lyric(self, song_id):
        # 歌词获取逻辑
        return lyric
```

注册: 在 `music_tagger/platforms/__init__.py` 中添加

### 2. 添加新标签字段

位置: `core.py` 的 `MusicTagger` 类

添加属性和方法即可

### 3. 修改匹配算法

位置: `utils.py` 的 `match_score()` 和 `match_artist()`

修改评分逻辑

### 4. 添加新功能

在相应模块添加函数, 在 `__init__.py` 中导出

## 配置

目前无配置文件,所有参数通过函数参数传递。

如需配置,可添加 `config.py`:

```python
# config.py
DEFAULT_TIMEOUT = 10
DEFAULT_SOURCES = ["qmusic", "netease", "migu", "kugou"]
MATCH_MODE = "strict"
```

## 测试

建议添加测试目录:

```
music-tagger/
└── tests/
    ├── test_core.py
    ├── test_matcher.py
    ├── test_platforms/
    │   ├── test_netease.py
    │   └── ...
    └── fixtures/
        └── test_files/
            └── song.mp3
```

使用 pytest:

```bash
pip install pytest
pytest tests/
```

## 部署

### 本地安装

```bash
pip install -e .
```

### 打包发布

```bash
python setup.py sdist bdist_wheel
twine upload dist/*
```

## 注意事项

1. **第三方依赖**: `component.music_tag` 和 `component.mz` 需要手动安装或复制
2. **网络请求**: 注意控制请求频率,避免被封
3. **编码问题**: 统一使用 UTF-8 编码
4. **异常处理**: 所有网络请求都有try-except保护
5. **兼容性**: Python 3.7+

## 性能优化

1. **并行搜索**: SmartTagClient 使用 ThreadPoolExecutor
2. **缓存**: 可考虑添加请求缓存
3. **批量操作**: auto_tag 和 batch_update_tags 支持批量处理
4. **懒加载**: 按需加载平台客户端
