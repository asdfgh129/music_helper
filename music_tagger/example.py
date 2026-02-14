# -*- coding: utf-8 -*-
"""
Music Tagger 使用示例
"""

from music_tagger import (
    MusicTagger,
    MusicResource,
    SmartTagClient,
    auto_tag,
    batch_update_tags,
    match_score,
)


# ==================== 示例1: 读取音乐文件信息 ====================
print("=" * 60)
print("示例1: 读取音乐文件信息")
print("=" * 60)

try:
    tagger = MusicTagger("song.mp3")
    print(f"标题: {tagger.title}")
    print(f"艺术家: {tagger.artist}")
    print(f"专辑: {tagger.album}")
    print(f"年份: {tagger.year}")
    print(f"时长: {tagger.duration}秒")
    
    # 获取所有信息
    info = tagger.to_dict()
    print(f"\n完整信息: {info}")
except FileNotFoundError:
    print("请确保存在 song.mp3 文件")


# ==================== 示例2: 在线搜索音乐 ====================
print("\n" + "=" * 60)
print("示例2: 在线搜索音乐")
print("=" * 60)

# 从网易云音乐搜索
songs = MusicResource("netease").fetch_id3_by_title("告白气球")
print(f"\n网易云音乐搜索结果 ({len(songs)}条):")
for song in songs[:5]:  # 只显示前5条
    print(f"  - {song['name']} - {song['artist']} - {song['album']}")

# 从QQ音乐搜索
songs = MusicResource("qmusic").fetch_id3_by_title("告白气球")
print(f"\nQQ音乐搜索结果 ({len(songs)}条):")
for song in songs[:5]:
    print(f"  - {song['name']} - {song['artist']} - {song['album']}")


# ==================== 示例3: 智能匹配 ====================
print("\n" + "=" * 60)
print("示例3: 智能匹配(多平台并行)")
print("=" * 60)

client = SmartTagClient()
results = client.fetch_id3_by_title({
    "title": "告白气球",
    "full_path": "song.mp3"  # 用于本地标签匹配
})

print(f"\n智能匹配结果 (按匹配度排序):")
for i, song in enumerate(results, 1):
    print(f"{i}. [{song['resource']}] {song['name']} - {song['artist']}")
    print(f"   专辑: {song['album']}")
    print(f"   匹配度: {song['score']}")


# ==================== 示例4: 更新音乐文件标签 ====================
print("\n" + "=" * 60)
print("示例4: 更新音乐文件标签")
print("=" * 60)

try:
    tagger = MusicTagger("song.mp3")
    
    # 更新标签
    tagger.update_tags({
        "title": "新标题",
        "artist": "周杰伦",
        "album": "周杰伦的床边故事",
        "year": "2016",
        "genre": "Pop",
        "lyrics": "歌词内容...",
        # "album_img": "http://example.com/cover.jpg",  # 封面URL或Base64
    })
    
    print("标签更新成功!")
except FileNotFoundError:
    print("请确保存在 song.mp3 文件")


# ==================== 示例5: 批量自动匹配 ====================
print("\n" + "=" * 60)
print("示例5: 批量自动匹配")
print("=" * 60)

# results = auto_tag(
#     music_folder="./music",
#     source_list=["qmusic", "netease", "migu", "kugou"],
#     select_mode="strict"
# )

# for result in results:
#     status = "✓" if result['status'] == 'success' else '✗'
#     print(f"{status} {result['file_name']}: {result['status']}")
#     if result['message']:
#         print(f"  错误: {result['message']}")


# ==================== 示例6: 批量更新标签 ====================
print("\n" + "=" * 60)
print("示例6: 批量更新标签")
print("=" * 60)

# batch_update_tags([
#     {
#         "file_full_path": "./music/song1.mp3",
#         "title": "歌曲1",
#         "artist": "艺术家1",
#         "album": "专辑1"
#     },
#     {
#         "file_full_path": "./music/song2.mp3",
#         "title": "歌曲2",
#         "artist": "艺术家2",
#         "album": "专辑2"
#     }
# ])
# print("批量更新完成!")


# ==================== 示例7: 模板语法 ====================
print("\n" + "=" * 60)
print("示例7: 模板语法(变量替换)")
print("=" * 60)

try:
    tagger = MusicTagger("song.mp3")
    
    # 使用模板语法, ${变量名} 会被实际值替换
    tagger.update_tags({
        "filename": "${artist} - ${title}",  # 文件重命名为 "艺术家 - 歌曲名"
        "albumartist": "${artist}",  # 专辑艺术家使用艺术家字段
    })
    
    print("模板语法应用成功!")
except FileNotFoundError:
    print("请确保存在 song.mp3 文件")


# ==================== 示例8: 匹配算法 ====================
print("\n" + "=" * 60)
print("示例8: 字符串匹配算法")
print("=" * 60)

score = match_score("告白气球", "告白气球")
print(f"'告白气球' vs '告白气球': {score} (完全匹配)")

score = match_score("告白气球", "周杰伦 - 告白气球")
print(f"'告白气球' vs '周杰伦 - 告白气球': {score} (包含匹配)")

score = match_score("告白气球", "稻香")
print(f"'告白气球' vs '稻香': {score} (不匹配)")


print("\n" + "=" * 60)
print("所有示例运行完成!")
print("=" * 60)
