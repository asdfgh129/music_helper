# -*- coding: utf-8 -*-
"""数据模型 - 全项目统一的音乐文件抽象"""

import os
from dataclasses import dataclass, field

from core.naming import normalize_key


@dataclass
class Track:
    """一个音乐文件的完整快照

    tags 统一使用小写键: title / artist / album / year / genre
    """

    path: str
    tags: dict = field(default_factory=dict)
    duration: float = 0.0
    size: int = 0
    mtime: float = 0.0

    # ---------- 基础属性 ----------

    @property
    def filename(self):
        return os.path.basename(self.path)

    @property
    def stem(self):
        return os.path.splitext(self.filename)[0]

    @property
    def ext(self):
        return os.path.splitext(self.path)[1].lower()

    @property
    def dirpath(self):
        return os.path.dirname(self.path)

    @property
    def lrc_path(self):
        return os.path.splitext(self.path)[0] + '.lrc'

    @property
    def has_lrc(self):
        return os.path.exists(self.lrc_path)

    # ---------- 标签访问 ----------

    def tag(self, key, default=''):
        value = self.tags.get(key, default)
        if value is None:
            return default
        value = str(value).strip()
        return value or default

    @property
    def title(self):
        return self.tag('title')

    @property
    def artist(self):
        return self.tag('artist')

    @property
    def album(self):
        return self.tag('album')

    @property
    def year(self):
        return self.tag('year')

    @property
    def genre(self):
        return self.tag('genre')

    @property
    def year_int(self):
        """解析出的四位年份，无法解析返回 0"""
        import re
        match = re.search(r'(\d{4})', self.year)
        if not match:
            return 0
        year = int(match.group(1))
        return year if 1900 <= year <= 2100 else 0

    @property
    def key(self):
        """去重用的宽松比对键"""
        return normalize_key(self.artist), normalize_key(self.title)

    def to_dict(self):
        return {
            'path': self.path,
            'filename': self.filename,
            'title': self.title,
            'artist': self.artist,
            'album': self.album,
            'year': self.year,
            'genre': self.genre,
            'duration': self.duration,
            'size': self.size,
            'has_lrc': self.has_lrc,
        }

    def __str__(self):
        return f'{self.artist} - {self.title}' if self.artist else self.stem
