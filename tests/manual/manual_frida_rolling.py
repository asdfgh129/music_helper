# -*- coding: utf-8 -*-
"""滚动方案验证：对每个文件「播放 -> 等 ekey -> 解密」

这是成功率最高的用法：客户端播放某首歌时它必然取到该歌的 ekey，
紧接着解密这首歌，就能拿到明文。

用法:
    python tests/manual/manual_frida_rolling.py <数量>
"""

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time

import frida

EXE = r"C:\Program Files (x86)\Tencent\QQMusic\QQMusic.exe"
HOOK = r"G:/Tools/QQ/hook_qq_music.js"
SRC = r"G:/QQMusic/VipSongsDownload"


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3

    cands = [f for f in os.listdir(SRC) if f.lower().endswith(".mflac")]
    cands = [f for f in cands if 0 < os.path.getsize(os.path.join(SRC, f)) < 12 * 1048576]
    cands.sort(key=lambda f: os.path.getsize(os.path.join(SRC, f)))
    picks = cands[:n]
    print(f"滚动测试 {len(picks)} 个文件\n")

    proc = subprocess.Popen([EXE], cwd=os.path.dirname(EXE))
    for _ in range(30):
        time.sleep(1)
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq QQMusic.exe"],
                           capture_output=True, text=True, errors="replace")
        if "QQMusic.exe" in (r.stdout or ""):
            break
    print("等 40s 登录")
    time.sleep(40)

    session = frida.attach("QQMusic.exe")
    with open(HOOK, encoding="utf-8") as f:
        script = session.create_script(f.read())
    script.load()
    print("hook 已加载\n")

    tmpdir = tempfile.mkdtemp(prefix="roll_")
    ok = 0
    for i, name in enumerate(picks, 1):
        src = os.path.join(SRC, name)
        print(f"[{i}/{len(picks)}] 播放: {name[:48]}")
        os.startfile(src)
        time.sleep(12)          # 等客户端取 ekey

        base, ext = os.path.splitext(name)
        key = hashlib.md5(name.encode()).hexdigest()
        tmp_src = os.path.join(tmpdir, key + ext)
        tmp_out = os.path.join(tmpdir, key + ".flac")
        shutil.copyfile(src, tmp_src)
        try:
            script.exports_sync.decrypt(tmp_src, tmp_out)
        except Exception as exc:
            print(f"      解密异常: {str(exc)[:60]}")
        head = None
        if os.path.exists(tmp_out):
            with open(tmp_out, "rb") as f:
                head = f.read(4)
        good = head == b"fLaC"
        ok += 1 if good else 0
        print(f"      {'✅ 明文 FLAC' if good else '❌ 密文 ' + (head.hex() if head else '无产物')}")
        for p in (tmp_src, tmp_out):
            if os.path.exists(p):
                os.remove(p)

    print(f"\n=== 汇总: {ok}/{len(picks)} 成功 ===")
    session.detach()
    shutil.rmtree(tmpdir, ignore_errors=True)
    try:
        proc.terminate()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
