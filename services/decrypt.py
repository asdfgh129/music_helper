# -*- coding: utf-8 -*-
"""
解密服务 - 合并原 vip_decrypt.py 与 decrypto 调用

相比旧实现的三个关键修正：
1. 只把「本次运行新产生」的文件搬回原目录（旧实现会把 TEMP 顶层所有文件搬走）；
2. 加密原文件解密成功后默认搬回 VIP 下载目录（config.ENCRYPTED_SOURCE_MODE 可改为
   trash=移入回收站 / keep=留在暂存区），失败则一律原样归还 VIP 目录；
3. 所有 subprocess 调用带超时并检查 returncode。

注意：归还与清理都只针对「本次运行移入暂存区的那几个文件」，不会遍历 VIP 目录或
暂存区顶层，因此不会误搬用户的其他文件。

外部程序：网易云的 `.ncm` 三平台都调 `um`（`decrypto/um.py` 负责按平台取程序并预检）；
QQ 由 `decrypto/qq.py` 自己选通道——Windows 优先 Frida，其余情况用 `um` 离线解密。
本模块不判断平台，只负责编排与加密原文件的去向。
"""

import os
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


def _snapshot(directory, exclude=None):
    """目录内全部文件的相对路径快照（可排除解密暂存子目录）"""
    result = set()
    if not os.path.isdir(directory):
        return result
    excluded = os.path.abspath(exclude) if exclude else None
    for root, _, files in os.walk(directory):
        if excluded and (os.path.abspath(root) == excluded
                         or os.path.abspath(root).startswith(excluded + os.sep)):
            continue
        for name in files:
            result.add(os.path.relpath(os.path.join(root, name), directory))
    return result


def decrypt_netease(month=None, dry_run=False, logger=None):
    """网易云 .ncm 解密（um，三平台同一套参数）"""
    return _decrypt(
        name='网易云',
        vip_dir=config.NETEASE_VIP_DIR,
        tmp_dir=config.NETEASE_STAGING_DIR,
        vip_exts=config.NETEASE_VIP_EXTENSIONS,
        month=month,
        dry_run=dry_run,
        logger=logger,
        runner=lambda: _run_um(config.NETEASE_STAGING_DIR, config.WORKSPACE_DIR, logger),
    )


def _run_um(input_dir, output_dir, logger=None):
    """调 um 解密一个目录（.ncm 不需要 mmkv 与密钥）"""
    try:
        from decrypto import um
    except Exception as exc:  # noqa: BLE001
        return None, f'um 解密模块不可用: {exc}'
    return um.run(input_dir, output_dir, mmkv='', key='', logger=logger)


def decrypt_qq(month=None, dry_run=False, logger=None):
    """QQ 音乐 .mflac/.mgg 解密"""
    return _decrypt(
        name='QQ音乐',
        vip_dir=config.QQ_VIP_DIR,
        tmp_dir=config.QQ_STAGING_DIR,
        vip_exts=config.QQ_VIP_EXTENSIONS,
        month=month,
        dry_run=dry_run,
        logger=logger,
        runner=lambda: _run_qq(logger),
        precheck=lambda: _precheck_qq(logger),
    )


def _precheck_qq(logger=None):
    """解密前检查客户端是否安装/启动/已登录

    放在搬运文件之前，环境不就绪就直接跳过——否则会白搬一趟（虽然会还原）。
    检查逻辑全部在 decrypto/qq_client.py，这里只做结果转换。
    """
    try:
        from decrypto import qq_client
    except Exception as exc:  # noqa: BLE001 - 模块问题交给 runner 报错
        if logger:
            logger.debug(f'qq_client 不可用: {exc}')
        return True, ''
    try:
        ready = qq_client.ensure_ready(logger)
    except Exception as exc:  # noqa: BLE001
        return False, f'QQ 音乐环境检查失败: {exc}'
    if ready:
        return True, ''
    return False, 'QQ 音乐环境未就绪（未安装 / 未启动 / 未登录），已跳过解密'


def _run_qq(logger=None):
    try:
        from decrypto import run_decrypt
    except Exception as exc:  # noqa: BLE001
        return None, f'decrypto 模块不可用: {exc}'
    try:
        # 环境已由 _precheck_qq 检查过，这里不再重复启动/等待
        run_decrypt(config.QQ_STAGING_DIR, config.WORKSPACE_DIR, logger=logger,
                    ensure_client=False)
    except Exception as exc:  # noqa: BLE001
        return None, f'解密异常: {exc}'
    return None, ''


