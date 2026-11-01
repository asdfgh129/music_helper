# -*- coding: utf-8 -*-
"""
检查模块 - 实现规划中的模块 2/3/4/5/6

一次遍历产出一份 CheckResult，再由 plan_fixes() 把「需要处理的动作」写进
Plan、由 report_into() 渲染成报告。检查本身不改动任何文件。
"""

import os
from dataclasses import dataclass, field

import core.tags as core_tags
from core import dedupe as dedupe_mod
from core import lyrics as lyrics_mod
from core.naming import (
    artist_tokens,
    canonicalize,
    format_filename,
    is_canonical,
    is_placeholder_artist,
    normalize_text,
    parse_filename,
)

KIND_FILENAME = '文件名格式'
KIND_MISMATCH = '文件名与标签不一致'
KIND_TAGS = '标签不完整'
KIND_DUP = '重复文件'
KIND_NO_LRC = '缺少歌词'
KIND_ORPHAN_LRC = '孤立歌词'

# Markdown 正文最多列这么多行，其余只进 CSV：大库上否则会生成上万行的表格
MAX_TABLE_ROWS = 200


@dataclass
class Finding:
    kind: str
    path: str
    detail: str
    fixable: bool = False
    severe: bool = False          # 是否属于「必须人工处理」级别（核心标签缺失/标签矛盾）
    track: object = None


@dataclass
class CheckResult:
    findings: list = field(default_factory=list)
    groups: list = field(default_factory=list)

    def add(self, kind, path, detail, fixable=False, severe=False, track=None):
        self.findings.append(Finding(kind, path, detail, fixable, severe, track))

    def by_kind(self, kind):
        return [item for item in self.findings if item.kind == kind]

    def counts(self):
        summary = {}
        for item in self.findings:
            summary[item.kind] = summary.get(item.kind, 0) + 1
        return summary


READY_FIELDS = (('title', '歌曲名'), ('artist', '歌手'),
                ('album', '专辑'), ('year', '年份'))


def _artist_conflict(file_artist, tag_artist):
    """文件名歌手与标签歌手是否矛盾

    三条放行规则，都是「宁可漏判不做误判」：
    1. 任一侧是「群星/未知」这类占位串 -> 不可比，放行；
    2. token 有交集 -> 一致（`周杰伦 & 方文山` vs `周杰伦`）；
    3. 任一 token 互为子串 -> 一致（`周杰伦` vs `周杰伦 (Jay Chou)`、`周杰伦 feat. 杨瑞代`）。
    """
    if is_placeholder_artist(file_artist) or is_placeholder_artist(tag_artist):
        return False

    file_tokens = artist_tokens(file_artist)
    tag_tokens = artist_tokens(tag_artist)
    if not file_tokens or not tag_tokens:
        return False
    if file_tokens & tag_tokens:
        return False
    for left in file_tokens:
        for right in tag_tokens:
            if left in right or right in left:
                return False
    return True


def _consistency_problem(track):
    """文件名与标签是否矛盾，返回问题描述或 None"""
    file_artist, file_title = parse_filename(track.filename)
    tag_artist, tag_title = track.artist, track.title

    if file_artist and tag_artist and _artist_conflict(file_artist, tag_artist):
        return f'歌手: 文件名「{file_artist}」≠ 标签「{tag_artist}」'

    file_norm, tag_norm = normalize_text(file_title), normalize_text(tag_title)
    if file_norm and tag_norm and file_norm != tag_norm:
        if file_norm not in tag_norm and tag_norm not in file_norm:
            return f'歌名: 文件名「{file_title}」≠ 标签「{tag_title}」'
    return None


def readiness_problems(track):
    """判断是否达到「可入库」标准：核心标签齐全、年份可解析、文件名与标签不矛盾

    封面与歌词不参与判定——它们缺失时只提示，不应把文件挡在 INCOMPLETE_DIR 之外。
    年份必须能解析成 1900-2100 的四位数字，否则归档阶段进不了年份目录，
    会出现「判定可入库、却落进 unknown/」的两套结论。
    """
    problems = [f'缺少{label}' for key, label in READY_FIELDS if not track.tag(key)]
    year = track.tag('year')
    if year and not track.year_int:
        problems.append(f'年份无法解析: {year}（需 1900-2100）')
    mismatch = _consistency_problem(track)
    if mismatch:
        problems.append(mismatch)
    return problems


def _filename_from_tags(track):
    """按标签生成规范文件名，返回文件名（含扩展名）或 None

    只在「标签可信」时给出建议：歌名、歌手齐全且与现有文件名不矛盾。
    标签本身自相矛盾时按标签改名，等于把错的那份写到文件名上。
    """
    if not track.title or not track.artist or _consistency_problem(track):
        return None
    name = format_filename(track.artist, track.title, track.ext)
    if not name or os.path.normcase(name) == os.path.normcase(track.filename):
        return None
    return name


