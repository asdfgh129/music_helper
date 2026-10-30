# 使用说明（完整用法手册）

`main.py` 是唯一入口。本文覆盖**全部参数、全部流程、全部单一动作、全部环境变量**，
按「先跑起来 → 查命令 → 看流程 → 抄场景」的顺序组织。

- 只想快速跑一遍：看 [1. 三分钟上手](#1-三分钟上手)
- 想查某个参数是什么意思：看 [4. 参数详解](#4-参数详解)
- 想抄一条现成的命令：看 [7. 典型场景速查](#7-典型场景速查)
- 路径/阈值怎么改：见 [configuration.md](configuration.md)
- 每条检查的判定规则：见 [features.md](features.md)

## 目录

1. [三分钟上手](#1-三分钟上手)
2. [运行前检查](#2-运行前检查)
3. [命令总览](#3-命令总览)
4. [参数详解](#4-参数详解)
5. [流程详解](#5-流程详解)
6. [产物、日志与回滚](#6-产物日志与回滚)
7. [典型场景速查](#7-典型场景速查)
8. [环境变量](#8-环境变量)
9. [退出码与报错](#9-退出码与报错)
10. [使用禁忌](#10-使用禁忌)

---

## 1. 三分钟上手

```bash
# 0. 装依赖（只需一次）
python -m pip install -r requirements.txt

# 1. 确认程序可用
python main.py --version          # 打印版本，例如 main.py v0.3.0
python main.py --help             # 全部参数与示例

# 2. 先体检，不动文件
python main.py --check --dry-run

# 3. 满意后再执行
python main.py --check            # 只出报告
python main.py --check --fix      # 出报告 + 执行修复
```

**第一次接触这个库，请务必先跑 `--dry-run`。** 所有流程都支持它，会把「本来要做什么」
打印出来但一行都不执行。

三条主流程一句话概括：

| 想做什么 | 命令 |
|---|---|
| 把下载目录里当月的新歌整理进主目录 | `python main.py` |
| 体检已有音乐库 | `python main.py --check` |
| 把临时目录里剩下的歌（人工确认过的）入库 | `python main.py --manual-archive` |

---

## 2. 运行前检查

### 2.1 Python 与依赖

- Python **3.11+**（用到 `match` 之外的现代语法与 `dataclass` 默认值）
- `python -m pip install -r requirements.txt`
- 开发/测试额外装 `python -m pip install -r requirements-dev.txt`

缺依赖时程序会在导入阶段报 `ModuleNotFoundError`，先把依赖装齐再排查其他问题。

### 2.2 目录是否就绪

程序启动时会打印当前配置，并对关键目录做存在性检查：

```
INFO: 配置: {'版本': '0.3.0', '主目录': 'D:\\music', ...}
WARNING: 主目录不存在: D:\music
WARNING: 临时目录不存在: G:\Temp
```

**WARNING 不会中断执行**，但后续扫描会得到 0 个文件。看到这类警告先确认盘符。

### 2.3 外部程序是否可用

| 程序 | 默认路径 | 缺失后果 |
|---|---|---|
| `soundalike.exe` | `fingerprint/soundalike.exe` | 声纹去重/建库/一致性检查失败，其余流程可用 |
| `um.exe` | `decrypto/um.exe` | 网易云 `.ncm` 解密失败 |
| Frida + 运行中的 QQMusic | 由 `decrypto/qq.py` 调用 | QQ 音乐 `.mflac/.mgg` 解密失败 |

两个 exe 随仓库分发，克隆即可用；换位置就设 `MUSIC_HELPER_SOUNDALIKE_EXE`、
`MUSIC_HELPER_UM_EXE`。

### 2.4 自检命令

```bash
python -m compileall -q .                 # 语法
python -c "import main"                   # 导入链
python -m pytest -q                       # 单元测试（需 requirements-dev.txt）
python main.py --checkdb                  # 只说声纹库与主目录是否一致
```

---

## 3. 命令总览

### 3.1 一个时刻只跑一个流程

`main.py` 按下面的**固定顺序**判断，命中即执行并返回，不会叠加执行：

| 顺序 | 参数 | 触发什么 |
|---|---|---|
| 1 | `--init` | 初始化/更新声纹库（不扫临时目录） |
| 2 | `--checkdb` | 声纹库与主目录一致性检查 |
| 3 | `--soundalike` | 声纹去重（主目录 + 临时目录） |
| 4 | `--only-decrypt` | 只解密当月 VIP 文件 |
| 5 | `--only-update-tag {master,temp}` | 只更新标签 |
| 6 | `--only-check-file-name {master,temp}` | 只检查文件名格式 |
| 7 | `--only-archive` | 只做临时目录的年份归档 |
| 8 | `--manual-archive`（别名 `--archive-manual`） | 手动归档：标签 → 改名 → 入库 |
| 9 | `--check` | 主目录体检 |
| 10 | 无流程参数 | 临时目录完整流水线 |

> `--archive` 不在判定表里，它是「默认流水线」的显式写法，便于在 bat/脚本里表达意图。
> `--version` / `--help` 由 argparse 直接处理，优先级最高。

**冲突示例**：`python main.py --init --check` 只执行 `--init`，`--check` 被忽略。
需要两件事就分两条命令跑。

### 3.2 全部参数一览

| 参数 | 取值 | 默认 | 说明 |
|---|---|---|---|
| `--version` | — | — | 打印版本后退出 |
| `--help` | — | — | 打印帮助与示例后退出 |
| `--debug` | 开关 | 关 | DEBUG 级日志；声纹工具追加 `-log-sec=1` |
| `--dry-run` | 开关 | 关 | 只生成计划，不移动/改名/写标签 |
| `--month` | `YYYYMM` | 当前月 | 只处理该月修改过的文件 |
| `--limit` | 整数 | `0`（不限） | 每个阶段最多处理 N 个文件 |
| `--report-dir` | 目录 | `log/reports` | 报告输出目录 |
| `--no-move` | 开关 | 关 | 不把不一致文件移出原位 |
| `--trash-dup` | 开关 | 关 | 重复文件进回收站（默认移入待处理目录/只报告） |
| `--fix` | 开关 | 关 | 配合 `--check` / `--only-check-file-name` 执行修复 |
| `--check` | 开关 | — | 主目录体检 |
| `--init` | 开关 | — | 初始化/更新声纹库 |
| `--checkdb` | 开关 | — | 声纹库一致性检查 |
| `--soundalike` | 开关 | — | 声纹去重 |
| `--only-decrypt` | 开关 | — | 只解密 |
| `--only-update-tag` | `master` / `temp` | — | 只更新标签 |
| `--only-check-file-name` | `master` / `temp` | — | 只检查文件名 |
| `--only-archive` | 开关 | — | 只做年份归档 |
| `--manual-archive` | 开关 | — | 手动归档入库（别名 `--archive-manual`） |
| `--archive` | 开关 | — | 等同默认流水线 |
| `--skip-vip` | 开关 | 关 | 跳过解密 + 普通文件拷贝 |
| `--skip-fingerprint` | 开关 | 关 | 跳过去重 |
| `--skip-tag-update` | 开关 | 关 | 跳过标签更新 |
| `--skip-check` | 开关 | 关 | 跳过检查 |
| `--skip-organize` | 开关 | 关 | 跳过年份归档 |

---

## 4. 参数详解

### 4.1 `--dry-run`（最该先用的参数）

把「要做什么」算出来、打印出来、写进日志，但**不执行任何移动、改名、写标签**。

```bash
python main.py --dry-run                    # 整条流水线试跑
python main.py --check --fix --dry-run      # 看修复计划会动哪些文件
python main.py --manual-archive --dry-run   # 看会入库到哪个目录
```

适合在换盘符、改规则、批量处理之前先确认计划。计划超过 30 条时日志会省略，用 `--debug`
查看完整清单。

### 4.2 `--month YYYYMM`

- 只影响**扫描范围**：修改时间落在该月的文件。
- 默认当前月（按系统日期）。
- 格式必须是 6 位数字，年份 1900–2099、月份 1–12，否则报错退出（退出码 1）。
- 主要用在「补齐处理某个月」的场景：

```bash
python main.py --month 202406          # 重新处理 2024 年 6 月的漏网文件
python main.py --only-decrypt --month 202406
```

> `--check` / `--only-update-tag` / `--only-archive` 等**不使用** `--month`，
> 它们始终全量扫描目标目录。

### 4.3 `--limit N`

每个阶段最多处理 N 个文件，`0` 表示不限制。用于大批量前的小样本验证：

```bash
python main.py --limit 5 --dry-run      # 只看 5 个文件会发生什么
python main.py --limit 5                # 真的只处理 5 个
```

注意它是「每个阶段各取前 N 个」，不是「整条流水线总共 N 个」。

### 4.4 `--fix`

只有两个命令认它：

| 命令 | 不加 `--fix` | 加 `--fix` |
|---|---|---|
| `--check` | 只出报告 | 出报告 + 执行修复动作 |
| `--only-check-file-name` | 只报告文件名问题 | 执行规范化改名 |

修复动作**只有三类**，且顺序固定（重复 → 移动 → 改名，避免同名冲突）：

1. **重复文件**：`--trash-dup` → 进 `log/_trash/`；否则 `--no-move` 未设 → 移入
   `review/重复文件/`；`--no-move` 已设 → 原样留下，只报告。
2. **必须人工处理的文件**：歌曲名或歌手标签缺失、文件名与标签矛盾 →
   移入 `review/<问题类型>/`。缺封面/专辑/年份**不会**移动文件。
3. **文件名规范化**：只有单个 `-` 的 `A-B.ext` 改成 `A - B.ext`。含多个 `-` 或已有
   ` - ` 的不动（避免误伤 `AC-DC - Back in Black`）。

### 4.5 `--no-move`

只抑制「移出原位」，不影响改名、不影响报告、不影响 `--trash-dup`。

```bash
python main.py --check --fix --no-move   # 只改名 + 出报告，文件都留在原目录
```

### 4.6 `--trash-dup`

重复文件**进回收站而不是待处理目录**。优先级高于「移入待处理目录」。

```bash
python main.py --check --fix --trash-dup
```

回收站在 `log/_trash/`，同名文件自动加 `_1`、`_2` 后缀，**不会真正删除**。
确认无误后由你手动清空该目录。

### 4.7 `--skip-*`（只对默认流水线有效）

逐步关掉流水线中的阶段，用于「只补某一环」：

| 参数 | 关掉什么 |
|---|---|
| `--skip-vip` | 解密 + 普通文件拷贝 |
| `--skip-fingerprint` | 声纹去重（同时也会让标签更新少一条查证途径） |
| `--skip-tag-update` | 标签更新 |
| `--skip-check` | 检查与修复 |
| `--skip-organize` | 按年份归档 |

组合示例：

```bash
# 只做「标签 + 检查 + 归档」，完全不碰外部程序与网络解密
python main.py --skip-vip --skip-fingerprint

# 只做归档，其他全跳过（等价于 --only-archive 的流水线写法）
python main.py --skip-vip --skip-fingerprint --skip-tag-update --skip-check
```

### 4.8 `--report-dir DIR`

报告与 CSV 换个地方存。默认 `log/reports/`。

```bash
python main.py --check --report-dir D:/reports/2026-10
```

目录不存在会自动创建。

### 4.9 `--debug`

- 主日志降到 DEBUG，并打印操作计划的完整清单（默认只打印前 30 条）。
- 声纹去重时给 `soundalike.exe` 追加 `-log-sec=1`，输出秒级进度。

```bash
python main.py --check --debug 2>&1 | tee debug.txt
```

---

## 5. 流程详解

### 5.1 临时目录流水线（默认 / `--archive`）

**目标**：把「下载下来、还没整理」的歌变成「标签完整、文件名规范、按年份入库」的曲目。

```
① 解密 VIP（网易云 .ncm / QQ .mflac .mgg）
② 普通文件拷贝到临时目录（排除 VipSOngsDownload 子目录）
③ 声纹去重（主目录 + 临时目录）
④ 更新标签（声纹→MusicBrainz，再→QQ/网易云，顺带封面与歌词）
⑤ 检查并修复（文件名 / 元数据 / 标签 / 重复 / 歌词）
⑥ 按年份归档到主目录
⑦ 生成报告
```

| 阶段 | 实现 | 关掉的开关 | dry-run 行为 |
|---|---|---|---|
| ① 解密 | `services/decrypt.py` | `--skip-vip` | 只列出待解密文件 |
| ② 拷贝 | `core/ops.copy_items` | `--skip-vip` | **仍会拷贝**（拷贝非破坏性，不受 dry-run 抑制） |
| ③ 去重 | `services/soundalike.py` | `--skip-fingerprint` | **仍会调用**（外部程序自己做判断） |
| ④ 标签 | `services/tagger.py` | `--skip-tag-update` | 只查询不写入 |
| ⑤ 检查 | `core/check.py` | `--skip-check` | 只报告，不修复 |
| ⑥ 归档 | `core/organize.py` | `--skip-organize` | 只打印计划 |

> **注意**：`--dry-run` 的边界是「本程序自己的破坏性文件操作」。外部 exe（声纹）和
> 拷贝动作不受控。想在完全不产生副作用的前提下看流程，用
> `--skip-vip --skip-fingerprint --dry-run`。

**解密后加密原文件的去向**由 `MUSIC_HELPER_ENCRYPTED_MODE` 决定：

| 值 | 行为 |
|---|---|
| `return`（默认） | 搬回对应 VIP 下载目录，只搬本次解密涉及的文件 |
| `trash` | 移入 `log/_trash/` |
| `keep` | 留在临时目录，后续人工处理 |

`return` 模式下，加密原文件回到 VIP 目录后，下次同月份运行可能被再次扫到。
不想重复处理就改用 `trash`，或把处理完的加密文件移出 VIP 目录。

**归档规则**：`<库根>/<年代>/<年份>/歌手 - 歌名.ext`

```
D:\music\1980-1989\1985\邓丽君 - 我只在乎你.flac
D:\music\1950-1979\1979\...
D:\music\unknown\...        # 缺歌手/歌名/年份，等人工作业
```

### 5.2 主目录检查（`--check`）

**目标**：不动库，先体检；确认后再修。

```
步骤 1  声纹库与目录一致性（soundalike -check）
步骤 2  文件名格式
步骤 3  元数据一致性（文件名解析 vs 音频标签）
步骤 4  标签完整性（歌曲名/歌手/专辑/年份/封面）
步骤 5  重复文件（歌手+歌名+时长 / 去掉 (1)(2) 的文件名+时长）
步骤 6  歌词（缺失 / 孤立）
步骤 7  报告（Markdown + CSV），`--fix` 时执行修复
```

```bash
python main.py --check                        # 只体检、只出报告
python main.py --check --fix                  # 体检 + 修复
python main.py --check --fix --no-move        # 只改名，不搬文件
python main.py --check --fix --trash-dup      # 重复文件进回收站
python main.py --check --limit 100 --dry-run  # 先看前 100 个文件的计划
```

报告固定列出 6 类计数，**即使为 0 也会列出**，避免「没看到 = 没问题」的误判。

### 5.3 手动归档（`--manual-archive` / `--archive-manual`）

**目标**：处理「已经检查过、只差最后一步入库」的临时目录文件。

```
更新标签 → 按标签重命名为「歌手 - 歌名」 → 按标签年份归档进主目录
```

```bash
python main.py --manual-archive
python main.py --manual-archive --limit 20 --dry-run
python main.py --manual-archive --skip-fingerprint   # 不查声纹，只按文件名查在线标签
```

与流水线的区别：**不做解密、不做拷贝、不做去重**，也不做全项检查。
无法确定年份的文件进 `主目录/unknown/`，并在报告里列出缺哪些字段。

### 5.4 单一动作模式

七个「只做一件事」的命令，适合嵌进 bat / 计划任务。

#### `--init` — 初始化或更新声纹库

```bash
python main.py --init
python main.py --init --debug
```

扫描主目录建库（不扫临时目录）。首次使用、或大批入库后建议重跑一次。
内部调用：`soundalike.exe -move-interactive <TMP_MOVE> <MAIN_DIR>`。

#### `--checkdb` — 声纹库一致性

```bash
python main.py --checkdb
```

只检查数据库与磁盘文件是否对得上，不改动任何文件。退出码能反映结果（见第 9 节）。

#### `--soundalike` — 声纹去重

```bash
python main.py --soundalike
python main.py --soundalike --debug
```

主目录 + 临时目录一起比对，重复文件由 `soundalike.exe` 交互式移入
`MUSIC_HELPER_MOVE_DIR`（默认 `G:\Tmp`）。**这个动作会真的移动文件**，且不受
`--dry-run` 控制，先想清楚再跑。

#### `--only-decrypt` — 只解密

```bash
python main.py --only-decrypt
python main.py --only-decrypt --month 202406 --dry-run
```

只做 VIP 解密，不做拷贝、不做后续流程。适合「先把加密文件解出来看看」。

#### `--only-update-tag {master,temp}` — 只更新标签

```bash
python main.py --only-update-tag temp     # 补临时目录的标签
python main.py --only-update-tag master   # 补主目录的标签
```

只写标签与封面/歌词，不改名、不移动、不检查。

#### `--only-check-file-name {master,temp}` — 只检查文件名

```bash
python main.py --only-check-file-name master
python main.py --only-check-file-name temp --fix
```

只做文件名格式检查（不查标签、不查重复、不查歌词）。加 `--fix` 执行规范化改名。
比 `--check` 快得多，适合改名后快速复验。

#### `--only-archive` — 只做年份归档

```bash
python main.py --only-archive
python main.py --only-archive --dry-run
```

把临时目录的文件按标签年份归档进主目录，**不更新标签、不检查**。
标签不全的文件进 `unknown/`。

---

## 6. 产物、日志与回滚

### 6.1 文件都在哪

| 产物 | 位置 | 说明 |
|---|---|---|
| 运行日志 | `log/Music-YYYYmmdd_HHMMSS.log` | 每次运行一个，含配置快照 |
| 操作日志 | `log/journal.jsonl` | 每个动作一行 JSON，只追加 |
| 检查报告 | `log/reports/report-YYYYmmdd_HHMMSS.md` | 人读，摘要 + 明细表 |
| 待处理清单 | `log/reports/review-YYYYmmdd_HHMMSS.csv` | `类型,路径,说明`，UTF-8 BOM，Excel 直接打开 |
| 回收站 | `log/_trash/` | 所有「删除」的真正落点 |
| 待处理目录 | `G:\Tmp\review\` | 被移出原位的不一致文件，按问题类型分子目录 |

### 6.2 journal 字段

```json
{"time": "2026-10-30 20:12:31", "plan": "主目录检查-修复", "action": "rename",
 "src": "D:\\music\\A-B.flac", "dst": "D:\\music\\A - B.flac",
 "reason": "统一分隔符为「 - 」", "ok": true, "error": ""}
```

`action` 三种：`move` / `rename` / `trash`。`reason` 说明为什么动它。

### 6.3 怎么回滚

没有一键回滚命令，但 journal 里有完整的 `src`/`dst` 对应关系，可以逐条反向操作：

```bash
# 1. 找出最近一次运行动过的文件
#    （按时间过滤，只取成功的记录）
python - <<'EOF'
import json
rows = [json.loads(l) for l in open('log/journal.jsonl', encoding='utf-8')]
for r in rows[-20:]:
    if r['ok']:
        print(f"{r['action']:6} {r['src']}  ->  {r['dst']}")
EOF
```

手工把 `dst` 搬回 `src` 即可。回收站里的文件（`action: trash`）直接把文件移回原来的
`src` 路径就能恢复。

> 移动时同名文件会自动加 `_1` 后缀，所以 `dst` 字段记录的是**实际落点**，
> 按它反向搬不会覆盖别的文件。

---

## 7. 典型场景速查

### 7.1 首次使用

```bash
python main.py --version                      # 能跑
python main.py --check --dry-run              # 看现状
python main.py --check                        # 出第一份报告
python main.py --init                         # 建声纹库
```

### 7.2 日常：每月把新歌入库

```bash
python main.py --limit 20 --dry-run           # 小样本试跑
python main.py --limit 20                     # 小样本真跑
python main.py                                # 全量
```

### 7.3 只想整理文件名，不动别的

```bash
python main.py --only-check-file-name master --fix --dry-run
python main.py --only-check-file-name master --fix
```

### 7.4 只补标签（封面/年份/歌词）

```bash
python main.py --only-update-tag master --limit 50 --dry-run
python main.py --only-update-tag master
```

### 7.5 怀疑有重复

```bash
python main.py --check --limit 2000 --dry-run     # 先看报告
python main.py --check --fix --trash-dup          # 确认后清进回收站
```

### 7.6 清理混淆的下载目录

```bash
python main.py --skip-tag-update --skip-check --dry-run   # 只看跳过了什么
python main.py --only-decrypt --month 202410
```

### 7.7 换盘符 / 换机器试跑（不碰真实库）

```bash
# Linux / macOS / Git Bash
MUSIC_HELPER_MAIN_DIR=/tmp/lib \
MUSIC_HELPER_TEMP_DIR=/tmp/temp \
MUSIC_HELPER_REVIEW_DIR=/tmp/review \
python main.py --check --dry-run
```

```powershell
# PowerShell
$env:MUSIC_HELPER_MAIN_DIR="C:\tmp\lib"
$env:MUSIC_HELPER_TEMP_DIR="C:\tmp\temp"
python main.py --check --dry-run
```

### 7.8 排查「跑完什么都没变」

```bash
python main.py --check --debug 2>&1 | tee run.log
grep -E "WARNING|ERROR|扫描到|检查结果" run.log
tail -20 log/journal.jsonl
```

按这个顺序看：扫描到几个文件 → 有没有 WARNING → journal 里有没有记录。

### 7.9 大型库分段处理

```bash
python main.py --check --limit 500 --report-dir D:/reports/batch1
python main.py --check --limit 500 --report-dir D:/reports/batch2   # 同样取前 500
```

`--limit` 永远取「排序后的前 N 个」，不记进度。要真正分段请用 `--month` 或按子目录
分批设置 `MUSIC_HELPER_MAIN_DIR`。

---

## 8. 环境变量

全部路径都可以用环境变量覆盖，优先级高于 `config.py` 里的默认值。

| 变量 | 默认值 | 作用 |
|---|---|---|
| `MUSIC_HELPER_MAIN_DIR` | `D:\music` | 主目录（最终音乐库） |
| `MUSIC_HELPER_TEMP_DIR` | `G:\Temp` | 流水线工作目录 |
| `MUSIC_HELPER_MOVE_DIR` | `G:\Tmp` | 声纹去重的移出目录 |
| `MUSIC_HELPER_REVIEW_DIR` | `G:\Tmp\review` | 不一致文件的待处理目录 |
| `MUSIC_HELPER_NETEASE_DIR` | `G:\Neteasymusic` | 网易云下载目录（VIP 子目录为 `VipSOngsDownload`） |
| `MUSIC_HELPER_NETEASE_TMP` | `G:\NeTmp` | 网易云解密临时目录 |
| `MUSIC_HELPER_QQ_DIR` | `G:\QQMusic` | QQ 音乐下载目录（VIP 子目录同上） |
| `MUSIC_HELPER_QQ_TMP` | `G:\QQTmp` | QQ 音乐解密临时目录 |
| `MUSIC_HELPER_UM_EXE` | `decrypto/um.exe` | 网易云解密程序 |
| `MUSIC_HELPER_SOUNDALIKE_EXE` | `fingerprint/soundalike.exe` | 声纹工具 |
| `MUSIC_HELPER_TIMEOUT` | `3600` | 外部程序超时（秒） |
| `MUSIC_HELPER_ENCRYPTED_MODE` | `return` | 加密原文件去向：`return`/`trash`/`keep` |

阈值类参数（`FPCALC_LENGTH`、`DURATION_TOLERANCE`、`FINGERPRINT_THRESHOLD`、
`MAX_COVER_SIZE`）目前只写在 `config.py`，改文件即可，详见 [configuration.md](configuration.md)。

---

## 9. 退出码与报错

| 码 | 含义 |
|---|---|
| `0` | 正常结束（**报告里有待处理项也是 0**） |
| `1` | 参数错误（如月份格式不对）、`--init`/`--checkdb`/`--soundalike` 失败、未捕获异常 |
| `130` | 用户 `Ctrl+C` 中断 |

`--check` / 默认流水线不会因为「发现问题」返回非 0 —— 退出码只表示**程序是否正常跑完**。
要看结果请读报告。

常见报错与处理：

| 现象 | 原因 | 处理 |
|---|---|---|
| `主目录不存在` WARNING | 盘符/路径不对 | 设 `MUSIC_HELPER_MAIN_DIR` 或改 `config.py` |
| `找不到外部程序: ...soundalike.exe` | exe 不在默认位置 | 设 `MUSIC_HELPER_SOUNDALIKE_EXE` |
| `执行超时（>3600s）` | 外部程序卡死 | 调大 `MUSIC_HELPER_TIMEOUT`，或检查 exe |
| `月份格式错误: 2024-06` | 传了分隔符 | 用 `202406` |
| 报告为空、扫描 0 个文件 | 目录不对 / 该月没有文件 | 去掉 `--month` 或核对路径 |
| `PermissionError` | 文件被播放器占用 | 关掉播放器重跑 |

更多排查见 [troubleshooting.md](troubleshooting.md)。

---

## 10. 使用禁忌

1. **不要在没跑过 `--dry-run` 的情况下对真实库直接 `--fix`。** 修复会移动文件，
   大批量时先 `--limit` 抽样。
2. **不要把 `--soundalike` 当只读命令。** 它会让 `soundalike.exe` 真的移动重复文件，
   且 `--dry-run` 拦不住。
3. **不要手动清空 `log/_trash/` 之前不看 journal。** 那是唯一的「删除」恢复来源。
4. **不要在主目录里直接跑默认流水线。** 默认流水线把 `MUSIC_HELPER_TEMP_DIR` 当输入，
   把 `MUSIC_HELPER_MAIN_DIR` 当归档目标；两个目录指到同一个地方会造成自我搬运。
5. **不要让多个实例同时跑同一个库。** 没有加锁，并发写 `journal.jsonl` 会交错。
6. **不要依赖时间戳版本号做对账。** 版本号是手写语义化版本，见 `CHANGELOG.md`。
