// Copyright 2022 Daniel Erat.
// All rights reserved.

package main

import (
	"flag"
	"fmt"
	"io"
	"math/bits"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"time"
)

var buildVersion = "[non-release]" // injected by create_release.sh

// teeWriter writes to both stdout and a log file.
type teeWriter struct {
	stdout io.Writer
	log    io.Writer
}

func (t *teeWriter) Write(p []byte) (n int, err error) {
	// Write to log first
	if _, err := t.log.Write(p); err != nil {
		return 0, err
	}
	// Then write to stdout
	return t.stdout.Write(p)
}

// createLogFile creates a log file with timestamp in the current directory.
func createLogFile() (*os.File, error) {
	timestamp := time.Now().Format("20060102_150405")
	logName := fmt.Sprintf("SoundAlike-%s.log", timestamp)
	logFile, err := os.Create(logName)
	if err != nil {
		return nil, fmt.Errorf("failed to create log file %q: %w", logName, err)
	}
	return logFile, nil
}

// globalLogWriter is the global writer that writes to both stdout and log file
var globalLogWriter io.Writer = os.Stdout

// globalLogFile keeps track of the log file for cleanup
var globalLogFile *os.File

// initGlobalLogging initializes the global log writer.
// Always creates a log file to record all output.
func initGlobalLogging() (func(), error) {
	file, err := createLogFile()
	if err != nil {
		return nil, err
	}
	globalLogFile = file

	// Create tee writer
	tee := &teeWriter{stdout: os.Stdout, log: file}
	globalLogWriter = tee

	// Return cleanup function
	return func() {
		if globalLogFile != nil {
			fmt.Fprintf(globalLogWriter, "\nLog saved to: %s\n", globalLogFile.Name())
			globalLogFile.Close()
		}
	}, nil
}

