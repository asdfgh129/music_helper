# 文档索引

本目录是 Music Helper 的完整文档。根目录只保留惯例文件：`README.md`、`CHANGELOG.md`、
`CONTRIBUTING.md`、`AGENTS.md`、`LICENSE`。

## 按问题找文档

| 我想… | 读这篇 | 不要在这里找 |
|---|---|---|
| 30 秒跑起来 | [../README.md](../README.md) | 参数细节 |
| 照着界面一步步操作 | [web-guide.md](web-guide.md) | 判定规则原理 |
| 用浏览器走一遍完整流程 | [web-wizard.md](web-wizard.md) | 单条判定规则 |
| 改试听、歌词显示、媒体接口或本机解码 | [media-player.md](media-player.md)、[../third_party/ffmpeg-build/README.md](../third_party/ffmpeg-build/README.md) | 判定规则、纯服务器分支方案 |
| 看一条文件从下载到入库的完整路径 | [workflow.md](workflow.md) | 单条规则的算法 |
| 弄清「为什么这个文件被判重复/未入库」 | [rules.md](rules.md) | 流程顺序 |
| 看某个判定背后的算法、公式、阈值与流程图 | [algorithms.md](algorithms.md) | 界面操作步骤 |
| 看自检到底查了什么、报告怎么读、误判怎么排查 | [self-check.md](self-check.md) | 单条规则的公式 |
| 查某个命令行参数 | [usage.md](usage.md) | 规则为什么这样定 |
| 改路径、换盘符、调阈值 | [configuration.md](configuration.md) | 规则怎么使用阈值 |
| 改代码 / 加检查项 | [architecture.md](architecture.md) | 具体判定规则 |
| 理解 AcoustID / MusicBrainz、声纹查重算法与版本碰撞 | [fingerprint.md](fingerprint.md) | 本地查重流程 |
| 出问题了 / 文件找不到了 | [troubleshooting.md](troubleshooting.md) | 正常运行说明 |
| 跑测试 | [../tests/README.md](../tests/README.md) | 项目整体使用 |
| 推不上 GitHub | [git-proxy.md](git-proxy.md) | 音乐流水线 |
| 规划「纯服务器 Web + 浏览器本机实现」分支 | [browser-local-roadmap.md](browser-local-roadmap.md) | 主干现有行为 |
| 浏览项目文档（侧栏直达、首页总览、状态看板、离线阅读） | [index.html](index.html) | 单篇规则细节、第三方源码自带文档 |
| 打包免 Python 绿色版 / 查绿色版参数 | [../README.md](../README.md)「绿色版」一节、[usage.md](usage.md) 第 9 节 | 源码模式安装依赖 |
| 看历史决策 | [history/](history/) | 当前行为 |

## 项目文档分类

[index.html](index.html) 的侧栏把 `docs/` 下 15 篇文档按用途分成四类，首页状态表也有「分类」列与
分类筛选。分类映射的唯一来源是 `scripts/build_docs_index.py` 的 `DOC_CATEGORY_OF`。

| 分类 | 面向 | 文档 |
|---|---|---|
| 使用与操作 | 跑流程、点界面、查参数、改配置 | [README.md](README.md)、[workflow.md](workflow.md)、[usage.md](usage.md)、[web-guide.md](web-guide.md)、[web-wizard.md](web-wizard.md)、[media-player.md](media-player.md)、[configuration.md](configuration.md) |
| 开发与规则 | 改代码、改判定规则、查算法与声纹原理 | [architecture.md](architecture.md)、[rules.md](rules.md)、[algorithms.md](algorithms.md)、[fingerprint.md](fingerprint.md) |
| 排错与运维 | 自检、故障排查、推拉失败 | [self-check.md](self-check.md)、[troubleshooting.md](troubleshooting.md)、[git-proxy.md](git-proxy.md) |
| 规划与路线 | 下一个分支的路线与待决决策 | [browser-local-roadmap.md](browser-local-roadmap.md) |

## 每篇文档的边界

