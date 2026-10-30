# 架构说明

本文说明代码怎么分层、为什么这样分层、以及改动时容易踩的坑。目标是：任何一个改动，
读完之后都知道该写在哪一层、会影响谁。

## 1. 分层

```
┌──────────────────────────────────────────────────────┐
│ main.py        编排：解析参数 → 串流程 → 汇总报告      │
└───────────────┬──────────────────────────┬───────────┘
                │                          │
┌───────────────▼───────────┐  ┌───────────▼───────────┐
│ core/     纯逻辑，可单测   │  │ services/  有副作用    │
│ model  scan  naming       │  │ decrypt               │
│ tags   lyrics dedupe      │  │ soundalike            │
│ organize check report ops │  │ tagger                │
└───────────────┬───────────┘  └───────────┬───────────┘
                │                          │ 外部世界
┌───────────────▼──────────────────────────▼───────────┐
│ config.py 纯数据（不导入业务模块）                     │
│ utils.py  日志 + 兼容旧接口的小函数                    │
└──────────────────────────────────────────────────────┘
```

### 各层职责

| 层 | 可以做 | 不可以做 | 判据 |
|---|---|---|---|
| `core/` | 读元信息、计算、生成 `Plan` | 网络、外部 exe、`os.remove`、直接 `shutil.move` | 「拿到同样的输入是否总得到同样输出」 |
| `services/` | HTTP、调用 exe、写标签/封面/歌词 | 决定目录结构、决定哪些文件该删 | 「离开这台机器还能不能跑」 |
| `main.py` | 解析参数、决定顺序、汇总 | 实现任何判定规则 | 「换一个入口，这些逻辑还要不要再写一遍」 |
| `config.py` | 字符串/数字/路径常量 | `import core` / `import services` | 「导入它会不会引发循环依赖」 |

## 2. 模块清单

### `core/`

| 模块 | 职责 | 关键接口 |
|---|---|---|
| `model.py` | 统一的 `Track` 抽象 | `Track(dirpath, ext, stem, key, year_int, has_lrc, tag())` |
| `scan.py` | 一次遍历建索引 | `scan(paths, month, with_tags, recursive, extensions)` |
| `naming.py` | 文件名规则（唯一实现） | `parse_filename`、`canonicalize`、`format_filename`、`split_artist` |
| `tags.py` | 标签读写 + 封面 + 时长（唯一实现） | `read_tags`、`write_tags`、`write_cover`、`has_cover`、`duration` |
| `lyrics.py` | 歌词缺失 / 孤立 | `missing_lrc`、`orphan_lrc` |
| `dedupe.py` | 重复判定 | `find_by_tag`、`find_by_filename`、`find_duplicates` |
| `organize.py` | 年份归档 | `plan_organize(tracks, base_dir, plan)` |
| `check.py` | 检查与修复计划 | `check_library`、`plan_fixes`、`report_into` |
| `report.py` | 报告渲染 | `Report.add/add_summary/add_review/save` |
| `ops.py` | 破坏性动作唯一出口 | `Plan.add_move/add_rename/add_trash/execute`、`copy_items` |
| `scoring.py` | 在线标签相似度打分 | `tag_score` |

### `services/`

| 模块 | 职责 | 依赖 |
|---|---|---|
| `decrypt.py` | 网易云 / QQ 解密 | `um.exe`、`decrypto`（Frida） |
| `soundalike.py` | 声纹去重、库一致性 | `fingerprint/soundalike.exe` |
| `tagger.py` | 声纹 + 在线标签、封面、歌词 | `fingerprint/`、`music_tagger/platforms/`、`requests` |

`music_tagger/` 只保留 `platforms/{qqmusic,netease}.py` 两个客户端，**不含**任何标签匹配或
写盘逻辑——那部分唯一实现在 `core/scoring.py` 与 `services/tagger.py`。历史上有过一套
`MusicTagger` / `SmartTagClient` 并行实现，已随仓库清理删除，避免同一件事两处可改。

外部依赖一律**延迟导入 + 失败降级**：缺 `requests` 只是不下载封面，缺 `fpcalc` 只是跳过声纹，
缺 `mutagen` 只是读不到标签——主程序永远能启动。

### 附属包与脚本（不属于上面两层）

| 目录 | 是什么 | 为什么不在 `core`/`services` |
|---|---|---|
| `decrypto/` | QQ 音乐解密：Frida hook 脚本 + 来源检索（`qq.py`、`source_finder.py`、`um.exe`） | 半独立的上游代码，自带 CLI；由 `services/decrypt.py` 调用，不参与流水线编排 |
| `fingerprint/` | AcoustID / MusicBrainz 指纹匹配（`musicbrainz_matcher.py` + `soundalike.exe`） | 同上，自带一套 HTTP 客户端与解析，被 `services/tagger.py`、`soundalike.py` 借用 |
| `music_tagger/` | QQ 音乐 / 网易云平台客户端（`platforms/`） | 上游项目名的沿用；包内只剩客户端，标签择优逻辑在 `core/scoring.py` |
| `scripts/` | 维护脚本：`check_docs.py`（文档校验）、`git_uplink.py`（出境代理） | 开发者工具，不参与运行时 |
| `test/` | pytest 用例 + `manual/` 手工脚本 + `fixtures/` 样本 | 不随程序分发 |

命名约定：**自有代码目录一律小写**（`core`/`services`/`decrypto`/`fingerprint`/`music_tagger`/
`scripts`/`test`/`docs`），`decrypto` 与 `fingerprint` 在 0.5.0 之前是 `Decrypto`/`Fingerprint`，
与同层目录大小写不一致、在大小写敏感的文件系统上易出现「同一目录两个名字」的问题。
外部程序文件名保持上游原样（`um.exe`、`soundalike.exe`），改它会连带上游脚本失效。

