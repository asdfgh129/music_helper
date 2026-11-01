// Copyright 2022 Daniel Erat.
// All rights reserved.

package main

import (
	"bytes"
	"database/sql"
	"encoding/binary"
	"path/filepath"
	"testing"

	"github.com/google/go-cmp/cmp"
	"github.com/google/go-cmp/cmp/cmpopts"
)

func TestNewAudioDB(t *testing.T) {
	p := filepath.Join(t.TempDir(), "test.db")
	settings := defaultFpcalcSettings()
	if db, err := newAudioDB(p, settings, useRelPaths); err != nil {
		t.Fatal("newAudioDB with new file failed: ", err)
	} else if _, err := db.save(&fileInfo{dirPath: "/music", path: "a/b.mp3", size: 123, duration: 65.3, fprint: []uint32{1}}); err != nil {
		t.Fatal("save failed: ", err)
	} else if err := db.close(); err != nil {
		t.Fatal("close failed: ", err)
	}
	if db, err := newAudioDB(p, settings, 0); err != nil {
		t.Fatal("newAudioDB with existing file failed: ", err)
	} else if err := db.close(); err != nil {
		t.Fatal("close failed: ", err)
	}

	settings.length *= 2
	if db, err := newAudioDB(p, settings, 0); err == nil {
		db.close()
		t.Fatal("newAudioDB with different settings unexpectedly succeeded")
	}
}

func TestAudioDB_Save_Get(t *testing.T) {
	p := filepath.Join(t.TempDir(), "test.db")
	settings := defaultFpcalcSettings()
	db, err := newAudioDB(p, settings, useRelPaths)
	if err != nil {
		t.Fatal("newAudioDB failed: ", err)
	}
	const (
		dirPath = "/music/library"
		relPath = "artist/album/01-title.mp3"
		size    = 2 * 1024 * 1024
		mtime   = 42
		dur     = 103.4
	)
	fprint := []uint32{
		2835786340, 2835868260, 2836164325, 2903256545, 3976998131, 3976543474,
		3980795026, 4156954754, 4135987330, 4135991426, 3532003458, 3532019842,
	}
	id, err := db.save(&fileInfo{dirPath: dirPath, path: relPath, size: size, mtime: mtime, duration: dur, fprint: fprint})
	if err != nil {
		db.close()
		t.Fatal("save failed: ", err)
	}
	if err := db.close(); err != nil {
		t.Fatal("close failed: ", err)
	}

	if db, err = newAudioDB(p, settings, useRelPaths); err != nil {
		t.Fatal("newAudioDB failed: ", err)
	}
	defer db.close()

	want := fileInfo{id: id, dirPath: dirPath, path: relPath, size: size, mtime: mtime, duration: dur, fprint: fprint}
	opts := []cmp.Option{
		cmp.AllowUnexported(fileInfo{}),
		cmpopts.IgnoreFields(fileInfo{}, "id", "dirID"),
	}
	if got, err := db.get(0, dirPath, relPath); err != nil {
		t.Errorf("get(0, %q, %q) failed: %v", dirPath, relPath, err)
	} else if got == nil {
		t.Errorf("get(0, %q, %q) returned nil", dirPath, relPath)
	} else if diff := cmp.Diff(want, *got, opts...); diff != "" {
		t.Errorf("get(0, %q, %q) returned bad results:\n%v", dirPath, relPath, diff)
	}
	if got, err := db.get(id, "", ""); err != nil {
		t.Errorf(`get(%d, "", "") failed: %v`, id, err)
	} else if got == nil {
		t.Errorf(`get(%d, "", "") returned nil`, id)
	} else if diff := cmp.Diff(want, *got, opts...); diff != "" {
		t.Errorf(`get(%d, "", "") returned bad results:\n%v`, id, diff)
	}

	const (
		newSize  = 3 * 1024 * 1024
		newMtime = 450
		newDur   = 105
	)
	newFprint := []uint32{
		3980795026, 4156954754, 4135987330, 4135991426, 3532003458, 3532019842,
		2835786340, 2835868260, 2836164325, 2903256545, 3976998131, 3976543474,
	}
	if newID, err := db.save(&fileInfo{id: id, dirPath: dirPath, path: relPath, size: newSize, mtime: newMtime, duration: newDur, fprint: newFprint}); err != nil {
		t.Error("save failed: ", err)
	} else if newID != id {
		t.Errorf("save returned id %v; want %v", newID, id)
	}
	want = fileInfo{id: id, dirPath: dirPath, path: relPath, size: newSize, mtime: newMtime, duration: newDur, fprint: newFprint}
	if got, err := db.get(0, dirPath, relPath); err != nil {
		t.Errorf("get(0, %q, %q) failed: %v", dirPath, relPath, err)
	} else if got == nil {
		t.Errorf("get(0, %q, %q) returned nil", dirPath, relPath)
	} else if diff := cmp.Diff(want, *got, opts...); diff != "" {
		t.Errorf("get(0, %q, %q) returned bad results:\n%v", dirPath, relPath, diff)
	}

	const otherDir = "/other/music"
	const otherRel = "song.mp3"
	if got, err := db.get(0, otherDir, otherRel); err != nil {
		t.Errorf("get(0, %q, %q) failed: %v", otherDir, otherRel, err)
	} else if got != nil {
		t.Errorf("get(0, %q, %q) = %+v; want nil", otherDir, otherRel, *got)
	}
}

