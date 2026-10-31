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
| `soundalike.exe` | 声纹去重、库一致性 | `tools/soundalike.exe` | `tools.soundalike_exe` / `MUSIC_HELPER_SOUNDALIKE_EXE` | 去重与 `--checkdb` 失败，其余流程可用 |
| `um.exe` | 网易云 `.ncm` 解密 | `tools/um.exe` | `tools.um_exe` / `MUSIC_HELPER_UM_EXE` | 网易云解密失败，QQ 不受影响 |
| Frida hook | QQ 音乐解密 | `tools/hook_qq_music.js` | `tools.qq_hook` / `MUSIC_HELPER_QQ_HOOK` | QQ 解密失败 |
| `fpcalc` | AcoustID 指纹 | 系统 `PATH` | — | 声纹补标签降级为在线平台查询 |

两个 exe 随仓库分发。`soundalike` 是 Go 程序，Windows 之外无法直接执行；macOS/Linux 上做
开发验证时请设置 `MUSIC_HELPER_SOUNDALIKE_EXE` 指向本机可用的等价程序，或跳过该步骤。

## 4. 超时与业务阈值

| 配置项 | 默认 | 环境变量 | 作用 |
|---|---|---|---|
| `subprocess_timeout` | `3600` 秒 | `MUSIC_HELPER_TIMEOUT` | 外部程序单次执行上限 |
| `fpcalc_length` | `120` 秒 | `MUSIC_HELPER_FPCALC_LENGTH` | 指纹采样长度，必须与声纹工具一致 |
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
| `AUDIO_EXTENSIONS` | `.flac .mp3 .wav .ape .ogg` | 可播放音频；扫描、查重、归档、歌词检查都使用它 |
| `MUSIC_EXTENSIONS` | 上面 + `.mflac .mgg .ncm` | 全部音乐文件（含加密） |
| `NETEASE_VIP_EXTENSIONS` | `.ncm` | 网易云解密扫描 |
| `QQ_VIP_EXTENSIONS` | `.mflac .mgg` | QQ 解密扫描 |
| `VIP_EXTENSIONS` | 两者并集 | 通用 VIP 判断 |

`core/naming.py` 的 `is_audio()` 直接引用 `config.AUDIO_EXTENSIONS`，不再维护第二份扩展名表。
新增可播放格式时只改 `config.py` 一处。

## 6. 自检

```bash
python -c "import config, json; print(json.dumps(config.as_dict(), ensure_ascii=False, indent=2))"
python main.py --check --dry-run
```

启动时会打印当前配置，并对不存在的 `LIBRARY_DIR` / `WORKSPACE_DIR` 给出 WARNING。
`config.validate()` 只返回问题列表，不抛异常，方便先 `--dry-run` 看清楚再动手。
