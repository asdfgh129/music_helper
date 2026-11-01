// Copyright 2024 Daniel Erat.
// All rights reserved.

package main

import (
	"bufio"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
)

// bitrateTolerance is the relative difference needed to call one file better than
// another within the same format tier. Anything smaller is treated as a tie.
const bitrateTolerance = 0.02

// quality describes how good a file's audio is, as far as it can be told without
// decoding it: the format's quality tier, and (within a tier) the effective bitrate.
type quality struct {
	tier    int   // 格式层级，越大越好；known=false 时无意义
	bitrate int64 // 估算码率 bps（size*8/duration），0 表示算不出来
	known   bool  // 格式是否认识；不认识就不敢判断好坏
}

// formatTier maps a file extension to a quality tier.
//
// 层级按「同样内容、不同容器」的常见音质排序：DSD > 未压缩 PCM > 无损压缩 >
// AAC/ALAC > 有损压缩。未知扩展名返回 known=false —— 调用方必须把它们交给人工
// 判断，绝不能当成「最低优先级」自动移走（历史上 .dsf 就因此被当成最差的一类）。
func formatTier(path string) (tier int, name string, known bool) {
	switch strings.ToLower(filepath.Ext(path)) {
	case ".dsf", ".dff":
		return 6, "DSD", true
	case ".wav", ".aif", ".aiff", ".aifc":
		return 5, "PCM 未压缩", true
	case ".flac", ".ape", ".wv", ".tta", ".tak":
		return 4, "无损压缩", true
	case ".m4a", ".aac":
		// .m4a 里可能装 AAC 也可能装 ALAC，只看扩展名分不出来，
		// 只能先放在有损之上，让同层级内按码率比。
		return 3, "AAC/ALAC", true
	case ".mp3", ".ogg", ".oga", ".opus":
		return 2, "有损", true
	case ".wma":
		return 1, "WMA 有损", true
	}
	return 0, "未知格式", false
}

// qualityOf estimates the quality of info.
func qualityOf(info *fileInfo) quality {
	tier, _, known := formatTier(info.path)
	q := quality{tier: tier, known: known}
	if info.duration > 0 && info.size > 0 {
		q.bitrate = int64(float64(info.size) * 8 / info.duration)
	}
	return q
}

// betterThan reports whether q is clearly better than o.
// 层级不同直接比层级；同层级比码率，差值不到 bitrateTolerance 视为一样好。
func (q quality) betterThan(o quality) bool {
	if q.tier != o.tier {
		return q.tier > o.tier
	}
	if q.bitrate <= 0 || o.bitrate <= 0 {
		return false
	}
	return float64(q.bitrate) > float64(o.bitrate)*(1+bitrateTolerance)
}

// sameAs reports whether两 files 的音质无法区分（谁都不比谁好）。
func (q quality) sameAs(o quality) bool {
	return !q.betterThan(o) && !o.betterThan(q)
}

// tierLabel returns a short label for a quality tier.
func tierLabel(tier int) string {
	switch tier {
	case 6:
		return "DSD 无损"
	case 5:
		return "PCM 未压缩"
	case 4:
		return "无损压缩"
	case 3:
		return "AAC/ALAC"
	case 2:
		return "有损压缩"
	case 1:
		return "WMA 有损"
	}
	return "未知格式"
}

// describe returns a short human-readable description of q.
func (q quality) describe() string {
	if !q.known {
		return "未知格式"
	}
	label := tierLabel(q.tier)
	if q.bitrate > 0 {
		return fmt.Sprintf("%s，约 %d kbps", label, q.bitrate/1000)
	}
	return label
}

// moveInteractive keeps the best-quality file from infos and moves the rest from
// srcDir to dstDir.
//
// 音质能分出高下时（不同格式层级，或同层级码率差 ≥2%），差的直接移走，不问。
// 音质分不出高下时（同格式同码率），才让用户挑一个保留 —— 这时没有「更差」的
// 文件可言，自动挑等于随机删。
// If db is provided, it also removes moved files from the database.
func moveInteractive(stdout io.Writer, stdin io.Reader,
	infos []*fileInfo, srcDir, dstDir string, db *audioDB) error {
	if len(infos) == 0 {
		return nil
	}

	qs := make([]quality, len(infos))
	allKnown := true
	best := 0
	for i, info := range infos {
		qs[i] = qualityOf(info)
		if !qs[i].known {
			allKnown = false
		}
		if qs[i].betterThan(qs[best]) {
			best = i
		}
	}

	// 有认不出的格式：不敢自动判断，全部交给人工（老行为），避免误移。
	if !allKnown {
		return promptKeep(stdout, stdin, infos, srcDir, dstDir, db)
	}

	var keepers, worse []*fileInfo
	for i, info := range infos {
		if i == best || qs[i].sameAs(qs[best]) {
			keepers = append(keepers, info)
		} else {
			worse = append(worse, info)
		}
	}

	if len(worse) > 0 {
		sort.Slice(worse, func(i, j int) bool { return worse[i].size > worse[j].size })
		fmt.Fprintf(stdout, "音质最好的是 %v（%v），移走 %d 个较差的（无需确认）：\n",
			keepers[0].fullPath(), qs[best].describe(), len(worse))
		for _, info := range worse {
			fmt.Fprintf(stdout, "  %v  [%v]\n", info.fullPath(), qualityOf(info).describe())
		}
		for _, info := range worse {
			if err := moveFileWithLoggingDB(info, srcDir, dstDir, stdout, db); err != nil {
				return err
			}
		}
		fmt.Fprintln(stdout)
	}

	// 剩下的几个音质一样，谁都不比谁差，只能问。
	if len(keepers) > 1 {
		return promptKeep(stdout, stdin, keepers, srcDir, dstDir, db)
	}
	return nil
}

