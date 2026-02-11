# Music Main Program - Implementation Complete

## Implementation Summary

**File Created**: `/Users/bemin/Code/music/main.py`
**Total Lines**: 1125
**Status**: Complete

## Features Implemented

### 1. Directory Configuration
- Main Directory: `D:\music`
- Netease Directory: `G:\Neteasymusic` with VIP subdir `G:\Neteasymusic\VipSOngsDownload`
- Netease Temp: `G:\NeTmp`
- QQ Directory: `G:\QQMusic` with VIP subdir `G:\QQMusic\VipSOngsDownload`
- QQ Temp: `G:\QQTmp`
- Temp Completed: `G:\Temp`
- Temp Move: `G:\Tmp`

### 2. Logging System
- Main log file: `Music-{timestamp}.log` in D:\music
- Operation-specific logs:
  - `Neteasy-{timestamp}.log` - Netease decryption
  - `QQ-{timestamp}.log` - QQ decryption
  - `UpdateTags-{timestamp}.log` - Tag updates
  - `Check-{timestamp}.log` - File consistency checks
  - `Organize-{timestamp}.log` - Year organization
- All logs use UTF-8 encoding
- Console + file dual logging

### 3. Command Line Arguments
- `--month YYYYMM` - Specify month to process (default: current month)
- `--check-master` - Check main directory D:\music
- `--uncheck-temp` - Don't check temp directory G:\Temp
- `--checkdb` - Database consistency check mode
- `--skip-vip` - Skip VIP decryption
- `--skip-fingerprint` - Skip audio fingerprinting
- `--skip-tag-update` - Skip tag updates
- `--skip-check` - Skip file checking
- `--skip-organize` - Skip year organization

### 4. Core Functions
1. **scan_music_files()** - Scan directories with month filtering
2. **decrypt_netease_vip()** - Call um.exe to decrypt Netease VIP files
3. **decrypt_qq_vip()** - Call qq.py to decrypt QQ VIP files
4. **run_soundalike_fingerprinting()** - Call soundalike.exe for deduplication
5. **update_tags_from_fingerprint()** - Update tags from online databases
6. **check_filename_consistency()** - Check filename vs tag consistency
7. **organize_by_year()** - Organize files by decade/year
8. **check_database_consistency()** - Check database consistency

### 5. Metadata Support
- MP3 (ID3 tags)
- FLAC (Vorbis comments)
- WAV (ID3 tags)
- APE (APEv2 tags)
- OGG (Vorbis comments)

### 6. Utility Functions
- `get_file_modification_month()` - Get file modification month
- `split_artist()` - Split artist names with multiple separators
- `normalize_text()` - Normalize text for comparison
- `parse_filename()` - Parse "Artist - Title" format
- `check_filename_format()` - Validate filename format
- `get_music_metadata()` - Read music file tags
- `set_music_metadata()` - Write music file tags
- `has_lrc_file()` - Check for LRC lyrics file

## Code Patterns Used
- UTF-8 encoding: `# -*- coding: utf-8 -*-`
- Import order: stdlib → third-party → local
- Snake_case naming
- Chinese comments
- f-strings for formatting
- os.path for cross-platform paths
- try/except for error handling
- Graceful degradation (MUTAGEN_AVAILABLE checks)

## External Program Calls
```python
# Netease decryption
um.exe -i G:\NeTmp -o G:\Temp

# QQ decryption
python qq.py -i G:\QQTmp -o G:\Temp

# Audio fingerprinting
soundalike.exe -move-interactive G:\Tmp -temp G:\Temp D:\music

# Database check
soundalike.exe -check D:\music
```

## Year Organization Structure
```
G:\Temp\
├── 1950-1979\
│   ├── 1955\
│   ├── 1960\
│   └── ...
├── 1980-1989\
│   ├── 1980\
│   ├── 1985\
│   └── ...
├── 1990-1999\
├── 2000-2009\
├── 2010-2019\
├── 2020-2029\
└── unknown\        # Files with incomplete tags
```

## Workflow
1. VIP Decryption (Netease + QQ)
2. Audio Fingerprinting & Deduplication
3. Tag Update from Online Sources
4. File Consistency Check
5. Year-based Organization

## Usage Examples
```bash
# Full processing (current month)
python main.py

# Process specific month
python main.py --month 202406

# Database consistency check only
python main.py --checkdb

# Check main directory + temp
python main.py --check-master

# Skip temp directory check
python main.py --uncheck-temp

# Skip certain steps
python main.py --skip-vip --skip-fingerprint
```

## Notes
- All functions include proper error handling
- Operations are logged with timestamps
- Statistics are recorded for each operation
- Files with incomplete tags are moved to 'unknown' folder
- Duplicate detection uses artist + title matching
- Artist splitting supports: ;, ；, ,, 、, /, &, |, +, etc.
