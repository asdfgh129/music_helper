# 配置说明

> 本文负责：配置来源与优先级、目录语义、外部程序、阈值、扩展名集合。
> 本文不负责：流程顺序（见 [workflow.md](workflow.md)）、判定规则（见 [rules.md](rules.md)）、
> 命令行参数（见 [usage.md](usage.md)）。

## 1. 配置来源与优先级

配置按以下顺序生效，**前面的覆盖后面的**：

1. 环境变量（`MUSIC_HELPER_*`）；
2. 项目根目录的 `config.ini`；
3. `config.py` 里的默认值。

复制示例文件即可开始本地配置：

```bash
# macOS / Linux
cp config.example.ini config.ini

# Windows PowerShell
Copy-Item config.example.ini config.ini
```

`config.ini` 已被 `.gitignore` 忽略。INI 的键名一律小写，分三节：

| 节 | 内容 |
|---|---|
| `[paths]` | 目录与声纹库路径 |
| `[tools]` | 外部程序路径 |
| `[settings]` | 超时、阈值、加密原文件去向 |

相对路径按**项目根目录**解析，例如 `db_path = data/music.db` 会得到
`<项目根>/data/music.db`；`D:\music` 这类绝对路径原样使用。
路径里出现 `%` 不会被当成插值（INI 以 `interpolation=None` 读取）。

环境变量 `MUSIC_HELPER_CONFIG` 可以让程序读取另一份 INI，便于测试或多环境切换：

```bash
MUSIC_HELPER_CONFIG=/path/to/test-config.ini python main.py --check --dry-run
```

`config.reload()` 可在同一进程内重新读取 INI 与环境变量；正常 CLI 运行不需要手动调用。

## 2. 目录语义

| 语义名 | 默认值 | 配置项 / 环境变量 | 作用 |
|---|---|---|---|
| `LIBRARY_DIR` | `D:\music` | `paths.library_dir` / `MUSIC_HELPER_LIBRARY_DIR` | 最终音乐库 |
| `WORKSPACE_DIR` | `G:\Temp` | `paths.workspace_dir` / `MUSIC_HELPER_WORKSPACE_DIR` | 流水线工作区：解密、拷贝、打标签都在这里；完整文件处理完仍留在这里 |
| `INCOMPLETE_DIR` | `G:\Unready` | `paths.incomplete_dir` / `MUSIC_HELPER_INCOMPLETE_DIR` | 标签不全、文件名与标签矛盾，等待人工处理 |
| `DUPLICATE_DIR` | `G:\Tmp` | `paths.duplicate_dir` / `MUSIC_HELPER_DUPLICATE_DIR` | 重复文件 |
| `NETEASE_DIR` | `G:\Neteasymusic` | `paths.netease_dir` / `MUSIC_HELPER_NETEASE_DIR` | 网易云下载根目录 |
| `NETEASE_VIP_DIR` | `<NETEASE_DIR>\VipSOngsDownload` | 随 `NETEASE_DIR` | 网易云加密文件目录 |
| `QQ_DIR` | `G:\QQMusic` | `paths.qq_dir` / `MUSIC_HELPER_QQ_DIR` | QQ 音乐下载根目录 |
| `QQ_VIP_DIR` | `<QQ_DIR>\VipSOngsDownload` | 随 `QQ_DIR` | QQ 加密文件目录 |
| `DECRYPT_STAGING_DIR` | `<WORKSPACE_DIR>\_decrypt` | `paths.decrypt_dir` / `MUSIC_HELPER_DECRYPT_DIR` | 解密暂存区 |
| `NETEASE_STAGING_DIR` | `<DECRYPT_STAGING_DIR>\netease` | 随上一项 | 网易云加密文件暂存 |
| `QQ_STAGING_DIR` | `<DECRYPT_STAGING_DIR>\qq` | 随上一项 | QQ 加密文件暂存 |
| `DB_PATH` | `<项目根>\music.db` | `paths.db_path` / `MUSIC_HELPER_DB` | soundalike 声纹库 |

