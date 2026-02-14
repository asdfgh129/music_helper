# -*- coding: utf-8 -*-
"""
Music Tagger - 音乐文件标签管理工具
安装脚本
"""
from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="music-tagger",
    version="1.0.0",
    author="Your Name",
    author_email="your.email@example.com",
    description="独立的音乐文件标签管理工具",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/music-tagger",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: End Users/Desktop",
        "Topic :: Multimedia :: Sound/Audio",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
    python_requires=">=3.7",
    install_requires=[
        "requests>=2.28.0",
        "mutagen>=1.45.0",
        "pycryptodomex>=3.15.0",
        "execjs>=1.5.1",
        "mako>=1.2.0",
        "Pillow>=9.0.0",
    ],
    entry_points={
        "console_scripts": [
            "music-tagger=music_tagger.cli:main",
        ],
    },
)
