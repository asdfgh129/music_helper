# Music Helper

Python 音乐库流水线：**解密 → 去重 → 补标签 → 检查 → 分流 → 归档 → 人工确认入库**。

面向「下载目录只是中转、最终库才是长期资产」的使用方式：默认流水线只把文件整理到工作区，
不会自动并入最终库；所有破坏性动作先出计划、写流水，删除一律进回收站。

| 项目 | 说明 |
|---|---|
| 当前版本 | `0.7.0`（见 [CHANGELOG.md](CHANGELOG.md)） |
| 运行环境 | Python 3.11+；Windows 为主要目标平台（QQ 解密仅 Windows） |
| 入口 | `python main.py` |
| 使用条款 | [LICENSE](LICENSE) |

## 能力

- **声纹去重**：调用 `soundalike.exe`，固定声纹库路径，识别重复曲目并移入重复区。
- **本地查重**：标签/文件名 + 时长双规则，保留无损格式与更大文件。
- **文件名规范**：`歌手 - 歌名` 格式检查，单个 `-` 自动规范化，避免误伤 `AC-DC`。
- **标签补全**：先按声纹查 MusicBrainz，再按文件名查 QQ 音乐 / 网易云，顺带封面与歌词。
- **完整性检查**：标签缺失、文件名与标签矛盾、重复、缺歌词、孤立歌词。
- **待补全分流**：核心标签齐全且无矛盾的文件留在工作区，其余移入 `INCOMPLETE_DIR`。
- **按年份归档**：`<年代>/<年份>/` 两级目录，例如 `1980-1989/1985/`。
- **人工确认入库**：`--manual-archive` 才把工作区文件并入最终库。
- **VIP 解密**：网易云 `.ncm`（`um.exe`）、QQ 音乐 `.mflac/.mgg`（Frida 注入运行中的
  客户端）。QQ 这条链路会自动检查客户端是否安装、启动、登录，缺哪一步补哪一步。

## 快速开始

```bash
# 1. 安装依赖
python -m pip install -r requirements.txt

# 2. 本地配置（可选；不建则使用 config.py 默认值）
cp config.example.ini config.ini

# 3. 看版本与帮助
python main.py --version
python main.py --help

# 4. 只出计划，不动任何文件
python main.py --dry-run

# 5. 跑完整流水线
python main.py

# 6. 人工确认工作区后，按年份并入最终库
python main.py --manual-archive
```

默认最终库是 `D:\music`，工作区是 `G:\Temp`。改路径、换盘符、调阈值见
[docs/configuration.md](docs/configuration.md)。

## 流水线

```
下载目录 ──► WORKSPACE_DIR ──┬─► 标签完整：留在工作区（按年代/年份整理）
                             ├─► INCOMPLETE_DIR  （标签不全 / 文件名矛盾）
                             └─► DUPLICATE_DIR   （重复文件）

--manual-archive：WORKSPACE_DIR ──► LIBRARY_DIR（最终音乐库）
```

每一步的细节、失败处理与声纹库生命周期见 [docs/workflow.md](docs/workflow.md)。

## 代码结构

```
music_helper/
├── main.py                 # 唯一 CLI 入口，只做编排
├── config.py               # 纯配置：config.ini / 环境变量 / 默认值
├── config.example.ini      # 本地配置示例
├── utils.py                # 日志、目录创建、月份工具
├── core/                   # 纯逻辑：不联网、不调用外部程序、不删文件
│   ├── model.py            # Track 数据模型
│   ├── scan.py             # 单次遍历建索引
│   ├── naming.py           # 文件名解析/生成（唯一实现）
│   ├── tags.py             # 标签读写与封面（唯一实现）
│   ├── lyrics.py           # 歌词检查
│   ├── dedupe.py           # 本地重复判定
│   ├── scoring.py          # 候选标签打分
│   ├── organize.py         # 年代/年份归档
│   ├── check.py            # 检查、修复计划、入库判定
│   ├── report.py           # Markdown 报告 + CSV 清单
│   └── ops.py              # Plan：移动/改名/回收 + journal
├── services/               # 有副作用：外部程序
│   ├── decrypt.py          # 网易云 / QQ 音乐解密编排
│   └── soundalike.py       # 声纹去重（外部 exe 包装）
├── tagger/                 # 标签、封面、歌词服务
├── decrypto/               # QQ 音乐 Frida 调用与来源检索
├── fingerprint/            # AcoustID / MusicBrainz 指纹匹配
├── music_tagger/           # 平台客户端（QQ 音乐、网易云）
├── tools/                  # um.exe、soundalike.exe、fpcalc、Frida hook
├── third_party/            # 上述外部程序的源码（um / soundalike / chromaprint）
├── tests/                  # 单元测试 + manual/ 手工脚本 + fixtures/ 样本
├── docs/                   # 用户与开发文档
├── scripts/                # 文档校验、git 出境代理
└── log/                    # 运行日志、报告、journal、回收站
```