建议把 `INCOMPLETE_DIR`、`DUPLICATE_DIR` 放在 `WORKSPACE_DIR` **外面**。`soundalike -temp` 会
递归扫描工作区，两个结果目录若嵌在里面，会被当成待扫描音频重复处理。

程序自身的运行产物固定写在项目内，不参与配置：

| 用途 | 路径 |
|---|---|
| 运行日志 | `log/Music-*.log` |
| 操作流水 | `log/journal.jsonl` |
| 报告 | `log/reports/` |
| 回收站 | `log/_trash/` |

旧配置名 `MAIN_DIR`、`TEMP_COMPLETED_DIR`、`TEMP_MOVE_DIR`、`TEMP_REVIEW_DIR`、
`NETEASE_TMP_DIR`、`QQ_TMP_DIR` 仍作为别名存在，但新代码与文档只使用语义名。

## 3. 外部程序

| 程序 | 用途 | 默认路径 | 配置项 / 环境变量 | 缺失时 |
|---|---|---|---|---|
| `soundalike` | 声纹去重、库一致性 | Windows `tools/soundalike.exe`；macOS `tools/soundalike-darwin-{arm64,amd64}` | `tools.soundalike_exe` / `MUSIC_HELPER_SOUNDALIKE_EXE` | 去重与 `--checkdb` 失败，其余流程可用 |
| `fpcalc` | 指纹（补标签 + 查重） | `tools/fpcalc`（macOS 通用二进制）；没有则用 `PATH` | `tools.fpcalc_exe` / `MUSIC_HELPER_FPCALC_EXE` | 补标签降级为在线平台查询，声纹去重失败 |
| `um` | 网易云 `.ncm`、QQ `.mflac/.mgg` 等离线解密 | Windows `tools/um.exe`；macOS `tools/um-darwin-{arm64,amd64}` | `tools.um_exe` / `MUSIC_HELPER_UM_EXE` | 网易云解密失败；QQ 在没有 Frida 方案时也失败 |
| Frida hook | QQ 音乐解密（**仅 Windows**） | `tools/hook_qq_music.js` | `tools.qq_hook` / `MUSIC_HELPER_QQ_HOOK` | QQ 自动退回 `um` 离线解密 |

**QQ 音乐客户端**是 QQ 解密的硬前提，由 `decrypto/qq_client.py` 统一管理：

| 配置项 | 环境变量 | 默认 | 说明 |
|---|---|---|---|
| `tools.qq_client_exe` | `MUSIC_HELPER_QQ_CLIENT` | 留空自动探测 | Windows 读注册表 `HKLM\SOFTWARE\WOW6432Node\Tencent\QQMusic` 的 `Install` 值，再按常见路径兜底；macOS 查 `/Applications/QQMusic.app` |
| `tools.qq_installer` | `MUSIC_HELPER_QQ_INSTALLER` | `tools/QQMusic_Setup_1951.exe` | 未安装时自动安装的旧版（19.51 下载的文件密钥内嵌，`um` 也能解） |
| `tools.qq_update_patch` | `MUSIC_HELPER_QQ_PATCH` | `tools/Q音屏蔽更新.zip` | 屏蔽自动更新；装完立即覆盖 `QQMusicUp.exe`，否则升级后导出符号变化会让 hook 失效 |
| `tools.qq_mac_dmg` | `MUSIC_HELPER_QQ_MAC_DMG` | `tools/QQMusicMac_Mgr_8.8.0_20230903.dmg` | macOS 未安装时用的旧版 |
| `tools.qq_mac_patch` | `MUSIC_HELPER_QQ_MAC_PATCH` | `tools/QQ 音乐 Mac 屏蔽升级.tar.gz` | macOS 屏蔽升级（改 `Info.plist` 版本号 + 重签 + 去 quarantine） |
| `tools.qq_login_timeout` | `MUSIC_HELPER_QQ_LOGIN_TIMEOUT` | `300` | 未登录时等待扫码的秒数；`0` 表示不等待 |

