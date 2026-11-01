// Copyright 2022 Daniel Erat.
// All rights reserved.

package main

import (
	"fmt"
	"io"
	"math/bits"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"
)

// ignoreDecodeEOFMaxBytes contains the max file size for which errDecodeEOF is ignored.
const ignoreDecodeEOFMaxBytes = 128 * 1024

// scanOptions contains options for scanFiles.
type scanOptions struct {
	dirs           []string       // directories containing audio files
	fileString     string         // uncompiled fileRegexp
	fileRegexp     *regexp.Regexp // matches files to scan
	logSec         int            // logging frequency
	lookupThresh   float64        // threshold for lookup table in (0.0, 1.0]
	matchThresh    float64        // threshold for bitwise comparisons in (0.0, 1.0]
	matchMinLength bool           // use min length (instead of max) for bitwise comparisons
	skipBadFiles   bool           // skip files that can't be fingerprinted by fpcalc
	ignoreMtimes   bool           // ignore file modification times when looking for updates
	tempDirs       []string       // temporary directories to scan without saving to db
	check          bool           // check database consistency with actual files
	debugMode      bool           // enable debug mode with verbose output
}

func defaultScanOptions() *scanOptions {
	return &scanOptions{
		// TODO: I'm just guessing what should be included here. See
		// https://en.wikipedia.org/wiki/Audio_file_format#List_of_formats and
		// https://en.wikipedia.org/wiki/FFmpeg#Supported_codecs_and_formats.
		fileString:   `(?i)\.(aiff|flac|m4a|mp3|oga|ogg|opus|wav|wma|ape)$`,
		logSec:       10,
		lookupThresh: 0.25,
		matchThresh:  0.95,
		skipBadFiles: true,
	}
}

func (o *scanOptions) finish() error {
	for i, dir := range o.dirs {
		dir = strings.TrimRight(dir, "/")
		o.dirs[i] = dir
		if fi, err := os.Stat(dir); err != nil {
			return err
		} else if !fi.IsDir() {
			return fmt.Errorf("%v is not a directory", dir)
		}
	}

	if o.lookupThresh <= 0 || o.lookupThresh > 1.0 {
		return fmt.Errorf("bad lookup threshold %v", o.lookupThresh)
	}
	if o.matchThresh <= 0 || o.matchThresh > 1.0 {
		return fmt.Errorf("bad match threshold %v", o.matchThresh)
	}

	var err error
	if o.fileRegexp, err = regexp.Compile(o.fileString); err != nil {
		return fmt.Errorf("bad file regexp: %w", err)
	}

	return nil
}