def check_library(tracks, directories=None, tolerance=None, check_tags=True,
                  check_lyrics=True, check_duplicates=True):
    """对一批曲目做全套检查

    Args:
        tracks: core.scan.scan() 的结果
        directories: 歌词孤立检查使用的目录（默认取曲目所在目录集合）
        tolerance: 重复判定允许的时长误差
        check_tags: 是否检测标签完整性与文件名一致性
        check_lyrics: 是否检测歌词
        check_duplicates: 是否检测重复
    """
    from config import DURATION_TOLERANCE

    result = CheckResult()
    tolerance = DURATION_TOLERANCE if tolerance is None else tolerance

    for track in tracks:
        if not is_canonical(track.filename):
            target = canonicalize(track.filename)
            if target:
                detail = f'建议改为: {target}'
            else:
                target = _filename_from_tags(track)
                detail = (f'建议改为: {target}（按标签）' if target
                          else '缺少「歌手 - 歌名」结构')
            result.add(KIND_FILENAME, track.path, detail,
                       fixable=bool(target), track=track)

        if check_tags:
            missing = core_tags.missing_tag_fields(track)
            if missing:
                # 只有「歌曲名/歌手」缺失才算严重，缺封面之类的仅提示，不挪动文件
                severe = any(label in ('歌曲名', '歌手') for label in missing)
                result.add(KIND_TAGS, track.path, '缺少: ' + '/'.join(missing),
                           severe=severe, track=track)

            problem = _consistency_problem(track)
            if problem:
                result.add(KIND_MISMATCH, track.path, problem, severe=True, track=track)

    if check_lyrics:
        for track in lyrics_mod.missing_lrc(tracks):
            result.add(KIND_NO_LRC, track.path, '没有同名 .lrc', track=track)
        for path in lyrics_mod.orphan_lrc(directories or sorted({t.dirpath for t in tracks})):
            result.add(KIND_ORPHAN_LRC, path, '没有对应音频文件')

    if check_duplicates:
        result.groups = dedupe_mod.find_duplicates(tracks, tolerance)
        for group in result.groups:
            for track in group.drop:
                if group.duration_unknown:
                    reason = '时长未知，需人工确认'
                else:
                    reason = f'{track.duration:.1f}s'
                result.add(KIND_DUP, track.path,
                           f'{group.kind}重复，保留 {group.keep.filename}（{reason}）',
                           track=track)

    return result


def plan_fixes(result, plan, review_dir=None, rename_canonical=True,
               move_bad=False, delete_duplicates=False, dup_dir=None,
               rename_by_tags=False):
    """把检查结果转成动作

    Args:
        plan: core.ops.Plan 实例
        review_dir: 不一致文件的目标目录；为 None 则不移动
        dup_dir: 重复文件目标目录，默认与 review_dir 相同
        rename_canonical: 是否把单个 '-' 的文件名规范化为 ' - '
        move_bad: 是否把标签不完整/文件名不一致的文件移入 review_dir
        delete_duplicates: 重复文件是否移入回收站（默认不动，只报告）
        rename_by_tags: 文件名缺歌手结构时，是否按标签全名重写（仅标签可信时生效）
    """
    planned = set()

    # 1. 重复文件优先级最高：先确定「移走」还是「回收站」，避免同一文件被多个规则重复处理
    for group in result.groups:
        # 时长读不出来多半是损坏文件，与同名曲目「可能」重复，交给人工，不自动搬运
        if group.duration_unknown:
            continue
        for track in group.drop:
            # --trash-dup 是显式指令，优先级高于「移入待处理目录」的默认行为
            if delete_duplicates:
                plan.add_trash(track.path, f'重复于 {group.keep.filename}')
                planned.add(track.path)
            elif move_bad and (dup_dir or review_dir):
                target_root = dup_dir or review_dir
                plan.add_move(track.path, os.path.join(target_root, KIND_DUP, track.filename),
                              f'重复于 {group.keep.filename}')
                planned.add(track.path)

    # 2. 核心标签缺失 / 文件名与标签矛盾 -> 移入待处理目录（缺封面这类只提示不动文件）
    if move_bad and review_dir:
        for item in result.findings:
            if item.kind not in (KIND_TAGS, KIND_MISMATCH) or item.path in planned:
                continue
            if not item.severe:
                continue
            plan.add_move(item.path,
                          os.path.join(review_dir, item.kind, os.path.basename(item.path)),
                          item.detail)
            planned.add(item.path)

    # 3. 最后才对「留下不动」的文件做命名规范化
    if rename_canonical:
        for item in result.findings:
            if item.kind != KIND_FILENAME or not item.fixable or item.path in planned:
                continue
            target = canonicalize(os.path.basename(item.path))
            if not target and rename_by_tags and item.track is not None:
                target = _filename_from_tags(item.track)
            if target:
                plan.add_rename(item.path, target, '规范为「歌手 - 歌名」')
                planned.add(item.path)


def report_into(result, report):
    """把 CheckResult 渲染进 Report"""
    for kind in (KIND_FILENAME, KIND_TAGS, KIND_MISMATCH, KIND_DUP, KIND_NO_LRC, KIND_ORPHAN_LRC):
        items = result.by_kind(kind)
        report.add_summary(kind, len(items))
        if not items:
            continue
        rows = [(item.path, item.detail) for item in items]
        note = ''
        if len(rows) > MAX_TABLE_ROWS:
            note = (f'共 {len(rows)} 条，正文只列前 {MAX_TABLE_ROWS} 条，'
                    f'完整清单见同目录下的 review-*.csv')
            rows = rows[:MAX_TABLE_ROWS]
        report.add(f'{kind}（{len(items)}）', ['文件', '说明'], rows, note=note)
        report.add_review(f'{kind}清单', [(kind, item.path, item.detail) for item in items])
    return report
