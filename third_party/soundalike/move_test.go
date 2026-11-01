// Copyright 2024 Daniel Erat.
// All rights reserved.

package main

import (
	"bytes"
	"fmt"
	"os"
	"path/filepath"
	"reflect"
	"sort"
	"strings"
	"testing"
)

func TestMoveSmaller(t *testing.T) {
	medium := fileInfo{id: 1, path: "medium.txt", size: 12, duration: 43.0}
	big := fileInfo{id: 2, path: "subdir/big.txt", size: 24, duration: 42.0}
	small := fileInfo{id: 3, path: "small.txt", size: 6, duration: 46.0}
	infos := []*fileInfo{&medium, &big, &small}

	td := t.TempDir()
	srcDir := filepath.Join(td, "src")
	writeTestFileInfos(t, srcDir, infos)
	dstDir := filepath.Join(td, "dst")
	var stdout bytes.Buffer
	if err := moveSmaller(&stdout, infos, srcDir, dstDir, nil); err != nil {
		t.Fatalf("moveSmaller(stdout, %+v, %q, %q, nil) failed: %v", infos, srcDir, dstDir, err)
	}
	checkTestDir(t, srcDir, map[string]string{big.path: makeTestData(big.size)})
	checkTestDir(t, dstDir, map[string]string{
		small.path:  makeTestData(small.size),
		medium.path: makeTestData(medium.size),
	})
}

func TestMoveInteractive(t *testing.T) {
	medium := fileInfo{id: 1, path: "medium.txt", size: 12, duration: 43.0}
	big := fileInfo{id: 2, path: "subdir/big.txt", size: 24, duration: 42.0}
	small := fileInfo{id: 3, path: "small.txt", size: 6, duration: 46.0}
	infos := []*fileInfo{&medium, &big, &small}

	td := t.TempDir()
	srcDir := filepath.Join(td, "src")
	writeTestFileInfos(t, srcDir, infos)
	dstDir := filepath.Join(td, "dst")

	// Without any input, nothing should be moved.
	var stdout, stdin bytes.Buffer
	if err := moveInteractive(&stdout, &stdin, infos, srcDir, dstDir, nil); err != nil {
		t.Fatalf("moveInteractive(stdout, stdin, %+v, %q, %q, nil) failed: %v", infos, srcDir, dstDir, err)
	}
	checkTestDir(t, srcDir, map[string]string{
		big.path:    makeTestData(big.size),
		small.path:  makeTestData(small.size),
		medium.path: makeTestData(medium.size),
	})
	checkTestDir(t, dstDir, nil)

	// Run again with some bogus input before selecting the second file
	// (which should be medium after sorting by descending size).
	stdout.Reset()
	stdin.WriteString("-1\n0\nabc\n4\n2\n")
	if err := moveInteractive(&stdout, &stdin, infos, srcDir, dstDir, nil); err != nil {
		t.Fatalf("moveInteractive(stdout, stdin, %+v, %q, %q, nil) failed: %v", infos, srcDir, dstDir, err)
	}
	checkTestDir(t, srcDir, map[string]string{medium.path: makeTestData(medium.size)})
	// 目标目录是平铺的：只保留文件名，重名再补 (1)(2)，不保留源目录层级。
	checkTestDir(t, dstDir, map[string]string{
		small.path: makeTestData(small.size),
		"big.txt":  makeTestData(big.size),
	})
}

func TestFormatTier(t *testing.T) {
	for _, tc := range []struct {
		path  string
		tier  int
		known bool
	}{
		{"a.dsf", 6, true},
		{"a.DFF", 6, true},
		{"a.wav", 5, true},
		{"a.flac", 4, true},
		{"a.ape", 4, true},
		{"a.m4a", 3, true},
		{"a.mp3", 2, true},
		{"a.opus", 2, true},
		{"a.wma", 1, true},
		// 认不出的扩展名必须 known=false，否则会被当成「最差」自动移走。
		{"a.txt", 0, false},
		{"a.mka", 0, false},
	} {
		tier, _, known := formatTier(tc.path)
		if tier != tc.tier || known != tc.known {
			t.Errorf("formatTier(%q) = %d, %v; want %d, %v", tc.path, tier, known, tc.tier, tc.known)
		}
	}
}

