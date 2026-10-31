# -*- coding: utf-8 -*-
"""
操作计划模块 - 所有破坏性动作的唯一出口

设计原则：
1. core 层只负责生成 Operation，不直接读写文件系统；
2. 真正执行集中在 Plan.execute()，逐条记录到 journal（JSONL）；
3. 删除一律走回收站目录，永不调用 os.remove；
4. 支持 dry_run，先出计划再执行。
"""

import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime

from core.naming import is_audio

MOVE = 'move'
RENAME = 'rename'
TRASH = 'trash'


@dataclass
class Operation:
    action: str
    src: str
    dst: str = ''
    reason: str = ''

    def describe(self):
        arrow = f' -> {self.dst}' if self.dst else ''
        note = f'  # {self.reason}' if self.reason else ''
        return f'[{self.action}] {os.path.basename(self.src)}{arrow}{note}'


@dataclass
class PlanResult:
    done: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    failed: list = field(default_factory=list)

    @property
    def total(self):
        return len(self.done) + len(self.skipped) + len(self.failed)

    def summary(self):
        return f'完成 {len(self.done)} / 跳过 {len(self.skipped)} / 失败 {len(self.failed)}'


def _unique_path(path):
    """目标已存在时追加 _1/_2 后缀"""
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    index = 1
    while os.path.exists(f'{stem}_{index}{ext}'):
        index += 1
    return f'{stem}_{index}{ext}'


class Plan:
    """一批文件操作的执行计划"""

    def __init__(self, name, dry_run=False, journal_path=None, trash_dir=None):
        self.name = name
        self.dry_run = dry_run
        self.operations = []
        self.journal_path = journal_path
        self.trash_dir = trash_dir

    # ---------- 收集 ----------

    def add_move(self, src, dst, reason=''):
        if os.path.normpath(src) != os.path.normpath(dst):
            self.operations.append(Operation(MOVE, src, dst, reason))

    def add_rename(self, src, new_name, reason=''):
        dst = os.path.join(os.path.dirname(src), new_name)
        if os.path.normpath(src) != os.path.normpath(dst):
            self.operations.append(Operation(RENAME, src, dst, reason))

    def add_trash(self, src, reason=''):
        self.operations.append(Operation(TRASH, src, '', reason))

    def __len__(self):
        return len(self.operations)

    def __iter__(self):
        return iter(self.operations)

    @property
    def is_empty(self):
        return not self.operations

    def describe(self, limit=30):
        lines = [op.describe() for op in self.operations[:limit]]
        if len(self.operations) > limit:
            lines.append(f'... 其余 {len(self.operations) - limit} 条省略')
        return '\n'.join(lines)

    # ---------- 执行 ----------

    def execute(self):
        result = PlanResult()

        if self.dry_run:
            result.skipped.extend(self.operations)
            return result

        for op in self.operations:
            try:
                done = self._apply(op)
                if done:
                    result.done.append(op)
                else:
                    result.skipped.append(op)
            except Exception as exc:  # noqa: BLE001 - 单条失败不影响整批
                op.reason = f'{op.reason} | 失败: {exc}'
                result.failed.append(op)
                self._journal(op, False, str(exc))
        return result

    def _apply(self, op):
        if not os.path.exists(op.src):
            return False

        if op.action == TRASH:
            if not self.trash_dir:
                raise RuntimeError('未配置回收站目录，拒绝删除')
            os.makedirs(self.trash_dir, exist_ok=True)
            dst = _unique_path(os.path.join(self.trash_dir, os.path.basename(op.src)))
        else:
            dst = _unique_path(op.dst)
            parent = os.path.dirname(dst)
            if parent:
                os.makedirs(parent, exist_ok=True)

        op.dst = dst
        shutil.move(op.src, dst)
        self._move_companion_lrc(op.src, dst)
        self._journal(op, True, '')
        return True

    @staticmethod
    def _move_companion_lrc(src, dst):
        """音频移动时同步搬走同名 .lrc"""
        if not is_audio(src):
            return
        src_lrc = os.path.splitext(src)[0] + '.lrc'
        if not os.path.exists(src_lrc):
            return
        dst_lrc = _unique_path(os.path.splitext(dst)[0] + '.lrc')
        try:
            shutil.move(src_lrc, dst_lrc)
        except Exception:  # noqa: BLE001 - 歌词失败不影响主文件
            pass

    def _journal(self, op, ok, error):
        if not self.journal_path:
            return
        record = {
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'plan': self.name,
            'action': op.action,
            'src': op.src,
            'dst': op.dst,
            'reason': op.reason,
            'ok': ok,
            'error': error,
        }
        try:
            os.makedirs(os.path.dirname(self.journal_path), exist_ok=True)
            with open(self.journal_path, 'a', encoding='utf-8') as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + '\n')
        except Exception:  # noqa: BLE001 - 日志失败不能影响主流程
            pass


def copy_items(items, logger=None):
    """按 (src, dst) 列表拷贝文件，返回成功条数

    拷贝不属于破坏性操作，因此不进 Plan，但仍统一处理重名与歌词伴随。
    """
    copied = 0
    for src, dst in items:
        if not os.path.exists(src):
            continue
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            final = _unique_path(dst)
            shutil.copy2(src, final)
            src_lrc = os.path.splitext(src)[0] + '.lrc'
            if os.path.exists(src_lrc):
                shutil.copy2(src_lrc, _unique_path(os.path.splitext(final)[0] + '.lrc'))
            copied += 1
            if logger:
                logger.info(f'拷贝: {src} -> {final}')
        except Exception as exc:  # noqa: BLE001
            if logger:
                logger.error(f'拷贝失败 {src}: {exc}')
    return copied

