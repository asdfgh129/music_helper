# -*- coding: utf-8 -*-
"""用用户原版 hook 脚本实测解密（复现 G:/Tools/QQ/main.py 的流程）

用法:
    python tests/manual/manual_frida_userhook.py <加密文件路径> [hook脚本路径]
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
DEFAULT_HOOK = r"G:/Tools/QQ/hook_qq_music.js"


def start_client():
    """启动 QQ 音乐并等它加载完 QQMusicCommon.dll"""
    running = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq QQMusic.exe"],
        capture_output=True, text=True, errors="replace",
    )
    if "QQMusic.exe" in (running.stdout or ""):
        print("[启动] 客户端已在运行")
        return None
    print("[启动] 拉起 QQ 音乐 ...")
    proc = subprocess.Popen([EXE], cwd=os.path.dirname(EXE))
    for i in range(20):
        time.sleep(1)
        r = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq QQMusic.exe"],
            capture_output=True, text=True, errors="replace",
        )
        if "QQMusic.exe" in (r.stdout or ""):
            print(f"[启动] 进程出现（{i + 1}s 后），再等 5s 让 DLL 加载")
            time.sleep(5)
            return proc
    raise RuntimeError("QQ 音乐启动失败")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    src = sys.argv[1]
    hook = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_HOOK

    if not os.path.isfile(src):
        print(f"[错] 源文件不存在: {src}")
        return 1
    size = os.path.getsize(src)
    print(f"[源] {os.path.basename(src)}  {size / 1048576:.2f} MB")
    if size == 0:
        print("[错] 源文件是 0 字节，无法测试")
        return 1
    print(f"[钩子] {hook}")

    start_client()

    logs = []

    def on_msg(msg, data):
        if msg.get("type") == "send":
            logs.append(str(msg.get("payload")))
        elif msg.get("type") == "error":
            logs.append("JS-ERROR: " + str(msg.get("description")))
            if msg.get("stack"):
                logs.append(str(msg["stack"])[:400])

    session = frida.attach("QQMusic.exe")
    print("[frida] attach OK")
    with open(hook, encoding="utf-8") as f:
        script = session.create_script(f.read())
    script.on("message", on_msg)
    script.load()
    print("[frida] 脚本已加载")
    time.sleep(2)

    print("\n--- 脚本初始化日志 ---")
    for line in logs:
        print("   ", line)
    logs.clear()

    tmpdir = tempfile.mkdtemp(prefix="qqdec_")
    base, ext = os.path.splitext(os.path.basename(src))
    # main.py 的做法：用 md5 命名避开中文路径
    key = hashlib.md5(os.path.basename(src).encode()).hexdigest()
    tmp_src = os.path.join(tmpdir, key + ext)
    tmp_out = os.path.join(tmpdir, key + ext.replace(".mflac", ".flac").replace(".mgg", ".ogg"))
    shutil.copyfile(src, tmp_src)
    print(f"\n[临时] {tmp_src}")

    print("[解密] 调用 rpc.exports.decrypt ...")
    t0 = time.time()
    ok = False
    try:
        script.exports_sync.decrypt(tmp_src, tmp_out)
        ok = True
    except Exception as exc:
        print(f"[失败] {type(exc).__name__}: {str(exc)[:300]}")

    print(f"[耗时] {time.time() - t0:.1f}s")
    print("\n--- 解密过程日志 ---")
    for line in logs:
        print("   ", line)

    if os.path.exists(tmp_out):
        out_size = os.path.getsize(tmp_out)
        with open(tmp_out, "rb") as f:
            head = f.read(4)
        kind = {b"fLaC": "FLAC", b"OggS": "OGG"}.get(head, f"未知({head.hex()})")
        print(f"\n[产物] {out_size / 1048576:.2f} MB  头部={kind}")
        if ok and head in (b"fLaC", b"OggS"):
            print("[结果] ✅ 解密成功，产物是合法音频")
        else:
            print("[结果] ⚠️ 有产物但格式不对")
    else:
        print("\n[结果] ❌ 没有产物")

    session.detach()
    shutil.rmtree(tmpdir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
