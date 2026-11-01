#!/bin/sh
# 构建 macOS 版 soundalike（arm64 + amd64）。
#
# 与 build_win.sh 的差别：macOS 上不方便准备 C 交叉工具链，因此用 CGO_ENABLED=0
# 走纯 Go 的 SQLite 实现（见 dbdriver_nocgo.go）。产物是普通 Mach-O 可执行文件，
# 生成的 music.db 与 Windows 版完全互通。
#
# 用法（本目录在 music_helper/third_party/soundalike）：
#   ./build_macos.sh                      # 产物落在当前目录
#   ./build_macos.sh ../../tools          # 直接落到 music_helper 的 tools/
set -e

version="0.1.5"
out="${1:-.}"

for arch in arm64 amd64; do
    echo "building darwin/${arch} -> ${out}/soundalike-darwin-${arch}"
    CGO_ENABLED=0 GOOS=darwin GOARCH="${arch}" go build -trimpath \
        -ldflags "-s -w -X main.buildVersion=${version}" \
        -o "${out}/soundalike-darwin-${arch}" .
done

echo "done"