未登录时 `EncAndDesMediaFile::Open` 会直接抛 `system error`，因此程序会先等登录再开始搬文件。

`tools/` 随仓库分发：`soundalike.exe`（Windows）、`soundalike-darwin-arm64` /
`soundalike-darwin-amd64`（macOS，纯 Go 构建）、`fpcalc`（macOS 通用二进制，arm64 + x86_64）、
`um.exe`（Windows）、`um-darwin-arm64`、`um-darwin-amd64`（macOS，纯 Go 构建）、
`hook_qq_music.js`。平台选择由 `config.SOUNDALIKE_EXE` / `config.UM_EXE` / `config.FPCALC_EXE`
自动完成（`sys.platform` + `platform.machine()`），需要换程序时用环境变量覆盖即可。

Windows 的 `fpcalc.exe` 一般已在 `C:\Windows\System32`，仓库里不再单独放一份；macOS 上
`soundalike` 只按 `PATH` 找 `fpcalc`，所以调用时会临时把 `tools/` 前置进 `PATH`。

**执行前会校验「这份产物在本机能跑」**（`utils.tool_problem`），三种情况直接报错而不是等
`subprocess` 抛异常：

| 现象 | 提示 |
|---|---|
| 文件没随仓库带过来 | `找不到…（当前平台 macOS，确认 tools/ 里带了该平台的产物）` |
| 从 Windows 克隆、缺可执行位 | `缺少可执行权限…运行 chmod +x "…"` |
| 拿错平台的文件 | `是 Windows PE，而本机是 macOS，执行会报 Exec format error` |

`chmod` 只对 macOS/Linux 有意义：Windows 克隆不记录 exec 位，到 Mac 上第一次用之前要补。
找不到配置的路径时，还会在 `PATH` 里找同名程序（`um`、`soundalike` 用系统包安装的场景）。

### 3.1 QQ 音乐解密凭据（`qmc_mmkv` / `qmc_mmkv_key`）

新版 qmc（`.mflac/.mgg` 里的 `qmc2`、`mflac1` 等）离线解密需要 QQ 音乐客户端的 mmkv 与
16 位密钥：

| 配置项 | 默认 | 环境变量 | 作用 |
|---|---|---|---|
| `qmc_mmkv` | 空（自动找） | `MUSIC_HELPER_QMC_MMKV` | mmkv 密钥库路径，macOS 上是 `…/QQMusicMac/mmkv/MMKVStreamEncryptId`；留空时按平台自动找（要求同名 `.crc` 存在） |
| `qmc_mmkv_key` | 空 | `MUSIC_HELPER_QMC_KEY` | mmkv 库自身的 16 位 ASCII 密码；只能人工填，客户端不会把它写成明文 |

**两个必须同时给。** 只给 mmkv 不给密钥时 `um` 会去开 vault 并报
`failed to load vault: failed to decode key: unexpected EOF`，连本来不需要凭据的旧版 qmc
也一起解不开，所以代码里只有一半凭据时会全部丢掉。

**这个密钥不是歌曲密钥**，而是 mmkv 数据库文件的加密密码（16 个 ASCII 字符）。只有 macOS
客户端从 2023.09.03 之后才加密 mmkv；官方没有公开提取方法，留空等于「库未加密」。

