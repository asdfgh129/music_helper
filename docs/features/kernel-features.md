# 各内核独有功能清单

「内核」= 解密途径。本项目有三条解密途径，通道选择逻辑集中在
`decrypto/qq.py` 的 `decrypt_backend()` 与 `web/api.py` 的 `_platform_info()`：
Windows 优先 Frida，其余情况走 `um`。与途径无关的公共能力见
[common-features.md](common-features.md)。

## 一、网易云内核（`um` 解密 `.ncm`，三平台同一套）

| 功能 | 实现位置 |
|---|---|
| `.ncm` 免密钥解密（三平台统一参数，不需要 mmkv/凭据） | `services/decrypt.decrypt_netease` + `decrypto/um.run` |
| 网易云 VIP 目录（默认 `<网易云目录>/VipSOngsDownload`）扫描 `.ncm` | `config.NETEASE_VIP_DIR` + `decrypt.encrypted_candidates` |
| 独立暂存区 `DECRYPT_STAGING_DIR/netease`（与 QQ 互不干扰） | `config.NETEASE_STAGING_DIR` |
| 产物扩展名由文件内容决定（`.ncm` 里可能是 mp3/flac），按产物回填结果 | `decrypt._find_output` |

网易云途径没有平台分支：`um` 是纯 Go 程序，`.ncm` 格式自带密钥头，
所以这一条在三平台上行为完全一致。

## 二、QQ 内核 · Windows Frida 通道（新版 QQ + 注入）

| 功能 | 实现位置 |
|---|---|
| Frida 附加运行中的 `QQMusic.exe`，按 MSVC 修饰名从 `QQMusicCommon.dll` 导出表定位 `EncAndDesMediaFile::Open` | `decrypto/qq._run_frida` + `tools/hook_qq_music.js` |
| 解密前置环境检查：未装 → 自动静默安装 19.51（`/S`）→ 未启动 → 启动并等待进程 → 未登录 → 轮询等待（默认 300 秒） | `decrypto/qq_client.ensure_ready`（安装/启动/登录三段各自独立可关） |
| Windows 客户端探测：注册表 `HKLM/HKCU` 的 Install 值 + 常见安装路径 | `qq_client.find_windows` |
| 进程探测与启动：`tasklist` 过滤 + 直接 `Popen` | `qq_client.is_running` / `start` |
| 屏蔽更新补丁：解 zip 覆盖客户端文件（升级会让导出符号变化，必须钉住版本） | `qq_client.apply_patch_windows` |
| 自动登录探测：采样最近解密样本目录判断客户端是否已登录（`probe_sample` → `probe_login`） | `qq_client.probe_sample` / `probe_login` / `wait_login` |
| 注入路径防截断：`Open` 会截断传入路径，先把加密文件按完整路径哈希复制到临时目录再解密 | `decrypto/qq._run_frida`（`tempfile.mkdtemp` + md5 命名） |
| 逐文件解密 + 失败隔离；全部失败时给出三条例程化原因（未登录 / 版本符号不匹配 / ekey 未加载） | `decrypto/qq._run_frida` finally 块 |
| Frida 起不来（没装 / 进程没开 / 脚本加载失败）自动回退 `um` 通道，不直接失败 | `decrypto/qq.run_decrypt` |
| 来源链接回查：QQ 搜索 API 反查歌曲页，写 `log/conversion_log.csv` | `decrypto/source_finder.guess_song_url` + `qq.append_csv` |
| frida 版本上限钉死 `<17.25.0`（17.25.0 在 Win10 21H2 上注入必崩） | `requirements.txt` |
| 独立 CLI 复现环境：`python decrypto/qq.py -i/-o`，可关安装/等待/前置检查（排错用） | `decrypto/qq.__main__` |

## 三、QQ 内核 · `um` 离线通道（macOS 主，Linux / 无 frida 的 Windows 兜底）