## 3. 数据流

```
磁盘
 │  core.scan.scan()
 ▼
[Track, ...]  ──────────────► core.check.check_library()
 │                                   │
 │                                   ├─► CheckResult.findings  ─► report_into() ─► Report ─► .md / .csv
 │                                   └─► CheckResult.groups    ─┐
 │                                                             │
 ├─► core.organize.plan_organize() ─┐                          │
 ├─► services.tagger.update()       │                          ▼
 └─► services.decrypt               └────────────► core.ops.Plan ─► execute() ─► 磁盘 + journal.jsonl
                                                        ▲
                                          --dry-run ────┘（只 describe，不执行）
```

关键点：**检查阶段永不改文件**，它只产出 `Finding`；所有改动集中到 `Plan.execute()`。
这一条让「报告」和「执行」可以分别验证，也让 `--dry-run` 天然成立。

## 4. 操作计划 `Plan`

```python
plan = Plan('主目录检查-修复', dry_run=False,
            journal_path='log/journal.jsonl', trash_dir='log/_trash')
plan.add_move(src, dst, reason)
plan.add_rename(src, new_name, reason)
plan.add_trash(src, reason)
result = plan.execute()      # PlanResult(done, skipped, failed)
```

约定：

- `src == dst` 的操作会被忽略（规范化后比较）；
- 目标已存在时自动加 `_1/_2` 后缀，**永不覆盖**；
- `trash` 不是删除，是把文件移到 `TRASH_DIR`，保留文件名；
- 单条失败不中断整批，失败原因进 `journal.jsonl` 的 `error` 字段；
- `dry_run=True` 时全部进 `skipped`，不创建任何目录。

## 5. 设计决策与由来

### 为什么 `config.py` 不许导入业务模块

重构前 `config.py` 是「导入中转站」，把 `MusicTagger`、`FingerprintMatcher`、`QQMusicApi`
从 config 导出。后果：

1. 任一可选依赖缺失，`from config import X` 直接 `ImportError`，主程序起不来；
2. `config → fingerprint → config` 循环导入，`fingerprint/musicbrainz_matcher.py` 拿到的
   是半初始化的 config，`FPCALC_LENGTH` 永远回退默认值 120，配置改了不生效。

现在 config 只有数据和 `_path()` 帮助函数。

### 为什么删除都要走回收站

旧实现在重名时直接 `os.remove(filepath)`，连 `.lrc` 一起删，仅凭文件名判断「重复」。
一次误判就是不可逆的数据丢失。现在 `core/` 层没有任何 `os.remove`，全部换成
`shutil.move` 到 `log/_trash/`。

### 为什么一个功能只留一处实现

重构前同一功能最多有四份实现，规则互相矛盾：

| 功能 | 旧实现 | 矛盾点 |
|---|---|---|
| 归档 | `archive.py`、`file_operations.organize_by_year`、`lrc.py` | 支持的格式不同、重名处理不同 |
| 歌词 | `lrc.py`、`file_operations`、`archive.py` | 扩展名集合三套 |
| 元数据 | `metadata.py`、`archive.generate_music_metadata` | 字段映射不同 |
| 重复 | `duplicate.py`（按文件名后缀）、`file_operations`（按 artist+title） | **两套都不比较时长**，判定结果互相打脸 |

现在收敛到 `core/{organize,lyrics,tags,dedupe}.py`，旧文件已删除，git 历史可追溯。

### 为什么扫描只遍历一次

旧 `check_filename_consistency` 对每个目录 `os.walk` 四遍（收集→改名→孤立 lrc→一致性）。
`core.scan.scan()` 一次遍历产出 `Track` 列表，后续全部基于内存数据，大库上省掉 3/4 的
磁盘遍历。

## 6. 扩展指南

### 新增一项检查

1. 在 `core/check.py` 加一个 `KIND_XXX` 常量；
2. 在 `check_library()` 里产出 `Finding`（`severe=True` 表示需要人工处理）；
3. 在 `report_into()` 的渲染顺序里加进去；
4. 如需修复，在 `plan_fixes()` 加对应分支，注意**先重复、后移动、最后改名**的顺序；
5. 补 `test/` 用例，更新 [features.md](features.md)。

### 新增一个外部工具

1. 在 `services/` 下新建模块，参考 `soundalike.py`：`subprocess.run` 必带 `timeout` 与
   `check=False`，自己判断 `returncode`；
2. 路径放 `config.py`，支持环境变量覆盖；
3. 失败返回结构化结果，不要抛异常到 `main`。

### 新增 CLI 开关

1. `main.py: build_parser()` 加参数；
2. 在 `main()` 的**单一动作模式**区按优先级插入分支（顺序敏感，见 [usage.md](usage.md)）；
3. 更新 `EPILOG` 示例与 [usage.md](usage.md)。

## 7. 已知坑

| 现象 | 原因 | 处理 |
|---|---|---|
| 声纹库「找不到记录」 | `soundalike.exe` 的 `music.db` 生成在**当前工作目录** | 固定从项目根启动，或把 `music.db` 放到固定位置 |
| 解密「成功但没产出」 | 外部程序返回 0 却没写文件 | 用前后快照差集判定产出，不看返回码 |
| 归档把文件搬进自己的子目录 | 边 `os.walk` 边在树内建年份目录 | 先扫描成列表再建计划，避免遍历中改结构 |
| 标签改了不生效 | 读到的 `FPCALC_LENGTH` 是循环导入的回退值 | 已修复；新增配置项时同样不要反向依赖 |
| `--fix` 把半库搬空 | 曾把「缺封面/缺专辑」也判为需移动 | 只有 `severe`（歌曲名/歌手缺失、标签矛盾）才移动 |