## 文档

| 文档 | 内容 |
|---|---|
| [docs/README.md](docs/README.md) | 文档索引与每篇文档的边界 |
| [docs/workflow.md](docs/workflow.md) | 端到端流程、状态迁移、失败处理 |
| [docs/rules.md](docs/rules.md) | 全部判定规则 |
| [docs/usage.md](docs/usage.md) | 命令行手册 |
| [docs/configuration.md](docs/configuration.md) | 配置、目录语义、外部工具、阈值 |
| [docs/architecture.md](docs/architecture.md) | 分层、模块、`Plan`、扩展指南 |
| [docs/fingerprint.md](docs/fingerprint.md) | AcoustID / MusicBrainz 与版本碰撞 |
| [docs/troubleshooting.md](docs/troubleshooting.md) | 故障排查与恢复 |
| [docs/git-proxy.md](docs/git-proxy.md) | 推不上 GitHub 时的本地代理 |
| [tests/README.md](tests/README.md) | 测试运行与覆盖矩阵 |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 开发、测试、提交规范 |
| [CHANGELOG.md](CHANGELOG.md) | 变更记录 |

## 安全底线

1. **计划先行**：移动/改名先形成 `Plan`，`--dry-run` 可完整预览。
2. **不真删文件**：唯一「删除」是移入 `log/_trash/`，`core/` 层没有 `os.remove`。
3. **可追溯**：每个动作追加一条 JSON 到 `log/journal.jsonl`。
4. **只动该动的**：缺封面/专辑/年份只报告；只有歌曲名/歌手缺失或文件名与标签矛盾才移入
   `INCOMPLETE_DIR`。重复文件默认进 `DUPLICATE_DIR`，`--trash-dup` 才进回收站。
5. **解密只碰自己搬过的文件**：加密原文件按 `ENCRYPTED_SOURCE_MODE` 处理，绝不遍历整个
   VIP 目录批量搬运。

## 已知限制

- QQ 解密依赖 Frida 与正在运行的 QQMusic 客户端，**仅 Windows**。解密前会自动做三件事
  （见 `decrypto/qq_client.py`）：
  1. 检测客户端是否安装——Windows 读注册表 `Install` 值 + 常见路径；没装就装
     `tools/QQMusic_Setup_1951.exe`，再打 `tools/Q音屏蔽更新.zip` 补丁（客户端升级会让
     Frida 依赖的 MSVC 修饰导出名变化，脚本随即失效，所以补丁是解密能力的一部分）。
  2. 客户端没启动就启动它。
  3. 确认已登录——未登录时 `EncAndDesMediaFile::Open` 直接抛 `system error`，每个文件都会
     失败；所以未登录会提示扫码并轮询等待（`qq_login_timeout` 控制等待时长）。

  macOS 版是 Mach-O，没有 `QQMusicCommon.dll` 也没有那套导出名，Frida 定位不到函数，
  因此 **macOS 固定走 `um` 离线解密**：安装/启动/打补丁照做，登录态只能提示用户自行确认。
  想要免密钥效果，用 `tools/QQMusicMac_Mgr_8.8.0_20230903.dmg` 装 2023.09.03 及更早的
  客户端——那之前的版本下载的 `.mflac` 密钥内嵌在文件里，`um` 直接能解。
- 声纹工具是三平台二进制（`tools/soundalike.exe`、`tools/soundalike-darwin-<arch>`），
  Linux 上需要自己编一份放进 `tools/`。
- 声纹工具是黑盒，同曲不同版本（Live/Remix/伴奏）可能给出高相似度，详见
  [docs/fingerprint.md](docs/fingerprint.md)。
- 在线标签查询只走 QQ 音乐与网易云。
- 仓库内含测试样本 `tests/fixtures/1.flac` 与 `tools/` 下的三平台外部程序，保持随仓库分发
  以便开箱即用；它们的源码在 `third_party/`，重编方法与旧版 QQ 音乐客户端的说明见
  [third_party/README.md](third_party/README.md)。

## 开发与测试

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -p 'test_*.py'
python -m pytest -q
python -m ruff check .
python scripts/check_docs.py
```

CI 在 Ubuntu/Windows × Python 3.11/3.12 上跑：语法编译、导入冒烟、单元测试、命令行可用性、
静态检查与文档校验。详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

仅供学习与个人使用，禁止商业用途。详见 [LICENSE](LICENSE)。
请遵守各音乐平台的服务条款，不要用本工具分发受版权保护的内容。
