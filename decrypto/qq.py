# -*- coding: utf-8 -*-
"""QQ 音乐 .mflac/.mgg 解密（Windows 走 Frida 注入，其他平台走 um 离线解密）

上游 Frida 实现来自唐晓宇的 QQ 音乐解密脚本，随本仓库长期维护。这里负责「按平台
选通道 + 逐个文件解密 + 记录来源链接」，目录与流水编排在 services/decrypt.py。

两条通道：

| 平台 | 通道 | 前提 |
|---|---|---|
| Windows | Frida 注入 `QQMusic.exe` | 客户端在运行 + 装了 frida；不需要密钥 |
| macOS / Linux / Windows 无 frida | `um` 离线解密（`decrypto/um.py`） | 新版 qmc 需要 mmkv + 16 位密钥 |

通道由 `decrypt_backend()` 决定，Frida 起不来（没装、进程没开、脚本加载失败）时
自动退回 um，而不是直接失败。

解密前还会做一次环境准备（`decrypto/qq_client.py`）：检测客户端是否安装（没装就安装
19.51 并打屏蔽更新补丁）→ 没启动就启动 → 确认已登录。这一步不能省——未登录时
`EncAndDesMediaFile::Open` 会直接抛 `system error`，跑下去只会得到一屏失败。
"""

import argparse
import csv
import hashlib
import logging
import os
import shutil
import sys
import tempfile
from datetime import datetime

try:
    from .source_finder import guess_song_url
except Exception:
    def guess_song_url(_):
        return None

# Frida 脚本统一放在 tools/；路径按 __file__ 定位，避免依赖 CWD。
_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _hook_path():
    """优先读 config.QQ_HOOK_JS（支持环境变量覆盖），读不到时退回 tools/ 默认位置。"""
    try:
        import config
        return config.QQ_HOOK_JS
    except Exception:
        return os.path.join(_PROJECT_DIR, "tools", "hook_qq_music.js")


HOOK_PATH = _hook_path()
# 转换流水写进仓库统一的 log/，不落进包目录（包目录混入运行产物会被误提交）
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "log")


def _default_download_dir():
    """QQ 音乐下载目录：优先用 config.QQ_VIP_DIR，读不到配置时退回用户目录旧约定。"""
    try:
        import config
        return config.QQ_VIP_DIR
    except Exception:
        return os.path.join(os.path.expanduser("~"), "Music", "VipSongsDownload")


def list_download_songs(logger=None, download_dir=None):
    """列出QQ音乐下载目录中的歌曲

    Args:
        logger: 日志记录器，如果为None则使用logging模块
        download_dir: 下载目录，默认取 config.QQ_VIP_DIR
    """
    log = logger if logger else logging

    download_dir = download_dir or _default_download_dir()
    if not os.path.exists(download_dir):
        log.error(f"默认下载目录不存在：{download_dir}")
        return
    log.info(f"QQ 音乐下载目录：{download_dir}")
    exts = {".mflac", ".mgg", ".ogg", ".flac", ".mp3", ".m4a"}
    count = 0
    for root, _, files in os.walk(download_dir):
        for file in files:
            if os.path.splitext(file)[1].lower() in exts:
                count += 1
                full_path = os.path.join(root, file)
                rel = os.path.relpath(full_path, download_dir)
                print(f"{count:4d}. {rel}")
    log.info(f"共找到 {count} 个文件")


def append_csv(song_name: str, src_url: str):
    csv_path = os.path.join(LOG_DIR, "conversion_log.csv")
    os.makedirs(LOG_DIR, exist_ok=True)
    exists = os.path.exists(csv_path)
    with open(csv_path, "a", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        if not exists:
            writer.writerow(["转换时间", "歌曲", "来源链接"])
        writer.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), song_name, src_url or ""])


QQ_OUTPUT_EXT = {'.mflac': '.flac', '.mgg': '.ogg'}


def decrypt_backend():
    """选解密通道

    Windows 上优先 **Frida**：直接向运行中的客户端要明文，不需要密钥，成功率高。
    其余情况（macOS、Linux、Windows 上没装 frida）走 **um 离线解密**：

    Frida 方案的前提全是 Windows 客户端——注入 `QQMusic.exe`，再按 MSVC 名字修饰
    （`?Open@EncAndDesMediaFile@@...`）从 `QQMusicCommon.dll` 的导出表里定位函数。
    macOS 版 QQ 音乐是 Mach-O 应用，没有这个 DLL 也没有这套导出名，换 Frida 也
    定位不到，所以 macOS 固定走 um。
    """
    if os.name != 'nt' or sys.platform == 'darwin':
        return 'um'
    try:
        import frida  # noqa: F401
    except ImportError:
        return 'um'
    return 'frida'


def _record(output_name, log):
    """记录来源链接（成功与「已存在跳过」都要记，方便事后回查）"""
    src_url = guess_song_url(output_name)
    log.info(f"来源: {src_url or '未找到（可稍后重试）'}")
    try:
        append_csv(output_name, src_url)
    except Exception as exc:  # noqa: BLE001 - 记账失败不该影响解密
        log.warning(f"写入转换日志失败: {exc}")


