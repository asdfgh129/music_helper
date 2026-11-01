# -*- coding: utf-8 -*-
"""批量解密验证：播放一次触发 ekey 后，连续解多个文件

用法:
    python tests/manual/manual_frida_batch.py <触发播放的文件> <数量>
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
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    trigger = sys.argv[1]
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 8

    # 挑一批文件
    cands = [f for f in os.listdir(SRC) if f.lower().endswith(".mflac")]
    cands = [f for f in cands if os.path.getsize(os.path.join(SRC, f)) > 0]
    cands.sort(key=lambda f: os.path.getsize(os.path.join(SRC, f)))
    picks = cands[:count]
    print(f"待解 {len(picks)} 个文件")

    print("[1] 启动客户端")
    proc = subprocess.Popen([EXE], cwd=os.path.dirname(EXE))
    for _ in range(30):
        time.sleep(1)
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq QQMusic.exe"],
                           capture_output=True, text=True, errors="replace")
        if "QQMusic.exe" in (r.stdout or ""):
            break
    print("    等 40s 登录")
    time.sleep(40)

    print("[2] attach + hook")
    session = frida.attach("QQMusic.exe")
    with open(HOOK, encoding="utf-8") as f:
        script = session.create_script(f.read())
    errs = []
    script.on("message", lambda m, d: errs.append(str(m.get("description"))[:100])
              if m.get("type") == "error" else None)
    script.load()

    print(f"[3] 播放触发: {os.path.basename(trigger)}")
    os.startfile(trigger)
    print("    等 20s 让 ekey 加载")
    time.sleep(20)

    print("[4] 批量解密")
    tmpdir = tempfile.mkdtemp(prefix="batch_")
    ok = bad = 0
    results = []
    t0 = time.time()
    for i, name in enumerate(picks, 1):
        src = os.path.join(SRC, name)
        base, ext = os.path.splitext(name)
        key = hashlib.md5(name.encode()).hexdigest()
        tmp_src = os.path.join(tmpdir, key + ext)
        tmp_out = os.path.join(tmpdir, key + ".flac")
        shutil.copyfile(src, tmp_src)
        err = None
        try:
            script.exports_sync.decrypt(tmp_src, tmp_out)
        except Exception as exc:
            err = str(exc)[:80]
        head = None
        if os.path.exists(tmp_out):
            with open(tmp_out, "rb") as f:
                head = f.read(4)
        good = head == b"fLaC"
        if good:
            ok += 1
        else:
            bad += 1
        results.append((i, name, good, head.hex() if head else "-", err))
        print(f"  {i:2d}. {'✅' if good else '❌'} {name[:50]}  {head.hex() if head else (err or '无产物')}")
        for p in (tmp_src, tmp_out):
            if os.path.exists(p):
                os.remove(p)

    print("\n=== 汇总 ===")
    print(f"  成功 {ok} / {len(picks)}   失败 {bad}   耗时 {time.time() - t0:.1f}s")
    if bad == 0:
        print("  → 批量解密完全可用")
    session.detach()
    shutil.rmtree(tmpdir, ignore_errors=True)
    try:
        proc.terminate()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
