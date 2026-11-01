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
| 声纹工具（Windows） | `tools/soundalike.exe` |
| 声纹工具（macOS） | `tools/soundalike-darwin-arm64` / `-amd64`，按架构自动选 |
| 指纹（macOS） | `tools/fpcalc` |
| 解密 um（Windows） | `tools/um.exe` |
| 解密 um（macOS） | `tools/um-darwin-arm64` / `-amd64`，按架构自动选 |
| Frida hook（仅 Windows） | `tools/hook_qq_music.js` |

路径由 `config.py` 按 `sys.platform` + `platform.machine()` 自动挑，不用手工切平台。
移动过就设置对应环境变量：

```powershell
$env:MUSIC_HELPER_SOUNDALIKE_EXE = "D:\tools\soundalike.exe"
$env:MUSIC_HELPER_UM_EXE = "D:\tools\um.exe"
```

报错文案能直接告诉你坏在哪一层：

| 文案 | 含义 |
|---|---|
| `找不到…（当前平台 macOS，确认 tools/ 里带了该平台的产物）` | 文件不在——多半是没把二进制一起提交/拷贝过去 |
| `缺少可执行权限…运行 chmod +x "…"` | 在 Windows 上克隆的仓库不记录 exec 位，到 Mac 上补一次即可 |
| `是 Windows PE，而本机是 macOS，执行会报 Exec format error` | 拿错了平台的产物（例如把 `soundalike.exe` 配给了 macOS） |
| `是 Mach-O，而本机是 Windows` | 反过来配错，或 `-darwin-arm64` / `-amd64` 挑错了架构 |

macOS 上首次使用：

```bash
chmod +x tools/fpcalc tools/soundalike-darwin-* tools/um-darwin-*
xattr -d com.apple.quarantine tools/* 2>/dev/null || true
```

### 声纹库「找不到记录」或结果和以前不一致

0.6.0 起固定使用 `-db <DB_PATH>`，并把工作目录设为库文件所在目录：

```bash
python -c "import config; print(config.DB_PATH)"
python main.py --checkdb
```

- 换过 `DB_PATH` 等于换了一个新库，需要重新 `--init`；
- `music.db` 被 `.gitignore` 忽略，不要指望克隆仓库自带；
- macOS 用 `tools/soundalike-darwin-<arch>`，Windows 用 `tools/soundalike.exe`；
  跨平台共用同一个 `music.db` 没有意义（记录里存的是绝对目录），复制过去也会被 `--checkdb` 清空。

### `database settings (...) don't match current settings (...)`

声纹库把指纹参数写进了 `Settings` 表，`fpcalc_length` / `algorithm` 变了就打不开。本项目现在
会**在开跑前**读库比对，直接给出处理办法，不会让你对着返回码 1 猜：

- 想保留新参数（默认 120 秒，判断更准）：删掉 `music.db`，重新 `python main.py --init`；
- 想沿用老库（15 秒，扫描更快）：把 `config.ini` 的 `fpcalc_length` 改成 15。

另外，换了 `fpcalc` 版本（仓库里现在 Windows 与 macOS 都是 1.6.2，早先 Windows 走的
`System32` 是 1.6.0）后，如果发现查重结果和以前不一致，先 `--checkdb` 再考虑重建库。

### `fpcalc not in path`

补标签会降级为在线平台查询，声纹去重直接失败。查找顺序是
`config.FPCALC_EXE` → 系统 `PATH`：

```bash
# 看当前用的是哪个
python -c "import config; print(config.FPCALC_EXE)"
```

- macOS：用仓库自带的 `tools/fpcalc`（通用二进制），调用时已自动把 `tools/` 加进 `PATH`；
  也可以 `brew install chromaprint`，再用 `MUSIC_HELPER_FPCALC_EXE` 指过去；
- Windows：一般已装在 `C://Windows//System32//fpcalc.exe`；
- 想换版本就覆盖 `tools/fpcalc`，注意指纹长度仍受 `Settings` 表约束（见上一节）。

### QQ 音乐解密失败

解密通道是按平台自动选的（`decrypto.qq.decrypt_backend()`），**不需要手工切换**。解密前还会
先做一次环境准备（`decrypto/qq_client.py`）：检测客户端是否安装（没装就装 19.51 并打屏蔽更新
补丁）→ 没启动就启动 → 确认已登录。任一步不满足就直接跳过，不会白搬一遍文件。

| 平台 / 状态 | 通道 | 前提 |
|---|---|---|
| Windows 且装了 `frida` | Frida 注入 `QQMusic.exe` | 客户端已安装 + 运行中 + **已登录** |
| macOS、Linux | `um` 离线解密 | 旧版 qmc 直接可解；新版要 mmkv + 16 位密钥 |
| Windows 但没装 frida | 自动退回 `um` 离线解密 | 同上 |