func main() {
	fps := defaultFpcalcSettings()
	opts := defaultScanOptions()

	flag.Usage = func() {
		fmt.Fprintln(flag.CommandLine.Output(), "Usage: soundalike [flag]... <DIR>...")
		fmt.Fprintln(flag.CommandLine.Output(), "Find duplicate audio files within one or more directories.")
		fmt.Fprintln(flag.CommandLine.Output())
		flag.PrintDefaults()
	}
	compare := flag.Bool("compare", false, `Compare two files given via positional args instead of scanning`+
		"\n(increases -fpcalc-length by default)")
	compareInterval := flag.Int("compare-interval", 0, `Score interval for -compare (0 to print overall score)`)
	dbPath := flag.String("db", "music.db", `SQLite database file for storing file info (temp file if unset)`)
	exclude := flag.Bool("exclude", false, `Update database to exclude files in positional args from being grouped together`)
	flag.StringVar(&opts.fileString, "file-regexp", opts.fileString, "Regular expression for audio files")
	flag.IntVar(&fps.algorithm, "fpcalc-algorithm", fps.algorithm, `Fingerprint algorithm`)
	flag.Float64Var(&fps.chunk, "fpcalc-chunk", fps.chunk, `Audio chunk duration in seconds`)
	flag.Float64Var(&fps.length, "fpcalc-length", fps.length, `Max audio duration in seconds to process`)
	flag.BoolVar(&fps.overlap, "fpcalc-overlap", fps.overlap, `Overlap audio chunks in fingerprints`)
	flag.BoolVar(&opts.ignoreMtimes, "ignore-mtimes", opts.ignoreMtimes, `Ignore file modification times when scanning`)
	flag.IntVar(&opts.logSec, "log-sec", opts.logSec, `Logging frequency in seconds (0 or negative to disable logging)`)
	flag.Float64Var(&opts.lookupThresh, "lookup-threshold", opts.lookupThresh, `Threshold for lookup table in (0.0, 1.0]`)
	flag.Float64Var(&opts.matchThresh, "match-threshold", opts.matchThresh, `Threshold for bitwise comparisons in (0.0, 1.0]`)
	flag.BoolVar(&opts.matchMinLength, "match-min-length", opts.matchMinLength,
		`Use shorter fingerprint length when scoring bitwise comparisons`)
	moveInteractiveDir := flag.String("move-interactive", "", `Directory to which worse-quality duplicate files are moved`+
		"\n(moved without prompting when quality differs; asked only when indistinguishable)")
	moveSmallerDir := flag.String("move-smaller", "", `Directory to which smaller duplicate files will be automatically moved`)
	printFileInfo := flag.Bool("print-file-info", true, `Print file sizes and durations`)
	printFullPaths := flag.Bool("print-full-paths", false, `Print absolute file paths (rather than relative to dir)`)
	dryRunFlag := flag.Bool("dry-run", false, `Print what would be moved without moving or deleting anything`)
	debugMode := flag.Bool("debug", false, `Enable debug mode with verbose output`)
	flag.BoolVar(&opts.skipBadFiles, "skip-bad-files", opts.skipBadFiles, `Skip files that can't be fingerprinted by fpcalc`)
	var tempDirs []string
	flag.Func("temp", `Directories containing temp audio files to scan without saving to database`, func(val string) error {
		tempDirs = append(tempDirs, val)
		return nil
	})
	doCheckDB := flag.Bool("check", false, `Check database consistency with actual files (requires -db)`)
	printVersion := flag.Bool("version", false, `Print version and exit`)
	flag.Parse()
	os.Exit(func() int {
		if *printVersion {
			doVersion()
			return 0
		}

		// Initialize global logging first to capture all output
		cleanupLogging, err := initGlobalLogging()
		if err != nil {
			fmt.Fprintln(os.Stderr, "Failed initializing logging:", err)
			return 1
		}
		defer cleanupLogging()

		// Enable debug mode
		if *debugMode {
			opts.debugMode = true
			if opts.logSec <= 0 {
				opts.logSec = 1 // Default to 1 second logging interval in debug mode
			}
			fmt.Fprintln(globalLogWriter, "Debug mode enabled")
		}

		// Perform some initial checks before creating the database file.
		if *compare {
			if flag.NArg() != 2 {
				flag.Usage()
				return 2
			}
		} else if *exclude {
			if flag.NArg() < 2 {
				flag.Usage()
				return 2
			}
			if *dbPath == "" {
				fmt.Fprintln(os.Stderr, "-exclude requires -db")
				return 2
			}
		} else {
			if flag.NArg() < 1 {
				flag.Usage()
				return 2
			}
			opts.dirs = flag.Args()
		}
		dryRun = *dryRunFlag
		if err := opts.finish(); err != nil {
			fmt.Fprintln(globalLogWriter, err)
			return 2
		}

		// Handle temp directory parameters
		opts.tempDirs = append(opts.tempDirs, tempDirs...)

		// Handle check parameter
		if *doCheckDB {
			if *dbPath == "" {
				fmt.Fprintln(globalLogWriter, "-check requires -db parameter")
				return 2
			}
		}

		if !haveFpcalc() {
			advice := "install from https://github.com/acoustid/chromaprint/releases"
			if _, err := exec.LookPath("apt"); err == nil {
				advice = "apt install libchromaprint-tools"
			}
			fmt.Fprintf(os.Stderr, "fpcalc not in path (%v)\n", advice)
			return 1
		}

		if *compare {
			// If -fpcalc-length wasn't specified, make it default to a larger
			// value so we'll fingerprint the files in their entirety.
			if !flagWasSet("fpcalc-length") {
				fps.length = 7200
			}
			return doCompare(flag.Arg(0), flag.Arg(1), opts, fps, *compareInterval)
		}

		if *moveSmallerDir != "" && *moveInteractiveDir != "" {
			fmt.Fprintln(globalLogWriter, "-move-interactive and -move-smaller can't both be supplied")
			return 2
		}

		// Check that move directories don't conflict with other directories
		moveDir := ""
		if *moveSmallerDir != "" {
			moveDir = *moveSmallerDir
		} else if *moveInteractiveDir != "" {
			moveDir = *moveInteractiveDir
		}

		if moveDir != "" {
			// Get absolute path for move directory
			moveAbs, err := filepath.Abs(moveDir)
			if err != nil {
				fmt.Fprintln(os.Stderr, "Failed to get absolute path for move directory:", err)
				return 2
			}

			// Check against temp directories
			for _, tempDir := range tempDirs {
				tempAbs, err := filepath.Abs(tempDir)
				if err != nil {
					fmt.Fprintln(os.Stderr, "Failed to get absolute path for temp directory:", err)
					return 2
				}
				if moveAbs == tempAbs {
					fmt.Fprintf(globalLogWriter, "Error: -move-interactive directory cannot be the same as -temp directory: %v\n", moveDir)
					return 2
				}
			}

			// Check against music directories
			for _, musicDir := range opts.dirs {
				musicAbs, err := filepath.Abs(musicDir)
				if err != nil {
					fmt.Fprintln(os.Stderr, "Failed to get absolute path for music directory:", err)
					return 2
				}
				if moveAbs == musicAbs {
					fmt.Fprintf(globalLogWriter, "Error: -move-interactive directory cannot be the same as music directory: %v\n", moveDir)
					return 2
				}
			}
		}

		if *dbPath == "" && *doCheckDB {
			fmt.Fprintln(globalLogWriter, "-check requires -db parameter")
			return 2
		}

		if *dbPath == "" {
			f, err := os.CreateTemp("", "soundalike.db.*")
			if err != nil {
				fmt.Fprintln(os.Stderr, "Failed creating temp file for database:", err)
				return 1
			}
			f.Close()
			*dbPath = f.Name()
			defer os.Remove(*dbPath)
		}
		// Always use directory-based storage
		db, err := newAudioDB(*dbPath, fps, 0)
		if err != nil {
			fmt.Fprintln(os.Stderr, "Failed opening database:", err)
			return 1
		}
		defer func() {
			if err := db.close(); err != nil {
				fmt.Fprintln(os.Stderr, "Failed closing database:", err)
			}
		}()

		if *exclude {
			// Save all possible pairs within the group.
			for i := 0; i < flag.NArg()-1; i++ {
				for j := i + 1; j < flag.NArg(); j++ {
					if err := db.saveExcludedPair(flag.Arg(i), flag.Arg(j)); err != nil {
						fmt.Fprintln(os.Stderr, "Failed saving excluded pair:", err)
						return 1
					}
				}
			}
			return 0
		}

		// Perform database check if requested
		if *doCheckDB {
			if err := checkDB(opts, db, fps, globalLogWriter); err != nil {
				fmt.Fprintln(globalLogWriter, "Database check failed:", err)
				return 1
			}
		}

		groups, err := scanFiles(opts, db, fps, globalLogWriter)
		if err != nil {
			fmt.Fprintln(globalLogWriter, "Failed scanning files:", err)
			return 1
		}

		var pre string
		if *printFullPaths {
			pre = opts.dirs[0]
		}
		for i, infos := range groups {
			// Print a blank line to separate groups or to separate the interactive prompt from
			// log messages printed while scanning.
			if i != 0 || (*moveInteractiveDir != "" && opts.logSec > 0) {
				fmt.Fprintln(globalLogWriter)
			}
			switch {
			case *moveInteractiveDir != "":
				if err := moveInteractive(globalLogWriter, os.Stdin, infos, opts.dirs[0], *moveInteractiveDir, db); err != nil {
					fmt.Fprintln(globalLogWriter, "Failed moving:", err)
					return 1
				}
			case *moveSmallerDir != "":
				if err := moveSmaller(globalLogWriter, infos, opts.dirs[0], *moveSmallerDir, db); err != nil {
					fmt.Fprintln(globalLogWriter, "Failed moving:", err)
					return 1
				}
			case *printFileInfo:
				for _, ln := range formatFiles(infos, pre) {
					fmt.Fprintln(globalLogWriter, ln)
				}
			default:
				for _, info := range infos {
					fmt.Fprintln(globalLogWriter, filepath.Join(pre, info.fullPath()))
				}
			}
		}

		return 0
	}())
}

