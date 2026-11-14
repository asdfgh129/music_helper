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
| `test_build_docs_index.py` | 文档索引生成器：状态收集、Markdown 渲染、`--check` 新鲜度 |
| `test_build_exe.py` | 绿色版打包脚本纯函数：工具清单、可选 FFmpeg 缺失不告警、打包清单 |
| `test_check.py` | 入库判定：核心标签与内嵌封面、文件名/标签一致性、歌词不参与 |
| `test_config.py` | 目录/扩展名/外部程序配置、版本号静态化、`validate()`、`config.ini` 优先级与相对路径解析 |
| `test_decrypt.py` | 解密后加密原文件的三种去向、暂存区快照排除、只搬自己动过或用户已选的文件 |
| `test_dedupe.py` | 重复判定（标签+时长、文件名+时长）、版本标记、同音质留更小文件的保留策略 |
| `test_git_uplink.py` | 出境代理工具：节点配置解析、单节点配置生成、环境变量注入（不连网） |
| `test_library.py` | 库「是否已初始化」判据与待办动作 |
| `test_lyrics.py` | 同名歌词路径、编码探测（UTF-8 / GB18030 / BOM）、LRC 结构化、多时间戳 / 双语 / `[offset:]`、逐字片段、`set_offset()` |
| `test_media.py` | 只读媒体层纯逻辑：路径白名单、Range 解析、MIME 矩阵、歌词 / 封面载荷、偏移与工作区写权限 |
| `test_media_api.py` | 试听接口的 HTTP 回归：206 / 416 / HEAD、封面、逐字字段、transcode 409 / 400、白名单拒绝 |
| `test_naming.py` | 「歌手 - 歌名」解析与规范化、多艺术家拆分、标准化、版本标记、匹配评分 |
| `test_ops.py` | 操作计划：dry-run、移动/改名、重名避让、回收站、journal、拷贝 |
| `test_organize.py` | 年代目录边界、归档目标路径、无法归档清单、计划生成 |
| `test_pipeline.py` | `WORKSPACE_DIR` 顶层完整文件保留、未达标文件移入 `INCOMPLETE_DIR`，dry-run 不移动 |
| `test_qq_client.py` | QQ 客户端安装检测 / 启动 / 登录确认 / 打补丁（全桩，不启动真实客户端） |
| `test_quality.py` | 音质比较：无损与有损、压缩无损、存储偏好与替换描述 |
| `test_report.py` | 报告渲染、CSV 导出、检查项与修复计划 |
| `test_scan.py` | 单次遍历：音频过滤、递归开关、跳过目录、月份过滤、扩展名白名单、去重与排序 |
| `test_settings_store.py` | 目录设置校验与 `config.ini` 持久化（临时 ini，不碰仓库配置） |
| `test_soundalike.py` | 外部工具包装：`-db` / `-temp` / `-move-interactive`、成功/失败/超时/缺失可执行文件、CWD |
| `test_source_finder.py` | 解密后来源检索 fail-soft：网络异常不影响已解出的文件 |
| `test_steps.py` | 八步向导预览数据：候选分组、单曲详情 / 保存 / 在线取标签（用 tempfile） |
| `test_tagger.py` | MusicBrainz 解析、QQ/网易结果筛选、双平台择优、标签完整性 |
| `test_tags.py` | 一次读三件事、封面探测、内嵌封面读写（9 种格式） |
| `test_transcode.py` | 本机解码状态机、命令与缓存键、进度解析、LRU、WMA / DSF 真实解码（探测到 FFmpeg 才跑） |
| `test_utils.py` | 日志初始化（可重复调用不叠 handler、debug 级别）、月份格式与当前月份 |
| `test_wizard_api.py` | 八步 Web 路由 HTTP 回归：preview / run、目录设置与浏览、任务队列、单曲编辑、参数校验与任务入参（后台 worker 全隔离） |

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
