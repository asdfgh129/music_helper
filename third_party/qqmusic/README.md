# QQ 音乐旧版客户端（安装包与屏蔽更新）

放这里的是**说明**，安装包本体在 [`tools/`](../../tools/)：

| 文件 | 版本 | 大小 | SHA256 |
|---|---|---|---|
| `tools/QQMusic_Setup_1951.exe` | Windows 19.51 | 74,865,032 | `86841d77c59fe4752c2a799f57b74faf25b07390612767ddc0b071a8cdb49f74` |
| `tools/QQMusicMac_Mgr_8.8.0_20230903.dmg` | macOS 8.8.0（20230903） | 49,461,724 | `e2f528142874d1e72b0fb12d705844ec0ba2897326ff56fd211cf92f22bda5ea` |
| `tools/Q音屏蔽更新.zip` | Windows 屏蔽更新 | 520 | 内含 1536 字节的空 `QQMusicUp.exe` |
| `tools/QQ 音乐 Mac 屏蔽升级.tar.gz` | macOS 屏蔽更新 | 372 | 内含 271 字节的 `.command` 脚本（改 Info.plist 版本号） |

为什要旧版：新版（Windows ≥19.57、macOS ≥2023-09-03）不再把 ekey 落盘，下载的
`.mflac/.mgg` 离开客户端就解不开（详见 [docs/troubleshooting.md](../../docs/troubleshooting.md)）。

## Windows 19.51

19.51 及以下下载的文件把密钥**内嵌在文件里**，`um` 直接能解，不需要任何凭据。

官方 CDN 已下架（`https://dldir1v6.qq.com/music/clntupate/QQMusic_Setup_1951.exe` → `404`），
现存的取法：

- **Telegram**：`https://t.me/um_lsr_ch/24`（71.4 MB，必须用客户端，网页版不给文件直链）
- 夸克分享 `https://pan.quark.cn/s/e09758934faf` 里有「去广告安装版 / 绿色版」，
  但那是第三方改过的二进制，完整性无从校验，不建议用

## macOS 8.8.0（20230903）

这一版的 `MMKVStreamEncryptId` **还没加密**，`um --qmc-mmkv` 能直接读 ekey。

腾讯官方早已 404。唯一可行的是 **archive.org 快照**——注意它**直连不通，必须走
`scripts/git_uplink.py` 代理**，这是 2026-11-01 复核时纠正的结论：

```bash
python scripts/git_uplink.py run -- python -c "
import urllib.request
u = 'https://web.archive.org/web/20230903023312id_/https://dldir1.qq.com/music/clntupate/mac/QQMusicMac_Mgr.dmg'
urllib.request.urlretrieve(u, 'tools/QQMusicMac_Mgr_8.8.0_20230903.dmg')
"
```

几个关键点，记下来省得再挖一遍：

- 文件名是 **`QQMusicMac_Mgr.dmg`**（不带版本号），这是个固定马甲名，内容随上架时间变；
- 快照要挑 **`20230903023312`** 这一个。用 CDX 接口能列出全部快照：

  ```bash
  python scripts/git_uplink.py run -- python -c "
  import urllib.request
  u='https://web.archive.org/cdx/search/cdx?url=dldir1.qq.com/music/clntupate/mac/QQMusicMac_Mgr.dmg&output=json&fl=timestamp,statuscode,length&collapse=digest'
  print(urllib.request.urlopen(u, timeout=60).read().decode())"
  ```

  结果里的 `20230903023312` 是 2023-09-03 的 8.8.0（49 MB），`20231106220657` 已经是
  8.8.5（78 MB）——**别拿错**，8.8.5 的 mmkv 已经加密了。
- URL 里的 `id_` 后缀表示取原始字节（不加 archive 的网页包装），少了它会拿到 HTML。
- 文件尾 512 字节以 `koly` 开头才是完整 dmg；头部看起来是 `78da` 属于正常（那是分区压缩数据）。

历史版本号的来源：Homebrew cask 的 `Casks/q/qqmusic.rb` 提交历史里有每一版的
`version "8.8.0,73226"`，逗号后面就是 Build 号，拼出来是
`QQMusicMac8.8.0Build73226.dmg`——但腾讯只保留近期文件，这个直链现在 `404`，
只能靠快照。

## 安装完：屏蔽自动更新

**Windows**：解压 `Q音屏蔽更新.zip`，把里面的空 `QQMusicUp.exe` 覆盖到安装目录的
同名文件上（`C:\Program Files (x86)\Tencent\QQMusic\QQMusicUp.exe`）。升级器被换成
个空壳，就不再自动更新了。

**macOS**：解压 `tools/QQ 音乐 Mac 屏蔽升级.tar.gz`，得到
`QQ 音乐 Mac 屏蔽升级.command`（271 字节，exec 位已带），双击运行。它做三件事：

```sh
sed -i.bak 's#<string>8.8.0</string>#<string>88.8.0</string>#' /Applications/QQMusic.app/Contents/Info.plist
codesign --force --deep --sign - /Applications/QQMusic.app
xattr -d com.apple.quarantine /Applications/QQMusic.app
```

也就是把 `Info.plist` 里的版本号改成 `88.8.0`，让客户端自认为比线上最新版还新，于是不再提示
升级；随后重新本地签名（改过 plist 会让原签名失效），并去掉隔离属性。

第一次运行可能提示「无法打开，因为来自身份不明的开发者」——右键点它 → 选菜单第一项「打开」
→ 在警告框里再点「打开」。详见
[um 官方答疑](https://unlock-music.liumingye.cn/questions/qqmusic)。

装完先确认版本别装错：

- Windows：右键 `QQMusic.exe` → 属性 → 详细信息，`文件版本` 应为 `19.51.x`
- macOS：`QQ 音乐` → 关于

## 注意：现在用的客户端是 21.92

本机当前装的是 **21.92**（`C:\Program Files (x86)\Tencent\QQMusic`），它下载的文件
`EncType` 全是 2（新版 qmc），必须外部 ekey，frida 也取不到——**想批量解密必须换成
19.51**。装之前先把 `G:\QQMusic\VipSongsDownload` 里已有的文件处理掉，因为换客户端
不会让老文件的 ekey 回来。

## 关于入库

`.gitignore` 目前排除了 `third_party/qqmusic/*.{exe,dmg,zip}`。这两个包合计约 118 MB，
进 git 会让每次 clone 都变慢且没有增量压缩。要入库就删掉那一行——但要注意
`tools/` 下的同名文件并不受这条规则约束，需要单独判断。
