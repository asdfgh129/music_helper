# -*- coding: utf-8 -*-
"""
音乐文件标签读写核心模块
"""
import os
import base64
import time
from concurrent.futures import ThreadPoolExecutor

# 假设music_tag模块已安装，或从原项目component目录引用
try:
    from component.music_tag import load_file
except ImportError:
    raise ImportError(
        "需要安装 music_tag 模块。请从原项目复制 component/music_tag 目录到 Python 路径中，"
        "或安装相应的音乐标签处理库。"
    )

from .platforms import MusicResource
from .matcher import match_score, match_artist
from .utils import ConstantTemplate, timestamp_to_dt


class MusicTagger:
    """音乐文件标签读写类"""

    def __init__(self, file_path):
        """
        初始化音乐标签对象
        
        Args:
            file_path: 音乐文件路径
        """
        self.file_path = file_path
        self._file = load_file(file_path)
        self._artwork_w = 0
        self._artwork_h = 0
        self._artwork_size = 0

    @property
    def title(self):
        """歌曲标题"""
        return self._file['title'].value

    @property
    def artist(self):
        """艺术家"""
        return self._file['artist'].value

    @property
    def album(self):
        """专辑"""
        album_name = self._file['album'].value
        if not album_name:
            album_name = "未知专辑"
        return album_name

    @property
    def albumartist(self):
        """专辑艺术家"""
        return self._file['albumartist'].value

    @property
    def year(self):
        """年份"""
        try:
            year = self._file['year'].value
        except Exception:
            return 0
        try:
            year = int(year)
        except Exception:
            year_list = year.split("-")
            if year_list and year_list[0]:
                try:
                    return int(year_list[0].replace(" ", ""))
                except Exception:
                    return 0
        return year

    @property
    def genre(self):
        """流派/类型"""
        genre = self._file['genre'].value
        if genre:
            genre = genre.upper()
        else:
            genre = "未知"
        return genre

    @property
    def comment(self):
        """评论"""
        return self._file['comment'].value

    @property
    def lyrics(self):
        """歌词"""
        return self._file['lyrics'].value

    @property
    def duration(self):
        """时长(秒)"""
        return round(self._file['#length'].value, 2)

    @property
    def size(self):
        """文件大小(MB)"""
        return round(os.path.getsize(self.file_path) / 1024 / 1024, 2)

    @property
    def suffix(self):
        """文件格式"""
        return self._file['#codec'].value

    @property
    def bit_rate(self):
        """比特率"""
        return int(self._file['#bitrate'].value / 1000)

    @property
    def track_number(self):
        """音轨号"""
        try:
            return self._file['tracknumber'].value
        except Exception:
            try:
                return self._file.mfile.tags["tracknumber"][0]
            except Exception:
                return 1

    @property
    def disc_number(self):
        """碟片号"""
        try:
            return self._file['discnumber'].value
        except Exception:
            try:
                return self._file.mfile.tags["discnumber"][0]
            except Exception:
                return 1

    @property
    def artwork(self):
        """封面图片(Base64)"""
        try:
            bs64_img = ""
            artwork = self._file['artwork'].values
            if artwork:
                if isinstance(artwork[0], bytes):
                    bs64_img = base64.b64encode(artwork[0]).decode()
                else:
                    zip_img = artwork[0].raw_thumbnail([128, 128])
                    bs64_img = base64.b64encode(zip_img).decode()
                    self._artwork_w = artwork[0].width
                    self._artwork_h = artwork[0].height
                    self._artwork_size = round(len(artwork[0].raw) / 1024 / 1024, 2)
            return "data:image/jpeg;base64," + bs64_img
        except Exception as e:
            print(f"获取封面失败: {e}")
            return ""

    @property
    def file_name(self):
        """文件名"""
        return os.path.basename(self.file_path)

    def to_dict(self):
        """转换为字典"""
        return {
            "year": self.year,
            "comment": self.comment,
            "lyrics": self.lyrics,
            "duration": self.duration,
            "size": self.size,
            "bit_rate": self.bit_rate,
            "tracknumber": self.track_number,
            "discnumber": self.disc_number,
            "artwork": self.artwork,
            "artwork_w": self._artwork_w,
            "artwork_h": self._artwork_h,
            "artwork_size": self._artwork_size,
            "title": self.title or self.file_name.split(".")[0],
            "artist": self.artist,
            "album": self.album,
            "genre": self.genre,
            "filename": self.file_name,
            "albumartist": self.albumartist,
        }

    def var_dict(self):
        """获取变量字典(用于模板替换)"""
        return {
            "title": self.title or self.file_name.split(".")[0],
            "artist": self.artist,
            "albumartist": self.albumartist,
            "discnumber": self.disc_number,
            "tracknumber": self.track_number,
            "album": self.album,
            "filename": self.file_name,
        }

    def update_tags(self, tag_info, is_raw_thumbnail=False):
        """
        更新音乐文件标签
        
        Args:
            tag_info: 标签信息字典
            is_raw_thumbnail: 是否使用原始缩略图
        """
        base_filename = ".".join(os.path.basename(self.file_path).split(".")[:-1])
        file_ext = os.path.basename(self.file_path).split(".")[-1]

        var_dict = self.var_dict()

        # 标题
        if tag_info.get("title"):
            if "${" in tag_info["title"]:
                self._file["title"] = ConstantTemplate(tag_info["title"]).resolve_data(var_dict)
            else:
                self._file["title"] = tag_info["title"]

        # 艺术家
        if tag_info.get("artist") is not None:
            if "${" in tag_info["artist"]:
                artist = ConstantTemplate(tag_info["artist"]).resolve_data(var_dict)
            else:
                artist = tag_info["artist"]
            artists = artist.split(",") if isinstance(artist, str) else [artist]
            self._file.set("artist", artists)

        # 专辑
        if tag_info.get("album") is not None:
            if "${" in tag_info["album"]:
                self._file["album"] = ConstantTemplate(tag_info["album"]).resolve_data(var_dict)
            else:
                self._file["album"] = tag_info["album"]

        # 专辑艺术家
        if tag_info.get("albumartist"):
            if "${" in tag_info["albumartist"]:
                self._file["albumartist"] = ConstantTemplate(tag_info["albumartist"]).resolve_data(var_dict)
            else:
                self._file["albumartist"] = tag_info["albumartist"]

        # 碟片号
        if tag_info.get("discnumber"):
            if "${" in tag_info["discnumber"]:
                discnumber = ConstantTemplate(tag_info["discnumber"]).resolve_data(var_dict)
            else:
                discnumber = tag_info["discnumber"]
            try:
                self._file["discnumber"] = int(discnumber.split("/")[0].strip())
            except Exception:
                self._file["discnumber"] = 0

        # 音轨号
        if tag_info.get("tracknumber"):
            if "${" in tag_info["tracknumber"]:
                tracknumber = ConstantTemplate(tag_info["tracknumber"]).resolve_data(var_dict)
            else:
                tracknumber = tag_info["tracknumber"]
            try:
                self._file["tracknumber"] = int(tracknumber.split("/")[0].strip())
            except Exception:
                self._file["tracknumber"] = 0

        # 流派
        if tag_info.get("genre"):
            self._file["genre"] = tag_info["genre"]

        # 年份
        if tag_info.get("year"):
            self._file["year"] = tag_info["year"]

        # 歌词
        if tag_info.get("lyrics"):
            self._file["lyrics"] = tag_info["lyrics"]
            if tag_info.get("is_save_lyrics_file", False):
                lyrics_file_path = f"{os.path.dirname(self.file_path)}/{base_filename}.lrc"
                with open(lyrics_file_path, "w", encoding="utf-8") as f_lyc:
                    f_lyc.write(tag_info["lyrics"])
        else:
            if tag_info.get("lyrics") is not None:
                self._file.remove_tag("lyrics")
            if tag_info.get("is_save_lyrics_file", False):
                lyrics_file_path = f"{os.path.dirname(self.file_path)}/cover-{base_filename}.lrc"
                if not os.path.exists(lyrics_file_path):
                    with open(lyrics_file_path, "w", encoding="utf-8") as f_lyc2:
                        f_lyc2.write(self._file["lyrics"].value)

        # 评论
        if tag_info.get("comment"):
            self._file["comment"] = tag_info["comment"]

        # 封面图片
        if tag_info.get("album_img"):
            try:
                img_content = None
                if tag_info["album_img"].startswith("http"):
                    # 下载图片
                    import requests
                    img_data = requests.get(tag_info["album_img"], timeout=10)
                    if img_data.status_code == 200:
                        img_content = img_data.content
                else:
                    # Base64解码
                    img_content = base64.b64decode(tag_info["album_img"])

                if img_content:
                    self._file['artwork'] = img_content

                    # 保存封面到文件
                    if tag_info.get("is_save_album_cover", False):
                        format_str = self._file['artwork'].value.format
                        album_cover_path = f"{os.path.dirname(self.file_path)}/cover-{self._file['album']}.{format_str}"
                        if os.path.exists(album_cover_path):
                            os.remove(album_cover_path)
                        with open(album_cover_path, "wb") as f_img:
                            f_img.write(img_content)

                    # 自动压缩>5MB的图片
                    if len(img_content) / 1024 / 1024 > 5:
                        self._file['artwork'] = self._file['artwork'].first.raw_thumbnail([2048, 2048])

                    if is_raw_thumbnail:
                        self._file['artwork'] = self._file['artwork'].first.raw_thumbnail([2048, 2048])
            except Exception as e:
                print(f"设置封面失败: {e}")
        else:
            if tag_info.get("is_save_album_cover", False):
                try:
                    format_str = self._file['artwork'].value.format
                    album_cover_path = f"{os.path.dirname(self.file_path)}/cover-{self._file['album']}.{format_str}"
                    if not os.path.exists(album_cover_path):
                        with open(album_cover_path, "wb") as f_img:
                            f_img.write(self._file['artwork'].value.raw)
                except Exception:
                    pass

        # 特殊标签(FLAC/ID3)
        if tag_info.get("album_type"):
            try:
                from mutagen.flac import VCFLACDict
                from mutagen.id3 import TXXX, ID3
                if isinstance(self._file.mfile.tags, VCFLACDict):
                    self._file.mfile.tags["RELEASETYPE"] = tag_info["album_type"]
                elif isinstance(self._file.mfile.tags, ID3):
                    self._file.mfile.tags["MusicBrainz Album Type"] = TXXX(
                        encoding=3,
                        desc="MusicBrainz Album Type",
                        text=tag_info["album_type"]
                    )
                else:
                    raise Exception("未知的音乐文件类型")
            except Exception as e:
                print(f"设置专辑类型失败: {e}")

        if tag_info.get("language"):
            try:
                from mutagen.flac import VCFLACDict
                from mutagen.id3 import TXXX, ID3
                if isinstance(self._file.mfile.tags, VCFLACDict):
                    self._file.mfile.tags["LANGUAGE"] = tag_info["language"]
                elif isinstance(self._file.mfile.tags, ID3):
                    self._file.mfile.tags["LANGUAGE"] = TXXX(
                        encoding=3,
                        desc="LANGUAGE",
                        text=tag_info["language"]
                    )
                else:
                    self._file.mfile.tags["LANGUAGE"] = tag_info["language"]
            except Exception as e:
                print(f"设置语言失败: {e}")

        # 保存修改
        self._file.save()

        # 重命名文件
        if tag_info.get("filename"):
            if "${" in tag_info["filename"]:
                tag_info["filename"] = ConstantTemplate(tag_info["filename"]).resolve_data(var_dict)
            if not tag_info["filename"].endswith(file_ext):
                tag_info["filename"] = f"{tag_info['filename']}.{file_ext}"
            parent_path = os.path.dirname(self.file_path)
            new_path = f"{parent_path}/{tag_info['filename']}"
            if self.file_path != new_path:
                os.rename(self.file_path, new_path)
                self.file_path = new_path

    def save(self):
        """保存文件修改"""
        self._file.save()


