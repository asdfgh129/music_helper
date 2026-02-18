# 测试文档

## 概述

本目录包含音乐文件管理系统的所有单元测试。

## 测试结构

```
test/
├── __init__.py                 # 测试包初始化
├── README.md                   # 本文档
├── test_config.py              # 配置模块测试
├── test_utils.py               # 工具函数测试
├── test_metadata.py            # 元数据模块测试
├── test_file_operations.py     # 文件操作模块测试
├── test_archive.py             # 归档模块测试
├── test_lrc.py                 # LRC歌词模块测试
├── test_soundalike.py          # 声纹识别模块测试
└── test_tag_fetcher.py         # 标签获取模块测试
```

## 运行测试

### 运行所有测试

```bash
# 从项目根目录运行
python -m unittest discover -s test -p 'test_*.py'

# 或者直接运行
python -m unittest discover
```

### 运行单个测试文件

```bash
# 运行配置模块测试
python -m unittest test.test_config

# 运行工具函数测试
python -m unittest test.test_utils

# 运行元数据模块测试
python -m unittest test.test_metadata
```

### 运行单个测试方法

```bash
# 运行特定的测试方法
python -m unittest test.test_utils.TestUtils.test_parse_filename_standard
```

### 查看详细输出

```bash
# 显示每个测试的详细信息
python -m unittest discover -v

# 显示更详细的输出
python -m unittest discover -vv
```

## 测试覆盖范围

### test_config.py
- 目录路径定义
- 音频扩展名定义
- 可执行文件路径
- 依赖库可用性检查

### test_utils.py
- 月份格式获取
- 月份格式验证
- 文件名解析（标准格式、无分隔符、多分隔符）
- 艺术家名称拆分（多种分隔符）
- 文本标准化
- 文件名格式检查

### test_metadata.py
- 读取元数据（不存在的文件、不支持的格式）
- 设置元数据（空标签、部分标签）
- 元数据结构验证

### test_file_operations.py
- 扫描音乐文件（空目录、不存在的目录、含MP3的目录）
- 移动文件到临时目录（空列表、单个文件、带LRC文件、同名文件）

### test_archive.py
- 艺术家名称拆分（多种分隔符）
- 查找缺失LRC文件（无缺失、有缺失、多个文件）
- 查找孤立LRC文件（无孤立、有孤立、多种格式、子目录）

### test_lrc.py
- 查找缺失LRC文件（无缺失、有缺失、临时路径恢复、多种格式）
- 查找孤立LRC文件（无孤立、有孤立、所有格式、子目录、大小写）

### test_soundalike.py
- 声纹识别（成功、失败、异常）
- 数据库一致性检查（成功、失败、异常）

### test_tag_fetcher.py
- 解析MusicBrainz记录（完整、最小、空记录、不同日期格式）
- 获取QQ音乐标签（无API、空标题）
- 获取网易云标签（无API、空标题）
- 获取专辑封面（无API）

## 注意事项

1. **依赖库测试**: 某些测试需要mutagen库安装才能运行，如果未安装会自动跳过。

2. **临时文件**: 测试使用临时目录，测试完成后会自动清理。

3. **外部工具测试**: 声纹识别和标签获取的测试使用mock，不需要实际的外部工具。

4. **路径处理**: 测试会自动处理跨平台的路径问题。

## 添加新测试

### 创建测试文件

1. 在test目录下创建新的测试文件，命名格式为`test_<module>.py`
2. 导入需要测试的模块
3. 创建测试类，继承`unittest.TestCase`
4. 编写测试方法，方法名以`test_`开头

### 示例

```python
# -*- coding: utf-8 -*-
"""
单元测试 - 示例模块
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from your_module import your_function


class TestYourModule(unittest.TestCase):
    """示例模块测试"""

    def test_your_function_normal_case(self):
        """测试正常情况"""
        result = your_function("test input")
        self.assertEqual(result, "expected output")

    def test_your_function_edge_case(self):
        """测试边界情况"""
        result = your_function("")
        self.assertEqual(result, "")


if __name__ == '__main__':
    unittest.main()
```

## 持续集成

测试可以集成到CI/CD流程中：

```bash
# 在CI脚本中运行测试
python -m unittest discover -s test -p 'test_*.py' --failfast
```

## 贡献指南

提交代码前请确保：

1. 所有测试通过
2. 新功能包含对应的测试用例
3. 代码覆盖率保持或提高
4. 测试命名清晰，易于理解
