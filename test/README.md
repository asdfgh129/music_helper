# 测试文档

## 运行

```bash
python -m pytest test -q
```

## 结构与覆盖

| 文件 | 覆盖内容 |
|---|---|
| `test_config.py` | 目录/扩展名/外部程序配置、版本号静态化 |
| `test_utils.py` | 月份格式、文件名解析、艺术家拆分、文本标准化 |
| `test_naming.py` | 「歌手 - 歌名」解析与规范化、多艺术家拆分、匹配评分 |
| `test_dedupe.py` | 重复判定（标签+时长、文件名+时长）、保留策略、年份归档目标 |
| `test_ops.py` | 操作计划：dry-run、移动/改名、重名避让、回收站、journal、拷贝 |
| `test_report.py` | 报告渲染、CSV 导出、检查项与修复计划 |
| `test_soundalike.py` | 外部工具包装：成功/失败/超时/缺失可执行文件 |
| `test_decrypt.py` | 解密流程中加密原文件的三种去向，以及「只搬自己动过的文件」 |
| `test_matcher.py` | `music_tagger` 平台匹配算法 |

## 手工/网络用例

`manual_musicbrainz_connection.py`、`manual_musicbrainz_direct.py` 需要网络与 AcoustID key，
不参与自动测试，按需手工执行：

```bash
python test/manual_musicbrainz_direct.py
```

## 约定

- 用例不写入仓库内的真实音乐库，全部使用 `tempfile` 临时目录。
- 不依赖已删除的旧模块（`metadata` / `file_operations` / `archive` / `duplicate` / `lrc` /
  `tag_fetcher` / `tag_updater` / `vip_decrypt` / `soundalike`），如看到相关导入说明用例已过期。