def match_song(resource, song_path, select_mode):
    """
    单平台精确匹配
    
    Args:
        resource: 平台名称
        song_path: 音乐文件路径
        select_mode: "strict" | "simple"
    
    Returns:
        bool: 是否匹配成功
    """
    tagger = MusicTagger(song_path)
    file_name = os.path.basename(song_path)
    file_title = file_name.split('.')[0]
    
    title = tagger.title or file_title
    artist = tagger.artist or ""
    album = tagger.album or ""

    songs = MusicResource(resource).fetch_id3_by_title(title)

    is_match = False
    song_select = None
    match_score_map = {
        "title": 0,
        "artist": 0,
        "album": 0,
    }

    for song in songs:
        match_score_map["title"] = match_score(title, song["name"])
        match_score_map["artist"] = match_artist(artist if artist else title, song["artist"])
        match_score_map["album"] = match_score(album if album else title, song["album"])
        
        if artist and match_score_map["artist"] == 0:
            match_score_map["artist"] = -2
        
        if not artist and match_score_map["artist"] >= 1:
            if match_score_map["title"] >= 1:
                match_score_map["title"] = 2
        
        if select_mode == "strict":
            if sum(match_score_map.values()) >= 3:
                is_match = True
                song_select = song
                break
        else:
            if match_score_map["title"] == 2:
                is_match = True
                song_select = song
                break

    if is_match:
        print(f"{title}>>>{song_select['name']}::{match_score_map}")
        song_select["filename"] = file_name
        song_select["file_full_path"] = song_path
        try:
            song_select["lyrics"] = MusicResource(resource).fetch_lyric(song_select["id"])
        except Exception as e:
            print(f"获取歌词失败: {e}")
            song_select["lyrics"] = ""
        tagger.update_tags(song_select, False)
    
    return is_match


