# 更新日志

本文件记录 Music Helper 的所有重要变更。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

自 `0.2.0` 起版本号手工维护在 `config.py: __version__`，每次发版必须同步本文件。
此前的 `xx.xx-b{时间戳}` 由运行时生成（每次启动都会变），已废弃。

## [Unreleased]

### 新增

- **`scripts/git_uplink.py`**：用已采集的免费节点临时自建本地代理，供 `git pull` / `push`
  在 github.com:443 被重置的环境下使用。单文件（仅标准库）、单内核（mihomo）、单节点全局模式，
  逐条试节点并探测 `https://github.com/`，通了就以 `-c http.proxy` 注入 git 命令；支持
  `run` / `push` / `pull` 一次性调用与 `start` + `env` 常驻两种用法。
  与 free-nodes 空间的 `uplink.py` 相比不复刻四内核与协议转换，只借用其节点池与内核二进制。
- `docs/git-proxy.md` 与 `test/test_git_uplink.py`（16 例，纯逻辑、不连网）。

### 计划中

- 支持更多音乐平台（Spotify、Apple Music 等）
- Web GUI 界面
- Docker 部署支持

## [0.4.0] - 2026-10-30

全仓审计后的一轮精简：删除无人引用的第二套标签实现与死文件，测试补齐到核心层。

### 移除

- **`music_tagger` 里的并行标签实现**：`core.py`、`matcher.py`、`utils.py`、`zhconv.py`
  与 558 KB 的 `zhcdict.json`。这套 `MusicTagger` / `SmartTagClient` 只有示例脚本与测试在调，
  主流程走的是 `services/tagger.py`；同一件事两处可改，已统一到后者。
- **不可用的平台客户端**：`platforms/{kugou,kuwo,migu,acoustid}.py`。酷狗/酷我/咪咕上游接口
  早已失效，`__init__.py` 里本来也整段注释着；`AcoustidClient` 只被上面那套实现使用。
- **`Fingerprint/` 下 3 个示例脚本**：它们 `from fingerprint_matcher import ...`，而模块早已
  改名 `musicbrainz_matcher.py`，实际跑不起来。
- **`examples/music_tagger_demo.py`**：演示的是已删除的 `MusicTagger` API。
- **`utils.py` 的 8 个兼容壳**：`create_operation_log`、`detect_language`、`has_lrc_file`、
  `check_filename_format`、`parse_filename`、`normalize_text`、`split_artist`、
  `get_file_modification_month` 生产代码零调用，仅 `test_utils` 经由它们测 `core.naming`。
  现在 `utils.py` 只剩日志与月份校验，测试直接导入 `core.naming`。

### 修复

- `--trash-dup` 优先于「移入待处理目录」：此前 `--check --fix --trash-dup` 仍会把重复文件
  移到 `review/重复文件/`，显式参数被默认行为覆盖。
- `--check --fix --no-move` 生效：此前 `flow_check` 只看 `--fix`，`--no-move` 被忽略。
- `--only-check-file-name` 现在只做文件名检查，不再跑全套（标签/重复/歌词）。
- 非 UTF-8 控制台（如英文 Windows 的 cp1252）下 `main.py --help` 不再因打印中文抛
  `UnicodeEncodeError`。
- `requirements.txt` 的两个包名/版本修正：`music-tag>=0.4.3`（PyPI 最高版本）、
  `PyExecJS`（`execjs` 只是导入名）。此前全新环境装不上依赖，CI 四个 test job 全挂。

### 文档

- `docs/usage.md` 重写为完整使用说明：全部参数逐条解释、三条主流程 + 七个单一动作、
  产物与回滚、场景速查、环境变量、退出码、使用禁忌。

### 变更

- 测试样本 `1.flac` → `test/fixtures/1.flac`；需要联网的手工脚本 → `test/manual/`
  （仍以 `manual_` 开头，不被 pytest 收集）。
