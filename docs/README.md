# 文档索引

本目录是 Music Helper 的全部文档。根目录只保留 `README.md`、`CHANGELOG.md`、`CONTRIBUTING.md`、
`LICENSE`、`AGENTS.md` 五个惯例文件。

## 按角色阅读

| 我想… | 先读 | 再读 |
|---|---|---|
| 把它跑起来 | [../README.md](../README.md) 快速开始 | [usage.md](usage.md) |
| 改路径 / 换盘符 / 调阈值 | [configuration.md](configuration.md) | — |
| 弄清某个检查到底怎么判定 | [features.md](features.md) | [requirements.md](requirements.md) |
| 改代码 | [architecture.md](architecture.md) | [../CONTRIBUTING.md](../CONTRIBUTING.md) |
| 出问题了 | [troubleshooting.md](troubleshooting.md) | — |
| 看这个项目原本要做什么 | [requirements.md](requirements.md) | — |
| 看历史决策 | [history/](history/) | [../CHANGELOG.md](../CHANGELOG.md) |

## 全部文档

| 文档 | 内容 |
|---|---|
| [requirements.md](requirements.md) | 功能规格：14 个模块、3 条操作流程，以及每项功能的实现落点 |
| [usage.md](usage.md) | **完整使用说明**：全部参数逐条解释、三条主流程 + 七个单一动作、产物与回滚、场景速查、环境变量、退出码、使用禁忌 |
| [configuration.md](configuration.md) | 目录、环境变量、外部程序、业务阈值 |
| [features.md](features.md) | 各功能的判定规则与边界，包括文件名规则、重复判定、归档、报告格式 |
| [architecture.md](architecture.md) | 分层设计、模块职责、数据流、扩展与踩坑记录 |
| [fingerprint.md](fingerprint.md) | AcoustID / MusicBrainz 指纹匹配（`Fingerprint/`） |
| [troubleshooting.md](troubleshooting.md) | 常见故障与排查步骤 |

## 历史归档

以下文档描述的是重构前（`0.2.0` 之前）的状态，**仅供追溯**，不再更新。
其中的模块名（`file_operations.py`、`tag_updater.py`、`archive.py` 等）已不存在。

| 文档 | 原文件名 | 说明 |
|---|---|---|
| [history/cleanup-2026-03.md](history/cleanup-2026-03.md) | `CLEANUP_SUMMARY.md`、`PROJECT_CLEANUP_SUMMARY.md` | 2026-03 的文件清理记录 |
| [history/debug-mode.md](history/debug-mode.md) | `DEBUG_MODE_GUIDE.md`、`DEBUG_MODE_SUMMARY.md` | Debug 模式的设计与实现 |
| [history/code-review-2026-02.md](history/code-review-2026-02.md) | `Doc/REVIEW_SUMMARY.md` | 2026-02 的代码审查与修复清单 |
| [history/extraction-2026-02.md](history/extraction-2026-02.md) | `Doc/EXTRACTION_SUMMARY.md` | `music_tagger` 从上游项目的提取记录 |

## 文档约定

- 所有文档用中文，代码标识符保持英文。
- 表格优先于长段落；命令示例必须可直接复制执行。
- 每篇文档开头一句话说明「解决什么问题」。
- 移动或重命名文档后跑 `python scripts/check_docs.py`，CI 会拦住死链。
