# third_party —— 外部程序的源码

**本目录只放源码，不放任何二进制。** 编译产物、安装包、屏蔽更新补丁一律在 [`tools/`](../tools/)：
那里是运行时的第三方程序仓库，随项目一起打包，缺了就要装。

两个目录的分工：

| 目录 | 放什么 | 入库 | 理由 |
|---|---|---|---|
| `third_party/` | 上游源码快照 | 是 | 上游仓库可能消失（`unlock-music/cli` 已因 DMCA 整站下架），留着才能重建 |
| `tools/` | 编译产物 + 安装包 + hook 脚本 | 是 | 运行时依赖；官方 CDN 已下架旧版客户端，仓库不带就无法复现 |

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

**安装包已入库**，在 `tools/QQMusic_Setup_1951.exe`（72 MB）与
`tools/QQMusicMac_Mgr_8.8.0_20230903.dmg`（48 MB），SHA256 见
[qqmusic/README.md](qqmusic/README.md)。之所以把这两个大文件放进仓库：2026-11-01 复核时
所有官方源都已下架，第三方转载的包无法校验真伪。留着它们，换机器时直接装即可；不留，
就再也拿不到一份可验证的 19.51 了。

| 源 | 结果 |
|---|---|
| `https://dldir1v6.qq.com/music/clntupate/QQMusic_Setup_1951.exe`（官方） | `404`，腾讯已下架 |
| `https://dldir1.qq.com/music/clntupate/mac/QQMusicMac_Mgr.dmg`（官方） | `404` |
| `web.archive.org` 快照 | 直连不通，必须走 `scripts/git_uplink.py` 代理，见 [qqmusic/README.md](qqmusic/README.md) |
| `t.me/um_lsr_ch`（um 官方分发频道） | 不通 |
| 第三方软件站 / 网盘转载 | 可访问，但**包无法校验真伪**，不作为入库来源 |

安装完成后，用 `QQMusic.exe` 的文件版本号确认是 **19.51**（右键属性 → 详细信息）。
macOS 侧对应 **8.8.0（20230903）**，装完不要让它自动升级。

---

## 4. `browser-local` 分支的前置源码（2026-11-09 快照）

**为什么留**：`browser-local` 分支要把解密、标签/封面、声纹、SQLite 库全部放进浏览器。
这些能力的上游有 DMCA 下架史（见 §2）、自建 Git 服务换过域名、npm/CDN 也可能断供。
按 §1 的同一口径再存一份**源码快照**：以后下载不到就能自己编，上游停更就能自己改。

**与 §1 的区别**：§1 是主干运行时要用的程序；本节是浏览器分支的编译输入，主干不引用。
全部快照都剔除了 `.git/`（避免仓库里嵌仓库），本目录仍只放源码与构建配置。

### 4.1 快照清单

| 目录 | 上游 | 分支 @ commit | 用途 | 许可证 |
|---|---|---|---|---|
| [um-react/](um-react/) | `git.um-react.app/um/um-react` | `main @ c8bb7d443073` | 浏览器解密前端（React），WASM 内核调用方 | MIT |
| [lib_um_crypto_rust/](lib_um_crypto_rust/) | `git.um-react.app/um/lib_um_crypto_rust` | `main @ ebad061dd557` | `@unlock-music/crypto`：Rust 解密算法 → WASM（`um_wasm` / `um_wasm_loader`） | MIT / Apache-2.0 双许可 |
| [qmpc-mmkv/](qmpc-mmkv/) | `git.um-react.app/um/qmpc-mmkv` | `main @ 80435076c924` | QQ 音乐 PC 客户端 MMKV / ekey 提取（C + meson） | `LICENSE.txt`，引入前须确认 |
| [go-mmkv/](go-mmkv/) | `git.um-react.app/um/go-mmkv` | `main @ 83770a01d697` | 纯 Go 的 MMKV 只读实现，CLI 侧读密钥用 | **未见 LICENSE**，引入前须确认 |
| [web/](web/) | `git.um-react.app/um/web` | `main @ f0d16e334129` | Unlock Music Web Edition（Vue 旧版），算法 JS 实现参考 | MIT |
| [taglib-wasm/](taglib-wasm/) | `github.com/CharlesWiltgen/TagLib-Wasm` | `main @ bd362c3f8a16` | 标签与内嵌封面读写 WASM | MIT |
| [unimusic-chromaprint/](unimusic-chromaprint/) | `github.com/UniMusic-app/unimusic-chromaprint` | `main @ ea8a9547f858` | Chromaprint 指纹 WASM | MIT |
| [ffmpeg-wasm/](ffmpeg-wasm/) | `github.com/ffmpegwasm/ffmpeg.wasm` | `main @ f876f907c7e9` | `.ape/.wma/.dsf` 等解码成 PCM | MIT |
| [pyodide/](pyodide/) | `github.com/pyodide/pyodide` | `main @ cf278c2a0c20` | mutagen 兜底路径的 Python 运行时 | MPL-2.0 |
| [sqlite-wasm/](sqlite-wasm/) | `sqlite.org` 官方分发包 + 源码包 | `3.54.1`（`3540100`） | `sqlite3` WASM 的 JS 胶水 / OPFS VFS + 完整 C 源码 | SQLite 公有领域 |

`sqlite-wasm/` 里两个来源：`sqlite-wasm-3540100.zip` 解压出的 `jswasm/*.js/.mjs`、
`common/`、demo 与文档（可直接使用），以及 `sqlite-src-3540100.zip`（14.9 MB，
完整源码树含 `ext/wasm/`，用来自己编译 `sqlite3.wasm`）。后者是**上游源码分发包**，
不是编译产物，故原样保留压缩容器。本地 SHA256：