func TestAudioDB_ExcludedPairs(t *testing.T) {
	p := filepath.Join(t.TempDir(), "test.db")
	settings := defaultFpcalcSettings()
	db, err := newAudioDB(p, settings, useRelPaths)
	if err != nil {
		t.Fatal("newAudioDB failed: ", err)
	}
	// Windows 上不关库，t.TempDir 的清理会失败（句柄仍打开）。
	defer db.close()

	const (
		a = "a.mp3"
		b = "b.mp3"
		c = "c.mp3"
	)

	if ok, err := db.isExcludedPair(a, b); err != nil {
		t.Fatalf("isExcludedPair(%q, %q) failed: %v", a, b, err)
	} else if ok {
		t.Fatalf("isExcludedPair(%q, %q) = %v; want %v", a, b, ok, false)
	}
	if err := db.saveExcludedPair(a, b); err != nil {
		t.Fatalf("saveExcludedPair(%q, %q) failed: %v", a, b, err)
	}
	if ok, err := db.isExcludedPair(a, b); err != nil {
		t.Fatalf("isExcludedPair(%q, %q) failed: %v", a, b, err)
	} else if !ok {
		t.Fatalf("isExcludedPair(%q, %q) = %v; want %v", a, b, ok, true)
	}
	if ok, err := db.isExcludedPair(b, a); err != nil {
		t.Fatalf("isExcludedPair(%q, %q) failed: %v", b, a, err)
	} else if !ok {
		t.Fatalf("isExcludedPair(%q, %q) = %v; want %v", b, a, ok, true)
	}
	if ok, err := db.isExcludedPair(a, c); err != nil {
		t.Fatalf("isExcludedPair(%q, %q) failed: %v", a, c, err)
	} else if ok {
		t.Fatalf("isExcludedPair(%q, %q) = %v; want %v", a, c, ok, false)
	}
}

