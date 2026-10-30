# 故障排查

按「症状 → 原因 → 处理」组织。所有排查都从 `log/` 开始：主日志、`journal.jsonl`、
报告三者能还原出「程序认为发生了什么」。

## 1. 启动相关

### `ImportError: cannot import name 'X' from 'config'`

可选依赖缺失，或运行时用了旧版本代码。

```bash
python -m pip install -r requirements.txt
python -c "import config, utils, main; print('ok', config.__version__)"
```

`config.py` 只放纯数据，不应该导出任何类。如果出现类似
`cannot import name 'MusicTagger' from 'config'`，说明代码是重构前（`0.2.0` 之前）的版本。

### `模块月份格式错误: 2024-06`

`--month` 只接受 6 位 `YYYYMM`：

```bash
python main.py --month 202406    # 正确
```

### 启动就提示「主目录不存在」

`config.validate()` 只警告不退出，方便先看计划。检查：

```bash
python -c "import config, json; print(json.dumps(config.as_dict(), ensure_ascii=False, indent=2))"
```

路径不对就改 `config.py` 或设环境变量（见 [configuration.md](configuration.md)）。

---

## 2. 解密相关

### 「没有待解密的加密文件」

- `--month` 按**文件修改时间**过滤，跨月的文件不会被选中；先去掉 `--month` 试。
- 只扫描 VIP 下载目录的**当层**（不递归），检查文件是否在子目录里。
- 扩展名要匹配：网易云 `.ncm`，QQ `.mflac/.mgg`。

### 「未产生解密文件（返回码 0）」

外部程序返回成功但没写文件。逐项确认：

1. `um.exe` / `Decrypto` 路径存在且可执行；
2. QQ 解密需要 **QQMusic 客户端正在运行**且已登录（Frida 注入进程）；
3. 用 `--debug` 看外部程序 stdout/stderr，日志里会原样打印；
4. 手动跑一次：

```bash
# 网易云
Decrypto\um.exe -i G:\NeTmp -o G:\Temp
```

### 「执行超时（>3600s）」

大批量时可能真的超过一小时。调整：

```bash
# Windows PowerShell
$env:MUSIC_HELPER_TIMEOUT = "7200"
```

超时按失败处理，本次移入的加密文件会自动还原回 VIP 目录，不会丢。

### 解密成功后加密原文件去哪了

由 `ENCRYPTED_SOURCE_MODE` 决定，默认 `return`：**搬回 VIP 下载目录**。

```bash
# 查这次运行搬了什么
findstr /C:"加密原文件" log\journal.jsonl
```

不想要原文件就设 `MUSIC_HELPER_ENCRYPTED_MODE=trash`（进回收站）。

---

## 3. 声纹去重

### `找不到外部程序: ...soundalike.exe`

路径默认是 `Fingerprint/soundalike.exe`。移动过就设：

```bash
$env:MUSIC_HELPER_SOUNDALIKE_EXE = "D:\tools\soundalike.exe"
```

### 声纹库「找不到记录」/ 每次都在重建

`soundalike.exe` 把 `music.db` 生成在**当前工作目录**。请固定从项目根启动：

```bash
cd /path/to/music_helper
python main.py --checkdb
```

`music.db` 已在 `.gitignore` 中，不会误提交。

### `-check` 返回非 0

数据库与磁盘不一致：有文件被手工删/移，或库是在别的目录建的。重新 `--init` 重建即可。

---

## 4. 标签补不上

按顺序排查：

| 检查 | 命令 / 现象 |
|---|---|
| 有没有 `fpcalc` | `fpcalc -version`；没有则声纹匹配不可用 |
| 网络是否通 | `python -c "import urllib.request;print(urllib.request.urlopen('https://api.acoustid.org/v2/lookup').status)"` |
| 分数是否够 | 加 `--debug` 看 `MusicBrainz(分数)`，低于 `FINGERPRINT_THRESHOLD`(50) 会被丢弃 |
| 是否已有标签 | **已有标签永不覆盖**，只填空缺；要刷新先手动清空对应字段 |
| 平台客户端是否可用 | 日志出现 `在线查询失败`；只支持 QQ 音乐与网易云 |
| `music_tagger` 是否可导入 | `python -c "import music_tagger"`，失败则是依赖缺失 |