```
387e7f6cad4797b17848c07d453dc6606917bb356a6cfe5a3abafd38c240c71b  sqlite-src-3540100.zip
85ebce90b6d189442b29e11d193337b5e63203aae9b6590dbe89a601b9891da2  sqlite-wasm-3540100.zip
```

> `git.unlock-music.dev` 2026-11-09 返回 `403`，故 Unlock Music 系列取自可达的
> `git.um-react.app` 镜像；GitHub 主站直连超时，归档走 `codeload.github.com`，
> commit 校验走 `api.github.com`。

### 4.2 submodule 已一并入库

归档 tarball **不含** submodule 内容，缺了就编不动。下表是各仓库 `.gitmodules`
里声明的路径与本次落地位置（路径与上游一致，可直接编译）：

| 上游声明路径 | 本仓库位置 | 上游 / 分支 @ commit |
|---|---|---|
| `taglib-wasm/lib/taglib` | `third_party/taglib-wasm/lib/taglib/` | `taglib/taglib` `master @ 8fe8b8235b85` |
| `taglib-wasm/lib/mpack` | `third_party/taglib-wasm/lib/mpack/` | `ludocode/mpack` `develop @ 9eacca4d3127` |
| `taglib/3rdparty/utfcpp` | `third_party/taglib-wasm/lib/taglib/3rdparty/utfcpp/` | `nemtrif/utfcpp` `master @ 42900b6befd2` |
| `unimusic-chromaprint/kissfft` | `third_party/unimusic-chromaprint/kissfft/` | `mborgerding/kissfft` `master @ f3fd3a58f1b9` |
| `unimusic-chromaprint/chromaprint` | `third_party/unimusic-chromaprint/chromaprint/` | `acoustid/chromaprint` `master @ 3b38c100022b` |
| `pyodide/pyodide-build` | `third_party/pyodide/pyodide-build/` | `pyodide/pyodide-build` `main @ b711a823bd93` |
| `ffmpeg-wasm/testdata` | **未入库** | 测试音视频素材，非编译必需且体积大 |

注意两点：

- `unimusic-chromaprint` 的 `.gitmodules` 指向 `acoustid/chromaprint` 的
  `update-kissfft-paths` 分支，该分支 2026-11-09 已不存在，改取 `master`；
  若编译时报 kissfft 路径错误，需手工补回该分支的路径补丁。
- `third_party/chromaprint/`（1.6.2，主干 `fpcalc` 上游）仍在，与
  `unimusic-chromaprint/chromaprint/` 是两份不同来源，不要互相覆盖。

### 4.3 复现与更新

```bash
# Unlock Music 系列（Gitea 归档，直连可达）
curl -fSL -o /tmp/um-react.tar.gz \
    https://git.um-react.app/um/um-react/archive/main.tar.gz
tar -xzf /tmp/um-react.tar.gz -C third_party/um-react --strip-components=1

# GitHub 系列（github.com 直连不通时用 codeload，或加 -x http://127.0.0.1:7897）
curl -fSL -o /tmp/taglib-wasm.tar.gz \
    https://codeload.github.com/CharlesWiltgen/TagLib-Wasm/tar.gz/refs/heads/main
tar -xzf /tmp/taglib-wasm.tar.gz -C third_party/taglib-wasm --strip-components=1

# SQLite 完整源码
curl -fSL -o third_party/sqlite-wasm/sqlite-src-3540100.zip \
    https://sqlite.org/2026/sqlite-src-3540100.zip
```

更新任一依赖后：同步本表的分支与 commit、按 §4.4 重新裁剪、重新运行
`python scripts/build_docs_index.py` 与 `python scripts/check_docs.py`。

### 4.4 裁剪口径

- 剔除 `.git/`，避免嵌套仓库被 git 当成 submodule 而只存一个指针；
- 删除上游自带的 `.gitignore`：它里面的规则会把自己的 `Makefile`、`CHANGELOG.md`、
  `.gitmodules` 等源码/构建文件误判为忽略项；根 `.gitignore` 已为 `build/` 构建脚本目录
  与 SQLite 源码 zip 加了精确例外。`.vscode/` 等 IDE 配置按根规则跳过；
- 剔除编译产物：`taglib-wasm/build/*.wasm`、`sqlite-wasm/jswasm/sqlite3.wasm`，
  以及 um-react 说明页附带的示例 `noop.exe` 与 pyodide-build 的测试用 `.so`；
- `ffmpeg-wasm/testdata` 不入库；
- 上游自带的 `*.md` 保留原文供 [docs/index.html](../docs/index.html) 查阅，但按
  `scripts/check_docs.py` 的约定不参与链接/命令校验——本目录只有
  `third_party/README.md` 与 `third_party/qqmusic/README.md` 是本仓库维护的。

### 4.5 合规

引入任何产物前先按 [docs/browser-local-roadmap.md](../docs/browser-local-roadmap.md)
§10「许可证合规」逐项确认：`go-mmkv`、`qmpc-mmkv` 没有明确的 SPDX 声明，
`taglib` 是 LGPL-2.1/MPL、`pyodide` 是 MPL-2.0、Chromaprint 链接的 FFmpeg 是 LGPL，
`lib_um_crypto_rust` 为双许可。Unlock Music 上游有 DMCA 历史，这些源码只作本地
可复现备份，**不随 Web 产物分发**。