// scanFiles scans opts.dirs and returns groups of similar files.
func scanFiles(opts *scanOptions, db *audioDB, fps *fpcalcSettings, writer io.Writer) ([][]*fileInfo, error) {
	lookup := newLookupTable()
	edges := make(map[fileID][]fileID)

	if opts.debugMode {
		fmt.Fprintf(writer, "[DEBUG] scanFiles started\n")
		fmt.Fprintf(writer, "[DEBUG] lookup threshold: %.2f\n", opts.lookupThresh)
		fmt.Fprintf(writer, "[DEBUG] match threshold: %.2f\n", opts.matchThresh)
	}

	// Store temporary file info for later reference
	// Use negative fileIDs to distinguish temp files from database files
	tempFileInfo := make(map[fileID]*fileInfo)
	var tempIDCounter fileID = -1

	// addAndCompare 把 info 加入查重表，并与表里已有的指纹逐个比较，命中就连边。
	// 正式运行的 info 已在库里（id>0）；工作区文件与试运行用负数 id，不写库。
	addAndCompare := func(info *fileInfo) error {
		lookup.add(info.id, info.fprint)
		thresh := int(float64(len(info.fprint)) * opts.lookupThresh)
		for _, oid := range lookup.find(info.fprint, thresh) {
			if oid == info.id {
				continue
			}
			var oinfo *fileInfo
			if oid > 0 {
				var err error
				if oinfo, err = db.get(oid, "", ""); err != nil {
					return err
				} else if oinfo == nil {
					return fmt.Errorf("%d not in database", oid)
				}
			} else {
				var ok bool
				if oinfo, ok = tempFileInfo[oid]; !ok {
					return fmt.Errorf("temp file %d not found", oid)
				}
			}
			if ok, err := db.isExcludedPair(info.fullPath(), oinfo.fullPath()); err != nil {
				return fmt.Errorf("check %q and %q: %w", info.fullPath(), oinfo.fullPath(), err)
			} else if ok {
				if opts.debugMode {
					fmt.Fprintf(writer, "[DEBUG]   Excluded pair with ID %d\n", oid)
				}
				continue
			}
			score, _, _ := compareFingerprints(info.fprint, oinfo.fprint, opts.matchMinLength)
			if score >= opts.matchThresh {
				edges[info.id] = append(edges[info.id], oid)
				edges[oid] = append(edges[oid], info.id)
			}
		}
		return nil
	}

	// Load all existing fingerprints from database into lookup table
	if db != nil && !dryRun {
		if opts.debugMode {
			fmt.Fprintf(writer, "[DEBUG] Loading fingerprints from database...\n")
		}
		ids, fprints, err := db.getAllFingerprints()
		if err != nil {
			return nil, fmt.Errorf("failed to load fingerprints from database: %w", err)
		}
		for i, id := range ids {
			lookup.add(id, fprints[i])
		}
		if len(ids) > 0 {
			fmt.Fprintf(writer, "Loaded %d fingerprint(s) from database\n", len(ids))
		}
		if opts.debugMode {
			fmt.Fprintf(writer, "[DEBUG] Loaded %d fingerprints into lookup table\n", len(ids))
		}
	}

	lastLog := time.Now()
	var scanned int

	// Scan main directories
	for _, dir := range opts.dirs {
		// filepath.Walk doesn't follow symlinks, so do it manually first.
		dir, err := filepath.EvalSymlinks(dir)
		if err != nil {
			return nil, err
		}

		if err := filepath.Walk(dir, func(p string, fi os.FileInfo, err error) error {
			if p == dir || fi.IsDir() || !opts.fileRegexp.MatchString(filepath.Base(p)) {
				return nil
			}

			// Use the first directory as base, extract relative path
			// e.g., G:/music/1980-1989/1986/1.mp3 -> dirPath=G:/music, relPath=1980-1989/1986/1.mp3
			baseDir := opts.dirs[0]
			relPath, err := filepath.Rel(baseDir, p)
			if err != nil {
				return err
			}

			// 先检查一下，文件是否已经存在于数据库中
			info, err := db.get(0, baseDir, relPath)
			if err != nil {
				return fmt.Errorf("get %q: %w", p, err)
			} else if info == nil {
				info = &fileInfo{}
			}

			//且文件大小和修改时间有没有变化，如果变化了就重新计算指纹
			mtime := fi.ModTime().Unix()
			needsFingerprint := info.id == 0 || info.size != fi.Size() || (!opts.ignoreMtimes && info.mtime != 0 && info.mtime != mtime)

			if opts.debugMode {
				fmt.Fprintf(writer, "[DEBUG] Processing: %s\n", relPath)
				fmt.Fprintf(writer, "[DEBUG]   Size: %d bytes\n", fi.Size())
				fmt.Fprintf(writer, "[DEBUG]   MTime: %d\n", mtime)
				fmt.Fprintf(writer, "[DEBUG]   Needs fingerprint: %v\n", needsFingerprint)
			}

			if dryRun {
				// 试运行：不写库，但照样参与比对。优先复用库里已有的指纹（文件没变
				// 就不用再跑 fpcalc），再以负数 id 放进内存。这样每次预览都能重新
				// 比出重复，而不会被「库里已经处理过」这个状态吃掉。
				var fprint []uint32
				var duration float64
				var compressed string
				reusable := info.id > 0 && info.size == fi.Size() &&
					(opts.ignoreMtimes || info.mtime == 0 || info.mtime == mtime)
				if reusable {
					fprint, duration, compressed = info.fprint, info.duration, info.compressedFprint
				} else {
					finfo, err := runFpcalc(p, fps)
					if err == errEmptyFingerprint || (err == errDecodeEOF && fi.Size() <= ignoreDecodeEOFMaxBytes) {
						return nil
					} else if err != nil {
						if opts.skipBadFiles {
							fmt.Fprintf(writer, "Skipping %v: %v\n", p, err)
							return nil
						}
						return fmt.Errorf("%v: %w", p, err)
					}
					fprint, duration, compressed = finfo.Fingerprint, finfo.Duration, finfo.CompressedFingerprint
				}
				tempIDCounter--
				dryInfo := &fileInfo{
					id:               tempIDCounter,
					dirPath:          baseDir,
					path:             relPath,
					size:             fi.Size(),
					mtime:            mtime,
					duration:         duration,
					fprint:           fprint,
					compressedFprint: compressed,
				}
				tempFileInfo[dryInfo.id] = dryInfo
				if err := addAndCompare(dryInfo); err != nil {
					return err
				}
			} else if needsFingerprint {
				if opts.debugMode {
					fmt.Fprintf(writer, "[DEBUG]   Running fpcalc...\n")
				}
				finfo, err := runFpcalc(p, fps)
				if err == errEmptyFingerprint || (err == errDecodeEOF && fi.Size() <= ignoreDecodeEOFMaxBytes) {
					return nil
				} else if err != nil {
					if opts.skipBadFiles {
						fmt.Fprintf(writer, "Skipping %v: %v\n", p, err)
						return nil
					}
					return fmt.Errorf("%v: %w", p, err)
				}

				if opts.debugMode {
					fmt.Fprintf(writer, "[DEBUG]   Duration: %.2fs\n", finfo.Duration)
					fmt.Fprintf(writer, "[DEBUG]   Fingerprint length: %d\n", len(finfo.Fingerprint))
					fmt.Fprintf(writer, "[DEBUG]   Compressed fingerprint length: %d\n", len(finfo.CompressedFingerprint))
				}

				info = &fileInfo{
					dirPath:          baseDir,
					path:             relPath,
					size:             fi.Size(),
					mtime:            mtime,
					duration:          finfo.Duration,
					fprint:           finfo.Fingerprint,
					compressedFprint:  finfo.CompressedFingerprint,
				}
				// 这里有问题，因为需要先判断是否重复，不重复才需要保存
				// 也可以是先保存，然后再查找重复的，删除文件的时候再来删除保存的数据
				if info.id, err = db.save(info); err != nil {
					return fmt.Errorf("save %q: %w", p, err)
				}

				if opts.debugMode {
					fmt.Fprintf(writer, "[DEBUG]   Saved to database with ID: %d\n", info.id)
				}

				// 新指纹：入查重表并跟已有指纹比较
				if opts.debugMode {
					thresh := int(float64(len(info.fprint)) * opts.lookupThresh)
					fmt.Fprintf(writer, "[DEBUG]   Lookup threshold: %d bits (%.2f%% of %d)\n",
						thresh, opts.lookupThresh, len(info.fprint))
				}
				if err := addAndCompare(info); err != nil {
					return err
				}
			}
			// If file hasn't changed (fingerprint already in database from initial load),
			// skip lookup and add operations for better performance

			scanned++
			if opts.logSec > 0 && time.Since(lastLog).Seconds() >= float64(opts.logSec) {
				fmt.Fprintf(writer, "Scanned %d files\n", scanned)
				lastLog = time.Now()
			}

			return nil
		}); err != nil {
			return nil, err
		}
	}
	// Scan temp directories (don't save to database)
	if len(opts.tempDirs) > 0 {
		fmt.Fprintf(writer, "\nScanning temp directories...\n")
		for _, dir := range opts.tempDirs {
			dir, err := filepath.EvalSymlinks(dir)
			if err != nil {
				return nil, err
			}

			if err := filepath.Walk(dir, func(p string, fi os.FileInfo, err error) error {
				if p == dir || fi.IsDir() || !opts.fileRegexp.MatchString(filepath.Base(p)) {
					return nil
				}

				// Use the first directory as base, extract relative path
				baseDir := opts.dirs[0]
				relPath, err := filepath.Rel(baseDir, p)
				if err != nil {
					return err
				}

				finfo, err := runFpcalc(p, fps)
				if err == errEmptyFingerprint || (err == errDecodeEOF && fi.Size() <= ignoreDecodeEOFMaxBytes) {
					return nil
				} else if err != nil {
					if opts.skipBadFiles {
						fmt.Fprintf(writer, "Skipping %v: %v\n", p, err)
						return nil
					}
					return fmt.Errorf("%v: %w", p, err)
				}

				// Assign a unique negative ID to this temp file
				tempIDCounter--
				tempID := tempIDCounter

				info := &fileInfo{
					id:               tempID,
					dirPath:          baseDir,
					path:             relPath,
					size:             fi.Size(),
					mtime:            fi.ModTime().Unix(),
					duration:          finfo.Duration,
					fprint:           finfo.Fingerprint,
					compressedFprint:  finfo.CompressedFingerprint,
				}

				// 工作区文件只入内存表，不写库
				tempFileInfo[tempID] = info
				if err := addAndCompare(info); err != nil {
					return err
				}

				scanned++
				if opts.logSec > 0 && time.Since(lastLog).Seconds() >= float64(opts.logSec) {
					fmt.Fprintf(writer, "Scanned %d files\n", scanned)
					lastLog = time.Now()
				}

				return nil
			}); err != nil {
				return nil, err
			}
		}
	}

	if opts.logSec > 0 {
		fmt.Fprintf(writer, "Finished scanning %d files\n", scanned)
	}

	var groups [][]*fileInfo
GroupLoop:
	for _, comp := range components(edges) {
		group := make([]*fileInfo, 0, len(comp))
		for _, id := range comp {
			var info *fileInfo
			var err error

			if id < 0 {
				// Temp file - retrieve from tempFileInfo map
				var ok bool
				info, ok = tempFileInfo[id]
				if !ok {
					return nil, fmt.Errorf("temp file %d not found", id)
				}
			} else {
				// Database file
				info, err = db.get(id, "", "")
				if err != nil {
					return nil, fmt.Errorf("getting info for %d: %w", id, err)
				} else if info == nil {
					return nil, fmt.Errorf("no info for %d", id)
				}
			}
			group = append(group, info)
		}
		for i := 0; i < len(group)-1; i++ {
			for j := i + 1; j < len(group); j++ {
				if ok, err := db.isExcludedPair(group[i].fullPath(), group[j].fullPath()); err != nil {
					return nil, err
				} else if ok {
					continue GroupLoop
				}
			}
		}
		sort.Slice(group, func(i, j int) bool { return group[i].fullPath() < group[j].fullPath() })
		groups = append(groups, group)
	}
	sort.Slice(groups, func(i, j int) bool { return groups[i][0].path < groups[j][0].path })
	return groups, nil
}

