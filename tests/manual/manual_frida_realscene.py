# -*- coding: utf-8 -*-
"""复现用户真实场景的解密实验

用户的用法是：客户端常驻、登录着、正在用（播放/下载），此时跑脚本解密。

本脚本按这个顺序来：
  1. 同一进程内拉起客户端（保证 frida 能枚举到）
  2. 等它完成登录
  3. 让客户端打开一个加密 .mflac 播放（触发它自己取 ekey）
  4. 再调用 hook 脚本解密另一个文件

用法:
    python tests/manual/manual_frida_realscene.py <触发播放的加密文件> <要解密的加密文件>
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


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    trigger, target = sys.argv[1], sys.argv[2]
    for p in (trigger, target):
        if not os.path.isfile(p) or os.path.getsize(p) == 0:
            print(f"[错] 文件无效: {p}")
            return 1

    print("[1] 启动客户端")
    proc = subprocess.Popen([EXE], cwd=os.path.dirname(EXE))
    for _ in range(30):
        time.sleep(1)
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq QQMusic.exe"],
                           capture_output=True, text=True, errors="replace")
        if "QQMusic.exe" in (r.stdout or ""):
            break
    print("    进程已起，等 40s 完成登录和列表加载")
    time.sleep(40)

    print("[2] attach 并加载 hook")
    session = frida.attach("QQMusic.exe")
    logs = []

    def on_msg(msg, data):
        if msg.get("type") == "send":
            logs.append(str(msg.get("payload")))
        elif msg.get("type") == "error":
            logs.append("JS-ERR: " + str(msg.get("description"))[:200])

    with open(HOOK, encoding="utf-8") as f:
        script = session.create_script(f.read())
    script.on("message", on_msg)
    script.load()
    print("    脚本已加载")

    print(f"[3] 让客户端打开并播放: {os.path.basename(trigger)}")
    os.startfile(trigger)
    print("    等 25s，让客户端自己解密、把 ekey 载入")
    time.sleep(25)
    for line in logs:
        print("      [客户端]", line)
    logs.clear()

    print(f"[4] 现在调用解密: {os.path.basename(target)}")
    tmpdir = tempfile.mkdtemp(prefix="realscene_")
    base, ext = os.path.splitext(os.path.basename(target))
    key = hashlib.md5(base.encode()).hexdigest()
    tmp_src = os.path.join(tmpdir, key + ext)
    tmp_out = os.path.join(tmpdir, key + ".flac")
    shutil.copyfile(target, tmp_src)

    try:
        script.exports_sync.decrypt(tmp_src, tmp_out)
        print("    RPC 返回成功")
    except Exception as exc:
        print(f"    RPC 失败: {type(exc).__name__}: {str(exc)[:200]}")

    for line in logs:
        print("      [脚本]", line)

    if os.path.exists(tmp_out):
        size = os.path.getsize(tmp_out)
        with open(tmp_out, "rb") as f:
            head = f.read(4)
        kind = {b"fLaC": "FLAC", b"OggS": "OGG"}.get(head, head.hex())
        print(f"\n[产物] {size / 1048576:.2f} MB  头部={kind}")
        print("[结果] ✅ 成功" if head in (b"fLaC", b"OggS") else "[结果] ⚠️ 产物格式不对")
    else:
        print("\n[结果] ❌ 无产物")

    session.detach()
    shutil.rmtree(tmpdir, ignore_errors=True)
    try:
        proc.terminate()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
