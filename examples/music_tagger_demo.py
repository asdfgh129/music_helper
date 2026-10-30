# -*- coding: utf-8 -*-
"""
music_tagger 模块使用示例

功能：
1. 自动从文件标签或文件名解析歌手和歌曲名
2. 从网易云音乐、QQ音乐等平台搜索标签信息
3. 自动匹配最合适的标签信息并更新到音乐文件

使用方法：
    python music_tagger_example.py <音乐文件路径>
    或
    python music_tagger_example.py --all <音乐文件夹路径>
"""
import os
import sys
import argparse

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from music_tagger import MusicTagger, MusicResource, SmartTagClient, auto_tag


def parse_filename(filename):
    """
    从文件名解析歌手和歌曲名
    
    支持格式：
    - 歌手名 - 歌曲名.ext
    - 歌曲名 - 歌手名.ext
    - 歌手名_歌曲名.ext
    - 歌曲名.ext (纯歌名)
    
    Args:
        filename: 文件名(不含路径)
    
    Returns:
        dict: {"artist": 歌手名, "title": 歌曲名}
    """
    # 去除扩展名
    base_name = os.path.splitext(filename)[0]
    
    # 移除常见的前缀和后缀
    base_name = base_name.lstrip("0123456789.- ")
    
    artist = ""
    title = base_name
    
    # 尝试按分隔符解析
    separators = [" - ", " -", "- ", "_", "｜", "|"]
    for sep in separators:
        if sep in base_name:
            parts = base_name.split(sep)
            if len(parts) == 2:
                # 判断哪部分是歌手名(通常较短)
                if len(parts[0]) < len(parts[1]):
                    artist = parts[0].strip()
                    title = parts[1].strip()
                else:
                    title = parts[0].strip()
                    artist = parts[1].strip()
                break
            elif len(parts) > 2:
                # 多个分隔符,第一个通常是歌手
                artist = parts[0].strip()
                title = sep.join(parts[1:]).strip()
                break
    
    # 清理括号中的额外信息
    import re
    title = re.sub(r'[\[（\(].*?[\]）\)]', '', title).strip()
    
    return {
        "artist": artist,
        "title": title
    }


def print_song_details(song, index=None):
    """
    打印歌曲的详细标签信息

    Args:
        song: 歌曲信息字典
        index: 结果索引（可选）
    """
    if index is not None:
        print(f"\n{'='*60}")
        print(f"结果 #{index} [{song['platform']} - 得分: {song['match_score']:.2f}]")
        print(f"{'='*60}")
    else:
        print(f"\n{'='*60}")
        print(f"[{song['platform']} - 得分: {song['match_score']:.2f}]")
        print(f"{'='*60}")

    print(f"\n🎵 基本信息")
    print(f"  歌曲ID: {song.get('id', 'N/A')}")
    print(f"  歌曲名: {song.get('name', 'N/A')}")
    print(f"  歌手: {song.get('artist', 'N/A')}")
    print(f"  歌手ID: {song.get('artist_id', 'N/A')}")
    print(f"  专辑: {song.get('album', 'N/A')}")
    print(f"  专辑ID: {song.get('album_id', 'N/A')}")
    print(f"  年份: {song.get('year', 'N/A')}")

    print(f"\n📀 专辑信息")
    print(f"  专辑封面: {song.get('album_img', 'N/A')}")

    # 打印所有其他字段
    print(f"\n📋 完整标签信息")
    excluded_keys = {'platform', 'match_score', 'file_full_path', 'filename'}
    for key, value in song.items():
        if key not in excluded_keys:
            # 格式化字段名显示
            display_key = key.replace('_', ' ').title()
            # 限制过长的值显示
            if isinstance(value, str) and len(value) > 100:
                value = value[:100] + "..."
            print(f"  {display_key}: {value}")


