# 出境代理：git pull / push 连不上 GitHub 时用

一句话：**用已采集的免费节点临时起一个本地代理，把 git 的流量指过去**。
工具是单文件 `scripts/git_uplink.py`，只用标准库，不引入任何新依赖。

## 1. 什么时候需要它

| 现象 | 说明 |
|---|---|
| `git push` 报 `502`、`Connection reset`、`Recv failure` | github.com:443 被重置，但 api.github.com 可能仍通 |
| `git ls-remote origin` 卡住后超时 | 同上 |
| 网页能开 GitHub，命令行不行 | 浏览器走了系统代理，git 没走 |

代理没起来时脚本会退回直连，直连也不通就如实报错，不会假装成功。

## 2. 工作方式

```
节点池 clash 配置（free-nodes 采集产物）
        │  取前 N 个节点，并发 TCP 预筛
        ▼
逐个起 mihomo 单节点代理（mode: global，本地 127.0.0.1:26xxx）
        │  探测 https://github.com/ 拿到 2xx/3xx 才算通
        ▼
git -c http.proxy=... -c https.proxy=...  <命令>
```

- **单节点全局模式**：一个配置里只放一个节点，失败就换下一个，不必维护分组与规则。
- **探测地址是 `https://github.com/`**：这才是 `git push` 的真实目标；`api.github.com` 通不代表能推。
- **git 额外带 `-c http.proxy`**：环境里若残留失效的代理变量，命令行参数优先，不会被顶掉。

## 3. 前置条件

| 依赖 | 默认位置 | 覆盖方式 |
|---|---|---|
| mihomo 内核 | `~/.workbuddy/data/free-nodes-tools/bin/mihomo/mihomo.exe` | `--exe` 或环境变量 `MIHOMO_EXE` |
| 节点源（clash 配置） | `~/.workbuddy/data/git-uplink/clash.yaml` → free-nodes 的 `nodes/pool/pool_clash.yaml` → `available_clash.yaml` | `--config` 或环境变量 `GIT_UPLINK_CONFIG` |

节点源可以直接放 free-nodes 空间采集出来的 `pool_clash.yaml`（JSON 也可，mihomo 与脚本都认）。
项目名与 Git 无关，纯粹是"顺带借一个能出境的通道"。

## 4. 两种用法

### 4.1 一次性（推荐，任何终端都可靠）

脚本自己起代理、跑命令、跑完收掉，不留后台进程：

```bash
python scripts/git_uplink.py push origin master          # 等于 git push origin master（走代理）
python scripts/git_uplink.py pull                        # 等于 git pull（走代理）
python scripts/git_uplink.py run -- git ls-remote origin # 任意命令
python scripts/git_uplink.py run --keep -- git fetch     # 跑完保留通道，方便连续操作
```

失败时通道默认保留（打印提示），改完立刻重试不用重新逐个试节点；用完 `stop` 收尾。

### 4.2 常驻（交互式终端）

自己要敲一串 git 命令时，起一次、用到底：

```bash
python scripts/git_uplink.py start          # 建立通道，stdout 打印 http://127.0.0.1:26000
eval "$(python scripts/git_uplink.py env)"  # 当前 shell 的 git / curl 都走代理
# ... 随便 push / pull ...
python scripts/git_uplink.py status         # 进程活着？探测还通？
python scripts/git_uplink.py stop           # 必须收尾，避免端口与内核残留
```

PowerShell：`python scripts/git_uplink.py env --shell powershell | Invoke-Expression`；
cmd：`for /f "delims=" %i in ('python scripts/git_uplink.py env --shell cmd') do @%i`。

> 若 `start` 报「内核进程启动后立即退出」，说明当前环境的作业管理会回收后台进程
> （部分 IDE / 沙箱终端如此），改用 4.1 的一次性方式即可，功能完全等价。

## 5. 参数

| 参数 | 作用 |
|---|---|
| `--config PATH` | 指定节点源（clash/mihomo 配置） |
| `--exe PATH` | 指定 mihomo 内核 |
| `--probe URL` | 探测地址，默认 `https://github.com/` |
| `--max-tries N` | 最多试几个节点，默认 12 |
| `--pool-scan N` | 参与 TCP 预筛的节点数，默认 80 |
| `--port N` | `start` 的本地端口，默认自动选（26000 起） |
| `--shell {bash,powershell,cmd}` | `env` 输出的变量格式 |
| `--no-proxy` | 不起代理，直接执行（等同于普通 git） |
| `--no-direct` | 代理起不来时**不**允许直连兜底（默认允许） |
| `--keep` | 命令结束后保留通道 |

退出码：`0` 成功；`1` 通道建立失败（且未允许直连）；其余透传被调用命令的退出码。

## 6. 与 free-nodes 空间 `uplink.py` 的关系

| | 本文件 `scripts/git_uplink.py` | free-nodes `src/uplink.py` |
|---|---|---|
| 目标 | 只服务 git 出境 | 采集、测试、发布全链路共用 |
| 依赖 | 仅标准库，约 630 行 | `collect_nodes`/`test_nodes`/`layout`/`pool`，合计约 7000 行 |
| 内核 | 只用 mihomo | v2ray / xray / mihomo / sing-box 轮换 |
| 节点格式 | 直接读 clash 配置（mihomo 原生） | 需要 URI → 四内核配置的转换器 |
| 候选来源 | 单一配置文件 | 节点池 + 可用清单 + 原始 URI 三级 |
| 跨进程复用 | 有（`.workbuddy/runtime/git_uplink.json`） | 有（`runtime/uplink_session.json`） |

结论：**本仓库不重复实现四内核与协议转换**，只在需要时借用那些产物（节点池文件 + 内核二进制），
保持 `scripts/` 下每个文件职责单一、可独立运行。

## 7. 排错

| 报错 | 处理 |
|---|---|
| `找不到节点配置（clash 格式）` | 用 `--config` 指到 free-nodes 的 `nodes/pool/pool_clash.yaml`，或把文件放到默认路径 |
| `找不到 mihomo 内核` | `--exe` 指定，或把 mihomo 放进默认目录 |
| `N 个候选全部失败` | 节点池过期。去 free-nodes 空间重跑一次采集/测试，再回来试 |
| `TCP 预筛 80 → 0 个可连` | 节点服务器整体不可达（换了网络环境），同上 |
| 通道通了但 `git push` 仍失败 | 检查远端地址与凭据：`git ls-remote origin`、`git config --get remote.origin.url`；凭据问题代理帮不上 |

## 8. 安全提醒

- 免费节点由第三方运营，**不要用它传输私有仓库的凭据**：HTTPS 推送时 token 会经过节点。
  SSH 推送同理，明文协议内容对出口节点可见。
- 私有仓库建议只在必要时开代理推送，推完 `stop`。
- 本工具不做任何持久化改动：不改 `git config`，不写系统代理，只对子进程生效。
