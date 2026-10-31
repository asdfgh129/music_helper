# 故障排查

> 本文负责：症状 → 原因 → 处理，日志与 journal 的位置，数据恢复。
> 本文不负责：正常流程说明（见 [workflow.md](workflow.md)）、参数含义（见 [usage.md](usage.md)）。

## 1. 先看哪里

| 信息 | 位置 |
|---|---|
| 本次运行日志 | `log/Music-*.log` |
| 操作流水（每一次移动/改名/回收） | `log/journal.jsonl` |
| 报告与待处理清单 | `log/reports/` |
| 已「删除」的文件 | `log/_trash/` |

`journal.jsonl` 每行一个 JSON，字段包括 `time`、`plan`、`action`、`src`、`dst`、`reason`、
`ok`、`error`。排查「文件去哪了」优先看它。

## 2. 启动与配置

### `import main` 失败

```bash
python -c "import config, utils, main"
```

- 确认 Python ≥ 3.11；
- 可选依赖缺失不应导致启动失败；如果报 `ModuleNotFoundError`，看栈顶是哪个模块，
  再检查是否有人把可选依赖改成了顶层导入；
- `config.py` 只依赖标准库，若这里报错通常是改坏了 `config.ini` 解析。

### `音乐库不存在` / `工作区不存在` WARNING

路径不存在只警告不退出，方便 `--dry-run` 先看计划。检查：

```bash
python -c "import config, json; print(json.dumps(config.as_dict(), ensure_ascii=False, indent=2))"
```

覆盖顺序是环境变量 > `config.ini` > 默认值，见 [configuration.md](configuration.md#1-配置来源与优先级)。

### Windows 控制台中文乱码或报错

程序已把 stdout/stderr 的错误策略设为 `replace`，不会因编码崩溃。仍建议：

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
```

## 3. 外部工具

### `找不到外部程序: ...soundalike.exe` / `...um.exe`

默认位置已统一到 `tools/`：

| 程序 | 默认路径 |
|---|---|
| 声纹工具 | `tools/soundalike.exe` |
| 网易云解密 | `tools/um.exe` |
| Frida hook | `tools/hook_qq_music.js` |

移动过就设置对应环境变量：

```powershell
$env:MUSIC_HELPER_SOUNDALIKE_EXE = "D:\tools\soundalike.exe"
$env:MUSIC_HELPER_UM_EXE = "D:\tools\um.exe"
```

### 声纹库「找不到记录」或结果和以前不一致

0.6.0 起固定使用 `-db <DB_PATH>`，并把工作目录设为库文件所在目录：

```bash
python -c "import config; print(config.DB_PATH)"
python main.py --checkdb
```

- 换过 `DB_PATH` 等于换了一个新库，需要重新 `--init`；
- `music.db` 被 `.gitignore` 忽略，不要指望克隆仓库自带；
- 在 macOS/Linux 上 `soundalike.exe` 无法执行，会报 `Exec format error` 或
  `无法执行外部程序`，这是平台限制，不影响其他步骤。

### `fpcalc not in path`

声纹补标签会降级为在线平台查询。安装 Chromaprint：

```bash
# macOS
brew install chromaprint
# Ubuntu / Debian
sudo apt install libchromaprint-tools
```

### QQ 音乐解密失败

- 仅 Windows 可用，需要正在运行的 `QQMusic.exe`；
- 需要安装 `frida`；
- hook 脚本路径默认 `tools/hook_qq_music.js`，移动过就设 `MUSIC_HELPER_QQ_HOOK`；
- 失败时本次移入暂存区的加密文件会自动还回 VIP 目录。

## 4. 回滚与恢复

1. **文件被移走**：在 `log/journal.jsonl` 搜文件名，`src`/`dst` 就是搬运路径；
2. **文件被「删除」**：实际在 `log/_trash/`，按原文件名找；
3. **批量回滚**：按 journal 的 `dst` 反向 `move` 回 `src`，建议先复制一份再操作；
4. **只想重跑**：`--dry-run` 先看计划，确认后再去掉；
5. **不要手工编辑 `music.db`**：用 `--init` 重建，或换 `DB_PATH` 重新建库。

## 5. 流水线结果不符合预期

### 文件全进了 `INCOMPLETE_DIR`

入库标准要求歌曲名、歌手、专辑、年份齐全，且文件名与标签不矛盾。
先看报告里的「标签不完整」明细，再决定补标签还是手工处理。

缺少 `mutagen` 时读不到任何标签，所有文件都会进 `INCOMPLETE_DIR`：

```bash
python -c "from core.tags import MUTAGEN_AVAILABLE; print(MUTAGEN_AVAILABLE)"
```

### 文件没有进 `DUPLICATE_DIR`

- `--dry-run` 会整步跳过声纹去重；
- soundalike 是交互式的，终端里需要确认才会移动；
- `--trash-dup` 只影响本地检查阶段，不影响 soundalike 的移动目标；
- 本地查重只在检查阶段运行，`--skip-check` 会跳过。

### `--fix` 没有修复缺封面/缺专辑

这是刻意设计：只有歌曲名/歌手缺失、文件名与标签矛盾才移动文件。其余问题只进报告，
避免一次 `--fix` 搬空整个库。见 [rules.md](rules.md#7-修复范围)。

### 孤立 `.lrc`

报告里的「孤立歌词」表示同目录下没有对应音频。确认音频是否被移走；如果音频还在，
检查扩展名是否在 `config.AUDIO_EXTENSIONS` 中。

## 6. 测试与手工验证

```bash
python -m unittest discover -s tests -p 'test_*.py'
python -m pytest -q
python scripts/check_docs.py
```

需要真实网络的脚本在 `tests/manual/`，不参与自动测试：

```bash
python tests/manual/manual_musicbrainz.py
python tests/manual/manual_musicbrainz.py --mode api
```

### macOS/Linux 上的路径

默认路径是 Windows 盘符。做本地验证时用临时目录覆盖：

```bash
MUSIC_HELPER_LIBRARY_DIR=/tmp/mh/lib \
MUSIC_HELPER_WORKSPACE_DIR=/tmp/mh/temp \
MUSIC_HELPER_INCOMPLETE_DIR=/tmp/mh/incomplete \
MUSIC_HELPER_DUPLICATE_DIR=/tmp/mh/dup \
MUSIC_HELPER_DB=/tmp/mh/music.db \
python main.py --dry-run
```

非 Windows 上 `utils.ensure_dirs()` 会跳过 `D:\...` 这类盘符路径，避免把字面量目录建到当前目录。

## 7. 推不上 GitHub

与音乐流水线无关，见 [git-proxy.md](git-proxy.md)。