def search_best_match(artist, title, platforms=None, max_results=5):
    """
    在多个平台搜索并找出最佳匹配

    Args:
        artist: 歌手名
        title: 歌曲名
        platforms: 平台列表，默认 ["netease", "qmusic", "migu", "kugou"]
        max_results: 此参数已废弃，现在会显示所有搜索结果

    Returns:
        dict: 最佳匹配结果，包含所有标签信息
    """
    if platforms is None:
        platforms = ["netease", "qmusic", "migu", "kugou"]
    
    all_results = []
    search_keyword = title
    
    # 如果有歌手名，组合搜索
    if artist:
        search_keyword = f"{artist} {title}"
    
    print(f"搜索关键词: {search_keyword}")
    print(f"搜索平台: {', '.join(platforms)}")
    
    # 从各平台搜索
    for platform in platforms:
        try:
            print(f"\n正在从 {platform} 搜索...")
            resource = MusicResource(platform)
            songs = resource.fetch_id3_by_title(search_keyword)
            
            for song in songs:
                song["platform"] = platform
                song["match_score"] = calculate_match_score(
                    artist, title, 
                    song.get("artist", ""), 
                    song.get("name", ""),
                    song.get("album", "")
                )
                all_results.append(song)
            
            print(f"{platform} 找到 {len(songs)} 个结果")
            
        except Exception as e:
            print(f"{platform} 搜索失败: {e}")
    
    if not all_results:
        print("\n未找到匹配结果")
        return None

    # 按匹配度排序
    all_results.sort(key=lambda x: x["match_score"], reverse=True)

    print(f"\n{'='*60}")
    print(f"总共找到 {len(all_results)} 个候选结果")
    print(f"{'='*60}")

    # 打印所有搜索结果及其详细标签信息
    for i, song in enumerate(all_results):
        print_song_details(song, i+1)

    # 标记最佳匹配
    print(f"\n{'='*60}")
    print(f"★ 最佳匹配结果: 结果 #{1}")
    print(f"{'='*60}")

    return all_results[0]


def calculate_match_score(artist, title, online_artist, online_title, online_album):
    """
    计算本地信息与在线信息的匹配度
    
    Args:
        artist: 本地歌手名
        title: 本地歌曲名
        online_artist: 在线歌手名
        online_title: 在线歌曲名
        online_album: 在线专辑名
    
    Returns:
        float: 匹配得分(0-100)
    """
    from music_tagger import match_score, match_artist
    
    score = 0.0
    
    # 标题匹配(权重40%)
    title_score = match_score(title, online_title)
    if title_score >= 2:
        score += 40
    elif title_score >= 1:
        score += 30
    else:
        score += 10
    
    # 歌手匹配(权重40%)
    if artist:
        artist_score = match_artist(artist, online_artist)
        if artist_score >= 2:
            score += 40
        elif artist_score >= 1:
            score += 30
        elif artist_score == 0:
            # 有明确歌手名但完全不匹配，扣分
            score -= 20
        else:
            score += 10
    else:
        # 没有歌手名，从标题中推断
        artist_score = match_artist(title, online_artist)
        if artist_score >= 1:
            score += 20
    
    # 专辑匹配(权重20%)
    album_score = match_score(title, online_album)
    if album_score >= 1:
        score += 20
    
    return max(0, score)


