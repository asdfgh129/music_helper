# 命令行手册

> 本文负责：全部参数、流程入口、参数优先级、退出码、使用禁忌。
> 本文不负责：流程内部细节（见 [workflow.md](workflow.md)）、判定规则（见 [rules.md](rules.md)）、
> 配置项与环境变量（见 [configuration.md](configuration.md)）。

入口只有一个：`python main.py`。

## 1. 全局参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--version` | — | 打印版本后退出 |
| `--debug` | 关 | 输出调试日志；声纹工具追加 `-log-sec=1` |
| `--month YYYYMM` | 当前月 | 只影响解密与普通文件拷贝（按文件修改时间） |
| `--dry-run` | 关 | 只生成计划：不移动/改名；声纹去重也跑试运行（打印将移动谁，不动文件、不写库） |
| `--report-dir DIR` | `log/reports/` | 报告输出目录 |
| `--limit N` | 0（不限） | 每类处理最多 N 个文件，调试用 |
| `--no-move` | 关 | 流水线/检查中不移动不一致文件 |
| `--trash-dup` | 关 | 重复文件直接进 `log/_trash/`，否则移入 `DUPLICATE_DIR` |

## 2. 三条主流程

| 命令 | 作用 | 终点 |
|---|---|---|
| `python main.py` / `python main.py --archive` | `WORKSPACE_DIR` 完整流水线 | 完整文件留在 `WORKSPACE_DIR`（按年代/年份整理）；`INCOMPLETE_DIR` 等待人工 |
| `python main.py --check` | 检查 `LIBRARY_DIR` | 报告；`--fix` 时按规则修复 |
| `python main.py --manual-archive` | 人工确认后入库 | `WORKSPACE_DIR` → `LIBRARY_DIR` |

完整步骤见 [workflow.md](workflow.md)。

### 2.1 流水线跳过开关

| 参数 | 跳过的步骤 |
|---|---|
| `--skip-vip` | 解密与普通文件拷贝 |
| `--skip-fingerprint` | 声纹去重；同时关闭标签阶段的声纹查询 |
| `--skip-tag-update` | 标签更新 |
| `--skip-check` | 检查与修复 |
| `--skip-organize` | 工作区内的年代/年份整理 |

未达标文件移入 `INCOMPLETE_DIR` 不受这些开关影响，执行完检查后总会运行。

## 3. 单一动作

| 参数 | 作用 |
|---|---|
| `--init` | 初始化/更新声纹库（不扫描工作区） |
| `--checkdb` | 校验声纹库与 `LIBRARY_DIR` 的一致性 |
| `--soundalike` | 运行声纹去重（`WORKSPACE_DIR` + `LIBRARY_DIR`）：音质差的自动移入 `DUPLICATE_DIR`，音质相同才询问 |
| `--soundalike-report` | 只列出声纹候选组：不移动文件、**不写声纹库**（等同 `--dry-run` 的声纹部分） |
| `--only-decrypt` | 只解密 |
| `--only-update-tag {master,temp}` | 只更新 `LIBRARY_DIR` 或 `WORKSPACE_DIR` 的标签 |
| `--only-check-file-name {master,temp}` | 只做文件名检查（可配 `--fix`，见下） |
| `--only-archive` | 只对 `WORKSPACE_DIR` 做年代/年份归档 |

`master` 指 `LIBRARY_DIR`，`temp` 指 `WORKSPACE_DIR`；名称沿用旧参数，避免破坏已有脚本。

`--only-check-file-name --fix` 只做分隔符级规范化（`A-B.flac` → `A - B.flac`）：
这一模式不读标签，无法按标签补全「帅哥.flac」这类缺歌手结构的文件名。
需要按标签补全请用 `python main.py --check --fix`。目标目录不存在时退出码为 1。

### QQ 解密的环境准备

`--only-decrypt` 会**先做环境准备，再搬文件**（`decrypto/qq_client.py`）：环境不就绪就直接
跳过本次解密，加密文件原地不动——不会白搬一趟进暂存区再还原。四步按顺序执行，任一步失败即中止：

1. **检测安装**：Windows 读注册表 `HKLM\SOFTWARE\WOW6432Node\Tencent\QQMusic` 的 `Install`
   值，再按 4 个常见路径兜底；macOS 查 `/Applications/QQMusic.app`。
