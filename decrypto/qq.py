# -*- coding: utf-8 -*-
"""QQ 音乐 .mflac/.mgg 解密（Frida 注入 QQMusic.exe）

上游实现来自唐晓宇的 QQ 音乐解密脚本，随本仓库长期维护。这里只负责「起 Frida 会话 +
逐个文件调 decrypt + 记录来源链接」，目录与流水编排在 services/decrypt.py。
"""

import os
import sys
import hashlib
import argparse
import logging
import shutil
import tempfile
import csv
from datetime import datetime

try:
    from .source_finder import guess_song_url
except Exception:
    def guess_song_url(_):
        return None

# Frida 脚本与本文件同目录，必须按 __file__ 定位；用相对路径时只有 CWD 恰好在
# decrypto/ 下才能跑到（历史上正是这个坑，靠 qq.bat 先 cd 过去绕过）
HOOK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hook_qq_music.js")
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


def run_decrypt(input_dir, output_dir, logger=None):
    """解密QQ音乐文件

    Args:
        input_dir: 输入目录
        output_dir: 输出目录
        logger: 日志记录器，如果为None则使用logging模块
    """
    # 使用传入的logger，如果没有则使用logging模块
    log = logger if logger else logging

    if not os.path.exists(input_dir):
        log.error(f"输入目录不存在: {input_dir}")
        return

    input_dir = os.path.abspath(input_dir)
    output_dir = os.path.abspath(output_dir)

    # frida 是可选依赖：延迟导入，缺了只让 QQ 解密不可用，不影响其余流程（也方便本文件单独跑）
    try:
        import frida
    except ImportError:
        log.error("未安装 frida（pip install frida），QQ 音乐解密不可用")
        return

    try:
        session = frida.attach("QQMusic.exe")
    except frida.ProcessNotFoundError:
        log.error("未找到 QQMusic.exe 进程，请先启动 QQ 音乐")
        return

    try:
        with open(HOOK_PATH, "r", encoding="utf-8") as f:
            script = session.create_script(f.read())
        script.load()
    except Exception as e:
        log.error(f"加载 Frida 脚本失败: {e}")
        return

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    temp_dir = tempfile.mkdtemp(prefix="qqmusic_", dir=output_dir)

    try:
        for root, _, files in os.walk(input_dir):
            for file in files:
                base, ext = os.path.splitext(file)
                if ext.lower() not in [".mflac", ".mgg"]:
                    continue

                log.info(f"开始解密: {file}")

                new_ext = ext.lower().replace("mflac", "flac").replace("mgg", "ogg")
                output_filename = base + new_ext
                output_file_path = os.path.join(output_dir, output_filename)

                if os.path.exists(output_file_path):
                    log.info(f"已存在，跳过: {output_file_path}")
                    src_url = guess_song_url(file) or guess_song_url(output_filename)
                    log.info(f"来源: {src_url or '未找到（可稍后重试）'}")
                    append_csv(output_filename, src_url)
                    continue

                src_abs_path = os.path.abspath(os.path.join(root, file))
                temp_src_path = os.path.join(temp_dir, hashlib.md5(file.encode()).hexdigest() + ext)
                shutil.copyfile(src_abs_path, temp_src_path)

                tmp_output_path = os.path.abspath(
                    os.path.join(temp_dir, hashlib.md5(file.encode()).hexdigest() + new_ext)
                )
                os.makedirs(os.path.dirname(tmp_output_path), exist_ok=True)

                try:
                    script.exports_sync.decrypt(temp_src_path, tmp_output_path)
                    os.rename(tmp_output_path, output_file_path)
                    log.info(f"解密成功: {output_file_path}")
                    src_url = guess_song_url(file) or guess_song_url(output_filename)
                    log.info(f"来源: {src_url or '未找到（可稍后重试）'}")
                    append_csv(output_filename, src_url)
                except Exception as e:
                    log.error(f"解密失败: {file} -> {e}")
                    try:
                        if os.path.exists(tmp_output_path):
                            os.remove(tmp_output_path)
                    except Exception:
                        pass
                    continue
    finally:
        session.detach()
        shutil.rmtree(temp_dir, ignore_errors=True)
        log.info("所有任务已完成")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="QQ 音乐加密文件（.mflac/.mgg）解密")
    parser.add_argument("-l", "--list", action="store_true", help="只列出下载目录里的歌曲")
    parser.add_argument("-d", "--dir", help="查看目录，默认取 config.QQ_VIP_DIR")
    parser.add_argument("-i", "--input", type=str, required=False, help="待解密的临时目录")
    parser.add_argument("-o", "--output", type=str, required=False, help="解密输出目录")
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
    run_decrypt(args.input, args.output)