def auto_tag(music_folder, source_list, select_mode="strict"):
    """
    批量自动标签匹配
    
    Args:
        music_folder: 音乐文件夹路径
        source_list: 平台列表, 如 ["qmusic", "netease", "migu", "kugou"]
        select_mode: "strict" | "simple"
    
    Returns:
        list: 处理结果列表
    """
    ALLOW_TYPE = {"flac", "mp3", "ape", "wav", "aiff", "wv", "tta", "m4a", "ogg", "mpc", "opus", "wma", "dsf", "dff"}
    
    results = []
    
    # 扫描文件夹
    for root, dirs, files in os.walk(music_folder):
        for file_name in files:
            file_path = os.path.join(root, file_name)
            file_ext = file_name.split(".")[-1].lower()
            
            if file_ext not in ALLOW_TYPE:
                continue
            
            result = {
                "file": file_path,
                "file_name": file_name,
                "status": "failed",
                "source": "",
                "message": ""
            }
            
            is_match = False
            for resource in source_list:
                print(f"正在匹配: {file_name} - {resource}")
                try:
                    is_match = match_song(resource, file_path, select_mode)
                    if is_match:
                        result["status"] = "success"
                        result["source"] = resource
                        break
                except Exception as e:
                    result["message"] = str(e)
                    print(f"匹配失败: {file_name} - {resource}, 错误: {e}")
                    is_match = False
                    break
            
            results.append(result)
            print(f"处理完成: {file_name} - {result['status']}")
    
    return results


def batch_update_tags(music_id3_info_list):
    """
    批量更新音乐文件标签
    
    Args:
        music_id3_info_list: 标签信息列表, 每个元素包含:
            - file_full_path: 文件路径
            - title: 标题(可选)
            - artist: 艺术家(可选)
            - album: 专辑(可选)
            - 其他标签字段...
    """
    for music_info in music_id3_info_list:
        file_path = music_info["file_full_path"]
        print(f"正在更新: {file_path}")
        try:
            tagger = MusicTagger(file_path)
            tagger.update_tags(music_info, False)
            print(f"更新成功: {file_path}")
        except Exception as e:
            print(f"更新失败: {file_path}, 错误: {e}")