// promptKeep asks which of infos to keep and moves the rest to dstDir.
// An empty answer (or EOF) keeps everything, so a non-interactive run never moves
// files whose quality can't be told apart.
func promptKeep(stdout io.Writer, stdin io.Reader,
	infos []*fileInfo, srcDir, dstDir string, db *audioDB) error {
	if len(infos) < 2 {
		return nil
	}
	sort.Slice(infos, func(i, j int) bool { return infos[i].size > infos[j].size })
	if dryRun {
		// 试运行不该停下来等人按回车：列出候选并说明正式运行会问什么。
		fmt.Fprintln(stdout, "[试运行] 以下文件音质相同，正式运行时会要求人工选择保留哪一个：")
		for _, ln := range formatFiles(infos, "") {
			fmt.Fprintln(stdout, "  "+ln)
		}
		return nil
	}
	width := strconv.Itoa(len(strconv.Itoa(len(infos))))
	for i, ln := range formatFiles(infos, "") {
		fmt.Fprintf(stdout, "%"+width+"d. %v\n", i+1, ln)
	}
	var keep int // 0-indexed
	r := bufio.NewReader(stdin)
	for {
		fmt.Fprintf(stdout, "File to keep [%d-%d, empty to keep all]: ", 1, len(infos))
		input, err := r.ReadString('\n')
		if err == io.EOF {
			fmt.Fprintln(stdout)
			return nil
		} else if err != nil {
			return err
		}
		if input = strings.TrimSpace(input); input == "" {
			return nil
		} else if v, err := strconv.Atoi(input); err != nil {
			fmt.Fprintln(stdout, "Invalid input")
		} else if v < 1 || v > len(infos) {
			fmt.Fprintf(stdout, "Selection not in range 1-%d\n", len(infos))
		} else {
			keep = v - 1
			break
		}
	}
	for i, info := range infos {
		if i == keep {
			continue
		}
		if err := moveFileWithLoggingDB(info, srcDir, dstDir, stdout, db); err != nil {
			fmt.Fprintf(stdout, "移动文件出错： %v\n", err)
		}
	}
	return nil
}

// dryRun makes moves and database deletions no-ops that only print what would
// happen. Set from the -dry-run flag.
var dryRun bool

func moveFileWithLoggingDB(info *fileInfo, srcDir, dstDir string, writer io.Writer, db *audioDB) error {
	// 试运行：只打印计划，不动文件、不改库，方便先看看会不会误移。
	if dryRun {
		fmt.Fprintf(writer, "[试运行] 将移动 %v -> %v\n", info.fullPath(), filepath.Join(dstDir, filepath.Base(info.path)))
		return nil
	}

	// 移动文件
	srcPath := info.fullPath()
	var dstPath string
	var err error
	if filepath.IsAbs(dstDir) {
		dstPath = filepath.Join(dstDir, filepath.Base(info.path))
	} else {
		dstPath, err = filepath.Abs(filepath.Join(dstDir, filepath.Base(info.path)))
		if err != nil {
			fmt.Fprintln(writer, "转换失败:", err)
			return err
		}
	}

	// Check if source file exists before attempting to move
	if _, err := os.Stat(srcPath); os.IsNotExist(err) {
		fmt.Fprintf(writer, "File %v does not exist, skipping\n", srcPath)
		return nil
	} else if err != nil {
		fmt.Fprintf(writer, "Error checking %v: %v\n", srcPath, err)
		return err
	}

	// If destination file exists, auto-rename by appending (1), (2), etc.
	basePath := dstPath
	counter := 1
	for {
		if _, err := os.Stat(basePath); err != nil {
			// Path doesn't exist, use it
			dstPath = basePath
			break
		}
		// Path exists, generate new name with counter
		ext := filepath.Ext(basePath)
		nameWithoutExt := basePath[:len(basePath)-len(ext)]
		basePath = fmt.Sprintf("%s(%d)%s", nameWithoutExt, counter, ext)
		counter++
	}

	// Create destination directory if needed
	if err := os.MkdirAll(filepath.Dir(dstPath), 0755); err != nil {
		return err
	}

	fmt.Fprintf(writer, "Moving %v -> %v\n", srcPath, dstPath)

	// Move the file
	if err := moveFile(srcPath, dstPath); err != nil {
		return err
	}

	// 先移成功再删记录：反过来的话，移动失败会让文件从库里消失，
	// 下次只能重算指纹，还可能因为「库里没有」被当成新文件。
	// Only delete from database if the file has a valid positive ID
	// Temporary files have negative IDs and are not stored in the database
	if db != nil && info.id > 0 {
		fmt.Fprintf(writer, "从数据库中删除记录: id: %v, path: %v\n", info.id, info.fullPath())
		if err := db.deleteByID(info.id); err != nil {
			fmt.Fprintf(writer, "WARNING: 文件已移走但库记录未删除（id %d）：%v\n", info.id, err)
		}
	}

	return nil
}