2. **未安装则安装**：Windows 跑 `tools/QQMusic_Setup_1951.exe`（先试 `/S` 静默，失败转交互），
   macOS 挂载 8.8.0 dmg 后拷进 `/Applications`；装完立即打屏蔽更新补丁。
3. **启动**：进程不在就拉起客户端。
4. **确认登录**：用 Frida 对**临时副本**调一次 `Open` 探测，未登录就提示扫码并轮询等待，
   默认 300 秒（`tools.qq_login_timeout`）。

单独跑 `decrypto/qq.py` 时也走同一套检查，另有 4 个开关可以关掉对应步骤：

| 参数 | 作用 |
|---|---|
| `--no-ensure` | 跳过全部环境准备（回到改动前的行为） |
| `--no-install` | 没装客户端时只报错，不自动安装 |
| `--no-wait-login` | 检测到未登录立即退出，不等待扫码 |
| `--login-timeout N` | 本次等待扫码的秒数，覆盖配置里的 `tools.qq_login_timeout` |

```bash
python decrypto/qq.py -l                                  # 只看下载目录里有哪些歌
python decrypto/qq.py -i <暂存目录> -o <输出目录>           # 解密（含环境准备）
python decrypto/qq.py -i <暂存目录> -o <输出目录> --no-wait-login --login-timeout 0
```

macOS 上第 2、3、4 步照做，但 Frida 通道不可用（Mach-O 没有 `QQMusicCommon.dll` 与那套
MSVC 修饰导出名），实际解密固定走 `um` 离线；登录态无法程序化探测，只能提示你自己确认。

## 4. 参数优先级

`main()` 按以下顺序判断，命中即返回，**后面的参数不会再生效**：

```
--init
--checkdb
--soundalike
--soundalike-report
--only-decrypt
--only-update-tag
--only-check-file-name
--only-archive
--manual-archive
--check
默认流水线
```

例如同时传 `--check --manual-archive` 时只执行手动归档。

## 5. 退出码

| 退出码 | 含义 |
|---|---|
| 0 | 正常完成 |
| 1 | 参数/月份格式错误；`--check` / `--only-check-file-name` 的目标目录不存在；`--init` / `--checkdb` / `--soundalike` 的外部工具失败；未处理异常 |
| 130 | 用户 Ctrl-C |

`--check` 与默认流水线即使发现「需要人工处理」的文件也返回 0——报告里有数量，
是否失败由使用者判断；外部程序失败、或目标目录根本不存在才会反映到退出码。

## 6. 场景速查

| 我想… | 命令 |
|---|---|
| 先看计划，不动文件 | `python main.py --dry-run` |
| 处理指定月份 | `python main.py --month 202406` |
| 只解密 | `python main.py --only-decrypt` |
| 看 QQ 下载目录里有哪些歌 | `python decrypto/qq.py -l` |
| 解密时跳过客户端检查 | `python decrypto/qq.py -i <暂存> -o <输出> --no-ensure` |
| 只补标签 | `python main.py --only-update-tag temp` |
| 只检查最终库 | `python main.py --check` |
| 检查并修复最终库 | `python main.py --check --fix` |
| 只检查文件名 | `python main.py --only-check-file-name master --fix` |
| 只对工作区归档 | `python main.py --only-archive` |
| 人工确认后入库 | `python main.py --manual-archive` |
| 首次建声纹库 | `python main.py --init` |
| 校验声纹库 | `python main.py --checkdb` |
| 先看声纹重复候选，不移动 | `python main.py --soundalike-report`（或 `--dry-run`） |

## 7. 使用禁忌

1. **`--soundalike` 会自己移文件**：不同音质的重复，较差的那份会被直接移入 `DUPLICATE_DIR`，
   不再逐个确认（这是刻意的：谁留谁走以音质为准）。不确定时先 `--dry-run` 或
   `--soundalike-report` 看计划——两者都不动文件、不写库。
