# 指纹一致性测试指南

本指南说明如何测试 `music_helper` 和 `soundalike` 项目对同一音频文件生成的指纹是否一致。

---

## 测试概述

### 测试目标

验证以下三个来源生成的指纹是否完全一致：

1. **fpcalc 命令行工具** - 基准工具
2. **music_helper 项目** - 使用 `FPCALC_LENGTH = 120` 配置
3. **soundalike 项目** - 使用默认 `length = 120` 配置

### 预期结果

所有三个来源应该生成**完全相同**的指纹，因为：

- `music_helper` 使用：`fpcalc -json -length 120`
- `soundalike` 使用：`fpcalc -raw -json -length 120`（默认）

---

## 测试文件

| 文件 | 说明 | 是否需要 fpcalc |
|------|------|----------------|
| `test_fingerprint_config.py` | 验证配置是否正确 | ❌ 不需要 |
| `test_fingerprint_consistency.py` | 完整的一致性测试 | ✅ 需要 |
| `test_fingerprint_consistency_simple.py` | 简化版测试框架 | ❌ 不需要 |

---

## 快速开始

### 1. 安装 fpcalc（必需）

**macOS:**
```bash
brew install chromaprint
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt install libchromaprint-tools
```

**Windows:**
1. 下载：https://github.com/acoustid/chromaprint/releases
2. 解压后将 `fpcalc.exe` 放到 PATH 中

**验证安装:**
```bash
fpcalc -version
```

### 2. 运行配置验证（不需要 fpcalc）

```bash
cd /Users/bemin/Code/music_helper
python test/test_fingerprint_config.py
```

**预期输出:**
```
✅ music_helper    配置正确 (120 秒)
✅ soundalike      配置正确 (120 秒)
✅ fpcalc          已安装
```

### 3. 运行完整一致性测试（需要 fpcalc）

```bash
cd /Users/bemin/Code/music_helper
python test/test_fingerprint_consistency.py <音频文件路径>
```

**示例:**
```bash
python test/test_fingerprint_consistency.py /Users/bemin/Code/music_helper/1.flac
```

**预期输出:**
```
✅ 所有指纹完全一致！
```

---

## 测试结果说明

### 情况 1: 完全一致 ✅

```
✅ fpcalc 指纹长度: 800
✅ music_helper 指纹长度: 800
✅ soundalike 指纹长度: 800
✅ 所有指纹完全一致！
```

**结论：** 配置正确，所有工具使用相同的指纹长度。

---

### 情况 2: 长度不一致 ❌

```
❌ fpcalc 指纹长度: 100
❌ music_helper 指纹长度: 800
❌ soundalike 指纹长度: 800
```

**可能原因：**
- fpcalc 使用的长度不是 120 秒
- audio 文件时长不足 120 秒

**解决方法：**
```bash
# 确保 fpcalc 使用 120 秒
fpcalc -json -length 120 <文件>
```

---

### 情况 3: 指纹值不一致 ❌

```
✅ 长度一致: 都是 800 个值
❌ 不同值数量: 5
❌ 匹配比例: 99.38%
```

**可能原因：**
- 两个调用使用了不同的算法参数
- 音频文件在两次调用之间被修改
- fpcalc 版本不一致

**解决方法：**
1. 检查 `algorithm` 参数（应该都是 2）
2. 验证音频文件未被修改
3. 确认 fpcalc 版本一致

---

## 手动测试步骤

如果自动化测试失败，可以手动验证：

### 步骤 1: 使用 fpcalc 直接生成

```bash
fpcalc -json -length 120 /path/to/audio.flac > fp1.json
cat fp1.json | python -m json.tool
```

### 步骤 2: 使用 music_helper 生成

```python
from Fingerprint.musicbrainz_matcher import FingerprintCalculator

calc = FingerprintCalculator()
result = calc.calculate("/path/to/audio.flac")

if result.success:
    print(f"指纹长度: {len(result.fingerprint)}")
    print(f"时长: {result.duration}")
```

### 步骤 3: 比较结果

```bash
# 查看指纹长度
jq '.fingerprint | length' fp1.json

# 提取前10个值
jq '.fingerprint[0:10]' fp1.json
```

---

## 常见问题

### Q1: fpcalc 生成错误 `Audio file too short`

**原因：** 音频文件时长不足 120 秒

**解决：**
- 使用较长的音频文件进行测试
- 或者临时降低测试长度：
  ```bash
  fpcalc -json -length 60 /path/to/audio.flac
  ```

### Q2: music_helper 返回失败

**原因：**
- fpcalc 未安装或不在 PATH 中
- 音频格式不支持

**解决：**
```bash
# 检查 fpcalc
which fpcalc

# 检查支持的格式
fpcalc -version
```

### Q3: soundalike 编译失败

**原因：** Go 环境问题

**解决：**
```bash
cd /Users/bemin/Code/soundalike
go mod tidy
go build -o soundalike .
```

---

## 配置文件位置

### music_helper 项目

- **配置文件:** `config.py`
- **关键配置:** `FPCALC_LENGTH = 120`
- **使用位置:** `Fingerprint/musicbrainz_matcher.py`

### soundalike 项目

- **配置文件:** `fpcalc.go`
- **关键配置:** `defaultFpcalcSettings()` 中的 `length = 120`
- **使用位置:** 所有调用 `runFpcalc()` 的地方

---

## 理论基础

### 为什么两个项目应该生成相同的指纹？

1. **相同的工具:** 两个项目都使用 Chromaprint 的 `fpcalc` 工具
2. **相同的参数:** 都使用 `-length 120 -algorithm 2`
3. **相同的算法:** Chromaprint 算法确定，相同输入产生相同输出

### 指纹长度与音频时长的关系

```
指纹值数量 ≈ 音频时长 × 指纹采样率
             ≈ 120 秒 × ~6.7 值/秒
             ≈ 800 个值
```

**注意:** 实际值可能略有不同，因为：
- 音频文件时长可能不是整数
- 指纹采样可能不精确
- 静音部分可能被跳过

---

## 测试检查清单

在运行测试前，确认以下内容：

- [ ] fpcalc 已安装并可用
- [ ] `config.py` 中 `FPCALC_LENGTH = 120`
- [ ] `fpcalc.go` 中 `length = 120`
- [ ] 有一个足够长的测试音频文件（≥ 120 秒）
- [ ] 测试文件格式被 fpcalc 支持（.flac, .mp3, .ogg 等）

---

## 下一步

### 测试通过后

1. ✅ 可以在两个项目间共享指纹数据
2. ✅ 可以用 soundalike 的结果查询 MusicBrainz
3. ✅ 可以用 music_helper 的结果进行重复检测

### 测试失败后

1. 检查配置文件中的长度设置
2. 验证 fpcalc 版本和参数
3. 查看 fpcalc 的错误输出
4. 参考本指南的"常见问题"部分

---

## 相关文档

- **配置说明:** `/Users/bemin/Code/music_helper/FINGERPRINT_LENGTH_CONFIG.md`
- **修改总结:** `/Users/bemin/Code/music_helper/FINGERPRINT_LENGTH_SUMMARY.md`
- **Soundalike 更新:** `/Users/bemin/Code/soundalike/FINGERPRINT_LENGTH_UPDATE.md`
- **MusicBrainz:** https://musicbrainz.org
- **Chromaprint:** https://github.com/acoustid/chromaprint

---

## 联系与反馈

如果测试过程中遇到问题：

1. 检查本文档的"常见问题"部分
2. 查看相关日志文件
3. 确认所有配置已正确更新

---

**版本:** 1.0
**日期:** 2026-03-05
**作者:** Music Helper Team