func TestQualityBetterThan(t *testing.T) {
	q := func(path string, size int64, dur float64) quality {
		return qualityOf(&fileInfo{path: path, size: size, duration: dur})
	}
	// DSD 再小也比 mp3 好（格式层级优先）。
	if !q("a.dsf", 50_000_000, 200).betterThan(q("a.mp3", 8_000_000, 200)) {
		t.Error("dsf should beat mp3")
	}
	// 同格式：码率高 10% 算更好。
	if !q("a.mp3", 11_000_000, 200).betterThan(q("a.mp3", 10_000_000, 200)) {
		t.Error("higher bitrate mp3 should win")
	}
	// 同格式：码率差不到 2% 视为一样好，不自动移。
	if q("a.mp3", 10_100_000, 200).betterThan(q("a.mp3", 10_000_000, 200)) {
		t.Error("2% bitrate difference should be a tie")
	}
	if !q("a.mp3", 10_100_000, 200).sameAs(q("a.mp3", 10_000_000, 200)) {
		t.Error("2% bitrate difference should be sameAs")
	}
	// 算不出码率（时长为 0）时同层级不判定高下。
	if q("a.flac", 10, 0).betterThan(q("a.flac", 20, 0)) {
		t.Error("unknown bitrate should not decide")
	}
}

func TestMoveByQuality(t *testing.T) {
	// dsf(DSD) / flac / mp3 三者同曲：flac、mp3 都该被自动移走，dsf 保留，
	// 全程不读 stdin。
	dsf := fileInfo{id: 1, path: "song.dsf", size: 60, duration: 200}
	flac := fileInfo{id: 2, path: "song.flac", size: 20, duration: 200}
	mp3 := fileInfo{id: 3, path: "song.mp3", size: 8, duration: 200}
	infos := []*fileInfo{&mp3, &flac, &dsf}

	td := t.TempDir()
	srcDir := filepath.Join(td, "src")
	writeTestFileInfos(t, srcDir, infos)
	dstDir := filepath.Join(td, "dst")

	var stdout, stdin bytes.Buffer // 空 stdin：模拟非交互运行
	if err := moveInteractive(&stdout, &stdin, infos, srcDir, dstDir, nil); err != nil {
		t.Fatalf("moveInteractive failed: %v", err)
	}
	checkTestDir(t, srcDir, map[string]string{dsf.path: makeTestData(dsf.size)})
	checkTestDir(t, dstDir, map[string]string{
		flac.path: makeTestData(flac.size),
		mp3.path:  makeTestData(mp3.size),
	})
	if !strings.Contains(stdout.String(), "无需确认") {
		t.Errorf("output should explain the automatic move; got:\n%v", stdout.String())
	}

	// 音质完全相同时不能自动移，空 stdin 应当一个都不动。
	dup1 := fileInfo{id: 11, path: "x1.flac", size: 10, duration: 200}
	dup2 := fileInfo{id: 12, path: "x2.flac", size: 10, duration: 200}
	dups := []*fileInfo{&dup1, &dup2}
	src2 := filepath.Join(td, "src2")
	writeTestFileInfos(t, src2, dups)
	dst2 := filepath.Join(td, "dst2")
	stdout.Reset()
	stdin.Reset()
	if err := moveInteractive(&stdout, &stdin, dups, src2, dst2, nil); err != nil {
		t.Fatalf("moveInteractive failed: %v", err)
	}
	checkTestDir(t, src2, map[string]string{
		dup1.path: makeTestData(dup1.size),
		dup2.path: makeTestData(dup2.size),
	})
	checkTestDir(t, dst2, nil)
}

func TestMoveDryRun(t *testing.T) {
	flac := fileInfo{id: 1, path: "song.flac", size: 10, duration: 200}
	mp3 := fileInfo{id: 2, path: "song.mp3", size: 4, duration: 200}
	infos := []*fileInfo{&flac, &mp3}

	td := t.TempDir()
	srcDir := filepath.Join(td, "src")
	writeTestFileInfos(t, srcDir, infos)
	dstDir := filepath.Join(td, "dst")

	dryRun = true
	defer func() { dryRun = false }()
	var stdout, stdin bytes.Buffer
	if err := moveInteractive(&stdout, &stdin, infos, srcDir, dstDir, nil); err != nil {
		t.Fatalf("moveInteractive failed: %v", err)
	}
	// 一个文件都不该动。
	checkTestDir(t, srcDir, map[string]string{
		flac.path: makeTestData(flac.size),
		mp3.path:  makeTestData(mp3.size),
	})
	checkTestDir(t, dstDir, nil)
	if !strings.Contains(stdout.String(), "试运行") {
		t.Errorf("dry run should say so; got:\n%v", stdout.String())
	}
}