2. **`--fix` 只移动严重问题**：缺封面/专辑/年份不会移动文件。这是刻意设计，见
   [rules.md](rules.md#7-修复范围)。
3. **`--manual-archive` 只处理工作区**：完整文件按年份并入 `LIBRARY_DIR`，未达标文件移入 `INCOMPLETE_DIR`。
4. **目录不要互相嵌套**：`DUPLICATE_DIR`、`INCOMPLETE_DIR` 不要放进 `WORKSPACE_DIR`，否则会被
   `soundalike -temp` 重复扫描。
5. **`LIBRARY_DIR` 不要等于 `WORKSPACE_DIR` / `DUPLICATE_DIR`**：`soundalike` 会拒绝相同目录，且容易自我搬运。
6. **`--month` 不筛选标签/检查**：它只按修改时间筛选解密与拷贝；后续步骤处理工作区全部文件。

## 8. Web UI（八步向导）

除 CLI 外，本项目提供一个 Vue 3 写的八步向导（FastAPI 后端）：目录设置 → 操作类型 →
拷贝 → 解密 → 标签歌词 → 查重 → 工作区自检 → 归档。每一步都能先看「将要发生什么」再执行，
长任务有逐条进度与实时日志。**完整说明见 [web-wizard.md](web-wizard.md)**，本节只给启动方式与接口索引。

### 8.1 启动

```bash
pip install -r requirements-dev.txt      # 仅需首次：安装 fastapi / uvicorn
cd /path/to/music_helper
python -m uvicorn web.api:app --host 127.0.0.1 --port 8000
# 浏览器打开 http://127.0.0.1:8000/         八步向导
#            http://127.0.0.1:8000/legacy  旧版仪表盘（配置/报告/任务日志）
```

> `uvicorn` 通常不在 PATH，请用 `python -m uvicorn`。服务只绑定 `127.0.0.1`，不对外暴露。
> 前端不依赖 CDN、不需要 Node 构建，Vue 运行时随仓库放在 `web/static/vendor/`。

### 8.2 向导接口

| 步骤 | 接口 | 说明 |
|---|---|---|
| 全局 | `GET /api/wizard/state` | 目录设置 + 库状态 + 平台能力 + 月份列表 |
| 1 目录 | `POST /api/wizard/dirs` | 写 `config.ini [paths]` 并热重载；有任务在跑时 409 |
| 1 目录 | `GET /api/fs/list`、`POST /api/fs/mkdir` | 选目录弹窗用；只列目录，不读文件内容 |
| 2 操作 | `GET /api/library/status` | 「是否已初始化」的判据（`core.library`） |
| 2a 初始化 | `POST /api/library/init` | 建目录 + 建声纹库，幂等 |
| 2b 自检 | `POST /api/tasks`（`kind=check`） | 复用 `main.flow_check`，可选 `fix` |
| 3 拷贝 | `GET /api/copy/preview`、`POST /api/copy/run` | 下载目录普通文件 → 工作区 |
| 4 解密 | `GET /api/decrypt/preview`、`POST /api/decrypt/run` | VIP 目录**直解**到工作区 |
| 5 标签 | `GET /api/tags/preview`、`POST /api/tags/run` | 标签/封面/歌词补全；`fields` 限定写入哪些字段 |
| 5 单曲 | `GET /api/track`、`POST /api/track/save`、`POST /api/track/fetch` | 单曲详情 / 手工保存 / 在线取标签（只预览不写盘） |
| 6 查重 | `GET /api/dedupe/preview`、`POST /api/dedupe/run` | 工作区 vs 库目录；库里已有的移入重复目录或回收站 |
| 7 自检 | `GET /api/selfcheck/preview`、`POST /api/selfcheck/run` | 工作区只读自检，含文件名 ↔ 标签逐项比对 |
| 8 归档 | `GET /api/archive/preview`、`POST /api/archive/run` | 按 `<年代>/<年份>` 归档，可选入库 |
| 任务 | `GET /api/tasks`、`GET /api/tasks/{id}` | 状态 / 逐条进度 / 日志 / 结果 |

### 8.3 保留的旧接口

只读与 CLI 时代的接口都还在，脚本可继续用：`GET /api/config`、`GET /api/platform`、
`GET /api/scan`、`GET /api/reports`、`GET /api/reports/view`、`POST /api/check`、
`POST /api/plan/preview`、`POST /api/plan/execute`、`POST /api/decrypt`。

### 8.4 安全约定

- 所有破坏性动作都走 `core.ops.Plan` + `log/journal.jsonl`，Web 没有自己的删除/移动实现。
- 删除永远是「移入 `log/_trash/`」，不调用 `os.remove`。
- 任务队列单线程串行；跑任务期间不允许改目录设置（界面会禁用，接口返回 409）。