- `qqmusic_analyzer.py`（抓包分析，与应用无关）→ `scripts/qqmusic_analyzer.py`。
- `music_tagger` 现在只导出 `QQMusicApi`、`NetEaseMusicClient` 两个客户端。
- 文档同步：`README` 目录结构、`docs/architecture` 的 tagger 依赖说明、
  `docs/fingerprint` 与 `docs/troubleshooting` 的脚本路径、`test/README` 覆盖矩阵。

### 新增测试

- `test_tagger.py`：MusicBrainz 解析、QQ/网易结果筛选、双平台择优、标签完整性（17 例）
- `test_scan.py`：遍历/递归/跳过目录/月份过滤/扩展名白名单/去重排序（10 例）
- `test_lyrics.py`：缺失与孤立歌词（6 例）
- `test_organize.py`：年代边界、归档路径、计划生成（11 例）

用例总数 125 → 135，`core` 层除 `tags.py` 外均有直接覆盖。

## [0.3.0] - 2026-10-30

面向「日常可用 + 可持续维护」的一轮整理：修正解密后原文件的去向、补齐 CI、重写文档。

### 变更

- **解密后的加密原文件默认搬回 VIP 下载目录**（`ENCRYPTED_SOURCE_MODE=return`）。
  只搬本次运行移入临时目录的那几个文件，不再有「整层搬运」的副作用。
  其他模式：`trash`（进回收站）、`keep`（留在临时目录）。
- 文档体系按 GitHub 惯例重整：根目录只留 `README.md`、`CHANGELOG.md`、`CONTRIBUTING.md`、
  `LICENSE`，其余归入 `docs/`，历史文档归档到 `docs/history/`。
- 版本号提升至 `0.3.0`。

### 新增

- `.github/workflows/ci.yml`：Ubuntu/Windows × Python 3.11/3.12 矩阵，跑语法编译、
  导入冒烟、单元测试、命令行可用性；另有文档链接检查与仓库卫生两个独立 job。
- `scripts/check_docs.py`：校验 Markdown 相对链接，避免重构后留下死链（已接入 CI）。
- `pyproject.toml`：pytest 与 ruff 配置（项目本身不作为分发包发布）。
- `docs/` 全套文档：规格、用法、配置、功能规则、架构、指纹、故障排查。
- `test/test_decrypt.py`：覆盖加密原文件的三种处理模式，并验证「只搬自己动过的文件」。
- `CONTRIBUTING.md`、`LICENSE`。

### 移除

- 根目录 `CLEANUP_SUMMARY.md`、`PROJECT_CLEANUP_SUMMARY.md`、`DEBUG_MODE_GUIDE.md`、
  `DEBUG_MODE_SUMMARY.md` 合并进 `docs/history/` 后删除。
- `Doc/` 目录（内容并入 `docs/`，`CHANGELOG.md` 提到仓库根目录）。

## [0.2.0] - 2026-10-30

全量重构：修复阻塞级缺陷、合并重复实现、补齐规划中缺失的功能。

### 修复（阻塞级，此前主程序无法启动）

- **`music_tagger` 包不可导入**：`matcher.py` / `core.py` 使用 `from ..utils import split_artist`
  越出顶层包，新增 `music_tagger/utils.py` 改为包内相对导入。
- **`create_operation_log()` 返回 tuple**，5 处调用方按 Logger 使用导致 `AttributeError`，改为统一返回 Logger。
- **`file_operations.py` 13 处裸 `main_logger`**（缺 `utils.` 前缀）导致 `NameError`。
- **`main.py` 引用不存在的 `args.check_master`**，默认流程第 4 步必崩。
- **`--archive` 是死参数**（声明后从未读取），现已接线。
- **config 循环导入**（config → Fingerprint → config）导致 `FPCALC_LENGTH` 永远回退默认值。

### 安全

- `move_decrypted_files_back()` 原本会把 `TEMP_COMPLETED_DIR` 顶层**所有**文件搬进 VIP 下载目录，
  改为只处理本次运行新产生的文件。
