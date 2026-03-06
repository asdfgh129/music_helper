# 指纹长度配置说明

## 概述

为了确保项目中的指纹匹配功能能够正确工作，统一了指纹提取长度的配置。

## 背景说明

### 问题

在 music_helper 项目中，存在两个使用指纹的功能模块：

1. **MusicBrainz 指纹匹配** (`Fingerprint/musicbrainz_matcher.py`)
   - 使用 `fpcalc` 工具提取音频指纹
   - 原来使用长度 120 秒
   - 指纹用于在 MusicBrainz 数据库中匹配音乐

2. **Soundalike 声纹去重** (`soundalike.exe`)
   - 使用外部工具 `soundalike.exe`
   - **已修改为使用长度 120 秒**（从 15 秒改为 120 秒）
   - 指纹用于检测重复音乐文件

### 问题分析

**关键问题**：MusicBrainz 网站匹配指纹的标准长度是 **120 秒**。

如果 Soundalike 使用长度 15 的指纹，那么这些指纹无法用于 MusicBrainz 匹配，因为：
- 15 秒指纹精度不足
- MusicBrainz 数据库中存储的指纹是 120 秒长度
- 不同长度的指纹无法正确匹配

**已解决**：已将 `soundalike` 项目的默认指纹长度从 15 秒修改为 120 秒，现在两个工具使用相同的长度。

### 解决方案

**统一使用 120 秒作为标准指纹长度**，理由：
- ✅ 兼容 MusicBrainz 数据库
- ✅ 提高指纹匹配准确率
- ✅ 实现项目内指纹数据共享
- ✅ 避免重复计算指纹

---

## 配置文件

### config.py

在 `config.py` 中添加了统一的指纹长度配置：

```python
# ==================== 指纹配置 ====================
# fpcalc 指纹提取长度（秒）
# MusicBrainz 需要的指纹长度为 120 秒
# 声纹识别去重工具 Soundalike 使用的指纹长度
# 注意：两个工具应该使用相同的长度以确保指纹兼容性
FPCALC_LENGTH = 120  # 统一使用 120 秒长度（MusicBrainz 标准长度）
```

---

## 修改的文件

### 1. config.py

**位置**: `/Users/bemin/Code/music_helper/config.py:93-99`

**修改内容**:
```python
# 外部程序路径
UM_EXE = r'um.exe'
SOUNDALIKE_EXE = r'soundalike.exe'

# ==================== 指纹配置 ====================
FPCALC_LENGTH = 120  # 统一使用 120 秒长度（MusicBrainz 标准长度）
```

### 2. Fingerprint/musicbrainz_matcher.py

**位置**: `/Users/bemin/Code/music_helper/Fingerprint/musicbrainz_matcher.py`

**修改内容**:
1. **添加导入**（第 18-26 行）:
   ```python
   import os
   import sys
   
   sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
   
   try:
       from config import FPCALC_LENGTH
   except ImportError:
       FPCALC_LENGTH = 120
       logging.warning(f"无法从 config 导入 FPCALC_LENGTH，使用默认值: {FPCALC_LENGTH}")
   ```

2. **修改 FingerprintCalculator.calculate**（第 427-438 行）:
   ```python
   def calculate(self, audio_file_path: str) -> FingerprintResult:
       """计算音频文件的指纹"""
       if not self.fpcalc_path:
           return FingerprintResult('', 0, success=False)

       # 使用配置的指纹长度
       logger.info(f"使用指纹长度: {FPCALC_LENGTH} 秒")

       try:
           result = subprocess.run(
               [self.fpcalc_path, '-json', '-length', str(FPCALC_LENGTH), audio_file_path],
               capture_output=True,
               text=True,
               timeout=60
           )
   ```

---

## 使用说明

### 读取配置

```python
from config import FPCALC_LENGTH

print(f"当前指纹长度配置: {FPCALC_LENGTH} 秒")
```

### 在代码中使用

