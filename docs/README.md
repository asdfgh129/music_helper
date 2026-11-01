# 文档索引

本目录是 Music Helper 的完整文档。根目录只保留惯例文件：`README.md`、`CHANGELOG.md`、
`CONTRIBUTING.md`、`AGENTS.md`、`LICENSE`。

## 按问题找文档

| 我想… | 读这篇 | 不要在这里找 |
|---|---|---|
| 30 秒跑起来 | [../README.md](../README.md) | 参数细节 |
| 看一条文件从下载到入库的完整路径 | [workflow.md](workflow.md) | 单条规则的算法 |
| 弄清「为什么这个文件被判重复/未入库」 | [rules.md](rules.md) | 流程顺序 |
| 看自检到底查了什么、报告怎么读、误判怎么排查 | [self-check.md](self-check.md) | 单条规则的公式 |
| 查某个命令行参数 | [usage.md](usage.md) | 规则为什么这样定 |
| 改路径、换盘符、调阈值 | [configuration.md](configuration.md) | 规则怎么使用阈值 |
| 改代码 / 加检查项 | [architecture.md](architecture.md) | 具体判定规则 |
| 理解 AcoustID / MusicBrainz、声纹查重算法与版本碰撞 | [fingerprint.md](fingerprint.md) | 本地查重流程 |
| 出问题了 / 文件找不到了 | [troubleshooting.md](troubleshooting.md) | 正常运行说明 |
| 跑测试 | [../tests/README.md](../tests/README.md) | 项目整体使用 |
| 推不上 GitHub | [git-proxy.md](git-proxy.md) | 音乐流水线 |
| 看历史决策 | [history/](history/) | 当前行为 |

## 每篇文档的边界

| 文档 | 只负责 | 明确不负责 |
|---|---|---|
| [workflow.md](workflow.md) | 端到端流程、目录角色、状态迁移、失败处理、声纹库生命周期 | 单条规则算法、CLI 参数表 |
| [rules.md](rules.md) | 文件名、标签完整性、一致性、重复、歌词、归档、报告的全部判定规则 | 流程顺序、参数、配置位置 |
| [self-check.md](self-check.md) | 自检的完整流程、六维度的取舍、严重级别与处置、报告解读、性能特征、已知局限与误判风险 | 单条规则的比对公式、流水线其他步骤 |
| [usage.md](usage.md) | CLI 全参数、流程入口、参数优先级、退出码、使用禁忌 | 规则为什么这样定 |
| [configuration.md](configuration.md) | 配置来源与优先级、目录语义、外部程序、阈值、扩展名 | 规则怎么使用这些配置 |
| [architecture.md](architecture.md) | 分层边界、模块职责、数据流、`Plan` 机制、扩展指南、设计决策 | 具体判定规则 |
| [fingerprint.md](fingerprint.md) | 指纹原理、AcoustID/MusicBrainz、声纹查重（soundalike）的流程与算法、阈值、平台支持、同曲不同版本的碰撞策略与审核结论 | 本地查重流程 |
| [troubleshooting.md](troubleshooting.md) | 症状 → 原因 → 处理、日志与 journal、数据恢复 | 正常流程说明 |
| [git-proxy.md](git-proxy.md) | GitHub 推拉失败时的本地代理 | 音乐库流水线 |

同一事实只在一个地方写完整版，其余文档链接过去。

## 历史归档

以下文档描述重构前（`0.2.0` 之前）的状态，**仅供追溯**，不再更新。其中的模块名
（`file_operations.py`、`tag_updater.py`、`archive.py` 等）已不存在。

| 文档 | 原文件名 | 说明 |
|---|---|---|
| [history/cleanup-2026-03.md](history/cleanup-2026-03.md) | `CLEANUP_SUMMARY.md`、`PROJECT_CLEANUP_SUMMARY.md` | 2026-03 的文件清理记录 |
| [history/debug-mode.md](history/debug-mode.md) | `DEBUG_MODE_GUIDE.md`、`DEBUG_MODE_SUMMARY.md` | Debug 模式的设计与实现 |
| [history/code-review-2026-02.md](history/code-review-2026-02.md) | `Doc/REVIEW_SUMMARY.md` | 2026-02 的代码审查与修复清单 |
| [history/extraction-2026-02.md](history/extraction-2026-02.md) | `Doc/EXTRACTION_SUMMARY.md` | `music_tagger` 从上游项目的提取记录 |

旧文档去向：

| 旧文档 | 现状 |
|---|---|
| 旧的需求文档（已删除） | 流程部分并入 [workflow.md](workflow.md)，规则部分并入 [rules.md](rules.md) |
| 旧的特性文档（已删除） | 已重写为 [rules.md](rules.md) |
| 根目录 `WORKFLOW.md` | 已删除并合并进 [workflow.md](workflow.md) |

## 文档约定

- 所有文档用中文，代码标识符保持英文；
- 表格优先于长段落，命令示例必须可直接复制执行；
- 每篇文档开头三行说明「负责 / 不负责 / 权威来源」；
- 新增或移动文档后运行 `python scripts/check_docs.py`，CI 会拦住死链与失效路径。
