# Music Helper

Python 音乐库流水线：**解密 → 去重 → 标签 → 检查 → 归档**。

面向「下载目录只是中转、主目录才是库」的使用方式。所有破坏性动作先出计划再执行，
全程留痕，可预览、可追溯、可回滚。

| 项目 | 说明 |
|---|---|
| 当前版本 | `0.3.0`（见 [CHANGELOG.md](CHANGELOG.md)） |
| 运行环境 | Python 3.11+，Windows 为主要目标平台（QQ 解密仅 Windows） |
| 入口 | `python main.py` |
| 使用条款 | [LICENSE](LICENSE) |

## 功能

- **声纹去重**：调用 `soundalike.exe` 建立/比对声纹库，识别重复曲目。
- **文件名规范**：检查 `歌手 - 歌名` 格式，`只有单个 -` 的文件名自动规范化。
- **标签一致性**：文件名解析出的歌手/歌名与音频标签比对，发现矛盾。
- **标签补全**：先按声纹查 MusicBrainz，再按文件名查 QQ 音乐 / 网易云，顺带下载封面与歌词。
- **重复判定**：`歌手+歌名+时长` 与 `去掉 (1)(2) 后的文件名+时长` 双策略。
- **歌词检查**：缺失同名 `.lrc`，以及没有对应音频的孤立 `.lrc`。
- **按年份归档**：`<年代>/<年份>/` 两级目录，例如 `1980-1989/1985/`。
- **检查报告**：Markdown 报告 + CSV 待处理清单，不一致文件可移入指定目录。
- **VIP 解密**：网易云 `.ncm`（um.exe）、QQ 音乐 `.mflac/.mgg`（Frida）。

## 快速开始

```bash
# 1. 安装依赖
python -m pip install -r requirements.txt

# 2. 看一眼配置（路径都支持环境变量覆盖）
python main.py --version

# 3. 只出计划，不动任何文件
python main.py --check --dry-run

# 4. 确认无误后执行检查与修复
python main.py --check --fix
```

默认主目录是 `D:\music`，流水线工作目录是 `G:\Temp`。换盘符改 `config.py` 或设环境变量，
见 [docs/configuration.md](docs/configuration.md)。

## 三条流程

| 流程 | 命令 | 做什么 |
|---|---|---|
| 临时目录流水线 | `python main.py`（或 `--archive`） | 解密 VIP → 拷贝普通文件 → 声纹去重 → 更新标签 → 检查修复 → 按年份归档 |
| 主目录检查 | `python main.py --check` | 声纹库一致性、文件名、元数据、标签、重复、歌词，产出报告 |
| 手动归档 | `python main.py --manual-archive` | 更新标签 → 按标签重命名 → 按年份移入主目录 |

完整用法（全部参数、全部流程、场景速查、环境变量、退出码）见 **[docs/usage.md](docs/usage.md)**，
原始规格见 [docs/requirements.md](docs/requirements.md)。

## 目录结构

```
music_helper/
├── main.py                 # 唯一 CLI 入口，只做编排
├── config.py               # 纯配置：路径/阈值/扩展名
├── utils.py                # 日志与兼容旧接口的小函数
├── core/                   # 纯逻辑：不联网、不调用外部程序、不删文件
│   ├── model.py            # Track 数据模型
│   ├── scan.py             # 单次遍历建索引
│   ├── naming.py           # 文件名解析/生成（唯一实现）
│   ├── tags.py             # 标签读写与封面检测（唯一实现）
│   ├── lyrics.py           # 歌词检查
│   ├── dedupe.py           # 重复判定
│   ├── organize.py         # 按年代/年份归档
│   ├── check.py            # 各项检查与修复计划
│   ├── report.py           # Markdown 报告 + CSV 清单
│   └── ops.py              # Plan：移动/改名/回收站 + journal
├── services/               # 有副作用：外部程序与网络
│   ├── decrypt.py          # 网易云 / QQ 音乐解密
│   ├── soundalike.py       # 声纹去重（外部 exe 包装）
│   └── tagger.py           # MusicBrainz + QQ/网易 标签、封面、歌词
├── Decrypto/               # QQ 音乐解密（um.exe + Frida hook）
├── Fingerprint/            # AcoustID / MusicBrainz 指纹匹配
├── music_tagger/           # 各平台搜索客户端
├── test/                   # pytest 用例
├── docs/                   # 用户与开发文档
├── scripts/                # 仓库维护脚本（文档链接检查）
└── log/                    # 运行日志、报告、journal、回收站
```

## 文档

| 文档 | 内容 |
|---|---|
| [docs/README.md](docs/README.md) | 文档索引 |
| [docs/requirements.md](docs/requirements.md) | 功能规格：14 个模块 + 3 条流程 |
| [docs/usage.md](docs/usage.md) | 命令行手册与流程详解 |
| [docs/configuration.md](docs/configuration.md) | 路径、环境变量、外部工具、阈值 |
| [docs/features.md](docs/features.md) | 各功能的判定规则与实现位置 |
| [docs/architecture.md](docs/architecture.md) | 分层设计、数据流、扩展约定 |
| [docs/fingerprint.md](docs/fingerprint.md) | AcoustID / MusicBrainz 指纹匹配 |
| [docs/troubleshooting.md](docs/troubleshooting.md) | 常见问题与排查 |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 开发环境、测试、提交规范 |
| [CHANGELOG.md](CHANGELOG.md) | 变更记录 |

## 安全设计

1. **计划先行**：所有移动/改名先形成 `Plan`，`--dry-run` 可完整预览。
2. **不真删文件**：唯一的「删除」是把文件移入 `log/_trash/`，`core/` 层没有 `os.remove`。
3. **可追溯**：每个动作追加一条 JSON 到 `log/journal.jsonl`（时间/动作/源/目标/原因/成败）。
4. **只动该动的**：缺封面/专辑/年份只在报告提示；只有**歌曲名/歌手缺失**或**文件名与标签矛盾**
   才把文件移入待处理目录。重复文件默认只报告，`--trash-dup` 才进回收站。
5. **解密只碰自己搬过的文件**：加密原文件按 `ENCRYPTED_SOURCE_MODE` 处理（默认搬回 VIP
   下载目录），绝不遍历整个临时目录。

## 已知限制

- QQ 解密依赖 Frida 与正在运行的 QQMusic 客户端，仅 Windows。
- 声纹去重依赖外部 `soundalike.exe` 的数据库格式，Python 侧只负责调用与结果搬运。
- 在线标签查询只走 QQ 音乐与网易云（酷狗/酷我/咪咕客户端已停用）。
- 仓库内含 `1.flac`（15 MB）与两个 exe（`Decrypto/um.exe` 8.2 MB、`Fingerprint/soundalike.exe`
  4.6 MB），保持随仓库分发以便开箱即用。

## 开发与测试

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

CI 在 Ubuntu/Windows × Python 3.11/3.12 上跑：语法编译、导入冒烟、单元测试、命令行可用性、
文档链接检查。详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

仅供学习与个人使用，禁止商业用途。详见 [LICENSE](LICENSE)。
请遵守各音乐平台的服务条款，不要用本工具分发受版权保护的内容。