def _new_outputs(output_dir, before):
    try:
        return sorted(set(os.listdir(output_dir)) - before)
    except OSError:
        return []


def run_decrypt(input_dir, output_dir, logger=None, ensure_client=True,
                auto_install=True, wait_login_enabled=True, login_timeout=None):
    """解密 QQ 音乐文件（Windows 走 Frida，其他平台走 um 离线解密）

    解密前会做环境准备（`decrypto/qq_client.py`）：检测客户端是否安装、未装则装
    19.51 并打屏蔽更新补丁、启动客户端、确认已登录。任一环节不满足就直接放弃——
    未登录时 Frida 侧每个文件都会抛 `system error`，硬跑只会刷一屏失败。

    Args:
        input_dir: 输入目录
        output_dir: 输出目录
        logger: 日志记录器，如果为None则使用logging模块
        ensure_client: 是否做上面的环境准备（测试时可关掉）
        auto_install: 未安装客户端时是否自动安装
        wait_login_enabled: 未登录时是否等待用户登录
        login_timeout: 等待登录的秒数
    """
    # 使用传入的logger，如果没有则使用logging模块
    log = logger if logger else logging

    if not os.path.isdir(input_dir):
        log.error(f"输入目录不存在: {input_dir}")
        return

    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    if ensure_client:
        from . import qq_client
        if not qq_client.ensure_ready(log, auto_install=auto_install,
                                      wait_login_enabled=wait_login_enabled,
                                      login_timeout=login_timeout):
            log.error("QQ 音乐运行环境未就绪，本次跳过解密")
            return

    if decrypt_backend() == 'frida' and _run_frida(os.path.abspath(input_dir), output_dir, log):
        return
    _run_um(os.path.abspath(input_dir), output_dir, log)


def _run_um(input_dir, output_dir, log):
    """um 离线解密：逐个文件调用，坏文件不影响其他文件

    um 处理整个目录时，只要有一个文件解不开就 FATAL 退出，后面的文件全都不处理；
    逐文件调用能把失败隔离出去，日志也能精确到文件。
    """
    from . import um

    problem = um.exe_problem()
    if problem:
        log.error(f"QQ 音乐解密不可用：{problem}")
        return

    mmkv, key = um.qmc_credentials()
    if mmkv and key:
        log.info(f"qmc 凭据：mmkv={mmkv}，密钥已提供")
    elif mmkv:
        log.warning(f"找到 mmkv（{mmkv}）但缺 16 位密钥，本次不传凭据"
                    f"（只传 mmkv 会让 um 打开 vault 失败，连旧版 qmc 也解不开）；"
                    f"新版 qmc 会解不出来。{um.QMC_HINT}")
    else:
        log.warning(um.QMC_HINT)

    before_all = set()
    try:
        before_all = set(os.listdir(output_dir))
    except OSError:
        pass

    for root, _, files in os.walk(input_dir):
        for file in sorted(files):
            base, ext = os.path.splitext(file)
            ext = ext.lower()
            if ext not in QQ_OUTPUT_EXT:
                continue

            output_name = base + QQ_OUTPUT_EXT[ext]
            output_path = os.path.join(output_dir, output_name)
            if os.path.exists(output_path):
                log.info(f"已存在，跳过: {output_path}")
                _record(output_name, log)
                continue

            source = os.path.join(root, file)
            log.info(f"开始解密: {file}（um 离线）")
            completed, error = um.run(source, output_dir, mmkv, key)
            if error:
                log.error(f"解密失败: {file} -> {error}")
                continue
            if completed.returncode != 0:
                detail = um.failure_detail(completed)
                log.error(f"解密失败: {file} -> {detail or f'返回码 {completed.returncode}'}")
                if not (mmkv and key):
                    log.warning(um.QMC_HINT)
                continue

            if os.path.exists(output_path):
                log.info(f"解密成功: {output_path}")
            else:
                # um 会按解出来的实际类型命名，个别容器不是「把扩展名换掉」那么简单
                produced = _new_outputs(output_dir, before_all)
                before_all = set(os.listdir(output_dir))
                if produced:
                    log.info(f"解密成功: {os.path.join(output_dir, produced[0])}")
                else:
                    log.warning(f"{file} 没有产出（可能本来就不是加密文件）")
                    continue
            _record(output_name, log)
    log.info("所有任务已完成")