// moveSmaller keeps the largest file from infos and moves the other files from srcDir to dstDir.
// If db is provided, it also removes moved files from the database.
func moveSmaller(stdout io.Writer, infos []*fileInfo, srcDir, dstDir string, db *audioDB) error {
	sort.Slice(infos, func(i, j int) bool { return infos[i].size > infos[j].size })
	for _, ln := range formatFiles(infos, "") {
		fmt.Fprintln(stdout, ln)
	}
	for _, info := range infos[1:] {
		if err := moveFileWithLoggingDB(info, srcDir, dstDir, stdout, db); err != nil {
			return err
		}
	}

	return nil
}

// moveFile renames srcPath to dstPath, creating the destination directory if needed.
//
// 目标已存在或与源相同都视为错误：前者会悄悄覆盖另一个文件，后者是空操作却看起来
// 「成功了」。调用方（moveInteractive / moveSmaller）会先挑一个没被占用的文件名，
// 所以正常路径不会撞上这两条。
func moveFile(srcPath, dstPath string) error {
	if same, err := sameFile(srcPath, dstPath); err != nil {
		return err
	} else if same {
		return fmt.Errorf("source and destination are the same file: %v", srcPath)
	}
	if _, err := os.Lstat(dstPath); err == nil {
		return fmt.Errorf("destination already exists: %v", dstPath)
	} else if !os.IsNotExist(err) {
		return err
	}
	if err := os.Rename(srcPath, dstPath); err == nil {
		return nil
	}
	// If the rename failed, maybe the paths were on different partitions.
	// Try copying and unlinking instead.
	return copyAndRemoveFile(srcPath, dstPath)
}

// sameFile reports whether both paths point at the same file.
func sameFile(a, b string) (bool, error) {
	fa, err := os.Stat(a)
	if err != nil {
		return false, err
	}
	fb, err := os.Stat(b)
	if err != nil {
		if os.IsNotExist(err) {
			return false, nil
		}
		return false, err
	}
	return os.SameFile(fa, fb), nil
}

// copyAndRemoveFile copies srcPath to dstPath and unlinks srcPath.
// This function is separate from moveFile so it can be exercised by tests.
func copyAndRemoveFile(srcPath, dstPath string) error {
	// 与 moveFile 保持同一套约束：不覆盖已有文件、不把文件「复制到自己身上」。
	if same, err := sameFile(srcPath, dstPath); err != nil {
		return err
	} else if same {
		return fmt.Errorf("source and destination are the same file: %v", srcPath)
	}
	if _, err := os.Lstat(dstPath); err == nil {
		return fmt.Errorf("destination already exists: %v", dstPath)
	} else if !os.IsNotExist(err) {
		return err
	}

	sf, err := os.Open(srcPath)
	if err != nil {
		return err
	}

	// 跨分区兜底时目标目录可能还不存在（os.Rename 失败前没人建过它）。
	if err := os.MkdirAll(filepath.Dir(dstPath), 0755); err != nil {
		sf.Close()
		return err
	}

	df, err := os.Create(dstPath)
	if err != nil {
		sf.Close()
		return err
	}
	if _, err := io.Copy(df, sf); err != nil {
		df.Close()
		sf.Close()
		return err
	}
	if err := df.Close(); err != nil {
		sf.Close()
		return err
	}
	// Windows 上必须先关掉源文件句柄再删，否则（跨盘时 os.Rename 已经失败）
	// 会得到「另一个程序正在使用此文件」，复制过去的副本留下、原件删不掉。
	if err := sf.Close(); err != nil {
		return err
	}
	return os.Remove(srcPath)
}
