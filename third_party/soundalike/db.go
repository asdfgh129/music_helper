// Copyright 2022 Daniel Erat.
// All rights reserved.

package main

import (
	"bytes"
	"database/sql"
	"encoding/binary"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

var dbByteOrder = binary.LittleEndian

// audioDB holds previously-computed audio fingerprints.
type audioDB struct {
	db       *sql.DB
	absPaths bool // deprecated: kept for backward compatibility
}

// audioDBFlag values can be passed to newAudioDB to configure its behavior.
type audioDBFlag uint8

const (
	useAbsPaths audioDBFlag = 1 << iota
	useRelPaths
)

// newAudioDB opens or creates a audioDB at path with the supplied settings.
// An error is returned if an existing database was created with different settings.
// The caller must check that paths that are passed later are appropriate for the passed flags.
func newAudioDB(path string, settings *fpcalcSettings, flags audioDBFlag) (*audioDB, error) {
	/*if (flags&useAbsPaths != 0) && (flags&useRelPaths != 0) {
		return nil, errors.New("can't use both absolute and relative paths")
	}*/
	if _, err := os.Stat(path); err != nil && !os.IsNotExist(err) {
		return nil, err
	}
	db, err := sql.Open(dbDriverName, path)
	if err != nil {
		return nil, err
	}
	defer func() {
		if db != nil {
			db.Close()
		}
	}()

	// Initialize or upgrade the schema.
	if err := initSchema(db); err != nil {
		return nil, err
	}

	// Check that the database wasn't created with different settings from what we're using now.
	var dbSettings string
	if err := db.QueryRow(`SELECT Desc FROM Settings`).Scan(&dbSettings); err == nil {
		if s := settings.String(); dbSettings != s {
			return nil, fmt.Errorf("database settings (%v) don't match current settings (%v)", dbSettings, s)
		}
	} else if err == sql.ErrNoRows {
		if _, err := db.Exec(`INSERT INTO Settings (Desc) VALUES(?)`, settings.String()); err != nil {
			return nil, err
		}
	} else {
		return nil, err
	}

	adb := &audioDB{db: db}

	// 不再需要判断路径类型
	/*var existingPath string
	if err := db.QueryRow(`SELECT Path FROM Files LIMIT 1`).Scan(&existingPath); err == nil {
		adb.absPaths = filepath.IsAbs(existingPath)
		if (flags&useAbsPaths != 0) && !adb.absPaths {
			return nil, errors.New("database already contains relative paths")
		} else if (flags&useRelPaths != 0) && adb.absPaths {
			return nil, errors.New("database already contains absolute paths")
		}
	} else if err == sql.ErrNoRows {
		switch {
		case flags&useAbsPaths != 0:
			adb.absPaths = true
		case flags&useRelPaths != 0:
			adb.absPaths = false
		default:
			return nil, errors.New("path type unspecified for empty database")
		}
	} else {
		return nil, err
	} */

	db = nil // disarm Close() call
	return adb, nil
}

// initSchema ensures that db contains the latest version of the database schema.
func initSchema(db *sql.DB) error {
	var upgraded bool
	tx, err := db.Begin()
	if err != nil {
		return err
	}
	err = func() error {
		var cnt int
		row := tx.QueryRow(`SELECT COUNT(*) FROM sqlite_master WHERE TYPE = 'table' AND NAME = 'Settings'`)
		if err := row.Scan(&cnt); err != nil {
			return err
		}
		if cnt == 0 {
			for _, s := range schemaInitStatements {
				if _, err := tx.Exec(cleanSQL(s)); err != nil {
					return err
				}
			}
		} else {
			var v int
			if err := tx.QueryRow(`PRAGMA user_version`).Scan(&v); err != nil {
				return err
			}
			if v > latestSchemaVersion {
				return fmt.Errorf("database has unknown schema version %v (latest is %v)", v, latestSchemaVersion)
			}
			for v = v + 1; v <= latestSchemaVersion; v++ {
				for _, s := range schemaUpgradeStatements[v] {
					if _, err := tx.Exec(cleanSQL(s)); err != nil {
						return err
					}
					upgraded = true
				}
				if v == 2 {
					if err := migrateToVersion2(tx); err != nil {
						return err
					}
				}
				if v == 3 {
					if err := migrateToVersion3(tx); err != nil {
						return err
					}
				}
			}
		}
		if _, err := tx.Exec(`PRAGMA user_version = ` + fmt.Sprint(latestSchemaVersion)); err != nil {
			return err
		}
		return nil
	}()

	if err != nil {
		tx.Rollback()
		return err
	}
	if err := tx.Commit(); err != nil {
		return err
	}

	if upgraded {
		if _, err := db.Exec(`VACUUM`); err != nil {
			return err
		}
	}

	return nil
}

// cleanSQL replaces all sequences of one or more tab characters with two spaces.
func cleanSQL(s string) string { return tabsRegexp.ReplaceAllString(s, "  ") }

var tabsRegexp = regexp.MustCompile(`\t+`)

type directoryID int32

func migrateToVersion2(tx *sql.Tx) error {
	rows, err := tx.Query(`SELECT Path, Duration, Size, ModTime, Fingerprint FROM FilesTmp`)
	if err != nil {
		return err
	}
	defer rows.Close()

	type oldFileInfo struct {
		path        string
		duration    float64
		size        int64
		mtime       int64
		fingerprint []byte
	}

	var oldFiles []oldFileInfo
	for rows.Next() {
		var f oldFileInfo
		if err := rows.Scan(&f.path, &f.duration, &f.size, &f.mtime, &f.fingerprint); err != nil {
			return err
		}
		oldFiles = append(oldFiles, f)
	}
	if err := rows.Err(); err != nil {
		return err
	}

	dirMap := make(map[string]directoryID)
	for _, f := range oldFiles {
		var dir string
		var relPath string

		if filepath.IsAbs(f.path) {
			dir = filepath.Dir(f.path)
			relPath = filepath.Base(f.path)
		} else {
			parts := strings.Split(filepath.ToSlash(f.path), "/")
			if len(parts) > 1 {
				dir = filepath.Join(parts[:len(parts)-1]...)
				relPath = parts[len(parts)-1]
			} else {
				dir = "."
				relPath = f.path
			}
		}

		var dirID directoryID
		if id, ok := dirMap[dir]; ok {
			dirID = id
		} else {
			var id64 int64
			err := tx.QueryRow(`INSERT INTO Directories (Path) VALUES(?) RETURNING DirectoryID`, dir).Scan(&id64)
			if err != nil {
				return err
			}
			dirID = directoryID(id64)
			dirMap[dir] = dirID
		}

		_, err := tx.Exec(
			`INSERT INTO Files (Path, DirectoryID, Duration, Size, ModTime, Fingerprint) VALUES(?, ?, ?, ?, ?, ?)`,
			relPath, dirID, f.duration, f.size, f.mtime, f.fingerprint,
		)
		if err != nil {
			return err
		}
	}

	_, err = tx.Exec(`DROP TABLE FilesTmp`)
	return err
}

func migrateToVersion3(tx *sql.Tx) error {
	// Version 3 adds CompressedFingerprint column.
	// For existing databases, we need to generate compressed fingerprints.
	// This is a migration that can be done later; for now we just add the column.
	// New files will have compressed fingerprints, existing files will get them
	// when they are rescanned.
	return nil
}

// schemaInitStatements contains statements that are executed to initialize an empty database
// to latestSchemaVersion.
var schemaInitStatements = []string{
	`CREATE TABLE Settings (
		Desc STRING PRIMARY KEY NOT NULL)`,
	`CREATE TABLE Directories (
		DirectoryID INTEGER PRIMARY KEY AUTOINCREMENT,
		Path STRING UNIQUE NOT NULL)`,
	`CREATE TABLE Files (
		Path STRING NOT NULL,
		DirectoryID INTEGER NOT NULL,
		Duration FLOAT NOT NULL,
		Size INTEGER NOT NULL,
		ModTime INTEGER NOT NULL,
		Fingerprint BLOB NOT NULL,
		CompressedFingerprint TEXT,
		PRIMARY KEY (DirectoryID, Path),
		FOREIGN KEY (DirectoryID) REFERENCES Directories(DirectoryID))`,
	`CREATE TABLE ExcludedPairs (
		PathA STRING NOT NULL,
		PathB STRING NOT NULL,
		PRIMARY KEY (PathA, PathB))`,
}

// schemaUpgradeStatements maps from a version number n to statements that are executed to upgrade
// an existing database from version n-1 to n.
var schemaUpgradeStatements = map[int][]string{
	1: { // add Files.ModTime column
		`ALTER TABLE Files RENAME TO FilesTmp`,
		`CREATE TABLE Files (
			Path STRING PRIMARY KEY NOT NULL,
			Duration FLOAT NOT NULL,
			Size INTEGER NOT NULL,
			ModTime INTEGER NOT NULL,
			Fingerprint BLOB NOT NULL)`,
		`INSERT INTO Files
			SELECT Path, Duration, Size, 0, Fingerprint
			FROM FilesTmp`,
		`DROP TABLE FilesTmp`,
	},
	2: { // add Directories table and update Files to use directory_id
		`CREATE TABLE Directories (
			DirectoryID INTEGER PRIMARY KEY AUTOINCREMENT,
			Path STRING UNIQUE NOT NULL)`,
		`ALTER TABLE Files RENAME TO FilesTmp`,
		`CREATE TABLE Files (
			Path STRING NOT NULL,
			DirectoryID INTEGER NOT NULL,
			Duration FLOAT NOT NULL,
			Size INTEGER NOT NULL,
			ModTime INTEGER NOT NULL,
			Fingerprint BLOB NOT NULL,
			PRIMARY KEY (DirectoryID, Path),
			FOREIGN KEY (DirectoryID) REFERENCES Directories(DirectoryID))`,
	},
	3: { // add Files.CompressedFingerprint column for chromaprint compressed format
		`ALTER TABLE Files ADD COLUMN CompressedFingerprint TEXT`,
	},
}

// latestSchemaVersion contains the latest schema version.
var latestSchemaVersion int

func init() {
	for v := range schemaUpgradeStatements {
		latestSchemaVersion = max(v, latestSchemaVersion)
	}
}

func (adb *audioDB) close() error { return adb.db.Close() }

func (adb *audioDB) getOrCreateDirectory(dirPath string) (directoryID, error) {
	var id64 int64
	err := adb.db.QueryRow(`SELECT DirectoryID FROM Directories WHERE Path = ?`, dirPath).Scan(&id64)
	if err == nil {
		return directoryID(id64), nil
	}
	if err != sql.ErrNoRows {
		return 0, err
	}

	err = adb.db.QueryRow(`INSERT INTO Directories (Path) VALUES(?) RETURNING DirectoryID`, dirPath).Scan(&id64)
	if err != nil {
		return 0, err
	}
	return directoryID(id64), nil
}

func (adb *audioDB) updateDirectoryPath(oldPath, newPath string) error {
	_, err := adb.db.Exec(`UPDATE Directories SET Path = ? WHERE Path = ?`, newPath, oldPath)
	return err
}

func (adb *audioDB) getAllDirectories() (map[directoryID]string, error) {
	rows, err := adb.db.Query(`SELECT DirectoryID, Path FROM Directories`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	dirs := make(map[directoryID]string)
	for rows.Next() {
		var id64 int64
		var path string
		if err := rows.Scan(&id64, &path); err != nil {
			return nil, err
		}
		dirs[directoryID(id64)] = path
	}
	return dirs, rows.Err()
}

// fileID uniquely identifies a file in audioDB.
type fileID int32

// fileInfo contains information about a file stored in audioDB.
type fileInfo struct {
	id                  fileID      // unique ID
	dirID               directoryID // directory ID
	dirPath             string      // directory path
	path                string      // relative path within directory
	size                int64       // bytes
	mtime               int64       // seconds since Unix epoch
	duration            float64     // seconds
	fprint              []uint32    // raw fingerprint (uint32 array)
	compressedFprint    string      // compressed fingerprint (chromaprint base64 string)
}

func (fi *fileInfo) fullPath() string {
	return filepath.Join(fi.dirPath, fi.path)
}

// get returns information about the file with the specified ID or dirPath+relPath.
// If the file is not present in the database, nil is returned.
func (adb *audioDB) get(id fileID, dirPath, relPath string) (*fileInfo, error) {
	var row *sql.Row
	if id > 0 {
		row = adb.db.QueryRow(`
			SELECT f.ROWID, f.DirectoryID, f.Path, f.Size, f.ModTime, f.Duration, f.Fingerprint, f.CompressedFingerprint, d.Path
			FROM Files f
			JOIN Directories d ON f.DirectoryID = d.DirectoryID
			WHERE f.ROWID = ?`, id)
	} else {
		row = adb.db.QueryRow(`
			SELECT f.ROWID, f.DirectoryID, f.Path, f.Size, f.ModTime, f.Duration, f.Fingerprint, f.CompressedFingerprint, d.Path
			FROM Files f
			JOIN Directories d ON f.DirectoryID = d.DirectoryID
			WHERE d.Path = ? AND f.Path = ?`, dirPath, relPath)
	}

	var b []byte
	var compressedFprint sql.NullString
	var info fileInfo
	var dirID64 int64
	if err := row.Scan(&info.id, &dirID64, &info.path, &info.size, &info.mtime, &info.duration, &b, &compressedFprint, &info.dirPath); err == sql.ErrNoRows {
		return nil, nil
	} else if err != nil {
		return nil, err
	}
	info.dirID = directoryID(dirID64)

	if compressedFprint.Valid {
		info.compressedFprint = compressedFprint.String
	}

	if len(b)%4 != 0 {
		return nil, fmt.Errorf("invalid fingerprint size %v", len(b))
	}
	info.fprint = make([]uint32, 0, len(b)/4)
	for i := 0; i < len(b); i += 4 {
		info.fprint = append(info.fprint, dbByteOrder.Uint32(b[i:i+4]))
	}
	return &info, nil
}

// save saves the supplied file information to the database.
// If the file already exists (based on dirID and path), it is updated.
func (adb *audioDB) save(info *fileInfo) (fileID, error) {
	if info.dirID == 0 {
		var err error
		info.dirID, err = adb.getOrCreateDirectory(info.dirPath)
		if err != nil {
			return 0, err
		}
	}

	var b bytes.Buffer
	if err := binary.Write(&b, dbByteOrder, info.fprint); err != nil {
		return 0, err
	}
	var id64 int64
	var compressedFprint interface{} = nil
	if info.compressedFprint != "" {
		compressedFprint = info.compressedFprint
	}
	if err := adb.db.QueryRow(
		`INSERT INTO Files (Path, DirectoryID, Size, ModTime, Duration, Fingerprint, CompressedFingerprint)
			VALUES(?, ?, ?, ?, ?, ?, ?)
			ON CONFLICT(DirectoryID, Path) DO UPDATE SET
				Size = excluded.Size,
				ModTime = excluded.ModTime,
				Duration = excluded.Duration,
				Fingerprint = excluded.Fingerprint,
				CompressedFingerprint = excluded.CompressedFingerprint
			RETURNING ROWID`,
		info.path, info.dirID, info.size, info.mtime, info.duration, b.Bytes(), compressedFprint).Scan(&id64); err != nil {
		return 0, err
	}
	if id64 <= 0 || id64 > math.MaxInt32 {
		return 0, fmt.Errorf("invalid id %v", id64)
	}
	return fileID(id64), nil
}

// delete removes the file with the specified dirPath and relPath from the database.
func (adb *audioDB) delete(dirPath, relPath string) error {
	_, err := adb.db.Exec(`
		DELETE FROM Files
		WHERE DirectoryID = (SELECT DirectoryID FROM Directories WHERE Path = ?)
		AND Path = ?`, dirPath, relPath)
	return err
}

// deleteByID removes the file with the specified ID from the database.
func (adb *audioDB) deleteByID(id fileID) error {
	_, err := adb.db.Exec(`DELETE FROM Files WHERE ROWID = ?`, id)
	return err
}

// getAllPaths returns all full file paths (dirPath + relPath) stored in the database.
func (adb *audioDB) getAllPaths() ([]string, error) {
	rows, err := adb.db.Query(`
		SELECT d.Path, f.Path
		FROM Files f
		JOIN Directories d ON f.DirectoryID = d.DirectoryID`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var paths []string
	for rows.Next() {
		var dirPath, relPath string
		if err := rows.Scan(&dirPath, &relPath); err != nil {
			return nil, err
		}
		paths = append(paths, filepath.Join(dirPath, relPath))
	}
	return paths, rows.Err()
}

// getAllFingerprints returns all file IDs and their fingerprints stored in the database.
func (adb *audioDB) getAllFingerprints() ([]fileID, [][]uint32, error) {
	rows, err := adb.db.Query(`
		SELECT f.ROWID, f.Fingerprint
		FROM Files f
		WHERE f.Fingerprint IS NOT NULL`)
	if err != nil {
		return nil, nil, err
	}
	defer rows.Close()

	var ids []fileID
	var fprints [][]uint32
	for rows.Next() {
		var id fileID
		var b []byte
		if err := rows.Scan(&id, &b); err != nil {
			return nil, nil, err
		}

		if len(b)%4 != 0 {
			return nil, nil, fmt.Errorf("invalid fingerprint size %v for file %v", len(b), id)
		}

		fprint := make([]uint32, 0, len(b)/4)
		for i := 0; i < len(b); i += 4 {
			fprint = append(fprint, dbByteOrder.Uint32(b[i:i+4]))
		}

		ids = append(ids, id)
		fprints = append(fprints, fprint)
	}
	return ids, fprints, rows.Err()
}

// saveExcludedPair records that the supplied full paths are not duplicates of each other.
func (adb *audioDB) saveExcludedPair(pa, pb string) error {
	if pb < pa {
		pa, pb = pb, pa
	}
	_, err := adb.db.Exec(`REPLACE INTO ExcludedPairs (PathA, PathB) VALUES(?, ?)`, pa, pb)
	return err
}

// isExcludedPair returns true if the supplied full paths have previously been recorded as
// not being duplicates of each other.
func (adb *audioDB) isExcludedPair(pa, pb string) (bool, error) {
	if pb < pa {
		pa, pb = pb, pa
	}
	if rows, err := adb.db.Query(`SELECT * FROM ExcludedPairs WHERE PathA = ? AND PathB = ?`, pa, pb); err != nil {
		return false, err
	} else {
		defer rows.Close()
		return rows.Next(), nil
	}
}
