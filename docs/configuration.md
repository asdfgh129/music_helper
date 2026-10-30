# 配置说明

所有配置集中在 `config.py`，且**只放纯数据**——不导入任何业务模块（避免循环导入）。
路径类配置都支持环境变量覆盖，换盘符或临时借用别的目录时不用改代码。

## 1. 目录结构约定

```
下载目录（平台管理）                 流水线工作目录            主目录（最终音乐库）
G:\Neteasymusic\VipSOngsDownload ┐                        ┌ D:\music\1980-1989\1985\
G:\Neteasymusic\（普通文件）      ├→ G:\Temp ──────────────┤ D:\music\1990-1999\1997\
G:\QQMusic\VipSOngsDownload ─────┘        （解密/去重/打标） └ D:\music\unknown\
G:\QQMusic\（普通文件）
```

| 角色 | 默认路径 | 配置项 | 环境变量 |
|---|---|---|---|
| 主目录（最终库） | `D:\music` | `MAIN_DIR` | `MUSIC_HELPER_MAIN_DIR` |
| 流水线工作目录 | `G:\Temp` | `TEMP_COMPLETED_DIR` | `MUSIC_HELPER_TEMP_DIR` |
| 重复/待处理文件 | `G:\Tmp` | `TEMP_MOVE_DIR` | `MUSIC_HELPER_MOVE_DIR` |
| 不一致文件待处理区 | `G:\Tmp\review` | `TEMP_REVIEW_DIR` | `MUSIC_HELPER_REVIEW_DIR` |
| 网易云根目录 | `G:\Neteasymusic` | `NETEASE_DIR` | `MUSIC_HELPER_NETEASE_DIR` |
| 网易云 VIP 下载 | `<NETEASE_DIR>\VipSOngsDownload` | `NETEASE_VIP_DIR` | 随上一项 |
| 网易云解密临时目录 | `G:\NeTmp` | `NETEASE_TMP_DIR` | `MUSIC_HELPER_NETEASE_TMP` |
| QQ 音乐根目录 | `G:\QQMusic` | `QQ_DIR` | `MUSIC_HELPER_QQ_DIR` |
| QQ VIP 下载 | `<QQ_DIR>\VipSOngsDownload` | `QQ_VIP_DIR` | 随上一项 |
| QQ 解密临时目录 | `G:\QQTmp` | `QQ_TMP_DIR` | `MUSIC_HELPER_QQ_TMP` |

程序自身产物固定在项目内，不可配置：

| 用途 | 路径 |
|---|---|
| 运行日志 | `log/Music-*.log`、`log/<操作>-*.log` |
| 操作流水 | `log/journal.jsonl` |
| 报告 | `log/reports/` |
| 回收站 | `log/_trash/` |

## 2. 外部程序

| 程序 | 用途 | 默认路径 | 环境变量 | 缺失时 |
|---|---|---|---|---|
| `soundalike.exe` | 声纹去重、库一致性 | `fingerprint/soundalike.exe` | `MUSIC_HELPER_SOUNDALIKE_EXE` | 去重与 `--checkdb` 报错，其余流程正常 |
| `um.exe` | 网易云 `.ncm` 解密 | `decrypto/um.exe` | `MUSIC_HELPER_UM_EXE` | 网易云解密报错，QQ 解密不受影响 |
| `fpcalc` | AcoustID 指纹 | 系统 PATH | — | 声纹→标签降级为纯在线查询 |

两个 exe 随仓库分发（约 8.2 MB + 4.6 MB），克隆即可用。若迁移位置，务必同步环境变量。

## 3. 超时

| 配置 | 默认 | 环境变量 | 说明 |
|---|---|---|---|
| `SUBPROCESS_TIMEOUT` | `3600` 秒 | `MUSIC_HELPER_TIMEOUT` | 外部程序（解密、声纹）单次执行上限 |

旧实现没有超时，外部 exe 卡死会拖住整条流水线。现在超时会中止该步骤并记日志，
不会杀掉整个进程。

## 4. 业务阈值

| 配置 | 默认 | 作用 |
|---|---|---|
| `DURATION_TOLERANCE` | `3.0` 秒 | 重复判定允许的时长误差；同一首歌不同剪辑版本常差 1–3 秒 |
| `FINGERPRINT_THRESHOLD` | `50` | 声纹/在线匹配的最低分数（0–100），低于此值不写入标签 |
| `FPCALC_LENGTH` | `120` | 指纹采样长度（秒），必须与 `soundalike` 一致，否则比对无意义 |
| `MAX_COVER_SIZE` | `5 MB` | 封面下载上限，超过直接放弃，避免拖慢批量处理 |

### 加密原文件去向

| 配置 | 默认 | 可选值 | 行为 |
|---|---|---|---|
| `ENCRYPTED_SOURCE_MODE` | `return` | `return` | 解密成功后，把本次移入临时目录的加密原文件搬回对应 VIP 下载目录 |
| | | `trash` | 移入 `log/_trash/` |
| | | `keep` | 留在解密临时目录，人工处理 |

环境变量：`MUSIC_HELPER_ENCRYPTED_MODE`。

> `return` 只处理「本次运行搬进去的那几个文件」，不会遍历 VIP 目录，也不会动临时目录里的其他文件。
> 由于原文件回到 VIP 目录，下次带 `--month` 运行时可能再次被扫到——这是刻意保留的旧行为，
> 便于对照原始加密文件；不想重复处理就把它们从 VIP 目录移走或改用 `trash`。

## 5. 扩展名集合

| 配置 | 内容 | 用途 |
|---|---|---|
| `AUDIO_EXTENSIONS` | `.flac .mp3 .wav .ape .ogg` | 普通音频，扫描与归档使用 |
| `MUSIC_EXTENSIONS` | 上面 + `.mflac .mgg .ncm` | 全部音乐文件（含加密），供需要广范围匹配的场景使用 |
| `NETEASE_VIP_EXTENSIONS` | `.ncm` | 网易云解密扫描 |
| `QQ_VIP_EXTENSIONS` | `.mflac .mgg` | QQ 解密扫描 |
| `VIP_EXTENSIONS` | 两者并集 | 通用 VIP 判断 |

`core/naming.py` 另有一份 `_AUDIO_EXTS` 用于「这是不是音频文件」的判断，**只描述可播放格式**，
不含加密后缀。新增格式时两处都要改。

## 6. 环境变量速查

```bash
# Windows PowerShell
$env:MUSIC_HELPER_MAIN_DIR = "E:\Music"
$env:MUSIC_HELPER_TEMP_DIR = "E:\Temp"
python main.py --check --dry-run
```

```bash
# bash
export MUSIC_HELPER_MAIN_DIR=/mnt/e/Music
python main.py --check --dry-run
```

## 7. 配置自检

```bash
python -c "import config, json; print(json.dumps(config.as_dict(), ensure_ascii=False, indent=2))"
python main.py --check --dry-run    # 启动时会打印配置并对不存在的目录给出 WARNING
```

`config.validate()` 只检查主目录与工作目录是否存在，缺失时是**警告**而非退出——
方便先用 `--dry-run` 看清楚再决定。