// compareFingerprints returns the ratio of identical bits in a and b to the
// total bits in the longer (or shorter if minLength is true) of the two.
// All possible alignments are checked, and the highest ratio is returned.
func compareFingerprints(a, b []uint32, minLength bool) (ratio float64, aoff, boff int) {
	if len(a) == 0 || len(b) == 0 {
		return 0, 0, 0
	}

	count := func(a, b []uint32) int {
		var cnt int
		for i := 0; i < len(a) && i < len(b); i++ {
			cnt += 32 - bits.OnesCount32(a[i]^b[i])
		}
		return cnt
	}

	best := count(a, b)
	for i := 1; i < len(a); i++ {
		if cnt := count(a[i:], b); cnt > best {
			best = cnt
			aoff, boff = i, 0
		}
	}
	for i := 1; i < len(b); i++ {
		if cnt := count(a, b[i:]); cnt > best {
			best = cnt
			aoff, boff = 0, i
		}
	}

	total := len(a)
	if (minLength && len(b) < total) || (!minLength && len(b) > total) {
		total = len(b)
	}
	return float64(best) / float64(32*total), aoff, boff
}

// components returns all components from the undirected graph described by edges.
func components(edges map[fileID][]fileID) [][]fileID {
	visited := make(map[fileID]struct{})

	var search func(fileID) []fileID
	search = func(src fileID) []fileID {
		if _, ok := visited[src]; ok {
			return nil
		}
		visited[src] = struct{}{}
		comp := []fileID{src}
		for _, dst := range edges[src] {
			comp = append(comp, search(dst)...)
		}
		return comp
	}

	var comps [][]fileID
	for src := range edges {
		if _, ok := visited[src]; !ok {
			comps = append(comps, search(src))
		}
	}
	return comps
}