def _run_frida(input_dir, output_dir, log):
    """Frida 注入客户端逐个解密；返回 False 表示没跑起来（可退回 um）"""
    # frida 是可选依赖：延迟导入，缺了只让 QQ 解密不可用，不影响其余流程
    try:
        import frida
    except ImportError:
        log.warning("未安装 frida（pip install frida），改用 um 离线解密")
        return False

    try:
        session = frida.attach("QQMusic.exe")
    except frida.ProcessNotFoundError:
        log.warning("未找到 QQMusic.exe 进程（请先启动 QQ 音乐），改用 um 离线解密")
        return False
    except Exception as exc:  # noqa: BLE001 - attach 失败的各种原因都不该中断流程
        log.warning(f"Frida 附加失败（{exc}），改用 um 离线解密")
        return False

    try:
        with open(HOOK_PATH, "r", encoding="utf-8") as f:
            script = session.create_script(f.read())
        script.load()
    except Exception as e:
        log.error(f"加载 Frida 脚本失败: {e}")
        session.detach()
        return False

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    temp_dir = tempfile.mkdtemp(prefix="qqmusic_", dir=output_dir)
    ok = failed = 0
    first_error = ''

    try:
        for root, _, files in os.walk(input_dir):
            for file in files:
                base, ext = os.path.splitext(file)
                ext = ext.lower()
                if ext not in QQ_OUTPUT_EXT:
                    continue

                log.info(f"开始解密: {file}")

                new_ext = QQ_OUTPUT_EXT[ext]
                output_filename = base + new_ext
                output_file_path = os.path.join(output_dir, output_filename)

                if os.path.exists(output_file_path):
                    log.info(f"已存在，跳过: {output_file_path}")
                    _record(output_filename, log)
                    continue

                src_abs_path = os.path.abspath(os.path.join(root, file))
                # 用完整路径哈希：不同子目录下可能有同名文件，用文件名会互相覆盖
                digest = hashlib.md5(src_abs_path.encode()).hexdigest()
                temp_src_path = os.path.join(temp_dir, digest + ext)

                tmp_output_path = os.path.abspath(os.path.join(temp_dir, digest + new_ext))
                os.makedirs(os.path.dirname(tmp_output_path), exist_ok=True)

                # Open 会截断传入路径，所以只把副本交给它，源文件留在原地
                try:
                    shutil.copyfile(src_abs_path, temp_src_path)
                except OSError as exc:
                    log.error(f"复制到暂存区失败: {file} -> {exc}")
                    failed += 1
                    continue

                try:
                    script.exports_sync.decrypt(temp_src_path, tmp_output_path)
                    os.replace(tmp_output_path, output_file_path)
                    log.info(f"解密成功: {output_file_path}")
                    _record(output_filename, log)
                    ok += 1
                except Exception as e:
                    log.error(f"解密失败: {file} -> {e}")
                    failed += 1
                    first_error = first_error or str(e)
                    try:
                        if os.path.exists(tmp_output_path):
                            os.remove(tmp_output_path)
                    except Exception:
                        pass
                    continue
    finally:
        session.detach()
        shutil.rmtree(temp_dir, ignore_errors=True)
        log.info(f"QQ 解密结束：成功 {ok} 个，失败 {failed} 个")
        if failed and not ok:
            log.warning("全部失败。常见原因：客户端未登录、客户端版本与 hook 脚本的导出"
                        "符号不匹配，或该曲目 ekey 尚未加载（客户端需先播放过一次）。"
                        + (f" 首个错误：{first_error}" if first_error else ""))
        log.info("所有任务已完成")
    return True


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="QQ 音乐加密文件（.mflac/.mgg）解密")
    parser.add_argument("-l", "--list", action="store_true", help="只列出下载目录里的歌曲")
    parser.add_argument("-d", "--dir", help="查看目录，默认取 config.QQ_VIP_DIR")
    parser.add_argument("-i", "--input", type=str, required=False, help="待解密的暂存目录")
    parser.add_argument("-o", "--output", type=str, required=False, help="解密输出目录")
    parser.add_argument("--no-install", action="store_true",
                        help="未安装 QQ 音乐时不自动安装 19.51")
    parser.add_argument("--no-wait-login", action="store_true",
                        help="未登录时不等待，直接尝试解密")
    parser.add_argument("--no-ensure", action="store_true",
                        help="跳过安装/启动/登录检查（调试用）")
    parser.add_argument("--login-timeout", type=int, default=None,
                        help="等待登录的秒数，默认取 config.QQ_LOGIN_TIMEOUT（300）")
    args = parser.parse_args()

    if len(sys.argv) == 1:
        print("命令用法（本文件也可直接运行，等价于 main.py --only-decrypt）:")
        print("  列出 QQ 音乐下载目录下的歌曲: python decrypto/qq.py -l")
        print("  解密转换指定目录下的歌曲（可批量转换）: python decrypto/qq.py -i input -o output")
        parser.print_help()
        sys.exit(0)

    if args.list:
        list_download_songs(download_dir=args.dir)
        sys.exit(0)

    if not args.input or not args.output:
        parser.error("解密模式需要提供 -i <输入目录> 和 -o <输出目录>；如仅想查看，请使用 -l")
    run_decrypt(args.input, args.output,
                ensure_client=not args.no_ensure,
                auto_install=not args.no_install,
                wait_login_enabled=not args.no_wait_login,
                login_timeout=args.login_timeout)
