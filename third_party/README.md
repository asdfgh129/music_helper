# third_party —— 外部程序的源码与安装包

`tools/` 里放的是**编译好的产物**，本目录放它们的**源码**，目的是让仓库自带可复现的
构建链：换一台机器、上游仓库哪天消失（`unlock-music/cli` 已经因为 DMCA 被整站下架），
仍然能从这里的源码重新编出可用的 `tools/`。

许可证跟着各自的 `LICENSE` 文件走，本仓库不改变它们的授权。

## 1. 清单

| 目录 | 程序 | 版本 | 许可证 | 对应产物 |
|---|---|---|---|---|
| [um-cli/](um-cli/) | unlock-music CLI（`um`） | v0.2.12 | MIT | `tools/um.exe`、`tools/um-darwin-{arm64,amd64}` |
| [soundalike/](soundalike/) | soundalike（声纹查重） | 0.1.5 | BSD-3-Clause | `tools/soundalike.exe`、`tools/soundalike-darwin-{arm64,amd64}` |
| [chromaprint/](chromaprint/) | Chromaprint（`fpcalc` 的上游） | 1.6.2 | MIT（链接的 FFmpeg 为 LGPL） | `tools/fpcalc`、`tools/fpcalc.exe` |
| [qqmusic/](qqmusic/) | QQ 音乐旧版客户端 | 19.51 (Win) / 8.8.0 (macOS) | 腾讯专有；安装包在 `tools/`，说明与 SHA256 在本目录 | 无（人工安装） |

### 关于 soundalike 的 0.1.5

`0.1.5` **不是一个 tag，也不是某个 commit**——上游 [codeberg.org/derat/soundalike][upstream]
最新 tag 只到 `v0.1.3`，本项目用的 0.1.4 / 0.1.5 是在本地 fork 上继续改的，版本号通过
`-ldflags "-X main.buildVersion=..."` 在编译时注入（见 `main.go:20`）。

所以「0.1.5 的源码」就是本目录这一份快照，它包含上游 v0.1.3 之后的全部本地改动：

- `dbdriver_cgo.go` / `dbdriver_nocgo.go`：按 `CGO_ENABLED` 在 `mattn/go-sqlite3` 与
  `modernc.org/sqlite` 之间切换，让没有 C 工具链的机器也能编出可用的二进制（0.1.4）
- `move.go` 的音质分层取舍（`formatTier` / `betterThan`）、`-dry-run`、跨盘删源修复（0.1.5）
- `scan.go` 的 `addAndCompare` 抽取、`db.go` 的参数化插入（0.1.5）

快照时已剔除 `.git/`、`testdata/`、`music.db`、`*.log` 和编译产物。

[upstream]: https://codeberg.org/derat/soundalike

## 2. 重建 `tools/` 里的产物

需要 Go 1.21 以上。`um` 与 macOS 版 soundalike 都是纯 Go 构建（`CGO_ENABLED=0`），
不依赖 C 工具链。

```bash
# ---- um：三个平台 ----
cd third_party/um-cli
export GOPROXY=https://goproxy.cn,direct    # 见下面的「为什么必须指定代理」
GOPROXY=$GOPROXY CGO_ENABLED=0 GOOS=windows GOARCH=amd64 go build -trimpath \
    -ldflags "-s -w" -o ../../tools/um.exe ./cmd/um
GOPROXY=$GOPROXY CGO_ENABLED=0 GOOS=darwin GOARCH=arm64 go build -trimpath \
    -ldflags "-s -w" -o ../../tools/um-darwin-arm64 ./cmd/um
GOPROXY=$GOPROXY CGO_ENABLED=0 GOOS=darwin GOARCH=amd64 go build -trimpath \
    -ldflags "-s -w" -o ../../tools/um-darwin-amd64 ./cmd/um

# ---- soundalike：macOS 两架构（脚本已写死 0.1.5）----
cd third_party/soundalike
./build_macos.sh ../../tools

# ---- soundalike：Windows ----
# 原版 build_win.sh 走 CGO + mingw-w64；本机没有 mingw 时用纯 Go 版，产物等价：
CGO_ENABLED=0 GOOS=windows GOARCH=amd64 go build -trimpath \
    -ldflags "-s -w -X main.buildVersion=0.1.5" -o ../../tools/soundalike.exe .
```

**为什么必须指定 GOPROXY**：`unlock-music/cli` 的 GitHub 仓库 2022-11 被 DMCA 下架，
现在连 release 资产都返回 `451`，`proxy.golang.org` 也查不到这个模块；只有
`goproxy.cn` 等国内代理能取到。

**fpcalc 不从本地源码构建**：Chromaprint 需要 CMake + FFmpeg 开发库，链路长且容易踩版本坑。
仓库里的 `tools/fpcalc` 与 `tools/fpcalc.exe` 直接取自上游 release 的预编译包：

- Windows：<https://github.com/acoustid/chromaprint/releases/download/v1.6.2/chromaprint-fpcalc-1.6.2-windows-x86_64.zip>
- macOS：<https://github.com/acoustid/chromaprint/releases/download/v1.6.2/chromaprint-fpcalc-1.6.2-macos-universal.tar.gz>

`chromaprint/` 下的源码是给「确实需要自己编」的场景留的，不是流水线的依赖。

## 3. QQ 音乐旧版客户端

**为什么需要它**：Windows 客户端 19.51 及以下版本下载的 `.mflac/.mgg` 把密钥内嵌在文件里，
`um` 直接就能解；19.51 以上改成需要额外密钥，而官方从未公开提取方法。macOS 同理，
8.8.0（2023-09-03）及以下版本的 `MMKVStreamEncryptId` 未加密，可以直接读。

> 本机装的 QQ 音乐是 **21.92**，属于已加密的版本——这就是 `G:/qqtmp/张杰 - 三生三世.mflac`
> 解不开（`no any decoder can resolve the file`）的原因。要批量解密，要么降到 19.51，
> 要么走 Frida 注入（`tools/hook_qq_music.js`）。

**当前状态：安装包未入库。** 2026-11-01 实测所有已知下载源都不可用：

| 源 | 结果 |
|---|---|
| `https://dldir1v6.qq.com/music/clntupate/QQMusic_Setup_1951.exe`（官方） | `404`，腾讯已下架 |
| `https://dldir1.qq.com/music/clntupate/mac/QQMusicMac_Mgr.dmg`（官方） | `404` |
| `web.archive.org` 快照 | 本机直连与走代理均不通（`000`） |
| `t.me/um_lsr_ch`（um 官方分发频道） | 不通 |
| 第三方软件站 / 网盘转载 | 可访问，但**包无法校验真伪**，不放进仓库 |

因此本目录只保留上表的地址清单，安装包需要人工获取：**优先用仍能访问官方 CDN 的网络
下载；拿不到时再去腾讯软件中心或可信归档，装完用 `QQMusic.exe` 的文件版本号确认是
19.51**（右键属性 → 详细信息）。第三方站点转载的安装包有捆绑风险，装之前建议先丢进
虚拟机或沙箱跑一次。

macOS 侧对应的是 **8.8.0（20230903）**，同样需要人工获取；安装后不要让它自动升级。