- 全部 `os.remove()` 替换为「移入 `log/_trash`」，并记录 `log/journal.jsonl`。
- 文件名冲突时不再直接删除原文件，改为 `_1` 后缀让位。
- 新增 `--dry-run`：先出计划再执行。
- 缺封面/专辑/年份只报告，不再把文件挪出库；仅「歌曲名/歌手缺失」或「文件名与标签矛盾」才移入待处理目录。
- 外部程序调用统一加超时（`MUSIC_HELPER_TIMEOUT`）并检查 `returncode`。

### 新增

- `core/` 层：`model` / `scan` / `naming` / `tags` / `lyrics` / `dedupe` / `organize` / `check` / `report` / `ops`。
- `services/` 层：`decrypt` / `soundalike` / `tagger`。
- **检查报告**（规划模块 8）：`log/reports/report-*.md` + `review-*.csv`。
- **重复判定加时长比对**（规划模块 5），容差 `DURATION_TOLERANCE = 3s`。
- **手动归档入库**（规划 3.4）：`--manual-archive` 按标签重命名后直接归档进主目录。
- `--limit`、`--no-move`、`--trash-dup`、`--report-dir`、`--fix`。
- 配置支持环境变量覆盖（`MUSIC_HELPER_*`）。

### 重构（删除的模块，逻辑已合并）

| 删除 | 合并到 |
|---|---|
| `metadata.py` | `core/tags.py` |
| `file_operations.py` | `core/{scan,lyrics,organize,check}.py` |
| `archive.py` | `core/organize.py` + `core/tags.py` |
| `duplicate.py` | `core/dedupe.py` |
| `lrc.py` | `core/lyrics.py` |
| `tag_fetcher.py` + `tag_updater.py` | `services/tagger.py` |
| `vip_decrypt.py` | `services/decrypt.py` |
| `soundalike.py` | `services/soundalike.py` |

### 变更

- 版本号改为手工维护（`0.2.0`）。
- 日志不再输出到 `D:\music`，统一为项目内 `log/`。
- `.gitignore` 修正 `。DS_Store` 全角句号，新增 `log/*`、`.pytest_cache/`；`.DS_Store` 移出版本库。

### 测试

- 用例改为 pytest，覆盖命名、评分、去重、归档、操作计划、报告、检查、配置、声纹服务。
- 网络类脚本改名为 `test/manual_*.py`，不再被自动收集。

## 历史版本（0.1 ~ 0.6-b*）

以下版本使用运行时时间戳作为版本号，保留记录以便追溯，不再更新。

### 0.6-b1772100000 - 2026-03-08

- 新增 Debug 模式：`--debug` 全链路传递，MusicBrainz / 指纹 / 声纹 / 标签各环节输出中间变量。
- `soundalike.exe` 在 debug 下追加 `-log-sec=1`。

### 0.5-b1772000000 - 2026-03-06

- 修复 macOS 上 MusicBrainz 的 SSL 证书校验失败。
- 清理临时测试脚本与报告，测试统一收到 `test/`。

### 0.4-b1771563799 - 2026-02-20

- 分离 VIP 加密文件与普通文件的处理流程，普通文件改为拷贝而非移动。

### 0.3-b1771562924 - 2026-02-20

- 日志统一到项目内 `log/`。
- VIP 解密后原文件搬回原目录并删除加密文件；新增 `NETEASE_VIP_EXTENSIONS` / `QQ_VIP_EXTENSIONS`。

### 0.2-b1771550000 - 2026-02-19

- 统一导入风格（`import module` + `module.func()`）。

### 0.1-b1771469452 - 2026-02-19

- 首个版本：引入版本号管理、`--version` 与变更日志。

## 版本规范

- `MAJOR`：不兼容的行为变更（例如文件搬运规则、目录结构）。
- `MINOR`：向后兼容的新功能。
- `PATCH`：向后兼容的缺陷修复。

发版检查清单：

1. 更新 `config.py` 的 `__version__`；
2. 在本文件顶部新增对应条目；
3. 确认 `python main.py --version` 输出一致；
4. 打 tag：`git tag -a v0.3.0 -m "v0.3.0"`。