def _decrypt(name, vip_dir, tmp_dir, vip_exts, month, dry_run, logger, runner,
             precheck=None):
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

    before = _snapshot(config.WORKSPACE_DIR, exclude=tmp_dir)

    move_in = Plan(f'{name}-移入暂存区', dry_run=dry_run,
                   journal_path=config.JOURNAL_PATH, trash_dir=config.TRASH_DIR)
    for track in encrypted:
        move_in.add_move(track.path, os.path.join(tmp_dir, track.filename), '移入解密暂存区')

    if dry_run:
        result.ok = True
        result.message = f'[dry-run] 拟解密 {len(encrypted)} 个文件'
        return result

    # 环境检查放在搬运之前：不就绪时加密文件原地不动
    if precheck:
        ok, message = precheck()
        if not ok:
            result.message = message
            if logger:
                logger.error(message)
            return result

    move_in.execute()

    started = time.time()
    completed, error = runner()
    if error:
        result.message = error
        _restore(encrypted, tmp_dir, vip_dir)
        return result

    produced = _snapshot(config.WORKSPACE_DIR, exclude=tmp_dir) - before
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


# --------------------------------------------------------------------------- #
# 直接解密：VIP 目录 → 目标目录，不经过暂存区                                  #
# --------------------------------------------------------------------------- #

# 加密扩展名 -> 预期产物扩展名；空串表示「由文件内容决定」（.ncm 里可能是 mp3/flac）
_EXPECT_EXT = {'.ncm': '', '.mflac': '.flac', '.mgg': '.ogg'}


def target_info(target):
    """解密目标 -> (名称, VIP 目录, 加密扩展名集合)"""
    if target == 'netease':
        return '网易云', config.NETEASE_VIP_DIR, config.NETEASE_VIP_EXTENSIONS
    if target == 'qq':
        return 'QQ音乐', config.QQ_VIP_DIR, config.QQ_VIP_EXTENSIONS
    raise ValueError(f'未知解密目标: {target}')


def _find_output(stem, output_dir):
    """在目标目录里找该曲目的解密产物（扩展名由内容决定，逐一试）"""
    for ext in sorted(config.AUDIO_EXTENSIONS):
        path = os.path.join(output_dir, stem + ext)
        if os.path.exists(path):
            return path
    return ''


def candidate(target, track, output_dir=None):
    """一个待解密文件的前端视图"""
    output_dir = output_dir or config.WORKSPACE_DIR
    stem, ext = os.path.splitext(track.filename)
    expect_ext = _EXPECT_EXT.get(ext.lower(), '')
    found = _find_output(stem, output_dir)
    return {
        'path': track.path,
        'name': track.filename,
        'stem': stem,
        'size': track.size,
        'ext': ext.lower(),
        'expect': stem + expect_ext if expect_ext else f'{stem}（扩展名由内容决定）',
        'existing': bool(found),
        'existing_path': found,
        'target_dir': output_dir,
    }


def encrypted_candidates(target, month_from=None, month_to=None, output_dir=None):
    """VIP 目录里的待解密文件（不移动任何文件）"""
    _name, vip_dir, exts = target_info(target)
    if not os.path.isdir(vip_dir):
        return []
    tracks = scanner.scan([vip_dir], with_tags=False, recursive=False, extensions=exts,
                          month_from=month_from, month_to=month_to)
    return [candidate(target, track, output_dir) for track in tracks]


def _emit(progress, done, total, item):
    if progress:
        try:
            progress(done, total, item)
        except Exception:  # noqa: BLE001 - 进度回调失败不该中断解密
            pass