日志里先看一行 `开始解密: xxx（um 离线）` 还是只有「开始解密」——前者说明走的是 um。

**登录是硬前提**：未登录时 `EncAndDesMediaFile::Open` 直接抛 `system error`，连文件都打不开。
2026-11-01 在本机 21.92 上实测：未登录时 3/3 全部 `system error`；登录后同一批文件 Open 成功。
程序现在会自动等你登录（`qq_login_timeout`，默认 300 秒）。

**ekey 是按曲目懒加载的**：客户端只把「实际播放过」的曲目的 ekey 载入内存。同文件播放前后对比：

| 阶段 | 结果 |
|---|---|
| 播放前 | `Error: system error` |
| 播放该文件后 | 输出 `fLaC`，字节数 = 原文件 - 192 |

所以批量解密前要让客户端把目标曲目过一遍（播放或试听一次）。客户端重启后内存里的 ekey 表清空，
需要重新预热。**这与会员状态无关**——账号到期不影响已缓存曲目的解密。

> ⚠️ **不要把源文件路径直接交给 `Open`**。`EncAndDesMediaFile::Open` 会把传入路径截断成 0 字节
> （实测踩过，一次性毁掉 7 个文件）。所有解密路径都必须先复制到暂存副本，只对副本操作。

**Frida 通道**（Windows 独有）：注入正在运行的 `QQMusic.exe`，从 `QQMusicCommon.dll` 的导出
表里按 MSVC 名字修饰找 `?Open@EncAndDesMediaFile@@...`；hook 脚本默认
`tools/hook_qq_music.js`，移动过就设 `MUSIC_HELPER_QQ_HOOK`。macOS 版 QQ 音乐是 Mach-O 应用，
没有 `QQMusicCommon.dll`，也没有那套导出名，所以 mac 上永远走 um。

**Frida 通道排错**（2026-11-01 在本机 21.92 上逐条实测过）：

| 现象 | 原因 | 处理 |
|---|---|---|
| `Frida-ERROR: Unable to locate the ntdll loader TLS routines`，进程直接消失 | frida 17.25.0 在 Windows 10 21H2 上的回归，注入任何进程都崩 | 降到 `frida==17.3.2`（`requirements.txt` 已钉 `<17.25.0`） |
| `frida.attach()` 报 `TransportError: timeout` | 同上；也可先 attach `notepad.exe` 验证 frida 本身是否可用 | 先修 frida 版本 |
| `Error: system error` | 未登录；或该曲目的 ekey 还没加载 | 登录，并让客户端播放/试听一次该曲目 |
| 有产出但头不是 `fLaC`（如 `577b5377`） | Open 成功却没拿到有效 ekey，读出来仍是密文 | 同上，先播放预热 |
| `expected at least one callback` | `Interceptor.attach` 的回调名写成了 `onExit` | 正确名是 `onLeave` |

判断 ekey 有没有就绪，看**输出文件的头 4 字节**最直接：`fLaC`/`OggS` 才算解开，其他十六进制
值都是密文。想看客户端有没有加载过 ekey，可以挂
`?SetEkey@EncAndDesMediaFile@@QAE_NPBDH@Z`（脚本 `tests/manual/manual_frida_e2e.py` 就是这么做的）。

**注意 `EncType`**：`?GetEncType@EncAndDesMediaFile@@SA?AW4EncType@1@PB_W@Z` 是静态函数，只读
文件头、不需要 ekey，最适合拿来判断「这批文件还需不需要密钥」。本机 21.92 下载的 1290 个文件
**全是 2**（新版 qmc），意味着 frida 和 um 都需要外部 ekey；19.51 下载的会是内嵌 ekey 的旧格式，
`um` 直接能解——这也是 macOS 上推荐装 8.8.0(20230903) 的原因。

**um 通道**报错对照表：

