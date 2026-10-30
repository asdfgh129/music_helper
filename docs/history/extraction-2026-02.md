# 历史归档：music_tagger 提取记录

> **归档说明**：本文原为 `Doc/EXTRACTION_SUMMARY.md`，记录 `music_tagger/` 从上游
> `music-tag-web` 项目提取的过程与来源映射。目录结构在 `0.2.0` 后基本未变
> （新增了 `music_tagger/utils.py` 以修正相对导入越界）。保留本文便于日后同步上游改动。

## 提取说明

本项目从原 `music-tag-web` 项目中提取了所有与音乐文件标签相关的核心代码,形成了一个独立的、纯命令行/库方式的工具。

## 提取的代码内容

### 1. 核心功能模块

#### music_tagger/core.py
**来源**: `applications/task/services/music_ids.py`
**功能**:
- 音乐文件标签读取
- 音乐文件标签写入
- 批量自动匹配
- 批量标签更新

#### music_tagger/matcher.py
**来源**: `applications/task/services/smart_tag_resource.py`
**功能**:
- 智能标签匹配
- 多平台并行搜索
- 评分算法

#### music_tagger/utils.py
**来源**: `applications/task/utils.py`, `applications/utils/constant_template.py`
**功能**:
- 字符串匹配算法
- 繁简转换
- 模板语法解析

### 2. 音乐平台API模块

#### music_tagger/platforms/netease.py
**来源**: `applications/task/services/music_resource.py` (NetEaseMusicClient类)
**功能**:
- 网易云音乐搜索
- 网易云音乐歌词获取
- AES+RSA加密请求

#### music_tagger/platforms/qqmusic.py
**来源**: `applications/task/services/qm.py`
**功能**:
- QQ音乐搜索
- QQ音乐歌词获取
- 音质判断

#### music_tagger/platforms/migu.py
**来源**: `applications/task/services/music_resource.py` (MiGuMusicClient类)
**功能**:
- 咪咕音乐搜索
- 咪咕音乐歌词获取

#### music_tagger/platforms/kugou.py
**来源**: `applications/task/services/kugou.py`
**功能**:
- 酷狗音乐搜索
- 酷狗音乐歌词获取
- MD5签名算法

#### music_tagger/platforms/kuwo.py
**来源**: `applications/task/services/kuwo.py`
**功能**:
- 酷我音乐搜索
- 酷我音乐歌词获取
- SHA1+MD5 Token生成

#### music_tagger/platforms/acoustid.py
**来源**: `applications/task/services/acoust.py`, `component/mz/run.py`
**功能**:
- 声纹识别
- 音频指纹匹配

### 3. 加密模块

#### music_tagger/crypto/encrypt.py
**来源**: `applications/utils/encrypt.py`
**功能**:
- AES加密 (CBC/ECB模式)
- RSA加密
- MD5哈希
- 网易云音乐三种加密方式

### 4. 命令行工具

#### music_tagger/cli.py
**来源**: 新创建(基于原项目的业务逻辑)
**功能**:
- info: 查看音乐文件信息
- search: 搜索音乐
- auto-tag: 批量自动匹配
- smart-search: 智能搜索

## 未提取的内容

以下内容未提取,因为与标签功能无关:

### Web界面相关
- `web/` 目录下的所有前端代码
- `static/` 目录下的静态资源
- `templates/` 目录下的模板文件

### 用户管理相关
- `applications/user/` 模块
- 用户认证、权限等

### 数据库相关
- Django ORM模型(音乐标签除外)
- 数据库迁移文件
- Celery异步任务

### 其他业务功能
- 文件夹扫描
- 文件整理
- Subsonic API
- 翻译功能

## 主要改动

### 1. 简化依赖

原项目依赖Django框架,新项目移除了所有Django依赖,只保留:
- requests (HTTP请求)
- mutagen (音乐标签读写)
- pycryptodomex (加密)
- execjs (JS执行)
- mako (模板解析)
- Pillow (图片处理)

### 2. 简化架构

原项目使用Django的MVC架构,新项目采用更简单的模块化设计:
- 每个功能独立为模块
- 通过统一的API调用
- 支持作为库和命令行工具两种方式使用