func TestAudioDB_UpdateSchema(t *testing.T) {
	// 用按平台拼出来的绝对路径：写死 "/music/foo/1.mp3" 在 Windows 上会被
	// filepath.Dir 当成「当前盘根下的 music\\foo」，迁移后的相对路径与断言对不上。
	musicDir := filepath.Join(t.TempDir(), "music", "foo")
	const (
		size1 = 131072
		dur1  = 60.5

		size2 = 262144
		dur2  = 120.0
	)
	absPath1 := filepath.Join(musicDir, "1.mp3")
	absPath2 := filepath.Join(musicDir, "2.mp3")

	fp := []uint32{1, 2, 3, 4}
	var b bytes.Buffer
	if err := binary.Write(&b, dbByteOrder, fp); err != nil {
		t.Fatal(err)
	}

	p := filepath.Join(t.TempDir(), "test.db")
	db, err := sql.Open(dbDriverName, p)
	if err != nil {
		t.Fatal(err)
	}
	settings := defaultFpcalcSettings()
	for _, s := range []string{
		`CREATE TABLE IF NOT EXISTS Settings (Desc STRING PRIMARY KEY NOT NULL)`,
		`CREATE TABLE IF NOT EXISTS Files (
			Path STRING PRIMARY KEY NOT NULL,
			Duration FLOAT NOT NULL,
			Size INTEGER NOT NULL,
			Fingerprint BLOB NOT NULL)`,
		`CREATE TABLE IF NOT EXISTS ExcludedPairs (
			PathA STRING NOT NULL,
			PathB STRING NOT NULL,
			PRIMARY KEY (PathA, PathB))`,
	} {
		if _, err := db.Exec(s); err != nil {
			db.Close()
			t.Fatal(err)
		}
	}
	// 用占位符插入，别用 fmt.Sprintf("%q")：%q 是 Go 的字面量转义，Windows 路径
	// 里的反斜杠会被翻倍写进库，迁移后路径对不上，测试在 Windows 上白跑。
	for _, stmt := range []struct {
		sql  string
		args []interface{}
	}{
		{`INSERT INTO Settings VALUES(?)`, []interface{}{settings.String()}},
		{`INSERT INTO Files VALUES(?, ?, ?, ?)`, []interface{}{absPath1, dur1, size1, b.Bytes()}},
		{`INSERT INTO Files VALUES(?, ?, ?, ?)`, []interface{}{absPath2, dur2, size2, b.Bytes()}},
		{`INSERT INTO ExcludedPairs VALUES(?, ?)`, []interface{}{absPath1, absPath2}},
	} {
		if _, err := db.Exec(stmt.sql, stmt.args...); err != nil {
			db.Close()
			t.Fatal(err)
		}
	}
	db.Close()

	adb, err := newAudioDB(p, settings, useRelPaths)
	if err != nil {
		t.Fatal(err)
	}
	defer adb.close()

	opts := []cmp.Option{
		cmp.AllowUnexported(fileInfo{}),
		cmpopts.IgnoreFields(fileInfo{}, "id", "dirID"),
	}

	// After migration, path should be relative to directory
	wantDir1 := musicDir
	wantPath1 := "1.mp3"
	want := fileInfo{dirPath: wantDir1, path: wantPath1, size: size1, duration: dur1, fprint: fp}
	if got, err := adb.get(0, wantDir1, wantPath1); err != nil {
		t.Errorf("get(0, %q, %q) failed: %v", wantDir1, wantPath1, err)
	} else if diff := cmp.Diff(want, *got, opts...); diff != "" {
		t.Errorf("get(0, %q, %q) returned bad results:\n%v", wantDir1, wantPath1, diff)
	}

	if got, err := adb.isExcludedPair(absPath1, absPath2); err != nil {
		t.Errorf("isExcludedPair(%q, %q) failed: %v", absPath1, absPath2, err)
	} else if !got {
		t.Errorf("isExcludedPair(%q, %q) = %v; want true", absPath1, absPath2, got)
	}

	want.mtime = 123
	if _, err := adb.save(&want); err != nil {
		t.Errorf("save(%v) failed: %v", want, err)
	} else if got, err := adb.get(0, wantDir1, wantPath1); err != nil {
		t.Errorf("get(0, %q, %q) failed: %v", wantDir1, wantPath1, err)
	} else if diff := cmp.Diff(want, *got, opts...); diff != "" {
		t.Errorf("get(0, %q, %q) returned bad results:\n%v", wantDir1, wantPath1, diff)
	}
}

