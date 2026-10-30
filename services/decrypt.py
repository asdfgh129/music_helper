# -*- coding: utf-8 -*-
"""
解密服务 - 合并原 vip_decrypt.py 与 decrypto 调用

相比旧实现的三个关键修正：
1. 只把「本次运行新产生」的文件搬回原目录（旧实现会把 TEMP 顶层所有文件搬走）；
2. 加密原文件解密成功后默认搬回 VIP 下载目录（config.ENCRYPTED_SOURCE_MODE 可改为
   trash=移入回收站 / keep=留在临时目录），失败则一律原样归还 VIP 目录；
3. 所有 subprocess 调用带超时并检查 returncode。

注意：归还与清理都只针对「本次运行移入临时目录的那几个文件」，不会遍历 VIP 目录或
临时目录顶层，因此不会误搬用户的其他文件。
"""

import os
import subprocess
import time
from dataclasses import dataclass

import config
import core.scan as scanner
from core.ops import Plan


@dataclass
class DecryptResult:
    name: str
    encrypted: int = 0
    produced: int = 0
    ok: bool = False
    message: str = ''

    def summary(self):
        state = '成功' if self.ok else '失败'
        return f'{self.name}: {state}（加密 {self.encrypted} / 产出 {self.produced}）{self.message}'


def _snapshot(directory):
    """目录内全部文件的相对路径快照"""
    result = set()
    if not os.path.isdir(directory):
        return result
    for root, _, files in os.walk(directory):
        for name in files:
            result.add(os.path.relpath(os.path.join(root, name), directory))
    return result


def _run(cmd, logger=None):
    if logger:
        logger.info(f'执行命令: {" ".join(str(part) for part in cmd)}')
    try:
        completed = subprocess.run(
            [str(part) for part in cmd],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=config.SUBPROCESS_TIMEOUT,
            check=False,
        )
    except FileNotFoundError:
        return None, f'找不到可执行文件: {cmd[0]}'
    except subprocess.TimeoutExpired:
        return None, f'执行超时（>{config.SUBPROCESS_TIMEOUT}s）'

    if logger:
        if completed.stdout:
            logger.info(f'标准输出:\n{completed.stdout.strip()}')
        if completed.stderr:
            logger.warning(f'标准错误:\n{completed.stderr.strip()}')
    return completed, ''


def decrypt_netease(month=None, dry_run=False, logger=None):
    """网易云 .ncm 解密"""
    return _decrypt(
        name='网易云',
        vip_dir=config.NETEASE_VIP_DIR,
        tmp_dir=config.NETEASE_TMP_DIR,
        vip_exts=config.NETEASE_VIP_EXTENSIONS,
        month=month,
        dry_run=dry_run,
        logger=logger,
        runner=lambda: _run([config.UM_EXE, '-i', config.NETEASE_TMP_DIR, '-o', config.TEMP_COMPLETED_DIR], logger),
    )


def decrypt_qq(month=None, dry_run=False, logger=None):
    """QQ 音乐 .mflac/.mgg 解密"""
    return _decrypt(
        name='QQ音乐',
        vip_dir=config.QQ_VIP_DIR,
        tmp_dir=config.QQ_TMP_DIR,
        vip_exts=config.QQ_VIP_EXTENSIONS,
        month=month,
        dry_run=dry_run,
        logger=logger,
        runner=lambda: _run_qq(logger),
    )


def _run_qq(logger=None):
    try:
        from decrypto import run_decrypt
    except Exception as exc:  # noqa: BLE001
        return None, f'decrypto 模块不可用: {exc}'
    try:
        run_decrypt(config.QQ_TMP_DIR, config.TEMP_COMPLETED_DIR, logger=logger)
    except Exception as exc:  # noqa: BLE001
        return None, f'解密异常: {exc}'
    return None, ''


def _decrypt(name, vip_dir, tmp_dir, vip_exts, month, dry_run, logger, runner):
    result = DecryptResult(name=name)

    if not os.path.isdir(vip_dir):
        result.message = f'VIP 目录不存在: {vip_dir}'
        return result

    encrypted = scanner.scan([vip_dir], month=month, with_tags=False,
                             extensions=vip_exts, recursive=False)
    result.encrypted = len(encrypted)
    if not encrypted:
        result.ok = True
        result.message = '没有待解密的加密文件'
        return result

    before = _snapshot(config.TEMP_COMPLETED_DIR)

    move_in = Plan(f'{name}-移入临时目录', dry_run=dry_run,
                   journal_path=config.JOURNAL_PATH, trash_dir=config.TRASH_DIR)
    for track in encrypted:
        move_in.add_move(track.path, os.path.join(tmp_dir, track.filename), '移入解密临时目录')
    move_in.execute()

    if dry_run:
        result.ok = True
        result.message = f'[dry-run] 拟解密 {len(encrypted)} 个文件'
        return result

    started = time.time()
    completed, error = runner()
    if error:
        result.message = error
        _restore(encrypted, tmp_dir, vip_dir)
        return result

    produced = _snapshot(config.TEMP_COMPLETED_DIR) - before
    result.produced = len(produced)
    result.ok = bool(produced) or (completed is not None and completed.returncode == 0)
    if not result.ok:
        result.message = f'未产生解密文件（返回码 {getattr(completed, "returncode", "?")}）'
        _restore(encrypted, tmp_dir, vip_dir)
        return result

    # 解密成功：加密原文件按配置处理
    cleanup = Plan(f'{name}-处理加密原文件',
                   journal_path=config.JOURNAL_PATH, trash_dir=config.TRASH_DIR)
    mode = (config.ENCRYPTED_SOURCE_MODE or 'return').lower()
    returned = 0
    for track in encrypted:
        leftover = os.path.join(tmp_dir, track.filename)
        if not os.path.exists(leftover):
            continue
        if mode == 'trash':
            cleanup.add_trash(leftover, '解密完成，加密原文件入回收站')
        elif mode == 'keep':
            continue
        else:  # return（默认）：搬回 VIP 下载目录
            target = os.path.join(vip_dir, track.filename)
            cleanup.add_move(leftover, target, '解密完成，加密原文件归还 VIP 下载目录')
            returned += 1
    cleanup.execute()

    result.message = f'耗时 {time.time() - started:.1f}s'
    if returned:
        result.message += f'，加密原文件已归还 {returned} 个'
    if logger:
        logger.info(result.summary())
    return result


def _restore(encrypted, tmp_dir, vip_dir):
    """解密失败时把加密文件原样还回 VIP 目录"""
    restore = Plan('还原加密文件', journal_path=config.JOURNAL_PATH, trash_dir=config.TRASH_DIR)
    for track in encrypted:
        leftover = os.path.join(tmp_dir, track.filename)
        if os.path.exists(leftover):
            restore.add_move(leftover, os.path.join(vip_dir, track.filename), '解密失败，原样归还')
    restore.execute()