| 文档 | 只负责 | 明确不负责 |
|---|---|---|
| [workflow.md](workflow.md) | 端到端流程、目录角色、状态迁移、失败处理、声纹库生命周期 | 单条规则算法、CLI 参数表 |
| [web-guide.md](web-guide.md) | 八步向导的**操作规范**：每页看什么、按钮动哪些文件、确认点在哪、失败怎么办、安全问题 | 判定规则的原理、接口定义 |
| [rules.md](rules.md) | 文件名、标签（完整性/来源/择优/写入）、一致性、自检、去重（集合内与跨集合）、音质比较与格式偏好、归档、执行安全、报告的全部判定规则 | 流程顺序、参数、配置位置 |
| [algorithms.md](algorithms.md) | 初始化、拷贝、解密、标签读取与补全、文件名匹配、自检、去重、声纹、归档、`Plan` 的算法：输入输出、判定顺序、公式、阈值、复杂度、UML 图 | 界面操作步骤、配置项位置 |
| [self-check.md](self-check.md) | 自检的完整流程、六维度的取舍、严重级别与处置、报告解读、性能特征、已知局限与误判风险 | 单条规则的比对公式、流水线其他步骤 |
| [usage.md](usage.md) | CLI 全参数、流程入口、参数优先级、退出码、使用禁忌 | 规则为什么这样定 |
| [configuration.md](configuration.md) | 配置来源与优先级、目录语义、外部程序、阈值、扩展名 | 规则怎么使用这些配置 |
| [web-wizard.md](web-wizard.md) | Web 向导八步做了什么、初始化判定、查重与自检、跳过/回退语义、接口与文件清单、um 跨盘核实结论 | 单条判定规则、CLI 参数 |
| [media-player.md](media-player.md) | 本机临时 Web 服务的部署口径、只读媒体层、Range 流式、LRC 解析口径（含增强 LRC 逐字）、封面与播放队列、歌词偏移写回、格式矩阵、`.ape/.wma/.dsf` 本机解码子进程与派生缓存、播放器交互与分期 | 判定规则、未来纯服务器分支的解码方案 |
| [architecture.md](architecture.md) | 分层边界、模块职责、数据流、`Plan` 机制、扩展指南、设计决策 | 具体判定规则 |
| [fingerprint.md](fingerprint.md) | 指纹原理、AcoustID/MusicBrainz、声纹查重（soundalike）的流程与算法、阈值、平台支持、同曲不同版本的碰撞策略与审核结论 | 本地查重流程 |
| [troubleshooting.md](troubleshooting.md) | 症状 → 原因 → 处理、日志与 journal、数据恢复 | 正常流程说明 |
| [git-proxy.md](git-proxy.md) | GitHub 推拉失败时的本地代理 | 音乐库流水线 |
| [browser-local-roadmap.md](browser-local-roadmap.md) | 下一个分支（纯服务器 Web + 浏览器本机实现）的目标、可行性、问题与方案、分期路线、验收与待决决策 | 主干行为定义、具体算法与阈值 |

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
- 新增或移动文档后先运行 `python scripts/build_docs_index.py` 重新生成 [index.html](index.html)，
  再运行 `python scripts/check_docs.py`，CI 会拦住死链与失效路径；新增项目文档还要在
  `scripts/build_docs_index.py` 的 `DOC_CATEGORY_OF` 补分类并登记到上面的分类表，
  否则索引里会显示「未分类」并在生成时告警；
- [index.html](index.html) 是生成产物，不要手工编辑。页面是单文件离线文档站：只收录项目自身
  维护的 Markdown（含历史归档；`third_party/` 下的上游源码自带文档不纳入），左侧栏按分组直达
  任意文档并在页内阅读正文，无需起服务器；首页汇总文档总数、生命周期状态、校验结果与最近提交日期，
  并提供状态筛选、全表检索与常用入口；正文里指向第三方文档的链接仍指向原文件（另开标签）；
- 状态口径：现行维护 / 规划中（[browser-local-roadmap.md](browser-local-roadmap.md)）/
  历史归档只读；每篇文档另标「校验通过 / N 处问题 / 免校验」。
  校验复用 `scripts/check_docs.py` 的唯一实现，历史归档与 `CHANGELOG.md` 按约定免校验；
- `python scripts/build_docs_index.py --check` 可在 CI 里检查索引是否过期：比较时忽略生成时间、
  git 日期与字节数（浅克隆、不同换行符不会误报），但正文已内嵌，任何 Markdown 改动都会让索引过期。