func TestAudioDB_Directories(t *testing.T) {
	p := filepath.Join(t.TempDir(), "test.db")
	settings := defaultFpcalcSettings()
	db, err := newAudioDB(p, settings, useRelPaths)
	if err != nil {
		t.Fatal("newAudioDB failed: ", err)
	}
	defer db.close()

	dir1 := "/music/library"
	dir2 := "/other/music"

	id1, err := db.getOrCreateDirectory(dir1)
	if err != nil {
		t.Fatalf("getOrCreateDirectory(%q) failed: %v", dir1, err)
	}
	if id1 == 0 {
		t.Errorf("getOrCreateDirectory(%q) returned 0", dir1)
	}

	id1again, err := db.getOrCreateDirectory(dir1)
	if err != nil {
		t.Fatalf("getOrCreateDirectory(%q) failed: %v", dir1, err)
	}
	if id1again != id1 {
		t.Errorf("getOrCreateDirectory(%q) returned %d; want %d", dir1, id1again, id1)
	}

	id2, err := db.getOrCreateDirectory(dir2)
	if err != nil {
		t.Fatalf("getOrCreateDirectory(%q) failed: %v", dir2, err)
	}
	if id2 == id1 {
		t.Errorf("getOrCreateDirectory(%q) returned same id as %q", dir2, dir1)
	}

	dirs, err := db.getAllDirectories()
	if err != nil {
		t.Fatalf("getAllDirectories failed: %v", err)
	}
	if len(dirs) != 2 {
		t.Errorf("getAllDirectories returned %d directories; want 2", len(dirs))
	}
	if dirs[id1] != dir1 {
		t.Errorf("getAllDirectories[%d] = %q; want %q", id1, dirs[id1], dir1)
	}
	if dirs[id2] != dir2 {
		t.Errorf("getAllDirectories[%d] = %q; want %q", id2, dirs[id2], dir2)
	}

	newDirPath := "/updated/music"
	if err := db.updateDirectoryPath(dir1, newDirPath); err != nil {
		t.Fatalf("updateDirectoryPath failed: %v", err)
	}

	dirs, err = db.getAllDirectories()
	if err != nil {
		t.Fatalf("getAllDirectories after update failed: %v", err)
	}
	if dirs[id1] != newDirPath {
		t.Errorf("getAllDirectories[%d] = %q; want %q after update", id1, dirs[id1], newDirPath)
	}
}

func TestAudioDB_Delete(t *testing.T) {
	p := filepath.Join(t.TempDir(), "test.db")
	settings := defaultFpcalcSettings()
	db, err := newAudioDB(p, settings, useRelPaths)
	if err != nil {
		t.Fatal("newAudioDB failed: ", err)
	}
	defer db.close()

	const dirPath = "/music"
	const relPath = "song.mp3"

	if _, err := db.save(&fileInfo{dirPath: dirPath, path: relPath, size: 100, duration: 60, fprint: []uint32{1}}); err != nil {
		t.Fatal("save failed: ", err)
	}

	got, err := db.get(0, dirPath, relPath)
	if err != nil {
		t.Fatalf("get failed: %v", err)
	}
	if got == nil {
		t.Fatal("get returned nil")
	}

	if err := db.delete(dirPath, relPath); err != nil {
		t.Fatalf("delete failed: %v", err)
	}

	got, err = db.get(0, dirPath, relPath)
	if err != nil {
		t.Fatalf("get after delete failed: %v", err)
	}
	if got != nil {
		t.Errorf("get after delete returned %+v; want nil", got)
	}
}

func TestAudioDB_GetAllPaths(t *testing.T) {
	p := filepath.Join(t.TempDir(), "test.db")
	settings := defaultFpcalcSettings()
	db, err := newAudioDB(p, settings, useRelPaths)
	if err != nil {
		t.Fatal("newAudioDB failed: ", err)
	}
	defer db.close()

	files := []struct {
		dir  string
		path string
	}{
		{"/music", "song1.mp3"},
		{"/music", "album/song2.mp3"},
		{"/other", "song3.mp3"},
	}

	for _, f := range files {
		if _, err := db.save(&fileInfo{dirPath: f.dir, path: f.path, size: 100, duration: 60, fprint: []uint32{1}}); err != nil {
			t.Fatalf("save failed: %v", err)
		}
	}

	paths, err := db.getAllPaths()
	if err != nil {
		t.Fatalf("getAllPaths failed: %v", err)
	}

	if len(paths) != len(files) {
		t.Errorf("getAllPaths returned %d paths; want %d", len(paths), len(files))
	}

	wantPaths := map[string]bool{
		"/music/song1.mp3":       true,
		"/music/album/song2.mp3": true,
		"/other/song3.mp3":       true,
	}
	for _, p := range paths {
		// Windows 上拼出来的是反斜杠路径，断言按 POSIX 写，统一成 / 再比。
		if !wantPaths[filepath.ToSlash(p)] {
			t.Errorf("getAllPaths returned unexpected path %q", p)
		}
	}
}