| 报错 | 原因 | 处理 |
|---|---|---|
| `找不到um（unlock-music CLI）… 当前平台 macOS` | `tools/` 里没有对应架构的 um | 补 `tools/um-darwin-<arch>`，或用 `MUSIC_HELPER_UM_EXE` 指过去 |
| `缺少可执行权限 … chmod +x` | 从 Windows 克隆的仓库不记录 exec 位 | 按提示执行 `chmod +x` |
| `qmc: detect file type failed` | 文件不是真的加密音频（或被别的东西改过） | 确认 `.mflac/.mgg` 来源 |
| `failed to load vault: failed to decode key: unexpected EOF` | 只给了 mmkv 没给密钥 | 同时配 `qmc_mmkv` + `qmc_mmkv_key`（见 [configuration.md](configuration.md#31-qq-音乐解密凭据qmc_mmkv--qmc_mmkv_key)） |
| `no any decoder can resolve the file` | 文件既不是 qmc 也不是 um 认识的容器 | 同上，先确认文件真的是从 QQ 音乐下载的加密文件 |

手工试一个文件（不经过流水线）：

```bash
# macOS（Windows 换成 tools/um.exe）
tools/um-darwin-arm64 -i path/to/song.mflac -o /tmp/out -V
# 新版 qmc 追加两个参数（两者必须同时给）
tools/um-darwin-arm64 -i path/to/song.mflac -o /tmp/out \
    --qmc-mmkv ~/Library/Containers/com.tencent.QQMusicMac/Data/Library/\
"Application Support/QQMusicMac/mmkv/MMKVStreamEncryptId" \
    --qmc-mmkv-key <16 位密钥> -V
```

`um` 同时能解 `.ncm`、`.kgm/.kgma`、`.kwm`、`.x2m/.x3m`、`.tm2/.tm3` 等，`--supported-ext`
可以看完整清单（三平台版本一致，都是 v0.2.12）。

**16 位密钥到底是什么**：它是 mmkv 库这个 SQLite 式文件本身的加密密码（16 个 ASCII 字符），
不是歌曲的 ekey。只有 macOS 客户端从 2023.09.03 之后才把 mmkv 加密；`--qmc-mmkv-key`
对的就是这种情况，官方没有公开提取方法，只能自行逆向。留空等于「库未加密」。

**Windows 上不要填这两项**：Windows 版 QQ 音乐不产生 `MMKVStreamEncryptId`，数据目录下的
`mmkv.default` 是客户端自己的配置库，把它当密钥库传给 um 只会得到 `key not found`。
所以 `find_mmkv()` 在 Windows 上直接返回空。那边正经的路是 Frida（`tools/hook_qq_music.js`），
或者用 19.51 及以下版本客户端下载（该区间文件本身不带 qmc2 加密）。

**但 Frida 也不是万能的**：实测 21.92 冷启动后 `GetSize` 恒为 0、60 秒内 `SetEkey`
一次都没被调用，说明 ekey 是「播放时从服务器取、只在内存里」的。所以对 21.92 下载的
新版 qmc，**唯一稳定可行的办法是换 19.51 客户端重新下载**。两个旧版安装包的获取方式、
校验值和屏蔽更新步骤见
[third_party/qqmusic/README.md](../third_party/qqmusic/README.md)。

**macOS 上拿不到 16 位密钥时**：旧版 qmc（`qmc1`/`mflac0`）本来就不需要它，能直接解；
新版 qmc 就是绕不过去，只能拿到 mmkv 库本身（未加密）或自行逆向出那个密码。
um 在 macOS 上会自动去 `~/Library/Containers/com.tencent.QQMusicMac/…/mmkv/` 读库，
所以本该加密的库如果读不出 key，报错会落在 `key not found` 而不是「找不到进程」。
代码不会去猜密钥。

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

### 声纹去重移走了我不想移的那份

现在「谁留谁走」按音质判断，不再逐个确认，所以出现这种情况只有两种原因：

1. **格式层级判断不符合你的口味**（例如你觉得 WAV 拷贝该让位给 FLAC）：层级表在
   `G:\soundalike` 的 `move.go: formatTier`，改完重新编译 `tools/soundalike*`；
2. **码率被当成音质**：同格式下 320 kbps 会赢 128 kbps，这是有意的；若两者其实一样，
   差值小于 2% 时不会自动移，而是停下来问。

移走的文件在 `DUPLICATE_DIR`，直接搬回去即可；`DUPLICATE_DIR` 与库不在同一盘时走
「复制 + 删除」，失败会报错而不是留下半份。

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

### `--check` 报「音乐库不存在，无法检查」

退出码 1，报告不会生成。这是刻意的：扫描不存在的目录只会得到「零问题」的假报告。
按提示检查 `config.ini` 的 `paths.library_dir` 或 `MUSIC_HELPER_LIBRARY_DIR`：

```bash
python -c "import config, os; print(config.LIBRARY_DIR, os.path.isdir(config.LIBRARY_DIR))"
```

### 报告里有「文件名格式」问题，`--fix` 却没改

改名撞车了：目标文件名已存在，`Plan` 不会加 `_1` 后缀，而是记一条失败。
去 `log/journal.jsonl` 搜 `"ok": false`，`error` 字段会写明「目标已存在」。
先手工确认那两个文件是不是同一首，再决定删哪个或改成别的名字。

### 文件被放进 `unknown/` 而不是年份目录

检查年份标签是否可解析（`2003` 可以，`0`、`2013年` 前后带奇怪字符、空值都不行）。
`--check` 报告里的「标签不完整」会指出具体缺哪一项；年份明明有值却报「年份无法解析」时，
说明值不是 1900–2100 之间的四位数字。

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