func TestMoveFile(t *testing.T) {
	type errorState int
	const (
		noError errorState = iota
		dstExists
		dstIsSrc
		dstIsSrcWithDot
	)

	for _, tc := range []struct {
		name       string
		fn         func(string, string) error
		errorState errorState
	}{
		{"moveFile", moveFile, noError},
		{"moveFile", moveFile, dstExists},
		{"moveFile", moveFile, dstIsSrc},
		{"copyAndRemoveFile", copyAndRemoveFile, noError},
		{"copyAndRemoveFile", copyAndRemoveFile, dstExists},
		{"copyAndRemoveFile", copyAndRemoveFile, dstIsSrc},
	} {
		t.Run(fmt.Sprintf("%v-%v", tc.name, tc.errorState), func(t *testing.T) {
			const data = "here's the data to copy\n"
			const existing = "here's existing data\n"

			td := t.TempDir()
			srcPath := filepath.Join(td, "src", "file.txt")
			if err := os.Mkdir(filepath.Dir(srcPath), 0755); err != nil {
				t.Fatal(err)
			}
			if err := os.WriteFile(srcPath, []byte(data), 0644); err != nil {
				t.Fatal(err)
			}

			dstPath := filepath.Join(td, "dst", "out.txt")
			switch tc.errorState {
			case dstExists:
				if err := os.Mkdir(filepath.Dir(dstPath), 0755); err != nil {
					t.Fatal(err)
				}
				if err := os.WriteFile(dstPath, []byte(existing), 0644); err != nil {
					t.Fatal(err)
				}
			case dstIsSrc:
				dstPath = srcPath
			case dstIsSrcWithDot:
				dstPath = filepath.Join(filepath.Dir(srcPath), ".", filepath.Base(srcPath))
			}

			if err := tc.fn(srcPath, dstPath); tc.errorState == noError {
				if err != nil {
					t.Fatalf("%v(%q, %q) failed: %v", tc.name, srcPath, dstPath, err)
				}
				if b, err := os.ReadFile(dstPath); err != nil {
					t.Error(err)
				} else if string(b) != data {
					t.Errorf("%v wrote %q; want %q", tc.name, string(b), data)
				}
				if _, err := os.Stat(srcPath); err == nil {
					t.Errorf("%v still exists", srcPath)
				}
			} else {
				if err == nil {
					t.Errorf("%v(%q, %q) unexpectedly succeeded", tc.name, srcPath, dstPath)
				}
				if _, err := os.Stat(srcPath); err != nil {
					t.Error(err)
				}
			}
		})
	}
}

// writeTestFileInfos writes the files described by infos under dir using makeTestData.
func writeTestFileInfos(t *testing.T, dir string, infos []*fileInfo) {
	for _, fi := range infos {
		// moveFileWithLoggingDB 用 fi.fullPath() 定位源文件；测试里的 fileInfo 只写了
		// 相对 path，不补 dirPath 就会拿相对路径去 Stat，在任意平台上都找不到文件。
		fi.dirPath = dir
		p := filepath.Join(dir, fi.path)
		if err := os.MkdirAll(filepath.Dir(p), 0755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(p, []byte(makeTestData(fi.size)), 0644); err != nil {
			t.Fatal(err)
		}
	}
}

// makeTestData repeats 'a' size times.
func makeTestData(size int64) string { return strings.Repeat("a", int(size)) }

// checkTestDir reads all the files under dir and verifies that they match want,
// a map from relative path to data.
func checkTestDir(t *testing.T, dir string, want map[string]string) {
	t.Helper()
	type file struct{ path, data string }

	var wantFiles []file
	for p, d := range want {
		wantFiles = append(wantFiles, file{p, d})
	}
	sort.Slice(wantFiles, func(i, j int) bool { return wantFiles[i].path < wantFiles[j].path })

	var gotFiles []file
	if err := filepath.Walk(dir, func(p string, fi os.FileInfo, err error) error {
		if p == dir {
			return nil // ignore root dir not existing
		} else if err != nil {
			return err
		} else if !fi.Mode().IsRegular() {
			return nil
		}
		b, err := os.ReadFile(p)
		if err != nil {
			return err
		}
		// Windows 上 Walk 返回的是反斜杠路径，want 里写的是正斜杠：统一成斜杠再比，
		// 否则这组用例在 Windows 上永远失败（与逻辑无关）。
		gotFiles = append(gotFiles, file{filepath.ToSlash(p[len(dir)+1:]), string(b)})
		return nil
	}); err != nil {
		t.Error(err)
		return
	}

	if !reflect.DeepEqual(gotFiles, wantFiles) {
		dump := func(files []file) string {
			lines := make([]string, len(files))
			for i, f := range files {
				lines[i] = fmt.Sprintf("  %v: %q", f.path, f.data)
			}
			return strings.Join(lines, "\n")
		}
		t.Errorf("%v doesn't contain expected files\nGot:\n%v\nWant:\n%v\n",
			dir, dump(gotFiles), dump(wantFiles))
	}
}
