# -*- coding: utf-8 -*-
"""
标签更新模块 - 从声纹和在线数据库更新标签
"""

import os
from config import (
    mutagen_available,
    fingerprint_matcher_available, music_tagger_available,
    FingerprintMatcher, MusicTagger, QQMusicApi, NetEaseMusicClient,
    AUDIO_EXTENSIONS, TEMP_COMPLETED_DIR
)
from utils import main_logger, create_operation_log, parse_filename
from metadata import get_music_metadata, set_music_metadata, MP3, FLAC
from tag_fetcher import (
    parse_musicbrainz_recording, fetch_qq_music_tags,
    fetch_netease_tags, fetch_album_cover
)


def update_tags_from_fingerprint(target_dir=None):
    """根据声纹信息从在线数据库更新标签

    Args:
        target_dir: 要扫描的目录，默认为TEMP_COMPLETED_DIR
    """
    if target_dir is None:
        target_dir = TEMP_COMPLETED_DIR

    main_logger.info(f'开始从声纹信息更新标签，目标目录: {target_dir}')
    op_logger = create_operation_log('UpdateTags')

    if not mutagen_available:
        main_logger.error('mutagen库未安装，无法更新标签')
        return 0, 0, 0

    success_count = 0
    fail_count = 0
    incomplete_tags = []
    failed_files = []
    fingerprint_success_count = 0
    online_success_count = 0

    # 初始化指纹匹配器
    fingerprint_matcher = None
    if fingerprint_matcher_available:
        fingerprint_matcher = FingerprintMatcher()
        main_logger.info('声纹匹配器已初始化')
    else:
        main_logger.warning('声纹匹配模块不可用，将跳过指纹查询')

    # 初始化音乐API客户端
    qq_api = None
    netease_api = None
    if fingerprint_matcher_available:
        try:
            qq_api = QQMusicApi()
            netease_api = NetEaseMusicClient()
            main_logger.info('音乐API客户端已初始化')
        except Exception as e:
            main_logger.warning(f'音乐API客户端初始化失败: {e}')

    # 扫描目标目录
    for root, _, files in os.walk(target_dir):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext not in AUDIO_EXTENSIONS:
                continue

            filepath = os.path.join(root, file)
            op_logger.info(f'处理文件: {filepath}')

            try:
                # 获取当前标签
                current_tags = get_music_metadata(filepath)
                if not current_tags:
                    # 从文件名解析
                    artist, title = parse_filename(file)
                    current_tags = {
                        'title': title,
                        'artist': artist,
                        'album': '',
                        'year': '',
                        'genre': ''
                    }

                # 第一步：尝试使用声纹查询MusicBrainz
                tag_updated = False
                if fingerprint_matcher:
                    try:
                        op_logger.info(f'  尝试声纹查询: {file}')
                        result = fingerprint_matcher.match_file(filepath)

                        if result.success and result.recordings:
                            # 选择最佳匹配（分数最高的）
                            best_recording = max(result.recordings, key=lambda x: x.get('score', 0))
                            score = best_recording.get('score', 0)

                            if score >= 50:  # 分数阈值
                                op_logger.info(f'  声纹匹配成功 (分数: {score:.1f}%)')

                                # 解析MusicBrainz记录
                                new_tags = parse_musicbrainz_recording(best_recording)

                                if new_tags:
                                    # 更新标签
                                    set_music_metadata(filepath, new_tags)
                                    tag_updated = True
                                    fingerprint_success_count += 1
                                    op_logger.info(f'  标签已从MusicBrainz更新: {new_tags.get("artist")} - {new_tags.get("title")}')

                                # 尝试下载封面
                                if music_tagger_available and new_tags.get('album'):
                                    try:
                                        tagger = MusicTagger(filepath)
                                        album_artists = []
                                        for artist_credit in best_recording.get('artist-credit', []):
                                            album_artists.append(artist_credit.get('artist', {}).get('name', ''))

                                        # 从QQ音乐或网易云音乐获取封面
                                        cover_url = fetch_album_cover(
                                            qq_api, netease_api,
                                            new_tags.get('title', ''),
                                            new_tags.get('artist', '')
                                        )

                                        if cover_url:
                                            op_logger.info(f'  已下载封面: {cover_url[:50]}...')
                                    except Exception as e:
                                        op_logger.warning(f'  下载封面失败: {e}')
                            else:
                                op_logger.info(f'  声纹匹配分数较低 ({score:.1f}%)，尝试其他方式')
                        else:
                            op_logger.info(f'  声纹查询无结果，尝试其他方式')
                    except Exception as e:
                        op_logger.warning(f'  声纹查询失败: {e}')

                # 第二步：如果声纹查询失败，使用歌曲名和歌手从音乐网站查询
                if not tag_updated and qq_api and netease_api:
                    try:
                        op_logger.info(f'  尝试在线音乐平台查询: {file}')

                        # 获取查询信息（优先使用标签信息，否则使用文件名）
                        title = current_tags.get('title', '')
                        artist = current_tags.get('artist', '')

                        if not title:
                            artist, title = parse_filename(file)

                        if title:
                            # 优先尝试QQ音乐
                            tag_info = fetch_qq_music_tags(qq_api, title, artist)
                            source = 'QQ音乐'

                            # 如果QQ音乐失败，尝试网易云音乐
                            if not tag_info:
                                tag_info = fetch_netease_tags(netease_api, title, artist)
                                source = '网易云音乐'

                            if tag_info:
                                # 更新标签
                                set_music_metadata(filepath, tag_info)
                                tag_updated = True
                                online_success_count += 1
                                op_logger.info(f'  标签已从{source}更新: {tag_info.get("artist")} - {tag_info.get("title")}')

                                # 尝试下载封面
                                if music_tagger_available and tag_info.get('album_img'):
                                    try:
                                        tagger = MusicTagger(filepath)
                                        tagger.update_tags({
                                            'album_img': tag_info['album_img']
                                        }, is_raw_thumbnail=False)
                                        op_logger.info(f'  已从{source}下载封面')
                                    except Exception as e:
                                        op_logger.warning(f'  下载封面失败: {e}')
                        else:
                            op_logger.warning(f'  无法确定歌曲名称，跳过在线查询')
                    except Exception as e:
                        op_logger.warning(f'  在线查询失败: {e}')

                # 检查标签完整性
                updated_tags = get_music_metadata(filepath) if tag_updated else current_tags
                missing_fields = []
                if updated_tags is not None and not updated_tags.get('title'):
                    missing_fields.append('歌曲名')
                if updated_tags is not None and not updated_tags.get('artist'):
                    missing_fields.append('歌手')
                if updated_tags is not None and not updated_tags.get('year'):
                    missing_fields.append('年份')

                # 检查封面（仅对MP3和FLAC）
                has_cover = False
                if ext == '.mp3':
                    try:
                        audio = MP3(filepath)
                        if audio.tags and any('APIC' in key for key in audio.tags.keys()):
                            has_cover = True
                    except Exception:
                        pass
                elif ext == '.flac':
                    try:
                        audio = FLAC(filepath)
                        if audio.pictures:
                            has_cover = True
                    except Exception:
                        pass

                if not has_cover:
                    missing_fields.append('封面')

                if missing_fields:
                    incomplete_tags.append({
                        'filepath': filepath,
                        'filename': file,
                        'missing': missing_fields,
                        'current_tags': updated_tags
                    })
                    op_logger.warning(f'标签不完整: {file} - 缺少: {", ".join(missing_fields)}')

                success_count += 1
                op_logger.info(f'处理完成: {file}')

            except Exception as e:
                fail_count += 1
                failed_files.append({'filepath': filepath, 'error': str(e)})
                op_logger.error(f'标签更新失败 {file}: {e}')

    # 记录统计信息
    op_logger.info(f'\n{"="*50}')
    op_logger.info(f'标签更新统计:')
    op_logger.info(f'处理总数: {success_count + fail_count}')
    op_logger.info(f'成功: {success_count}')
    op_logger.info(f'失败: {fail_count}')
    op_logger.info(f'  - 声纹匹配成功: {fingerprint_success_count}')
    op_logger.info(f'  - 在线查询成功: {online_success_count}')

    if incomplete_tags:
        op_logger.info(f'\n标签不完整的文件 ({len(incomplete_tags)} 个):')
        for item in incomplete_tags:
            op_logger.info(f"  - {item['filename']}: 缺少 {', '.join(item['missing'])}")

    if failed_files:
        op_logger.info(f'\n更新失败的文件 ({len(failed_files)} 个):')
        for item in failed_files:
            op_logger.info(f"  - {item['filepath']}: {item['error']}")

    main_logger.info(f'标签更新完成: 成功 {success_count}, 失败 {fail_count}, 声纹 {fingerprint_success_count}, 在线 {online_success_count}')
    return success_count, fail_count, fingerprint_success_count + online_success_count
