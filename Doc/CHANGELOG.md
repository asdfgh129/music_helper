# 更新日志 (CHANGELOG)

本文件记录 Music Helper 项目的所有重要更改和版本发布。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
版本号格式: `xx.xx-b{时间戳}` (时间戳为 Unix 时间戳)

---

## [Unreleased]

### 计划中
- 支持更多音乐平台（Spotify、Apple Music 等）
- Web GUI 界面
- Docker 部署支持

---

## [0.4-b1771563799] - 2026-02-20

### 改进
- **业务逻辑优化**: 分离VIP加密文件和普通音乐文件的处理流程
  - VIP解密函数（`decrypt_netease_vip()` 和 `decrypt_qq_vip()`）现在只处理加密文件，不再处理普通文件
  - 普通音乐文件使用独立的拷贝函数（`copy_netease_normal_files()` 和 `copy_qq_normal_files()`）
  - 在 `file_operations.py` 中添加 `scan_normal_music_files()` 函数，专门扫描普通音频文件（不包括加密格式）
  - 将原 `move_netease_normal_files()` 和 `move_qq_normal_files()` 改为 `copy_netease_normal_files()` 和 `copy_qq_normal_files()`
  - 更新 `main.py` 中的函数调用和日志信息

---

## [0.3-b1771562924] - 2026-02-20

### 改进
- **日志目录重构**: 将日志文件统一存储到项目目录下的 `log/` 子目录
  - 在 `config.py` 中添加 `LOG_DIR` 配置项
  - 修改 `utils.py` 中的 `setup_logging()` 和 `create_operation_log()` 函数
  - 修改 `archive.py` 中的日志配置
  - 创建 `log/.gitkeep` 保留目录结构
  - 所有日志文件不再存储在主目录中
- **VIP解密功能改进**: 优化网易云和QQ音乐文件解密流程
  - 网易云和QQ音乐普通文件使用拷贝而非移动到临时目录
  - 网易云加密文件（.ncm）和QQ音乐加密文件（.mflac, .mgg）移动到临时目录
  - 解密后的文件自动移回原目录，删除对应的加密文件
  - 在 `config.py` 中添加 `NETEASE_VIP_EXTENSIONS` 和 `QQ_VIP_EXTENSIONS` 配置
  - 在 `file_operations.py` 中添加 `copy_files_to_temp()` 和 `move_decrypted_files_back()` 函数
  - 更新 `decrypt_netease_vip()` 和 `decrypt_qq_vip()` 函数支持普通文件处理和文件移回

---

## [0.2-b1771550000] - 2026-02-19

### 改进
- **导入语句重构**: 统一项目中的导入风格，提升代码可读性
  - 模块函数调用改用 `import module` + `module.func()` 方式
  - 配置变量继续使用 `from config import xxx` 直接导入方式
  - 修改的文件包括: `main.py`, `tag_updater.py`, `vip_decrypt.py`, `soundalike.py`, `tag_fetcher.py`, `file_operations.py`, `archive.py`

---

## [0.1-b1771469452] - 2026-02-19

### 新增
- **changelog.md**: 新增版本更新日志文档，记录每次更新的内容
- **版本号管理**: 在 `config.py` 中添加 `__version__` 配置项，版本号格式为 `xx.xx-b{时间戳}`
  - 主版本号 (xx): 功能重大变更
  - 次版本号 (xx): 功能新增或改进
  - 时间戳 (b{timestamp}): 发布时间 (Unix 时间戳)

### 改进
- 完善项目版本管理，便于跟踪功能演进
- 统一版本号管理方式，为后续发布做准备
- 支持通过 `python main.py --version` 查看版本信息

---

## 版本说明

### 版本号格式

版本号格式: `MAJOR.MINOR-b{TIMESTAMP}`

- **MAJOR (主版本)**: 功能重大变更或架构调整
- **MINOR (次版本)**: 功能新增或改进
- **TIMESTAMP (时间戳)**: 发布时间的 Unix 时间戳 (10位数字)

**示例**:
```
0.1-b1771469452  # 第一个正式版本，发布于 2026-02-19
0.2-b1771469560  # 功能新增版本
1.0-b1771470000  # 重大功能升级
```

### 时间戳生成

时间戳使用 Python 的 `datetime.now().timestamp()` 生成，转换为整数：
```python
from datetime import datetime
timestamp = int(datetime.now().timestamp())  # 10位 Unix 时间戳
```

### 依赖版本

项目依赖的主要库版本（当前版本 0.1-b1771469452）:

```
# 基础依赖
mutagen>=1.47.0

# QQ 音乐解密
frida>=16.0.0
requests>=2.31.0

# 声纹识别
acoustid>=1.2.0

# 音乐标签管理
music-tag>=0.4.0

# 网易云加密
pycryptodome>=3.19.0
```

### 更新日志模板

如需添加新版本，请按照以下模板更新:

```markdown
## [x.x-b{时间戳}] - YYYY-MM-DD

### 新增
- 新功能描述

### 改进
- 改进功能描述

### 修复
- 修复问题描述

### 废弃
- 废弃功能说明

### 移除
- 移除功能说明

### 安全
- 安全修复说明

### 文档
- 文档更新说明
```

**注意**: 在创建新版本时，请更新 `config.py` 中的 `__version__` 变量，使用新的时间戳。
