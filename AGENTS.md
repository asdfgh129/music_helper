# AGENTS.md - Music Utility Project

## Project Overview

This is a Python-based music file management toolkit with multiple utilities:
- **QQ Music Decryption**: Frida-based tool to decrypt QQ Music encrypted audio files (`.mflac`, `.mgg`)
- **Archive Tool**: Music file metadata management, duplicate detection, and organization by year
- **LRC Management**: Find missing/orphan `.lrc` (lyric) files
- **Duplicate Detection**: Find duplicate music files with variations

## Environment

- **Language**: Python 3.11+
- **Platform**: Cross-platform (Windows, macOS, Linux)
- **Main Directory**: `/Users/bemin/Code/music`
- **Key Subdirectory**: `QQ/` - Contains QQ Music decryption tool

## Build/Run/Test Commands

### Installation
```bash
# Install dependencies for QQ Music tool
pip install -r QQ/requirements.txt

# Core dependencies
pip install frida>=16.0.0 requests>=2.31.0
pip install mutagen  # For archive.py, lrc.py
```

### Running Individual Scripts

```bash
# QQ Music Decryption Tool
cd QQ
python main.py -l                    # List songs in default download directory
python main.py -i <input> -o <output>  # Decrypt and convert files

# Archive Tool (organize music by year)
python archive.py                    # Runs full archival pipeline

# Find duplicate files
python duplicate.py                  # Find files with (1), (2), (3) patterns

# LRC file management
python lrc.py                        # Find missing/orphan .lrc files
```

### No Build System
- **No pytest/unittest framework** - Scripts are standalone utilities
- **No linting/formatting configs** - No `.flake8`, `pyproject.toml`, or similar
- **No CI/CD** - Manual execution only
- **No git repository** - This is a loose collection of scripts

## Code Style Guidelines

### File Organization
- **Encoding**: UTF-8 with BOM for CSV files (`utf-8-sig`)
- **Line Endings**: Windows-style (`\r\n`) for most files
- **Encoding Declaration**: `# -*- coding: utf-8 -*-` at top of files

### Import Style
```python
# Standard library imports first
import os
import sys
import csv
from datetime import datetime

# Third-party imports
import frida
import requests
from mutagen.flac import FLAC
from mutagen.mp3 import MP3

# Local imports last
try:
    from source_finder import guess_song_url
except Exception:
    def guess_song_url(_):
        return None
```

**Import Rules**:
- Group imports: stdlib → third-party → local
- Use specific imports (`from X import Y`) for frequently used items
- Graceful degradation for optional dependencies (use try/except)
- No relative imports (all local imports use module names)

### Naming Conventions
```python
# Functions: snake_case with descriptive names
def find_missing_lrc_files(root_dir):
def generate_music_metadata(directory):
def split_artist(artist):

# Variables: snake_case
dest_dir = 'D:\\music\\'
temp_metadata = []
csv_path = os.path.join(...)

# Constants: snake_case (not SCREAMING_SNAKE_CASE in this codebase)
music_extensions = {'.flac', '.mp3', '.wav', '.ape', '.ogg'}

# Private functions: single underscore prefix
def _normalize_text(s: str) -> str:
def _qq_search_api(artist: str, title: str):
def _best_match_songmid(resp_json, artist: str, title: str):
```

### Type Hints
```python
# Use type hints for public functions (Python 3.10+ union syntax)
def guess_song_url(file_basename: str) -> str | None:
def _normalize_text(s: str) -> str:
def append_csv(song_name: str, src_url: str):

# No type hints for internal/simple functions is acceptable
def list_download_songs():  # No return type hint
```

### String Formatting
```python
# Use f-strings (preferred)
logging.info(f"开始解密: {file}")
print(f"{count:4d}. {rel}")

# Format specifiers for alignment
f"{count:4d}"  # Right-aligned integer with 4 chars width
```

### Path Handling
```python
# Always use os.path for cross-platform compatibility
os.path.join(root, file)
os.path.abspath(input_dir)
os.path.expanduser("~")
os.path.splitext(file)

# Windows paths: Use raw strings or double backslashes
dest_dir = 'D:\\music\\'  # or r'D:\music\'
```