def decrypt_direct(target, paths=None, month_from=None, month_to=None, logger=None,
                   progress=None, output_dir=None):
    """把 VIP 目录里的加密文件**直接**解密到工作区，省掉「搬进暂存区再解密」

    与 `decrypt_netease` / `decrypt_qq` 的区别只有一处：不再把加密文件搬到
    `DECRYPT_STAGING_DIR`。原来那条路在 VIP 目录和工作区不同盘时要多付两次
    跨盘复制（搬进去一次、`ENCRYPTED_SOURCE_MODE=return` 时再搬回来一次），
    而 um 本身是「读源文件 → 逐字节写目标文件」，跨不跨盘都能写。

    Args:
        paths: 只解密这些文件；None 表示按月份筛选整个 VIP 目录
        progress: `progress(done, total, item)`，item 为单文件结果
        output_dir: 解密产物落点，默认 WORKSPACE_DIR
    """
    name, vip_dir, _exts = target_info(target)
    output_dir = output_dir or config.WORKSPACE_DIR
    result = DecryptResult(name=name)

    if not os.path.isdir(vip_dir):
        result.message = f'VIP 目录不存在: {vip_dir}'
        return result

    candidates = encrypted_candidates(target, month_from, month_to, output_dir)
    if paths:
        wanted = {os.path.normcase(os.path.abspath(p)) for p in paths}
        candidates = [item for item in candidates if os.path.normcase(item['path']) in wanted]

    result.encrypted = len(candidates)
    if not candidates:
        result.ok = True
        result.message = '没有待解密的加密文件'
        return result

    if precheck_error := _precheck_direct(target, logger):
        result.message = precheck_error
        return result

    os.makedirs(output_dir, exist_ok=True)
    total = len(candidates)
    started = time.time()
    outcomes = []

    if target == 'qq' and _qq_backend() == 'frida':
        # Frida 一次 attach 处理整批；过程中没有逐文件回调，结束后按产物判定
        try:
            from decrypto import run_decrypt
            run_decrypt(vip_dir, output_dir, logger=logger, ensure_client=False,
                        files=[item['path'] for item in candidates])
        except Exception as exc:  # noqa: BLE001
            result.message = f'解密异常: {exc}'
            if logger:
                logger.error(result.message)
            return result
        for index, item in enumerate(candidates, 1):
            produced = _find_output(item['stem'], output_dir)
            outcomes.append({'name': item['name'], 'ok': bool(produced),
                             'output': produced,
                             'message': '' if produced else '没有产出'})
            _emit(progress, index, total, outcomes[-1])
    else:
        from decrypto import um
        mmkv, key = um.qmc_credentials()
        if target == 'netease':
            # .ncm 不需要凭据；传了反而会让 um 去开一个用不上的 vault
            mmkv, key = '', ''
        for index, item in enumerate(candidates, 1):
            completed, error = um.run(item['path'], output_dir, mmkv, key, logger=logger)
            produced = ''
            message = ''
            if error:
                message = error
            elif completed is None or completed.returncode != 0:
                message = um.failure_detail(completed) or 'um 返回失败'
            else:
                produced = _find_output(item['stem'], output_dir)
                if not produced:
                    message = '没有产出（可能不是加密文件）'
                elif item['existing']:
                    message = '已存在，跳过'
            outcomes.append({'name': item['name'], 'ok': bool(produced),
                             'output': produced, 'message': message})
            _emit(progress, index, total, outcomes[-1])

    produced_count = sum(1 for item in outcomes if item['ok'])
    result.produced = produced_count
    result.ok = produced_count > 0
    result.message = f'耗时 {time.time() - started:.1f}s，成功 {produced_count}/{total}'

    # 加密原文件去向：默认留在原地（直接解密天然满足「归还」的语义）
    mode = (config.ENCRYPTED_SOURCE_MODE or 'return').lower()
    if mode == 'trash' and produced_count:
        cleanup = Plan(f'{name}-处理加密原文件', journal_path=config.JOURNAL_PATH,
                       trash_dir=config.TRASH_DIR)
        for item, outcome in zip(candidates, outcomes):
            if outcome['ok']:
                cleanup.add_trash(item['path'], '解密完成，加密原文件入回收站')
        cleanup.execute()
        result.message += '，加密原文件已入回收站'

    if logger:
        logger.info(f'{name}直接解密: {result.message}')
    return result


def _qq_backend():
    try:
        from decrypto.qq import decrypt_backend
        return decrypt_backend()
    except Exception:  # noqa: BLE001
        return 'um'


def _precheck_direct(target, logger):
    """直接解密前的环境检查，返回错误信息（可用返回空串）

    QQ 在 Windows 上依赖注入客户端，环境不就绪时一个文件也解不开；网易云用 um
    离线解密，没有前置条件。
    """
    if target != 'qq' or _qq_backend() != 'frida':
        return ''
    try:
        from decrypto import qq_client
    except Exception:  # noqa: BLE001 - 模块缺失交给执行阶段报错
        return ''
    try:
        if qq_client.ensure_ready(logger):
            return ''
    except Exception as exc:  # noqa: BLE001
        return f'QQ 音乐环境检查失败: {exc}'
    return 'QQ 音乐环境未就绪（未安装 / 未启动 / 未登录）'