**Windows 上自动发现是关闭的**（`find_mmkv()` 直接返回空）：Windows 版客户端不产生
`MMKVStreamEncryptId`，数据目录里的 `mmkv.default` 只是它的配置库，拿它当密钥库喂给 um 只会
`key not found`。Windows 上的正路是 Frida 注入（见 [troubleshooting.md](troubleshooting.md#qq-音乐解密失败)），
或者用 19.51 及以下版本客户端下载——那个区间的文件本身不带 qmc2 加密。

旧版 qmc（`qmc1` / `mflac0`）不需要这两个值，留空就能解。

## 4. 超时与业务阈值

| 配置项 | 默认 | 环境变量 | 作用 |
|---|---|---|---|
| `subprocess_timeout` | `3600` 秒 | `MUSIC_HELPER_TIMEOUT` | 外部程序单次执行上限 |
| `fpcalc_length` | `120` 秒 | `MUSIC_HELPER_FPCALC_LENGTH` | 指纹采样长度；补标签与声纹去重共用。声纹库会锁定该值，改它要删库重建（见 [fingerprint.md](fingerprint.md#85-阈值)） |
| `fingerprint_threshold` | `50` | `MUSIC_HELPER_FP_THRESHOLD` | 声纹/在线匹配最低分（0–100） |
| `duration_tolerance` | `3.0` 秒 | `MUSIC_HELPER_DURATION_TOLERANCE` | 标签/文件名查重允许的时长误差 |
| `max_cover_size` | `5242880` 字节 | `MUSIC_HELPER_MAX_COVER_SIZE` | 封面下载上限，超过直接放弃 |
| `encrypted_source_mode` | `return` | `MUSIC_HELPER_ENCRYPTED_MODE` | 解密成功后加密原文件去向 |

`encrypted_source_mode` 的可选值：

| 值 | 行为 |
|---|---|
| `return` | 把本次移入暂存区的加密原文件搬回对应 VIP 下载目录 |
| `trash` | 移入 `log/_trash/` |
| `keep` | 留在 `<WORKSPACE_DIR>\_decrypt` 下，人工处理 |

无论哪种模式，都只处理**本次运行搬进去的文件**，不遍历 VIP 目录或暂存区顶层。

## 5. 扩展名集合

| 配置 | 内容 | 用途 |
|---|---|---|
| `AUDIO_EXTENSIONS` | `.flac .mp3 .wav .ape .ogg .opus .m4a .wma .dsf` | 可播放音频；扫描、查重、归档、歌词检查都使用它 |
| `MUSIC_EXTENSIONS` | 上面 + `.mflac .mgg .ncm` | 全部音乐文件（含加密） |
| `NETEASE_VIP_EXTENSIONS` | `.ncm` | 网易云解密扫描 |
| `QQ_VIP_EXTENSIONS` | `.mflac .mgg` | QQ 解密扫描 |
| `VIP_EXTENSIONS` | 两者并集 | 通用 VIP 判断 |

`core/naming.py` 的 `is_audio()` 直接引用 `config.AUDIO_EXTENSIONS`，不再维护第二份扩展名表。

裸 `.aac`（ADTS 流）**故意不在表里**：它没有统一的容器标签，读不出歌手/歌名，
一旦纳入扫描，整批文件会被判成「标签不完整」搬进 `INCOMPLETE_DIR`。

### 5.1 新增可播放格式要做两件事

只改 `config.py` 不够——`core/tags.py` 里必须有对应的读取器，否则整类文件读不到标签：

1. `config.AUDIO_EXTENSIONS` 加扩展名（顺带 `MUSIC_EXTENSIONS`）；
2. `core/tags.py` 的 `_READERS` 与 `_COVER_READERS` 各注册一项（`_WRITERS` 用于写标签）。

`tests/test_tags.py` 会遍历 `AUDIO_EXTENSIONS` 检查「每个扩展名都有读取器」，漏注册直接红。

## 6. 自检

```bash
python -c "import config, json; print(json.dumps(config.as_dict(), ensure_ascii=False, indent=2))"
python main.py --check --dry-run
```

启动时会打印当前配置，并对不存在的 `LIBRARY_DIR` / `WORKSPACE_DIR` 给出 WARNING。
`config.validate()` 只返回问题列表，不抛异常，方便先 `--dry-run` 看清楚再动手。

但**检查类命令例外**：`--check` 与 `--only-check-file-name` 发现目标目录不存在时会直接
报错并以退出码 1 结束——扫描空目录只会得到「零问题」的假报告，比报错更危险。
