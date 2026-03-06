#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, '/Users/bemin/Code/music_helper/Fingerprint')

from musicbrainz_matcher import FingerprintMatcher

# 测试
matcher = FingerprintMatcher()
result = matcher.match_file("/Users/bemin/Code/music_helper/1.flac")

print(f"Success: {result.success}")
print(f"Error: {result.error}")
print(f"Recordings count: {len(result.recordings)}")

if result.recordings:
    print(f"Best match: {result.recordings[0].get('title', 'N/A')}")
