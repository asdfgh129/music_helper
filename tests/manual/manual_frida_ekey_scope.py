# -*- coding: utf-8 -*-
"""判断 ekey 是按文件生效还是全局

流程：
  1. 启动客户端（同进程，保证 frida 可见）
  2. 等登录
  3. 让客户端播放 A（A 的 ekey 必然被加载）
  4. 分别解密 A 自己 和 另一个没播放过的 B
  5. 检查两个产物的头部：fLaC = 明文，其他 = 密文

如果 A 是 fLaC、B 不是 → ekey 按文件生效，只能解"当前/最近播放过"的歌
如果两个都不是 fLaC  → 调用方式仍有问题

用法:
    python tests/manual/manual_frida_ekey_scope.py <播放的A.mflac> <另一个B.mflac>
"""

import hashlib
import os
import shutil
import subprocess
import sys
import time

import frida

EXE = r"C:\Program Files (x86)\Tencent\QQMusic\QQMusic.exe"
HOOK = r"G:/Tools/QQ/hook_qq_music.js"
OUTDIR = r"C:/Users/bemin/AppData/Local/Temp/ekey_scope_out"


def decrypt_one(script, path, tag):
    tmpdir = tempfile_dir()
    base, ext = os.path.splitext(os.path.basename(path))
    key = hashlib.md5(base.encode()).hexdigest()
    tmp_src = os.path.join(tmpdir, key + ext)
    tmp_out = os.path.join(tmpdir, key + ".flac")
    shutil.copyfile(path, tmp_src)

    result = {"tag": tag, "name": os.path.basename(path), "ok": False, "err": None,
              "size": None, "head": None}
    try:
        script.exports_sync.decrypt(tmp_src, tmp_out)
        result["ok"] = True
    except Exception as exc:
        result["err"] = f"{type(exc).__name__}: {str(exc)[:150]}"

    if os.path.exists(tmp_out):
        result["size"] = os.path.getsize(tmp_out)
        with open(tmp_out, "rb") as f:
            result["head"] = f.read(8)
        keep = os.path.join(OUTDIR, tag + "_" + base + ".flac")
        shutil.copyfile(tmp_out, keep)
        result["kept"] = keep
    shutil.rmtree(tmpdir, ignore_errors=True)
    return result


def tempfile_dir():
    import tempfile
    return tempfile.mkdtemp(prefix="sc_")


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    a, b = sys.argv[1], sys.argv[2]
    no_trigger = "--no-trigger" in sys.argv
    shutil.rmtree(OUTDIR, ignore_errors=True)
    os.makedirs(OUTDIR, exist_ok=True)

    print("[1] 启动客户端")
    proc = subprocess.Popen([EXE], cwd=os.path.dirname(EXE))
    for _ in range(30):
        time.sleep(1)
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq QQMusic.exe"],
                           capture_output=True, text=True, errors="replace")
        if "QQMusic.exe" in (r.stdout or ""):
            break
    print("    等 40s 完成登录")
    time.sleep(40)

    print("[2] attach + 加载 hook")
    session = frida.attach("QQMusic.exe")
    logs = []

    def on_msg(msg, data):
        if msg.get("type") == "send":
            logs.append(str(msg.get("payload")))
        elif msg.get("type") == "error":
            logs.append("JS-ERR: " + str(msg.get("description"))[:150])

    with open(HOOK, encoding="utf-8") as f:
        script = session.create_script(f.read())
    script.on("message", on_msg)
    script.load()

    if no_trigger:
        print("[3] 跳过播放触发（--no-trigger），只靠客户端启动时自动加载")
    else:
        print(f"[3] 播放 A: {os.path.basename(a)}")
        os.startfile(a)
        time.sleep(20)
    logs.clear()

    print("[4] 解密 A（刚播放过的）")
    ra = decrypt_one(script, a, "A")
    print(f"    结果: ok={ra['ok']} size={ra['size']} head={ra['head']}")

    print("[5] 解密 B（没播放过的）")
    rb = decrypt_one(script, b, "B")
    print(f"    结果: ok={rb['ok']} size={rb['size']} head={rb['head']}")

    print("\n=== 判定 ===")
    for r in (ra, rb):
        h = r["head"]
        kind = "FLAC明文" if h and h[:4] == b"fLaC" else ("OGG明文" if h and h[:4] == b"OggS" else "密文/未知")
        print(f"  {r['tag']}: {r['name'][:40]:<42} {kind}  {h.hex() if h else '-'}")

    if ra["head"] and ra["head"][:4] == b"fLaC" and (not rb["head"] or rb["head"][:4] != b"fLaC"):
        print("\n  → ekey 按文件生效，只有刚播放/下载过的能解")
    elif ra["head"] and ra["head"][:4] == b"fLaC" and rb["head"] and rb["head"][:4] == b"fLaC":
        print("\n  → 两个都能解，ekey 是全局的，批量解密可行")
    else:
        print("\n  → 两个都不是明文，调用方式还有问题")

    print(f"\n产物保留在: {OUTDIR}")
    session.detach()
    try:
        proc.terminate()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