### 封面没下载

- 超过 `MAX_COVER_SIZE`（5 MB）直接放弃；
- 文件已有内嵌封面时不会重复下载；
- 未安装 `requests` 时不下载，日志无提示——这是设计上的静默降级。

### 歌词没写入

只在「在线结果带歌词」且「本地没有同名 `.lrc`」时写入；已有歌词不覆盖。

---

## 5. 文件被移动了，怎么恢复

### 先定位

```bash
# 最近 20 条操作记录
tail -n 20 log/journal.jsonl
```

每行是一条 JSON：

```json
{"time":"2026-10-30 17:50:13","plan":"主目录检查-修复","action":"move",
 "src":"D:\\music\\a.flac","dst":"G:\\Tmp\\review\\重复文件\\a.flac",
 "reason":"重复于 b.flac","ok":true,"error":""}
```

### 恢复方式

1. **回收站**：`log/_trash/` 里保留原文件名，直接搬回；
2. **待处理目录**：`review/<问题类型>/`，按 `journal.jsonl` 的 `src` 原路搬回；
3. **重名让位**：目标冲突时会生成 `xxx_1.flac`，找出原始文件按记录改回。

目前没有自动 `--rollback`，只能按记录人工还原。这也是为什么每个动作都必须写 `reason`。

### 怎么避免再次误搬

```bash
python main.py --check --dry-run     # 先看计划
python main.py --check --fix --no-move   # 只改名，不移动文件
```

---

## 6. 检查结果不符合预期

### 「这个文件明明是重复的，为什么没识别出来」

判定要求**时长相近（≤3 秒）**。以下情况不会判重：

- 两个文件时长差超过 `DURATION_TOLERANCE`；
- 时长读取失败（会标注「时长未知」，需人工确认）；
- 歌手/歌名标签不同，且文件名也不同（策略 A、B 都不命中）。

### 「缺封面也报了，但我不想它被移走」

不会移走。缺封面/专辑/年份只进报告；只有**歌曲名/歌手缺失**或**文件名与标签矛盾**
才会移入待处理目录。

### 「文件名被改坏了」

`canonicalize` 仅在「恰好一个 `-` 且不含 ` - `」时改写，`AC-DC-Back.flac`
（两个连字符）不会被改。如果仍被改，用 `journal.jsonl` 的 `rename` 记录改回。

### 报告里中文乱码

- Markdown/CSV 都是 UTF-8（CSV 带 BOM，Excel 可直接打开）；
- Windows 控制台若显示乱码，执行 `chcp 65001` 或改用 Windows Terminal。

---

## 7. 测试与开发

### `pytest` 报模块找不到

从项目根目录运行，或确保 `test/` 里的 `sys.path.insert` 生效：

```bash
python -m pytest -q
```

### 想在不碰真实库的情况下验证

```bash
# 造一个临时库
mkdir -p /tmp/lib /tmp/temp
cp 1.flac "/tmp/lib/Tester-TestSong.flac"

MUSIC_HELPER_MAIN_DIR=/tmp/lib MUSIC_HELPER_TEMP_DIR=/tmp/temp \
  python main.py --check --dry-run
```

Windows 下用绝对路径，例如 `C:/mh_test/lib`（Git Bash 的 `/tmp` 与 Python 看到的不是同一路径）。

### 网络相关脚本为什么没被 pytest 收集

它们叫 `test/manual_*.py`，需要真实网络与密钥，手动运行：

```bash
python test/manual_musicbrainz_connection.py
```

---

## 8. 收集信息以便反馈

```bash
python main.py --version
python -c "import sys, platform; print(sys.version, platform.platform())"
tail -n 50 log/Music-*.log          # 取最新一个
tail -n 20 log/journal.jsonl
python scripts/check_docs.py        # 若与文档相关
```
