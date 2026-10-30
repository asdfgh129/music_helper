# 贡献指南

感谢你愿意改进 Music Helper。本文说明本地开发、测试与提交的约定。

## 先读这些

| 文档 | 为什么要读 |
|---|---|
| [docs/architecture.md](docs/architecture.md) | 分层边界与「一个功能只有一处实现」的约束 |
| [docs/features.md](docs/features.md) | 各功能的判定规则，改行为前先确认规则 |
| [docs/requirements.md](docs/requirements.md) | 原始功能规格（14 模块 + 3 流程） |
| [CHANGELOG.md](CHANGELOG.md) | 版本规范与发版清单 |

## 环境准备

```bash
git clone <repo-url> music_helper
cd music_helper
python -m pip install -r requirements-dev.txt
```

- Python 3.11+（CI 覆盖 3.11 / 3.12）。
- 主要目标平台是 Windows；Linux/macOS 上除 QQ 解密外均可运行。
- 外部程序 `Decrypto/um.exe`、`Fingerprint/soundalike.exe` 随仓库提供，缺失时对应功能降级，
  不影响程序启动与测试。

## 运行与测试

```bash
python -m pytest -q                 # 全量单元测试
python scripts/check_docs.py        # 文档链接检查（改了 md 就跑一次）
python main.py --help               # 命令行冒烟
python main.py --check --dry-run    # 用真实库验证时先 dry-run
```

约定：

- 单元测试**不得**触碰真实音乐库、网络、外部 exe。需要外部依赖的验证脚本放在
  `test/manual/` 下、以 `manual_` 开头，不参与自动收集。
- 新增/修改行为时，必须同时补 `test/` 下的用例。当前基线是**全部通过**，不接受「已知失败」。
- 提交前跑一遍 CI 等价命令：

```bash
python -m compileall -q core services music_tagger main.py config.py utils.py
python -c "import config, utils, main"
python -m pytest -q
```

## 代码约定

### 分层

| 层 | 允许 | 禁止 |
|---|---|---|
| `core/` | 纯计算、读文件元信息、生成 `Plan` | 网络请求、调用外部程序、删除文件、`os.remove` |
| `services/` | 外部 exe、HTTP、写标签与封面 | 直接改目录结构（应返回结果由 `main` 编排） |
| `main.py` | 解析参数、串流程、汇总报告 | 业务规则实现 |
| `config.py` | 纯数据（路径、阈值、扩展名） | 导入任何业务模块（避免循环导入） |

### 唯一实现原则

以下规则**只能有一处实现**，其他模块必须复用：

- 文件名解析与生成 → `core/naming.py`
- 标签读写与封面 → `core/tags.py`
- 歌词检查 → `core/lyrics.py`
- 重复判定 → `core/dedupe.py`
- 归档规则 → `core/organize.py`
- 破坏性动作 → `core/ops.py: Plan`

不要在别处再写一套「差不多」的逻辑——重构前项目里同一个功能最多有四份实现，
规则互相矛盾，这是最主要的维护成本来源。

### 破坏性操作

新增任何移动/删除/改名逻辑时：

1. 一律通过 `Plan.add_move / add_rename / add_trash` 表达，不要在业务代码里直接 `shutil.move`；
2. 必须支持 `dry_run`；
3. 必须写 `reason`，最终会进 `log/journal.jsonl`；
4. 不做硬删除，删除 = 移入 `config.TRASH_DIR`。

### 风格

- 注释与日志用中文，标识符用英文。
- 行宽 110，`ruff` 配置见 `pyproject.toml`。
- 异常处理要写清楚降级行为，不要裸 `except: pass`（除了明确标注 `noqa: BLE001` 的日志兜底）。

## 提交规范

采用 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/)：

```
<type>(<scope>): <简述>

<可选正文：为什么改、影响范围>
```

常用 `type`：`feat`、`fix`、`refactor`、`docs`、`test`、`chore`、`ci`。
`scope` 用目录或模块名，如 `core/dedupe`、`services/decrypt`、`docs`。

示例：

```
fix(services/decrypt): 解密成功后把加密原文件归还 VIP 目录

旧实现会把临时目录顶层所有文件搬走，现只处理本次移入的文件。
```

### 提交前检查

- [ ] `python -m pytest -q` 全绿
- [ ] 改了行为 → 同步 [docs/features.md](docs/features.md) 与 [CHANGELOG.md](CHANGELOG.md)
- [ ] 改了配置项 → 同步 [docs/configuration.md](docs/configuration.md)
- [ ] 没有把 `log/`、`__pycache__/`、`*.log`、测试产物提交进仓库

## Pull Request

1. 从 `main` 切分支：`feat/xxx`、`fix/xxx`、`docs/xxx`。
2. 一个 PR 只做一件事；纯格式化改动单独提。
3. PR 描述里写清：**改了什么、为什么改、怎么验证的**（贴命令或报告片段）。
4. CI 必须全绿才能合并。
5. 涉及文件搬运规则的改动，请在描述里明确说明「对用户已有音乐库的影响」。

## 文档改动

文档结构见 [docs/README.md](docs/README.md)：

- 用户向内容放 `docs/`，不要新增根目录散装 md。
- 历史归档放 `docs/history/`，只读，不再更新。
- 图片等静态资源放 `docs/assets/`。
- 新增/移动文档后跑 `python scripts/check_docs.py`，CI 会拦住死链。

## 报告问题

提交 issue 时请附上：

- 运行的命令（完整参数）
- 操作系统与 Python 版本
- `log/` 下对应日志的末尾 50 行（可脱敏路径）
- 若涉及文件搬运：`log/journal.jsonl` 中相关记录