```python
from Fingerprint.musicbrainz_matcher import FingerprintCalculator

# 创建计算器（自动使用配置的长度）
calculator = FingerprintCalculator()

# 计算指纹
result = calculator.calculate('song.flac')
print(f"指纹: {result.fingerprint}")
print(f"长度: {result.duration} 秒")
```

---

## 影响范围

### 已修改的模块

| 模块 | 文件 | 修改内容 |
|------|------|---------|
| 配置 | `config.py` | 添加 `FPCALC_LENGTH` 常量 |
| 指纹匹配 | `Fingerprint/musicbrainz_matcher.py` | 使用 `FPCALC_LENGTH` 替代硬编码的 120 |

### 需要更新的模块（外部工具）

| 工具 | 当前状态 | 需要修改 |
|------|---------|---------|
| `soundalike.exe` | 已修改为 120 秒长度 | ✅ 已重新编译 |
| `fpcalc` | 支持通过 `-length` 参数指定 | ✅ 已通过参数控制 |

### 可能受影响的代码

如果您的代码中有硬编码的指纹长度，需要更新为使用 `FPCALC_LENGTH`：

```python
# ❌ 不推荐
fpcalc_length = 120

# ✅ 推荐
from config import FPCALC_LENGTH
fpcalc_length = FPCALC_LENGTH
```

---

## 注意事项

### 1. Soundalike 工具

`soundalike.exe` 是一个外部可执行工具，已将默认指纹长度从 15 秒修改为 120 秒：

- ✅ **已完成**: 修改 `fpcalc.go` 中 `defaultFpcalcSettings()` 函数
- ✅ **已完成**: 重新编译生成新的 `soundalike` 可执行文件
- ✅ **已完成**: 更新所有相关文档（README.md, FEATURES.md, AGENTS.md）

### 2. 现有数据库

如果您的 `soundalike` 数据库中存储的是 15 秒长度的指纹，建议：

1. 备份现有数据库
2. 删除旧的数据库文件
3. 使用新的 120 秒长度重新扫描音乐文件
4. 重建声纹数据库

### 3. 性能考虑

**120 秒 vs 15 秒**:

| 指标 | 15 秒 | 120 秒 |
|------|--------|--------|
| 计算速度 | 快 | 较慢（约 8 倍） |
| 匹配准确率 | 较低 | 高 |
| MusicBrainz 兼容性 | ❌ 不兼容 | ✅ 完全兼容 |
| 数据库大小 | 小 | 大 |

**建议**: 对于 MusicBrainz 匹配，使用 120 秒；对于快速去重，可以考虑两套指纹。

---

## 验证方法

### 验证指纹长度

运行指纹计算并查看日志：

```bash
python -c "
from Fingerprint.musicbrainz_matcher import FingerprintCalculator
calc = FingerprintCalculator()
result = calc.calculate('test.flac')
print(f'指纹长度: {len(result.fingerprint)} 字符')
print(f'音频时长: {result.duration} 秒')
"
```

预期输出：
```
INFO: 使用指纹长度: 120 秒
指纹长度: [指纹字符数] 字符
音频时长: [音频时长] 秒
```

### 验证 MusicBrainz 匹配

使用 `Fingerprint/musicbrainz_matcher.py` 匹配测试文件：

```bash
python -c "
from Fingerprint.musicbrainz_matcher import FingerprintMatcher

matcher = FingerprintMatcher()
result = matcher.match_file('test.flac')

if result.success:
    print('MusicBrainz 匹配成功!')
    print(f'匹配数: {len(result.recordings)}')
else:
    print('MusicBrainz 匹配失败')
"
```

---

## 相关文档

- [MusicBrainz API 文档](https://musicbrainz.org/doc/Development/XML_Web_Service/Version_2)
- [AcoustID API 文档](https://acoustid.org/webservice)
- [Chromaprint/fpcalc 文档](https://acoustid.org/chromaprint)

---

## 更新日志

| 日期 | 版本 | 修改内容 |
|------|------|---------|
| 2026-03-02 | 0.1 | 统一指纹长度配置为 120 秒 |
