// Copyright 2022 Daniel Erat.
// All rights reserved.

//go:build !cgo

package main

import (
	// 没有 C 工具链时（CGO_ENABLED=0，用于交叉编译 macOS / 免 gcc 构建）
	// 回退到纯 Go 的 SQLite 实现。数据库文件格式完全相同，可直接互读。
	_ "modernc.org/sqlite"
)

// dbDriverName 是 database/sql 使用的驱动名。
const dbDriverName = "sqlite"
