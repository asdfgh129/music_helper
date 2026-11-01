# AGENTS.md - Coding Guidelines for soundalike

## Project Overview

Go 1.21 CLI application that finds duplicate audio files by comparing acoustic fingerprints using Chromaprint's `fpcalc` utility. Flat project structure with all source files in the root directory. Single `main` package (no exported types).

## Build Commands

**Build:**
```bash
go build                    # Build executable
go install ./...            # Install to GOPATH
```

**Test:**
```bash
go test -v ./...            # Run all tests
go test -v -run TestNewAudioDB ./...      # Run specific test
go test -v ./db_test.go     # Run tests in specific file
```

**Formatting:**
```bash
gofmt -w .                 # Format all Go files
```

**Cross-platform Release:**
```bash
./build/create_release.sh <os> <arch> <version>  # e.g. linux amd64 v1.0.0
```

## External Dependencies

- **Required:** `fpcalc` utility from Chromaprint must be in PATH (install from https://github.com/acoustid/chromaprint/releases)
- **CGO:** Required for SQLite3 support (github.com/mattn/go-sqlite3)

## Code Style Guidelines

### Imports

```go
import (
	"flag"
	"fmt"
	"os"           // stdlib first, alphabetized
	"path/filepath"
	"strconv"

	_ "github.com/mattn/go-sqlite3"  // third-party on separate line
	"github.com/google/go-cmp/cmp"
)
```

### Naming Conventions

- **Functions:** camelCase (`scanFiles`, `runFpcalc`, `newAudioDB`)
- **Variables:** camelCase (`globalLogWriter`, `scanOptions`)
- **Types:** camelCase for package-private (`fileInfo`, `audioDB`, `fpcalcSettings`)
- **Constants:** lowercase camelCase (`useAbsPaths`, `useRelPaths`, `ignoreDecodeEOFMaxBytes`)
- **Files:** lowercase, descriptive (`main.go`, `scan.go`, `db.go`)
- **Tests:** `<source>_test.go` pattern (`db_test.go`, `scan_test.go`)

### Type Definitions

Use custom types for domain-specific concepts:

```go
type fileID int32                    // Type alias for semantic meaning
type audioDBFlag uint8               // Bit flag type

const (
	useAbsPaths audioDBFlag = 1 << iota
	useRelPaths
)
```

### Error Handling

- Always return `error` as last return value
- Use `fmt.Errorf` with `%w` for error wrapping (Go 1.13+)
- Check errors immediately after calls

```go
func scanFiles(opts *scanOptions, db *audioDB) ([][]*fileInfo, error) {
	if err := opts.finish(); err != nil {
		return nil, fmt.Errorf("invalid options: %w", err)
	}
	// ...
	return groups, nil
}
```

Define sentinel errors for expected cases:
```go
var (
	errEmptyFingerprint = errors.New("empty fingerprint")
	errDecodeEOF       = errors.New("EOF while decoding frame")
)
```

### Comments & Documentation

**File header:**
```go
// Copyright 2022 Daniel Erat.
// All rights reserved.

package main
```

**Function documentation:**
```go
// scanFiles scans opts.dirs and returns groups of similar files.
func scanFiles(opts *scanOptions, db *audioDB) ([][]*fileInfo, error)
```

**Inline comments:** Explain "why" not "what", use for non-obvious logic only.

### Formatting

- Use `gofmt` (standard Go formatter)
- Indentation: tabs
- Line length: typically < 100-120 characters
- Brace style: opening on same line, closing on new line
- One blank line between functions

### Struct Definitions

```go
type scanOptions struct {
	dirs           []string       // directories containing audio files
	fileRegexp     *regexp.Regexp // matches files to scan
	lookupThresh   float64        // threshold for lookup table
}
```

### Testing Pattern

Tests require `soundalike` executable in PATH and `testdata/` directory (from https://codeberg.org/derat/soundalike-testdata).

```go
func TestNewAudioDB(t *testing.T) {
	p := filepath.Join(t.TempDir(), "test.db")
	if db, err := newAudioDB(p, settings, useRelPaths); err != nil {
		t.Fatal("newAudioDB failed: ", err)
	}
	// ...
}
```

Integration tests use `exec.Command` to run the built binary.

## File Structure

```
soundalike/
├── main.go          # Entry point, CLI flags, orchestration
├── scan.go          # Core scanning and duplicate detection algorithm
├── db.go            # SQLite database operations for fingerprint caching
├── fpcalc.go        # Wrapper for external fpcalc utility
├── lookup.go        # Lookup table implementation
├── move.go          # File movement operations
├── *_test.go        # Unit tests for each module
├── build/           # Release scripts and CI configuration
├── go.mod           # Module definition
└── go.sum           # Dependency checksums
```

## Key Patterns

**Constructor pattern:** `newX()` for type initialization
```go
func newAudioDB(path string, settings *fpcalcSettings, flags audioDBFlag) (*audioDB, error)
```

**Default options pattern:**
```go
func defaultScanOptions() *scanOptions {
	return &scanOptions{
		lookupThresh: 0.25,
		matchThresh:  0.95,
	}
}
```

**Defer for cleanup:**
```go
defer func() {
	if err := db.close(); err != nil {
		fmt.Fprintln(os.Stderr, "Failed closing database:", err)
	}
}()
```

## Performance Notes

- Database caching via `-db` flag recommended for large collections
- Memory usage grows with file count and fingerprint length
- Default `-fpcalc-length=120` (MusicBrainz standard) can be increased for accuracy at performance cost
