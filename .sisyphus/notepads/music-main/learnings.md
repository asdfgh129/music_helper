# Music Main Program - Learnings and Patterns

## Existing Code Patterns (from archive.py, qq.py, lrc.py)

### Import Style
```python
# Standard library imports first
import os
import sys
import csv
import argparse
import logging
import shutil
import subprocess
import tempfile
import re
from datetime import datetime

# Third-party imports
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.wave import WAVE
from mutagen.apev2 import APEv2File
from mutagen.oggvorbis import OggVorbis
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TRCK, TYER, APIC, error, ID3NoHeaderError

# Local imports
from source_finder import guess_song_url
```

### Logging Configuration
```python
logging.basicConfig(
    filename='archive.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
```

### Directory Configuration Pattern
```python
dest_dir = 'D:\\music\\'
temp_dir = 'G:\\temp\\'
music_extensions = {'.flac', '.mp3', '.wav', '.ape', '.ogg'}
```

### File Walking Pattern
```python
for root, dirs, files in os.walk(directory):
    for file in files:
        if any(file.lower().endswith(ext) for ext in music_extensions):
            file_path = os.path.join(root, file)
            # Process file...
```

### Metadata Reading Pattern
```python
if file.lower().endswith('.mp3'):
    audio = MP3(file_path)
    year = audio.get('TDRC', [None])[0]
    title = audio.get('TIT2', [None])[0] or 'Unknown'
    artist = audio.get('TPE1', [None])[0] or 'Unknown'
    album = audio.get('TALB', [None])[0] or 'Unknown'
elif file.lower().endswith('.flac'):
    audio = FLAC(file_path)
    year = audio.get('date', [None])[0]
    title = audio.get('title', [None])[0]
    artist = audio.get('artist', [None])[0]
    album = audio.get('album', [None])[0]
```

### Artist Split Pattern
```python
def split_artist(artist):
    return [a.strip() for a in artist.lower().replace('；', ',').replace(';', ',').replace('，', ',').replace('&', ',').replace('/', ',').split(',') if a.strip()]
```

### External Tool Execution Pattern
- Use subprocess.run() for external tools like um.exe, soundalike.exe
- Capture output with stdout=subprocess.PIPE
- Handle return codes properly

### Command Line Args Pattern
```python
parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("-l", "--list", action="store_true")
parser.add_argument("-i", "--input", type=str, required=False)
parser.add_argument("-o", "--output", type=str, required=False)
args = parser.parse_args()
```

## Required External Programs
1. **um.exe** - Netease music decryption (params: -i input_dir -o output_dir)
2. **qq.py** - QQ music decryption (params: -i input_dir -o output_dir)
3. **soundalike.exe** - Audio fingerprinting (params: -move-interactive G:\tmp -temp G:\Temp D:\music or -check D:\music)

## Directory Structure
```
D:\music                    - Main working directory
G:\Neteasymusic             - Netease music directory
  └── VipSOngsDownload      - VIP songs download
G:\NeTmp                    - Netease temp for decryption
G:\QQMusic                 - QQ music directory
  └── VipSOngsDownload      - VIP songs download
G:\QQTmp                   - QQ temp for decryption
G:\Temp                    - Completed temp directory
G:\Tmp                     - Temporary move directory
```

## Key Features to Implement
1. Directory configuration constants
2. Month-based filtering (--month parameter)
3. Log file creation with timestamps
4. Music file scanning with date filtering
5. VIP decryption workflows for both Netease and QQ
6. Audio fingerprinting with soundalike.exe
7. Tag updating from online databases
8. File naming verification ("Artist - Song Name" format)
9. Duplicate detection
10. LRC file checking and downloading
11. Year-based organization
12. Database consistency check (--checkdb)

## Implementation Notes
- Use separate log files per operation with timestamps
- Support Chinese file names and paths
- Handle various artist separators (;
, /)
- Case-insensitive comparisons
- Interactive prompts for user decisions
- Count and report statistics
- Handle missing metadata gracefully