### 3. 标准化接口

统一了各平台的接口格式:
- `fetch_id3_by_title(title)`: 返回标准化的歌曲列表
- `fetch_lyric(song_id)`: 返回歌词字符串

### 4. 独立化处理

将原来耦合在一起的代码拆分为独立模块:
- 移除了Django模型依赖
- 移除了Celery异步任务
- 移除了Web视图
- 纯Python函数/类实现

## 使用方式对比

### 原项目(需要Django环境)

```python
# 需要启动Django服务器
# 通过Web界面操作
POST /api/task/fetch_id3_by_title
{
    "resource": "netease",
    "title": "告白气球"
}
```

### 新项目(独立工具)

```python
# 直接作为Python库使用
from music_tagger import MusicResource

songs = MusicResource("netease").fetch_id3_by_title("告白气球")

# 或使用命令行
python -m music_tagger.cli search "告白气球" --source netease
```

## 功能对比

| 功能 | 原项目 | 新项目 |
|------|--------|--------|
| 读取标签 | ✅ Web界面 | ✅ 库+CLI |
| 写入标签 | ✅ Web界面 | ✅ 库+CLI |
| 在线搜索 | ✅ 多平台 | ✅ 多平台 |
| 智能匹配 | ✅ Web界面 | ✅ 库+CLI |
| 批量处理 | ✅ Celery异步 | ✅ 同步 |
| 歌词下载 | ✅ | ✅ |
| 封面下载 | ✅ | ✅ |
| 文件重命名 | ✅ | ✅ |
| 模板语法 | ✅ | ✅ |
| Web界面 | ✅ | ❌ |
| 用户管理 | ✅ | ❌ |
| 文件整理 | ✅ | ❌ |

## 依赖对比

### 原项目主要依赖
- Django (Web框架)
- djangorestframework
- celery (异步任务)
- redis
- 其他Django相关包

### 新项目主要依赖
- requests
- mutagen
- pycryptodomex
- execjs
- mako
- Pillow

**减少依赖数量**: 约 90% 减少依赖

## 代码规模

| 模块 | 原项目 | 新项目 | 说明 |
|------|--------|--------|------|
| 核心标签 | ~200行 | ~350行 | 优化并增强 |
| 平台API | ~800行 | ~650行 | 精简优化 |
| 加密模块 | ~80行 | ~100行 | 保持一致 |
| 工具函数 | ~100行 | ~140行 | 整合优化 |
| 总计 | ~1180行 | ~1240行 | 功能增强 |

**注意**: 未包含原项目的Web界面代码(数千行)

## 优势

1. **轻量级**: 无需Django等重量级依赖
2. **独立性**: 可独立运行,不依赖Web服务器
3. **易集成**: 作为Python库,易于集成到其他项目
4. **易测试**: 纯函数/类,易于单元测试
5. **易部署**: 无需数据库、消息队列等基础设施
6. **可扩展**: 模块化设计,易于添加新平台/功能

## 限制

1. **无Web界面**: 需要通过CLI或编程方式使用
2. **无用户管理**: 无多用户支持
3. **同步处理**: 批量操作为同步,非异步
4. **部分功能未实现**: 文件整理、翻译等未提取

## 适用场景

### 推荐使用新项目的场景
- ✅ 本地音乐库管理
- ✅ 脚本自动化处理
- ✅ 集成到其他工具
- ✅ 命令行用户
- ✅ 学习和研究

### 推荐使用原项目的场景
- ✅ 需要Web界面
- ✅ 需要多用户协作
- ✅ 需要异步大批量处理
- ✅ 需要完整的音乐管理系统

## 后续扩展建议

1. **添加Web界面**: 使用Flask/FastAPI搭建轻量级Web界面
2. **异步支持**: 使用asyncio实现异步批量处理
3. **缓存机制**: 添加搜索结果缓存
4. **配置文件**: 支持配置文件自定义
5. **测试覆盖**: 添加单元测试和集成测试
6. **文档完善**: 补充API文档和使用案例

## 许可证

MIT License - 保持与原项目一致