// checkDB checks database consistency with actual files in opts.dirs.
func checkDB(opts *scanOptions, db *audioDB, fps *fpcalcSettings, writer io.Writer) error {
	fmt.Fprintf(writer, "\nChecking database consistency...\n")

	dbPaths, err := db.getAllPaths()
	if err != nil {
		return fmt.Errorf("failed to get database paths: %w", err)
	}

	actualFiles := make(map[string]string)
	for _, dir := range opts.dirs {
		dir, err := filepath.EvalSymlinks(dir)
		if err != nil {
			return err
		}

		if err := filepath.Walk(dir, func(p string, fi os.FileInfo, err error) error {
			if p == dir || fi.IsDir() || !opts.fileRegexp.MatchString(filepath.Base(p)) {
				return nil
			}

			// Use the first directory as base, extract relative path
			baseDir := opts.dirs[0]
			relPath, err := filepath.Rel(baseDir, p)
			if err != nil {
				return err
			}
			fullPath := filepath.Join(baseDir, relPath)

			actualFiles[fullPath] = p
			return nil
		}); err != nil {
			return err
		}
	}

	var removed int
	for _, dbPath := range dbPaths {
		if _, ok := actualFiles[dbPath]; !ok {
			dirPath := opts.dirs[0]
			relPath, err := filepath.Rel(dirPath, dbPath)
			if err != nil {
				fmt.Fprintf(writer, "Error parsing path %s: %v\n", dbPath, err)
				continue
			}
			if err := db.delete(dirPath, relPath); err != nil {
				fmt.Fprintf(writer, "Error removing %s from database: %v\n", dbPath, err)
			} else {
				fmt.Fprintf(writer, "Removed from database: %s\n", dbPath)
				removed++
			}
		}
	}

	var added int
	for fullPath, realPath := range actualFiles {
		dirPath := opts.dirs[0]
		relPath, err := filepath.Rel(dirPath, fullPath)
		if err != nil {
			fmt.Fprintf(writer, "Error parsing path %s: %v\n", fullPath, err)
			continue
		}
		info, err := db.get(0, dirPath, relPath)
		if err != nil {
			return fmt.Errorf("get %q: %w", realPath, err)
		} else if info == nil {
			fi, err := os.Stat(realPath)
			if err != nil {
				fmt.Fprintf(writer, "Error getting info for %s: %v\n", realPath, err)
				continue
			}

			finfo, err := runFpcalc(realPath, fps)
			if err != nil {
				fmt.Fprintf(writer, "Skipping %s: %v\n", realPath, err)
				continue
			}

			info = &fileInfo{
				dirPath:          dirPath,
				path:             relPath,
				size:             fi.Size(),
				mtime:            fi.ModTime().Unix(),
				duration:          finfo.Duration,
				fprint:           finfo.Fingerprint,
				compressedFprint:  finfo.CompressedFingerprint,
			}

			if _, err := db.save(info); err != nil {
				fmt.Fprintf(writer, "Error saving %s to database: %v\n", realPath, err)
			} else {
				fmt.Fprintf(writer, "Added to database: %s\n", fullPath)
				added++
			}
		}
	}

	fmt.Fprintf(writer, "Database check complete: removed %d, added %d files\n", removed, added)
	return nil
}
