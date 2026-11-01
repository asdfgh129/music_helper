# 端到端流程

> 本文负责：文件从下载目录到最终库的完整路径、状态迁移、失败处理、声纹库生命周期。
> 本文不负责：单条判定规则的算法（见 [rules.md](rules.md)）、参数表（见 [usage.md](usage.md)）、
> 路径默认值（见 [configuration.md](configuration.md)）。

## 1. 目录角色

```
下载目录（平台管理）                         流水线工作区                       结果目录
G:\Neteasymusic\VipSOngsDownload ┐
G:\Neteasymusic\（普通文件）      ├─► G:\Temp ──┬─► 完整文件留在 G:\Temp（按年代/年份整理）
G:\QQMusic\VipSOngsDownload ─────┤             ├─► G:\Unready  （待补全）
G:\QQMusic\（普通文件）           ┘             └─► G:\Tmp      （重复文件）
                                                     │
                                                     └─► D:\music（--manual-archive）
```

运行目录的默认值与覆盖方式见 [configuration.md](configuration.md#2-目录语义)。

## 2. 主流水线（默认 / `--archive`）

### 2.1 选择月份

- 不传 `--month` 时使用当前月份；
- 传 `--month YYYYMM` 时按**文件最后修改时间**过滤，只影响「解密」和「普通文件拷贝」；
- 标签更新、检查、分流、归档会扫描工作区的全部文件，不受月份限制。

### 2.2 解密 VIP 文件

1. 在 `NETEASE_VIP_DIR` / `QQ_VIP_DIR` 顶层按扩展名找加密文件（不递归）；
2. 把本次要处理的文件移入 `NETEASE_STAGING_DIR` / `QQ_STAGING_DIR`（都在 `<WORKSPACE_DIR>\_decrypt` 下）；
3. 网易云调用 `um -i <暂存目录> -o <WORKSPACE_DIR>`（三平台同一套参数）；
4. QQ 按平台选通道：Windows 优先 Frida 注入正在运行的客户端；macOS / Linux，以及 Windows 上
   没装 frida 或客户端没开时，用 `um` **逐个文件**离线解密（`.mflac → .flac`、`.mgg → .ogg`）。
   新版 qmc 需要 `qmc_mmkv` + `qmc_mmkv_key`，见 [configuration.md](configuration.md#31-qq-音乐解密凭据qmc_mmkv--qmc_mmkv_key)；
5. 用**运行前后的文件快照差集**判断是否真的产出，不只看外部程序返回码；
6. 加密原文件按 `encrypted_source_mode` 归还 / 回收 / 保留；
7. 失败时把本次移入的加密文件原样还回 VIP 目录。

为什么 QQ 逐个文件调：`um` 处理整个目录时，只要有一个文件解不开就 `FATAL` 退出，后面的
文件全都不处理。逐个调能把坏文件隔离出去，其他文件照常产出，日志也能精确到文件。

### 2.3 拷贝普通文件

扫描两个下载根目录下的可播放音频，跳过 `VipSOngsDownload` 子目录，复制到 `WORKSPACE_DIR`。
目标重名时自动加 `_1`、`_2` 后缀，同名 `.lrc` 一起复制。

### 2.4 声纹去重

调用：

```text
soundalike -db <DB_PATH> -fpcalc-length <FPCALC_LENGTH> -file-regexp <RE> \
           -move-interactive <DUPLICATE_DIR> [-dry-run] -temp <WORKSPACE_DIR> <LIBRARY_DIR>
```

- `-db` 固定指向 `DB_PATH`，程序的工作目录也设到库文件所在目录，避免「库建在启动目录」；
- `-fpcalc-length` 固定取 `config.FPCALC_LENGTH`，与补标签用的指纹长度保持一致；
- `-file-regexp` 由 `config.AUDIO_EXTENSIONS` 并入 soundalike 内置格式后生成，保证
  `.dsf/.dff` 这类格式也参与比对（内置正则不含 dsf）；
- `-temp` 让工作区参与比对，但不写入声纹库；
- `LIBRARY_DIR` 作为音乐目录参与建库与比对；
- `DB_PATH` 不存在时，soundalike 会扫描 `LIBRARY_DIR` 自动建库，这就是首次初始化；
- 调用时会把 `tools/` 临时前置到 `PATH`，让外部程序找到随仓库分发的 `fpcalc`。

**谁保留谁移走以音质为准**，移走音质差的那份不需要人工确认：

1. 格式层级：`.dsf/.dff`(DSD) > `.wav/.aif`(PCM) > `.flac/.ape`(无损压缩) >
   `.m4a`(AAC/ALAC) > `.mp3/.ogg/.opus` > `.wma`；
2. 同层级比码率（`size*8/duration` 估算），差 ≥2% 才算更好；
3. 比最好那份差的，直接移入 `DUPLICATE_DIR`，不问；
4. 只有音质**完全一样**的几个才列序号问「保留哪个」，回车 = 全部保留；
5. 认不出的扩展名不参与自动判断，整组退回人工。

`-temp` 依赖「相对第一个音乐目录」推算路径，**跨盘会直接失败**。检测到
`WORKSPACE_DIR` 与 `LIBRARY_DIR` 不同盘时，本步骤退化为只比对音乐库，并在日志里告警。

`--dry-run` 会真跑一次试运行：复用库里已有指纹、打印完整计划（含自动移走的那部分），
但不动文件、不写库；`--soundalike-report` 是它的别名。

算法细节（倒排筛选、位相似度、连通分量、阈值）与已知缺陷见
[fingerprint.md](fingerprint.md#8-声纹查重soundalike)。

### 2.5 补标签

对工作区内的文件依次尝试：

1. 声纹 → AcoustID → MusicBrainz（`fpcalc` 与网络可用时）；
2. 文件名解析出的「歌手 + 歌名」→ QQ 音乐 / 网易云；
3. 已有标签优先，只填补空缺；顺带写封面与同名 `.lrc`。

任何可选依赖缺失只降级对应能力，不中断流水线。

### 2.6 检查与修复

在一个只读的检查阶段产出 `Finding`：

- 文件名是否符合「歌手 - 歌名」；
- 标签是否完整；
- 文件名与标签是否矛盾；
- 是否存在重复组；
- 是否缺歌词、是否有孤立歌词。

`--fix` 只在检查阶段开启修复计划：

- 重复文件：`--trash-dup` 进回收站，否则移入 `DUPLICATE_DIR`；
- 「时长未知」的重复组只报告，不移动——读不出时长多半是文件损坏，交人工；
- **只有**歌曲名/歌手缺失、文件名与标签矛盾这类 `severe` 问题才移入 `INCOMPLETE_DIR`；
- 缺封面、缺专辑、缺年份只报告，不移动文件；
- 单个 `-` 的文件名做分隔符规范化；
- 文件名缺「歌手 - 歌名」结构、但标签齐全可信时，按标签补全文件名。

主流水线默认执行这些修复（`--no-move` 可关闭移动，`--dry-run` 只出计划）。
规则细节见 [rules.md](rules.md#7-修复范围)。

### 2.7 待补全分流

扫描 `WORKSPACE_DIR` **顶层**（不递归）的音频，逐首判断：

| 条件 | 去向 |
|---|---|
| 有歌曲名、歌手、专辑、年份（年份可解析），且文件名与标签不矛盾 | 留在 `WORKSPACE_DIR` |
| 缺少任一核心字段、年份解析不出，或文件名与标签矛盾 | `INCOMPLETE_DIR` |

封面与歌词不参与判断。分离后 `WORKSPACE_DIR` 顶层只剩完整文件与非音频文件。

### 2.8 工作区内按年代/年份整理

完整文件按标签年份移入 `<WORKSPACE_DIR>/<年代>/<年份>/`，例如 `1980-1989/1985/`。
缺歌曲名/歌手/年份的文件进入 `<WORKSPACE_DIR>/unknown/`（正常分流后不应出现）。

## 3. 人工确认后入库（`--manual-archive`）

1. 扫描 `WORKSPACE_DIR`（含已整理的子目录）；
2. 再补一次标签；
3. 只对完整文件按标签把文件名规范化为 `歌手 - 歌名.ext`；
4. 完整文件按年代/年份移入 `LIBRARY_DIR`，未达标文件移入 `INCOMPLETE_DIR`；
5. 统计 `INCOMPLETE_DIR` 剩余数量并在日志中提醒。

这是一步**显式确认**：默认流水线不会把文件并入最终库。

## 4. 最终库检查（`--check`）

1. 目录校验：`LIBRARY_DIR` 不存在直接报错退出（退出码 1），不会产出一份「零问题」的假报告；
2. `soundalike -check -db <DB_PATH> <LIBRARY_DIR>` 校验声纹库与文件系统一致性（`--dry-run` 跳过）；
3. 对 `LIBRARY_DIR` 执行与 2.6 相同的检查；
4. `--fix` 时按同一套修复规则移动/改名/回收；
5. 生成 Markdown 报告与 CSV 待处理清单。

## 5. 失败处理与可回滚性

| 场景 | 行为 |
|---|---|
| 外部程序缺失 | 该步骤返回失败结果，其余步骤继续；`--init` / `--checkdb` 以非 0 退出 |
| 外部程序超时 | 终止该次调用并记录日志，不杀主进程 |
| 解密未产出 | 本次移入的加密文件原样还回 VIP 目录 |
| 单条移动/改名失败 | 记入 `log/journal.jsonl` 的 `error`，不中断整批 |
| 用户 Ctrl-C | 退出码 130，已完成的动作仍可在 journal 中追溯 |

所有移动、改名、回收都经过 `core.ops.Plan`，`--dry-run` 可以完整预览。
回滚步骤见 [troubleshooting.md](troubleshooting.md#4-回滚与恢复)。

## 6. 声纹库生命周期

| 操作 | 命令 | 行为 |
|---|---|---|
| 首次建库 | 任意去重步骤，或 `python main.py --init` | 扫描 `LIBRARY_DIR` 建库 |
| 日常增量 | `python main.py` | 更新 `LIBRARY_DIR`，工作区只比对不写库 |
| 一致性检查 | `python main.py --checkdb` | 校验库记录与实际文件 |
| 换库位置 | 改 `DB_PATH` / `MUSIC_HELPER_DB` | 新位置会被当作新库重新建立 |

`DB_PATH` 与 `tools/soundalike.exe` 是两回事：前者是数据，后者是程序。
