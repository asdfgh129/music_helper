# 功能规格

本文是项目的原始需求规格（重构前的 `Doc/项目规划.md`），并补上每项功能当前的实现落点。
**规格本身是需求，不是现状**——两者不一致时以本文的「实现位置」为准去核对代码。

## 一、功能模块

| # | 模块 | 要求 | 实现位置 |
|---|---|---|---|
| 1 | 声纹去重 | 对音乐文件做声纹分析，识别重复文件，并建立数据库记录已存在的文件 | `services/soundalike.py: run()` |
| 2 | 文件名检查 | 检查命名是否符合 `[歌手] - [歌曲]`，并提取歌手/歌曲信息 | `core/naming.py`、`core/check.py` |
| 3 | 元数据检查 | 检查歌手、歌曲名是否与文件名一致 | `core/check.py: _consistency_problem` |
| 4 | 标签检查 | 检查歌手、歌曲名、专辑、年份、封面是否齐全，必要时更新 | `core/tags.py`、`services/tagger.py` |
| 5 | 重复检查 | 按歌手 + 歌名 + 时长判断；文件名去掉 `(1)(2)` 后相同且时长相近也算重复 | `core/dedupe.py` |
| 6 | 歌词检查 | 检查同名 `.lrc` 是否存在，以及是否只有歌词没有音频 | `core/lyrics.py` |
| 7 | 文件归档 | 按月份参数取 QQ/网易云的文件，按年份分类存储 | `core/scan.py`、`core/organize.py` |
| 8 | 检查报告 | 把不一致文件移到指定目录，并生成检查报告供后续手动归档 | `core/report.py`、`core/check.py: plan_fixes` |
| 9 | 主目录一致性 | 检查主目录文件与 soundalike 数据库记录是否一致 | `services/soundalike.py: check()` |
| 10 | VIP 解密 | 解密 QQ 音乐 / 网易云 VIP 目录中的加密文件 | `services/decrypt.py` |
| 11 | 普通文件移动 | 把未被识别为重复的文件移到指定目录 | `services/soundalike.py`（`-move-interactive` 输出到 `TEMP_MOVE_DIR`）、`main.py: _copy_normal_files` |
| 12 | 声纹 → 标签 | 按声纹从 MusicBrainz 取标签并写入文件 | `services/tagger.py` + `fingerprint/` |
| 13 | 文件名 → 标签 | 按文件名从 QQ 音乐 / 网易云 API 取标签并写入 | `services/tagger.py` + `music_tagger/platforms/` |
| 14 | 日志 | 记录运行中的错误、警告、调试信息 | `utils.py`、`log/journal.jsonl` |

### 实现状态说明

| 状态 | 含义 | 涉及模块 |
|---|---|---|
| 完整 | 规格要求的行为已在单一实现中覆盖 | 1、2、5、6、7、8、9、10、12、13、14 |
| 有边界约束 | 行为已实现，但收窄了触发条件（出于安全考虑） | 3、4：`须人工处理` 只对核心标签（歌曲名/歌手）缺失或标签矛盾生效，缺封面/专辑/年份仅报告 |
| 依赖外部程序 | 结果取决于外部工具，Python 侧只做调用与结果搬运 | 1、9、11（`soundalike.exe`）、10（`um.exe` / Frida）、12（`fpcalc`） |

### 与原始规格的差异

1. **平台范围收窄**：原始设想包含酷狗、酷我、咪咕，对应客户端已删除（上游接口不可用），
   实际只有 QQ 音乐与网易云两个平台。
2. **模块 11 语义**：「把主目录中未被识别为重复的文件移到指定目录」与现有流水线方向相反
   （流水线是「下载目录 → 临时目录 → 主目录」）。当前实现为：声纹去重时由 `soundalike.exe`
   以 `-move-interactive` 把重复项交互式移到 `TEMP_MOVE_DIR`，不重复的正常文件留在主目录。
3. **模块 7 月份参数**：`--month` 只影响解密与普通文件拷贝阶段的**取件范围**（按文件修改月份），
   归档本身按标签年份建目录。

## 二、操作流程

### 流程 1：主目录检查 `--check`

| 步骤 | 内容 | 实现 |
|---|---|---|
| 1.1 | 声纹去重并建立数据库 | `services/soundalike.run()`（`--soundalike` 单独触发） |
| 1.2 | 数据库与目录文件一致性 | `services/soundalike.check()` |
| 1.3 | 文件名格式检查 | `core/check.py: check_library` |
| 1.4 | 文件名与元数据匹配检查 | `core/check.py: _consistency_problem` |
| 1.5 | 标签完整性检查 | `core/tags.py: missing_tag_fields` |
| 1.6 | 歌手 + 歌名 + 时长重复检查 | `core/dedupe.py` |
| 1.7 | 同名歌词 / 孤立歌词检查 | `core/lyrics.py` |
| 1.8 | 不一致文件移入指定目录并生成报告 | `core/report.py` + `core/check.py: plan_fixes`（需 `--fix`） |

### 流程 2：临时目录归档 `--archive`（等同默认流程）

| 步骤 | 内容 | 实现 |
|---|---|---|
| 2.1 | 按月份拷贝 QQ VIP 目录文件到临时目录 | `services/decrypt.py: decrypt_qq`（移入） |
| 2.2 | 解密 QQ 临时目录 | 同上（Frida / `decrypto`） |
| 2.3 | 按月份拷贝网易云文件到临时目录 | `services/decrypt.py: decrypt_netease` |
| 2.4 | 解密网易云临时目录 | 同上（`um.exe`） |
| 2.5 | 拷贝普通文件到临时目录 | `main.py: _copy_normal_files` |
| 2.6 | 临时目录声纹去重 | `services/soundalike.run(with_temp=True)` |
| 2.7 | 文件名检查 | `core/check.py` |
| 2.8 | 元数据一致性检查 | `core/check.py` |
| 2.9 | 标签检查与补全（先声纹，再文件名） | `services/tagger.py` |
| 2.10 | 按年份归档 | `core/organize.py` |
| 2.11 | 不一致文件移入指定目录并生成报告 | `core/check.py: plan_fixes` + `core/report.py` |

### 流程 3：手动归档 `--manual-archive`

| 步骤 | 内容 | 实现 |
|---|---|---|
| 3.1 | 用标签工具更新歌手/歌名/专辑/年份/封面 | `services/tagger.py` |
| 3.2 | 按更新后的标签重命名为 `[歌手] - [歌曲]` | `main.py: flow_manual_archive` |
| 3.3 | 按更新后的标签归档 | `core/organize.py` |
| 3.4 | 把临时目录文件移入主目录 | 3.3 的归档目标根就是 `MAIN_DIR`，一步完成 |
| 3.5 | 记录日志 | `utils.py`、`log/journal.jsonl` |

## 三、非功能要求

| 要求 | 落地方式 |
|---|---|
| 破坏性操作可预览 | 所有动作先成 `Plan`，`--dry-run` 打印完整计划 |
| 破坏性操作可追溯 | `log/journal.jsonl` 每行一条（时间/动作/源/目标/原因/成败） |
| 不真删数据 | 删除 = 移入 `log/_trash/`，保留原始文件名与内容 |
| 可选依赖缺失不影响启动 | 外部程序、网络库、`mutagen` 全部延迟导入或降级 |
| 大库扫描性能 | `core/scan.py` 单次遍历建索引，替代原先每个目录 `os.walk` 四遍 |
