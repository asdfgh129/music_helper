# 测试说明

## 运行

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q                        # 全量
python -m pytest tests/test_scan.py -v     # 单个文件

# 没装 pytest 时
python -m unittest discover -s tests -p 'test_*.py'
```

- pytest 配置在 `pyproject.toml`：`testpaths = ["tests"]`，只收集 `test_*.py`。
- 所有用例都跑在 `tempfile` 临时目录里，不触碰真实音乐库，也不需要网络。
- 样本音频是 `tests/fixtures/1.flac`，仅手工脚本与文档示例使用。

## 目录

```
tests/
├── fixtures/1.flac        # 测试样本
├── manual/                # 需要网络与密钥的手工脚本，不被 pytest 收集
│   └── manual_musicbrainz.py
└── test_*.py              # 自动测试：文件名 = 被测模块名
```

## 覆盖矩阵

| 文件 | 覆盖内容 |
|---|---|
| `test_config.py` | 目录/扩展名/外部程序配置、版本号静态化、`validate()`、`config.ini` 优先级与相对路径解析 |
| `test_utils.py` | 日志初始化（可重复调用不叠 handler、debug 级别）、月份格式与当前月份 |
| `test_naming.py` | 「歌手 - 歌名」解析与规范化、多艺术家拆分、标准化、版本标记、匹配评分 |
| `test_scan.py` | 单次遍历：音频过滤、递归开关、跳过目录、月份过滤、扩展名白名单、去重与排序 |
| `test_lyrics.py` | 缺失歌词、孤立歌词、嵌套目录、五种音频扩展名 |
| `test_dedupe.py` | 重复判定（标签+时长、文件名+时长）、版本标记、保留策略 |
| `test_check.py` | 入库判定：核心标签、文件名/标签一致性、封面不参与 |
| `test_pipeline.py` | `WORKSPACE_DIR` 顶层完整文件保留、未达标文件移入 `INCOMPLETE_DIR`，dry-run 不移动 |
| `test_organize.py` | 年代目录边界、归档目标路径、无法归档清单、计划生成 |
| `test_ops.py` | 操作计划：dry-run、移动/改名、重名避让、回收站、journal、拷贝 |
| `test_report.py` | 报告渲染、CSV 导出、检查项与修复计划 |
| `test_soundalike.py` | 外部工具包装：`-db` / `-temp` / `-move-interactive`、成功/失败/超时/缺失可执行文件、CWD |
| `test_decrypt.py` | 解密后加密原文件的三种去向、暂存区快照排除、只搬自己动过的文件 |
| `test_tagger.py` | MusicBrainz 解析、QQ/网易结果筛选、双平台择优、标签完整性 |
| `test_git_uplink.py` | 出境代理工具：节点配置解析、单节点配置生成、环境变量注入（不连网） |

## 手工/网络用例

`tests/manual/` 下的脚本需要真实网络与 AcoustID key，不参与自动测试。
`manual_musicbrainz.py` 用 `--mode` 区分两条链路：

```bash
python tests/manual/manual_musicbrainz.py                # 全链路：fpcalc → AcoustID → MusicBrainz
python tests/manual/manual_musicbrainz.py --mode api     # 裸 API，用来区分网络问题与匹配链路问题
python tests/manual/manual_musicbrainz.py --debug        # 打开调试日志
```

## 约定

- 用例不写入仓库内的真实音乐库，全部使用 `tempfile` 临时目录。
- 不依赖已删除的旧模块（`metadata` / `file_operations` / `archive` / `duplicate` / `lrc` /
  `tag_fetcher` / `tag_updater` / `vip_decrypt` / `soundalike`），如看到相关导入说明用例已过期。
- 新增检查项时，优先在 `core/` 写纯函数，再在 `tests/` 补对应用例——`core/` 不允许联网与删除文件。
- 需要 mock 配置路径时，用 `unittest.mock.patch.object(config, ...)`，并在 `tearDown` 里恢复。