### Error Handling
```python
# Catch specific exceptions when possible
try:
    session = frida.attach("QQMusic.exe")
except frida.ProcessNotFoundError:
    logging.error("未找到 QQMusic.exe 进程，请先启动 QQ 音乐")
    return

# Bare except for cleanup only
except Exception as e:
    logging.error(f"解密失败: {file} -> {e}")
    try:
        if os.path.exists(tmp_output_path):
            os.remove(tmp_output_path)
    except Exception:  # Cleanup can ignore errors
        pass

# Use finally for cleanup
finally:
    session.detach()
    shutil.rmtree(temp_dir, ignore_errors=True)
```

### Logging
```python
# Configure at module entry point
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)

# Or log to file
logging.basicConfig(
    filename='archive.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Log levels
logging.info(f"共找到 {count} 个文件")       # Informational
logging.warning(f"Delete {temp_filepath}")   # Warnings
logging.error(f"默认下载目录不存在：{dir}")   # Errors
logging.error(traceback.format_exc())        # Exception details
```

### Comments and Documentation
- **Chinese comments are acceptable** (codebase uses mix of English/Chinese)
- Document complex logic with inline comments
- Use descriptive function names over excessive comments
- No docstrings present in codebase (not required)

### File Operations
```python
# Always use context managers for files
with open(csv_path, "a", encoding="utf-8-sig", newline="") as f:
    writer = csv.writer(f)
    writer.writerow([...])

# Check existence before operations
if os.path.exists(download_dir):
    # ...

# Use shutil for file operations
shutil.copyfile(src_abs_path, temp_src_path)
shutil.move(file_path, new_file_path)
shutil.rmtree(temp_dir, ignore_errors=True)
```

### Regular Expressions
```python
import re

# Use raw strings for regex patterns
s = re.sub(r"[（(].*?[）)]", "", s)
s = re.sub(r"\s+", " ", s)
value = re.sub(r'\b(\w)', lambda m: m.group(1).upper(), value.lower())
```

## Anti-Patterns to Avoid

### DO NOT:
- ❌ Use `as any` / type suppression (not applicable to Python)
- ❌ Use bare `except:` without cleanup justification
- ❌ Hardcode paths that should be configurable (paths are OK for personal scripts)
- ❌ Suppress errors silently - always log failures
- ❌ Use `print()` for operational logs - use `logging` module
- ❌ Leave files open without context managers

### DO:
- ✅ Use `logging` for all operational messages
- ✅ Use `print()` only for user-facing output (command help, results)
- ✅ Check file existence before operations
- ✅ Use `os.path` for cross-platform path handling
- ✅ Use `finally` blocks for cleanup (Frida sessions, temp directories)
- ✅ Gracefully handle missing dependencies
- ✅ Use f-strings for string formatting

## Special Considerations

### Frida Integration (QQ/main.py)
- Always attach to running process: `frida.attach("QQMusic.exe")`
- Load JavaScript hook from file: `session.create_script(f.read())`
- Use synchronous exports: `script.exports_sync.decrypt(...)`
- Always detach in finally block: `session.detach()`

### Music Metadata (archive.py)
- Use `mutagen` library for audio file metadata
- Support formats: `.mp3`, `.flac`, `.wav`, `.ape`, `.ogg`
- Different metadata APIs per format (MP3 uses ID3, FLAC uses Vorbis comments)
- Always save after modifications: `audio.save()`

### CSV Logging
- Use `utf-8-sig` encoding for Excel compatibility
- Include headers only when creating new file
- Use `newline=''` parameter to avoid double line breaks on Windows

### Temporary Files
- Use `tempfile.mkdtemp()` for temp directories
- Always cleanup in finally block with `shutil.rmtree(temp_dir, ignore_errors=True)`
- Use MD5 hashes for temp filenames to avoid collisions

## Common Patterns

### Walking Directory Trees
```python
for root, dirs, files in os.walk(directory):
    for file in files:
        if file.lower().endswith(('.mp3', '.flac', '.wav')):
            full_path = os.path.join(root, file)
            # Process file...
```

### Safe File Deletion
```python
if os.path.exists(filepath):
    logging.warning(f"Delete {filepath}")
    os.remove(filepath)
```

### Argparse Pattern
```python
parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("-l", "--list", action="store_true")
parser.add_argument("-i", "--input", type=str, required=False)
args = parser.parse_args()

if len(sys.argv) == 1:
    print("命令用法:")
    # Print help manually
    sys.exit(0)
```
