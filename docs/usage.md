# 命令行手册

> 本文负责：全部参数、流程入口、参数优先级、退出码、使用禁忌。
> 本文不负责：流程内部细节（见 [workflow.md](workflow.md)）、判定规则（见 [rules.md](rules.md)）、
> 配置项与环境变量（见 [configuration.md](configuration.md)）。

入口只有一个：`python main.py`。

## 1. 全局参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--version` | — | 打印版本后退出 |
| `--debug` | 关 | 输出调试日志；声纹工具追加 `-log-sec=1` |
| `--month YYYYMM` | 当前月 | 只影响解密与普通文件拷贝（按文件修改时间） |
| `--dry-run` | 关 | 只生成计划，不移动/改名；声纹去重整步跳过 |
| `--report-dir DIR` | `log/reports/` | 报告输出目录 |
| `--limit N` | 0（不限） | 每类处理最多 N 个文件，调试用 |
| `--no-move` | 关 | 流水线/检查中不移动不一致文件 |
| `--trash-dup` | 关 | 重复文件直接进 `log/_trash/`，否则移入 `DUPLICATE_DIR` |

## 2. 三条主流程

| 命令 | 作用 | 终点 |
|---|---|---|
| `python main.py` / `python main.py --archive` | `WORKSPACE_DIR` 完整流水线 | 完整文件留在 `WORKSPACE_DIR`（按年代/年份整理）；`INCOMPLETE_DIR` 等待人工 |
| `python main.py --check` | 检查 `LIBRARY_DIR` | 报告；`--fix` 时按规则修复 |
| `python main.py --manual-archive` | 人工确认后入库 | `WORKSPACE_DIR` → `LIBRARY_DIR` |

完整步骤见 [workflow.md](workflow.md)。

### 2.1 流水线跳过开关

| 参数 | 跳过的步骤 |
|---|---|
| `--skip-vip` | 解密与普通文件拷贝 |
| `--skip-fingerprint` | 声纹去重；同时关闭标签阶段的声纹查询 |
| `--skip-tag-update` | 标签更新 |
| `--skip-check` | 检查与修复 |
| `--skip-organize` | 工作区内的年代/年份整理 |

未达标文件移入 `INCOMPLETE_DIR` 不受这些开关影响，执行完检查后总会运行。

## 3. 单一动作

| 参数 | 作用 |
|---|---|
| `--init` | 初始化/更新声纹库（不扫描工作区） |
| `--checkdb` | 校验声纹库与 `LIBRARY_DIR` 的一致性 |
| `--soundalike` | 运行声纹去重（`WORKSPACE_DIR` + `LIBRARY_DIR`） |
| `--only-decrypt` | 只解密 |
| `--only-update-tag {master,temp}` | 只更新 `LIBRARY_DIR` 或 `WORKSPACE_DIR` 的标签 |
| `--only-check-file-name {master,temp}` | 只做文件名检查（可配 `--fix`） |
| `--only-archive` | 只对 `WORKSPACE_DIR` 做年代/年份归档 |

`master` 指 `LIBRARY_DIR`，`temp` 指 `WORKSPACE_DIR`；名称沿用旧参数，避免破坏已有脚本。

## 4. 参数优先级

`main()` 按以下顺序判断，命中即返回，**后面的参数不会再生效**：

```
--init
--checkdb
--soundalike
--only-decrypt
--only-update-tag
--only-check-file-name
--only-archive
--manual-archive
--check
默认流水线
```

例如同时传 `--check --manual-archive` 时只执行手动归档。

## 5. 退出码

| 退出码 | 含义 |
|---|---|
| 0 | 正常完成 |
| 1 | 参数/月份格式错误；`--init` / `--checkdb` / `--soundalike` 的外部工具失败；未处理异常 |
| 130 | 用户 Ctrl-C |

`--check` 与默认流水线即使发现「需要人工处理」的文件也返回 0——报告里有数量，
是否失败由使用者判断；外部程序失败才会反映到退出码。

## 6. 场景速查

| 我想… | 命令 |
|---|---|
| 先看计划，不动文件 | `python main.py --dry-run` |
| 处理指定月份 | `python main.py --month 202406` |
| 只解密 | `python main.py --only-decrypt` |
| 只补标签 | `python main.py --only-update-tag temp` |
| 只检查最终库 | `python main.py --check` |
| 检查并修复最终库 | `python main.py --check --fix` |
| 只检查文件名 | `python main.py --only-check-file-name master --fix` |
| 只对工作区归档 | `python main.py --only-archive` |
| 人工确认后入库 | `python main.py --manual-archive` |
| 首次建声纹库 | `python main.py --init` |
| 校验声纹库 | `python main.py --checkdb` |

## 7. 使用禁忌

1. **`--soundalike` 不是只读命令**：它会交互式把重复文件移入 `DUPLICATE_DIR`。不确定时先用
   `--dry-run`，但注意 dry-run 会整步跳过声纹去重。
2. **`--fix` 只移动严重问题**：缺封面/专辑/年份不会移动文件。这是刻意设计，见
   [rules.md](rules.md#7-修复范围)。
3. **`--manual-archive` 只处理工作区**：完整文件按年份并入 `LIBRARY_DIR`，未达标文件移入 `INCOMPLETE_DIR`。
4. **目录不要互相嵌套**：`DUPLICATE_DIR`、`INCOMPLETE_DIR` 不要放进 `WORKSPACE_DIR`，否则会被
   `soundalike -temp` 重复扫描。
5. **`LIBRARY_DIR` 不要等于 `WORKSPACE_DIR` / `DUPLICATE_DIR`**：`soundalike` 会拒绝相同目录，且容易自我搬运。
6. **`--month` 不筛选标签/检查**：它只按修改时间筛选解密与拷贝；后续步骤处理工作区全部文件。