// flagWasSet returns true if the specified flag was passed on the command line.
func flagWasSet(name string) bool {
	var found bool
	flag.Visit(func(f *flag.Flag) {
		if f.Name == name {
			found = true
		}
	})
	return found
}

// doVersion prints the soundalike and fpcalc versions to stdout.
func doVersion() {
	fmt.Printf("soundalike version %v compiled with %v for %v/%v\n",
		buildVersion, runtime.Version(), runtime.GOOS, runtime.GOARCH)
	if ver, err := getFpcalcVersion(); err != nil {
		fmt.Printf("Failed getting fpcalc version: %v\n", err)
	} else {
		fmt.Println(ver)
	}
}

// doCompare compares the files at pa and pb on behalf of the -compare flag.
func doCompare(pa, pb string, opts *scanOptions, fps *fpcalcSettings, interval int) int {
	ra, err := runFpcalc(pa, fps)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed fingerprinting %v: %v\n", pa, err)
		return 1
	}
	rb, err := runFpcalc(pb, fps)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed fingerprinting %v: %v\n", pb, err)
		return 1
	}
	score, aoff, boff := compareFingerprints(ra.Fingerprint, rb.Fingerprint, opts.matchMinLength)
	if interval <= 0 {
		fmt.Printf("%0.3f\n", score)
	} else {
		if aoff > boff {
			fmt.Printf("[%d only in b]\n", aoff-boff)
		} else if boff > aoff {
			fmt.Printf("[%d only in a]\n", boff-aoff)
		}
		a := ra.Fingerprint[aoff:]
		b := rb.Fingerprint[boff:]
		var i, ncmp, nbits int
		for ; i < len(a) && i < len(b); i++ {
			if i%interval == 0 && ncmp > 0 {
				fmt.Printf("%4d: %0.3f\n", i, float64(nbits)/float64(32*ncmp))
				nbits = 0
				ncmp = 0
			}
			nbits += 32 - bits.OnesCount32(a[i]^b[i])
			ncmp++
		}
		if ncmp > 0 {
			fmt.Printf("%4d: %0.3f\n", i, float64(nbits)/float64(32*ncmp))
		}
		if na, nb := len(a), len(b); na > nb {
			fmt.Printf("[%d only in a]\n", na-nb)
		} else if nb > na {
			fmt.Printf("[%d only in b]\n", nb-na)
		}
	}
	return 0
}

// formatFiles returns column-aligned lines describing each supplied file.
func formatFiles(infos []*fileInfo, pathPrefix string) []string {
	if len(infos) == 0 {
		return nil
	}

	var rows [][]string
	lens := make([]int, 3)
	for _, info := range infos {
		row := []string{
			filepath.Join(pathPrefix, info.fullPath()),
			strconv.FormatFloat(float64(info.size)/(1024*1024), 'f', 2, 64),
			strconv.FormatFloat(info.duration, 'f', 2, 64),
		}
		rows = append(rows, row)
		for i, max := range lens {
			if ln := len(row[i]); ln > max {
				lens[i] = ln
			}
		}
	}
	lines := make([]string, len(rows))
	fs := strings.Join([]string{
		"%" + strconv.Itoa(-lens[0]) + "s",    // path
		"%" + strconv.Itoa(lens[1]) + "s MB",  // size
		"%" + strconv.Itoa(lens[2]) + "s sec", // duration
	}, "  ")
	for i, row := range rows {
		lines[i] = fmt.Sprintf(fs, row[0], row[1], row[2])
	}
	return lines
}