def auto_tag_single_file(file_path, platforms=None):
    """
    自动为单个音乐文件打标签
    
    Args:
        file_path: 音乐文件路径
        platforms: 平台列表，默认 ["netease", "qmusic", "migu", "kugou"]
    
    Returns:
        bool: 是否成功更新标签
    """
    print(f"\n{'='*60}")
    print(f"处理文件: {os.path.basename(file_path)}")
    print(f"{'='*60}\n")
    
    # 读取文件标签
    tagger = MusicTagger(file_path)
    
    print("=== 当前文件信息 ===")
    print(f"标题: {tagger.title}")
    print(f"歌手: {tagger.artist}")
    print(f"专辑: {tagger.album}")
    print(f"年份: {tagger.year}")
    print(f"时长: {tagger.duration} 秒")
    print(f"格式: {tagger.suffix}")
    
    # 确定搜索关键词
    artist = tagger.artist
    title = tagger.title
    
    # 如果标签为空，从文件名解析
    if not title or not artist:
        print("\n标签信息不完整，尝试从文件名解析...")
        parsed = parse_filename(tagger.file_name)
        if not title:
            title = parsed["title"]
            print(f"从文件名解析得到歌曲名: {title}")
        if not artist:
            artist = parsed["artist"]
            if artist:
                print(f"从文件名解析得到歌手名: {artist}")
    
    if not title:
        print("错误: 无法确定歌曲名")
        return False
    
    # 搜索最佳匹配
    best_match = search_best_match(artist, title, platforms)
    
    if not best_match:
        print("\n未找到匹配结果，跳过更新")
        return False
    
    print(f"\n=== 将更新为 ===")
    print(f"平台: {best_match['platform']}")
    print(f"歌曲: {best_match['name']}")
    print(f"歌手: {best_match['artist']}")
    print(f"专辑: {best_match['album']}")
    print(f"得分: {best_match['match_score']:.2f}")
    
    # 获取歌词
    try:
        lyrics = MusicResource(best_match['platform']).fetch_lyric(best_match['id'])
        if lyrics:
            print(f"歌词: 已获取 ({len(lyrics)} 字符)")
            best_match['lyrics'] = lyrics
    except Exception as e:
        print(f"获取歌词失败: {e}")
    
    # 确认更新
    print(f"\n是否更新标签？(y/n): ", end='')
    try:
        confirm = input().strip().lower()
        if confirm == 'y':
            # 添加文件路径信息
            best_match['file_full_path'] = file_path
            best_match['filename'] = tagger.file_name
            
            # 更新标签
            tagger.update_tags(best_match)
            print("\n✓ 标签更新成功!")
            return True
        else:
            print("\n取消更新")
            return False
    except (EOFError, KeyboardInterrupt):
        print("\n\n取消更新")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="音乐文件自动标签工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 处理单个文件
  python music_tagger_example.py song.mp3
  
  # 处理整个文件夹
  python music_tagger_example.py --all /path/to/music
  
  # 指定搜索平台
  python music_tagger_example.py song.mp3 --platforms netease qmusic
        """
    )
    
    parser.add_argument(
        "path",
        nargs="?",
        help="音乐文件路径或文件夹路径"
    )
    
    parser.add_argument(
        "--all",
        action="store_true",
        help="批量处理文件夹中的所有音乐文件"
    )
    
    parser.add_argument(
        "--platforms",
        nargs="+",
        choices=["netease", "qmusic", "migu", "kugou", "kuwo"],
        default=["netease", "qmusic", "migu", "kugou"],
        help="指定搜索平台 (默认: netease qmusic migu kugou)"
    )
    
    parser.add_argument(
        "--auto",
        action="store_true",
        help="自动更新，不询问确认"
    )
    
    args = parser.parse_args()
    
    if not args.path:
        parser.print_help()
        return
    
    path = os.path.abspath(args.path)
    
    if not os.path.exists(path):
        print(f"错误: 路径不存在: {path}")
        return
    
    # 处理单个文件
    if os.path.isfile(path):
        auto_tag_single_file(path, args.platforms)
    
    # 批量处理文件夹
    elif os.path.isdir(path) and args.all:
        print(f"\n批量处理模式")
        print(f"文件夹: {path}")
        print(f"平台: {', '.join(args.platforms)}")
        print(f"自动确认: {'是' if args.auto else '否'}\n")
        
        results = auto_tag(path, args.platforms)
        
        print(f"\n{'='*60}")
        print(f"处理完成")
        print(f"{'='*60}")
        
        success_count = sum(1 for r in results if r["status"] == "success")
        failed_count = sum(1 for r in results if r["status"] == "failed")
        
        print(f"\n成功: {success_count}")
        print(f"失败: {failed_count}")
        print(f"总计: {len(results)}")
        
        if failed_count > 0:
            print(f"\n失败的文件:")
            for r in results:
                if r["status"] == "failed":
                    print(f"  - {r['file_name']}: {r.get('message', '未知错误')}")
    
    else:
        print("错误: 请使用 --all 参数来处理文件夹")


if __name__ == "__main__":
    main()