| 功能 | 实现位置 |
|---|---|
| 旧版 qmc（`qmc1`/`mflac0`）免密钥解密 | `decrypto/um.run`（不传凭据） |
| 新版 qmc（`qmc2`、mflac1）凭据：QQ 音乐客户端 mmkv 库 + 16 位密钥（随账号下发，只能手工配置） | `config.QMC_MMKV` / `QMC_MMKV_KEY` + `um.qmc_credentials` |
| macOS mmkv 自动发现：扫 `~/Library/Containers/*/.../QQMusic` 等三个常见根，找 `MMKVStreamEncryptId`（需同名 `.crc` 才算可用） | `um.find_mmkv`（Windows 刻意不自动发现：客户端不产生该文件） |
| 凭据必须成对生效：只传 mmkv 不传密钥会让 um 连旧版 qmc 也解不开，运行时丢弃半套凭据 | `um.run` |
| 密钥日志脱敏：命令行回显时 `--qmc-mmkv-key` 的值打码为 `***` | `um._display_command` |
| 逐文件调用 um（um 处理目录遇到坏文件会 FATAL 整批退出，逐个调用隔离失败） | `decrypto/qq._run_um` |
| 失败详情提取（优先 FATAL 行）+ 缺凭据时给可照做的 `QMC_HINT` | `um.failure_detail` / `um.QMC_HINT` |
| macOS 源码编译指引（上游因 DMCA 整站 451，只能走 `goproxy.cn`） | `um.exe_problem` 的提示文本 |
| 逐文件解密 + 与 Frida 同一套「已存在跳过 / 产物判定 / 来源记录」 | `decrypto/qq._run_um` |

## 四、平台差异功能（解密之外）

| 功能 | Windows | macOS |
|---|---|---|
| QQ 客户端安装器 | `tools/QQMusic_Setup_1951.exe`（静默 `/S`） | `tools/QQMusicMac_Mgr_8.8.0_20230903.dmg`（挂载安装） |
| 屏蔽更新补丁 | `Q音屏蔽更新.zip` | `QQ 音乐 Mac 屏蔽升级.tar.gz` |
| 客户端定位 | 注册表 + 安装路径 | `/Applications/QQMusic.app` |
| 启动方式 | `Popen(exe)` | `open -a QQMusicMac` |
| 进程探测 | `tasklist /FI` | `pgrep -x` |
| 解密产物命名 | `tools/um.exe`、`soundalike.exe`、`fpcalc.exe`、`ffmpeg.exe` | `tools/um-darwin-<arch>`、`soundalike-darwin-<arch>` 等（按 CPU 架构挑） |
| 二进制预检 | PE 魔数校验 | Mach-O 魔数校验 + `chmod +x` 检查 |
| 子进程窗口 | `CREATE_NO_WINDOW` 防黑框 | — |

平台分支的实现约束（`AGENTS.md` 硬约束 9）：业务模块不写 `sys.platform` 分支，
路径由 `config._default_*()` 按平台挑、支持环境变量覆盖，执行前统一走
`utils.tool_problem()` 预检；平台专属的安装/启动/登录逻辑集中在
`decrypto/qq_client.py` 一处。

## 五、能力矩阵速查

| 能力 | 网易云 um | QQ Frida（Win） | QQ um 离线 |
|---|---|---|---|
| 需要密钥/凭据 | 否 | 否（向运行中的客户端要明文） | 旧版 qmc 否；新版 qmc 要 mmkv+key |
| 需要客户端运行 | 否 | 是（已安装+启动+登录） | 否 |
| 自动安装客户端 | — | 19.51 + 屏蔽更新补丁 | — |
| 失败粒度 | 文件级（逐个调） | 文件级（脚本逐个导出） | 文件级（逐个调） |
| 平台 | 三平台一致 | 仅 Windows | macOS / Linux / 无 frida 的 Windows |
| 回退关系 | — | 失败自动回退 um | 是 Frida 的回退目标 |
