// Copyright 2022 Daniel Erat.
// All rights reserved.

//go:build cgo

package main

import (
	// 有 C 工具链时使用 mattn/go-sqlite3：与历史版本行为完全一致，
	// Windows 官方构建（build_win.sh）走的就是这条路。
	_ "github.com/mattn/go-sqlite3"
)

// dbDriverName 是 database/sql 使用的驱动名。
const dbDriverName = "sqlite3"
