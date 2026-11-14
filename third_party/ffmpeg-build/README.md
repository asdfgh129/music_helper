# FFmpeg 精简构建配方（P2 试听解码，可选）

本目录**只放构建配方与许可说明，不放二进制**，与 `third_party/README.md` 的分工一致：
编译产物若随包分发，放在 `tools/`，由 `scripts/build_exe.py` 的可选清单复制。

## 1. 为什么需要它

浏览器原生 `<audio>` 解不了 `.ape`（Monkey's Audio）、`.wma`（ASF/WMA，含 Lossless）
和 `.dsf`（DSD 1bit）。P2 用**本机 Python 进程起一个 FFmpeg 子进程**把这三种格式派生为
临时 MP3，落到 `log/_media_cache/` 再复用 `/api/media/stream` 的 Range 实现；原文件绝不改写。
契约见 `docs/media-player.md` §6，调用实现是 `services/transcode.py`。

FFmpeg 原生就带这些解码器，不需要自己写解码器，也不使用 WASM（当前分支是本机临时 Web
服务，把几百 MB 送进浏览器内存解码纯属绕远路）。

## 2. 三种来源，按优先级

`services/transcode.py:ffmpeg_exe()` 依次找：

1. `config.ini` 的 `[tools] ffmpeg_exe` / 环境变量 `MUSIC_HELPER_FFMPEG_EXE`，
   默认 `tools/` 下的 `ffmpeg.exe`（Windows）或 `ffmpeg-darwin-<arch>` / `ffmpeg`；
2. 系统 PATH 里的 `ffmpeg`；
3. 可选的 Python 包 `imageio-ffmpeg`（`pip install imageio-ffmpeg`，`requirements-dev.txt` 已列）。

三处都没有**不是错误**：`GET /api/media/transcode` 返回 `available=false` 与安装提示，
播放器退回 P0 就有的「用系统播放器打开」按钮。本配方是给想内置精简二进制的人用的，
`imageio-ffmpeg` 提供的完整静态构建（约 80 MB）已实测覆盖下面全部解码器。

## 3. 精简构建配方

用 FFmpeg 7.x 源码 + LAME，关闭默认全量组件，只留试听需要的解码/编码/封装：

```bash
./configure \
  --prefix=$PWD/../../tools/_ffmpeg_build \
  --disable-everything --disable-doc --disable-programs --enable-ffmpeg \
  --disable-network --disable-autodetect --disable-iconv --disable-zlib \
  --enable-demuxer=ape,asf,dsf,mp3 --enable-muxer=mp3 \
  --enable-parser=ape,mpegaudio \
  --enable-decoder=ape,wmav1,wmav2,wmalossless,wmapro,dsd_lsbf_planar,dsd_msbf_planar \
  --enable-encoder=libmp3lame --enable-protocol=file \
  --enable-filter=aresample --enable-libmp3lame \
  --enable-small
make -j"$(nproc)" && make install
```

产物按平台改名为 `tools/` 里的 `ffmpeg.exe` / `ffmpeg-darwin-arm64` /
`ffmpeg-darwin-amd64` / `ffmpeg`。构建前用
`ffmpeg -hide_banner -decoders | grep -E 'ape|wma|dsd'` 自检解码器清单。

`services/transcode.py:build_command()` 的参数是：

```
ffmpeg -hide_banner -loglevel error -nostdin -y -i <src> -map 0:a:0 -vn -sn -dn
       -c:a libmp3lame -b:a 192k -ar 44100 -ac 2 -map_metadata -1
       -progress pipe:1 -nostats -f mp3 <cache>.part
```

`-progress pipe:1` 供前端显示解码进度；成功后 `.part` 原子改名为 `<hash>.mp3`。
DSF 的 DSD64（2.8224 MHz / 1bit）由 `dsd_*_planar` 解成 PCM 再重采样到 44.1 kHz，试听足够。

## 4. 许可

FFmpeg 的许可取决于 configure 选项；**启用 `--enable-libmp3lame` 后整体为 GPLv2**，
不能静态链进本项目的 MIT 许可代码里分发。因此本项目采取的是「独立可执行文件 +
运行时调用子进程」，二进制**不随仓库分发**，也不进 `REQUIRED_MODULES`。
若要自行分发精简构建，必须同时提供对应源码与 GPL 许可文本；只启用
`--disable-gpl --enable-encoder=libshine` 等方案可保持 LGPL，但编码质量与可用性另评。

`imageio-ffmpeg` 自带的构建同样带 GPL 组件，其许可文本随该包提供；本项目只是可选依赖，
不把它打进 PyInstaller 产物。

## 5. 边界

- 带 DRM 的 WMA 解不了，会在转码状态里显式报错并提示用系统播放器打开；
- 转码产物只写 `log/_media_cache/`，最多 12 个文件 / 512 MiB，LRU 清理；
- 转码在独立后台线程执行，不进 `web/tasks.py` 串行队列，不生成 `core.ops.Plan`。
