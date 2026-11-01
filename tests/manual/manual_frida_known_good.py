# -*- coding: utf-8 -*-
"""复测「历史上解密成功过」的文件，判断是否环境变化导致失能"""

import csv
import hashlib
import os
import shutil
import sys
import tempfile
import time

import frida

HOOK = r"G:/Tools/QQ/hook_qq_music.js"
SRC = r"G:/QQMusic/VipSongsDownload"
LOGCSV = r"G:/Tools/QQ/conversion_log.csv"


def load_last(n=6):
    rows = []
    with open(LOGCSV, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    out = []
    for r in rows[-n:][::-1]:
        name = r["歌曲"]
        base = os.path.splitext(name)[0]
        for ext in (".mflac", ".mgg", ".mflac0", ".mgg1"):
            p = os.path.join(SRC, base + ext)
            if os.path.exists(p) and os.path.getsize(p) > 0:
                out.append((r["转换时间"], base + ext, p))
                break
    return out


def main():
    targets = load_last(8)
    if not targets:
        print("日志里的文件在 VipSongsDownload 找不到")
        return 1

    print(f"取 {len(targets)} 个历史成功样本\n")
    session = frida.attach("QQMusic.exe")
    with open(HOOK, encoding="utf-8") as f:
        script = session.create_script(f.read())
    script.on("message", lambda m, d: None)
    try:
        script.set_log_handler(lambda lv, t: None)
    except Exception:
        pass
    script.load()
    time.sleep(1)

    tmpdir = tempfile.mkdtemp(prefix="known_")
    ok = bad = 0
    for i, (when, name, path) in enumerate(targets, 1):
        key = hashlib.md5(name.encode()).hexdigest()[:8]
        ts = os.path.join(tmpdir, f"k{i}_{key}.mflac")
        to = os.path.join(tmpdir, f"k{i}_{key}.flac")
        shutil.copyfile(path, ts)
        err = None
        try:
            script.exports_sync.decrypt(ts, to)
        except Exception as exc:
            err = str(exc).splitlines()[0][:50]
        head = None
        if os.path.exists(to):
            with open(to, "rb") as f:
                head = f.read(4)
        good = head == b"fLaC"
        ok += good
        bad += not good
        print(f"  {i}. [历史成功 {when}] {'OK ' if good else 'BAD'} {name[:44]}  "
              f"{(head.hex() if head else (err or '无产物'))}")
        for p in (ts, to):
            for _ in range(4):
                try:
                    if os.path.exists(p):
                        os.remove(p)
                    break
                except OSError:
                    time.sleep(0.4)

    print(f"\n=== 历史成功样本复测：成功 {ok} / {len(targets)} ===")
    session.detach()
    shutil.rmtree(tmpdir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
