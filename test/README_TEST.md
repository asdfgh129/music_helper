# 测试脚本目录说明

本目录包含用于验证 `music_helper` 和 `soundalike` 项目指纹一致性的测试脚本。

---

## 文件列表

### 指纹测试相关

| 文件 | 说明 | 是否需要 fpcalc |
|------|------|----------------|
| `test_fingerprint_config.py` | 验证两个项目的配置是否正确 | ❌ 不需要 |
| `test_fingerprint_consistency.py` | 完整的一致性测试（推荐） | ✅ 需要 |
| `test_fingerprint_consistency_simple.py` | 简化版测试框架 | ❌ 不需要 |
| `test_fingerprint_consistency.sh` | Shell 脚本版本 | ✅ 需要 |
| `FINGERPRINT_TEST_GUIDE.md` | 详细测试指南 | - |

### 其他测试

| 文件 | 说明 |
|------|------|
| `test_matcher.py` | 艺术家匹配算法测试 |
| `test_fingerprint_length.py` | 指纹长度配置测试 |

---

## 快速开始

### 1. 配置验证（不需要 fpcalc）

```bash
python test_fingerprint_config.py
```

**作用：** 检查两个项目的配置是否都设置为 120 秒。

**输出示例：**
```
✅ music_helper    配置正确 (120 秒)
✅ soundalike      配置正确 (120 秒)
```

---

### 2. 完整一致性测试（需要 fpcalc）

**安装 fpcalc:**
```bash
# macOS
brew install chromaprint

# Linux
sudo apt install libchromaprint-tools
```

**运行测试:**
```bash
# 使用项目中的测试文件
python test_fingerprint_consistency.py

# 或指定音频文件
python test_fingerprint_consistency.py /path/to/your/audio.flac
```

**预期输出：**
```
✅ 所有指纹完全一致！
```

---

## 测试说明

### test_fingerprint_config.py

**功能：**
- 验证 `music_helper/config.py` 中的 `FPCALC_LENGTH` 配置
- 验证 `soundalike/fpcalc.go` 中的默认 `length` 配置
- 检查文档中的说明是否更新
- 检查 fpcalc 是否已安装

**适用场景：**
- 修改配置后验证是否正确
- 部署前检查配置一致性

**依赖：**
- Python 3.6+
- 不需要 fpcalc

---

### test_fingerprint_consistency.py

**功能：**
- 使用 fpcalc 命令行工具生成指纹
- 使用 music_helper 项目生成指纹
- 使用 soundalike 的默认配置生成指纹
- 比较三个指纹是否完全一致

**适用场景：**
- 验证两个项目生成的指纹是否一致
- 排查指纹不一致的问题
- 验证配置修改后的效果

**依赖：**
- Python 3.6+
- fpcalc 工具

**输出内容：**
- 每个指纹的长度
- 每个指纹的值
- 比较结果（差异位置、数量、比例）
- 测试总结

---

### test_fingerprint_consistency_simple.py

**功能：**
- 检查 fpcalc 是否已安装
- 如果未安装，提供安装指南
- 演示测试框架

**适用场景：**
- 快速检查是否可以运行完整测试
- 为新手提供安装指导

**依赖：**
- Python 3.6+
- 不需要 fpcalc

---

### test_fingerprint_consistency.sh

**功能：**
- Shell 脚本版本的一致性测试
- 使用 fpcalc 命令行工具
- 调用 Python 脚本生成 music_helper 指纹

**适用场景：**
- 习惯使用 Shell 的用户
- 需要在 CI/CD 中集成测试

**依赖：**
- Bash
- fpcalc 工具
- Python 3.6+
- jq 工具（用于 JSON 处理）

---

## 测试结果解读

### ✅ 完全一致

```
✅ fpcalc 指纹长度: 800
✅ music_helper 指纹长度: 800
✅ soundalike 指纹长度: 800
✅ 所有指纹完全一致！
```

**结论：**
- 配置正确
- 两个项目使用相同的指纹长度
- 可以共享指纹数据

---

### ❌ 长度不一致

```
❌ fpcalc 指纹长度: 100
❌ music_helper 指纹长度: 800
```

**可能原因：**
- fpcalc 使用的长度不是 120 秒
- 音频文件时长不足

**解决方法：**
```bash
# 确保 fpcalc 使用 120 秒
fpcalc -json -length 120 <文件>
```

---

### ❌ 指纹值不一致

```
✅ 长度一致: 都是 800 个值
❌ 不同值数量: 5
❌ 匹配比例: 99.38%
```

**可能原因：**
- 使用了不同的算法参数
- 音频文件被修改
- fpcalc 版本不一致

---

## 常见问题

### Q: 测试提示 "fpcalc not found"

**A:** 需要先安装 fpcalc

```bash
# macOS
brew install chromaprint

# Linux
sudo apt install libchromaprint-tools
```

### Q: 测试文件在哪里？

**A:** 脚本会自动查找以下位置的文件：

- `/Users/bemin/Code/music_helper/1.flac`
- `/Users/bemin/Code/music_helper/test.flac`
- `/Users/bemin/Code/music_helper/test.mp3`

如果找不到，可以手动指定：
```bash
python test_fingerprint_consistency.py /path/to/your/audio.flac
```

### Q: 为什么需要测试？

**A:**

1. **验证配置正确：** 确保两个项目都使用 120 秒长度
2. **确保兼容性：** 验证指纹可以在两个项目间共享
3. **提前发现问题：** 在实际使用前发现配置错误
4. **文档完整性：** 确保配置修改没有遗漏

---

## 相关文档

- **详细测试指南:** `FINGERPRINT_TEST_GUIDE.md`
- **配置说明:** `../FINGERPRINT_LENGTH_CONFIG.md`
- **修改总结:** `../FINGERPRINT_LENGTH_SUMMARY.md`
- **Soundalike 更新:** `/Users/bemin/Code/soundalike/FINGERPRINT_LENGTH_UPDATE.md`

---

## 贡献指南

如果你发现测试脚本有问题或有改进建议：

1. 检查现有测试是否覆盖你的场景
2. 参考现有测试代码的风格
3. 添加必要的测试用例
4. 更新相关文档

---

## 版本历史

| 版本 | 日期 | 说明 |
|------|------|------|
| 1.0 | 2026-03-05 | 初始版本，支持指纹一致性测试 |
