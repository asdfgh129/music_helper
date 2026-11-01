// Copyright 2022 Daniel Erat.
// All rights reserved.

package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"runtime"
	"strconv"
	"strings"
)

// fpcalcSettings contains command-line settings for the fpcalc utility.
type fpcalcSettings struct {
	length    float64 // "-length SECS   Restrict the duration of the processed input audio (default 120)"
	chunk     float64 // "-chunk SECS    Split the input audio into chunks of this duration"
	algorithm int     // "-algorithm NUM Set the algorithm method (default 2)"
	overlap   bool    // "-overlap       Overlap the chunks slightly to make sure audio on the edges is fingerprinted"
}

func defaultFpcalcSettings() *fpcalcSettings {
	return &fpcalcSettings{
		length:    120,
		chunk:     0,
		algorithm: 2,
		overlap:   false,
	}
}

func (s *fpcalcSettings) String() string {
	return fmt.Sprintf("length=%0.3f,chunk=%0.3f,algorithm=%d,overlap=%v",
		s.length, s.chunk, s.algorithm, s.overlap)
}

// fpcalcExe returns the name of the fpcalc executable.
func fpcalcExe() string {
	// This (hopefully) mitigates the dumb "BatBadBut" command injection vulnerability on Windows,
	// where CreateProcess() implicitly spawns cmd.exe for batch files, resulting in different
	// argument-escaping rules being used. Include the extension so a batch file won't be executed.
	// This probably doesn't matter in practice, but whatever.
	if runtime.GOOS == "windows" {
		return "fpcalc.exe"
	}
	return "fpcalc"
}

// haveFpcalc returns false if fpcalc isn't in $PATH.
func haveFpcalc() bool {
	_, err := exec.LookPath(fpcalcExe())
	if err != nil {
		fmt.Fprintln(os.Stderr, "Failed looking up fpcalc:", err)
	}
	return err == nil
}

// getFpcalcVersion returns a string describing the installed version of fpcalc.
func getFpcalcVersion() (string, error) {
	if !haveFpcalc() {
		return "", errors.New("fpcalc executable not found")
	}
	var stderr bytes.Buffer
	cmd := exec.Command(fpcalcExe(), "-version")
	cmd.Stderr = &stderr
	out, err := cmd.Output()
	if err != nil {
		return "", fmt.Errorf("%v (%q)", err, strings.Split(stderr.String(), "\n")[0])
	}
	return strings.TrimSpace(string(out)), nil
}

// fpcalcResult contains the result of running fpcalc against a file.
type fpcalcResult struct {
	Fingerprint          []uint32 `json:"fingerprint"`       // Raw fingerprint (uint32 array)
	CompressedFingerprint string   `json:"fingerprint_string"` // Compressed fingerprint (base64 string)
	Duration             float64  `json:"duration"`
}

var (
	// emptyFingerprintError is returned by runFpcalc when an audio file is too short
	// to be fingerprinted.
	errEmptyFingerprint = errors.New("empty fingerprint")
	// errDecodeEOF is returned by runFpcalc when EOF is encountered while decoding a frame.
	// This also seems to happen for short files, e.g. 64 KB or smaller.
	errDecodeEOF = errors.New("EOF while decoding frame")
)

// runFpcalc runs fpcalc to compute a fingerprint for path per settings.
func runFpcalc(path string, settings *fpcalcSettings) (*fpcalcResult, error) {
	// First, get the raw fingerprint (uint32 array)
	rawArgs := []string{
		"-raw",
		"-json",
		"-length", strconv.FormatFloat(settings.length, 'f', 3, 64),
		"-algorithm", strconv.Itoa(settings.algorithm),
	}
	if settings.chunk > 0 {
		rawArgs = append(rawArgs, "-chunk", strconv.FormatFloat(settings.chunk, 'f', 3, 64))
	}
	if settings.overlap {
		rawArgs = append(rawArgs, "-overlap")
	}
	rawArgs = append(rawArgs, path)

	rawOut, err := exec.Command(fpcalcExe(), rawArgs...).Output()
	exitErr, _ := err.(*exec.ExitError)
	if exitErr != nil && exitErr.ExitCode() == 3 {
		// fpcalc exits with 3 when it encounters an error but can still generate a fingerprint:
		// https://github.com/acoustid/chromaprint/issues/137#issuecomment-2049126005
		// https://github.com/acoustid/chromaprint/blob/aa67c95b9e486884a6d3ee8b0c91207d8c2b0551/src/cmd/fpcalc.cpp#L405
		// This seems to happen frequently in fpcalc 1.5.1 if a too-long -length is passed:
		//  ERROR: Error decoding audio frame (End of file)
		err = nil
		exitErr = nil
	}
	if err != nil {
		// Try to get some additional info from stderr.
		if exitErr != nil {
			if stderr := strings.SplitN(string(exitErr.Stderr), "\n", 2)[0]; stderr != "" {
				if ln := strings.TrimSpace(stderr); ln == "ERROR: Empty fingerprint" {
					err = errEmptyFingerprint
				} else if ln == "ERROR: Error decoding audio frame (End of file)" {
					err = errDecodeEOF
				} else {
					err = fmt.Errorf("%v (%v)", err, stderr)
				}
			}
		}
		return nil, err
	}

	var rawRes fpcalcResult
	if err := json.Unmarshal(rawOut, &rawRes); err != nil {
		return nil, err
	}

	// Second, get the compressed fingerprint (base64 string)
	compArgs := []string{
		"-json", // No -raw flag for compressed format
		"-length", strconv.FormatFloat(settings.length, 'f', 3, 64),
		"-algorithm", strconv.Itoa(settings.algorithm),
	}
	if settings.chunk > 0 {
		compArgs = append(compArgs, "-chunk", strconv.FormatFloat(settings.chunk, 'f', 3, 64))
	}
	if settings.overlap {
		compArgs = append(compArgs, "-overlap")
	}
	compArgs = append(compArgs, path)

	compOut, compErr := exec.Command(fpcalcExe(), compArgs...).Output()
	if compErr != nil {
		// If we fail to get compressed fingerprint, we can still return the raw one
		fmt.Fprintf(os.Stderr, "Warning: failed to get compressed fingerprint: %v\n", compErr)
		return &rawRes, nil
	}

	var compRes struct {
		Fingerprint string `json:"fingerprint"`
		Duration    float64  `json:"duration"`
	}
	if err := json.Unmarshal(compOut, &compRes); err != nil {
		fmt.Fprintf(os.Stderr, "Warning: failed to parse compressed fingerprint: %v\n", err)
		return &rawRes, nil
	}

	// Combine both formats
	rawRes.CompressedFingerprint = compRes.Fingerprint
	return &rawRes, nil
}
