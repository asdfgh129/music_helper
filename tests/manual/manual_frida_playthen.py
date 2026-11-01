# -*- coding: utf-8 -*-
"""验证「播放预热 ekey」假设：同一文件播放前后各解一次

安全机制：
  - 解密一律用临时副本，绝不把源路径交给 Open
  - 播放前先备份源文件；若客户端把源文件截断为 0，自动还原
  - 结束时打印源文件是否完好

用法:
    python tests/manual/manual_frida_playthen.py "<加密文件绝对路径>"
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
BACKUP = r"G:/music_helper/.backup_enc"


def running():
    r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq QQMusic.exe"],
                       capture_output=True, text=True, errors="replace")
    return "QQMusic.exe" in (r.stdout or "")


def ensure_client():
    if running():
        print("[0] 复用已运行客户端")
        return
    print("[0] 启动客户端")
    subprocess.Popen([EXE], cwd=os.path.dirname(EXE))
    for _ in range(40):
        time.sleep(1)
        if running():
            break
    time.sleep(8)
    print("    已启动")


def decrypt_once(script, src, tmpdir, tag):
    key = hashlib.md5((src + tag).encode()).hexdigest()[:10]
    base, ext = os.path.splitext(src)
    ts = os.path.join(tmpdir, f"{tag}_{key}{ext}")
    to = os.path.join(tmpdir, f"{tag}_{key}.out")
    shutil.copyfile(src, ts)          # 只对副本操作
    err = None
    try:
        script.exports_sync.decrypt(ts, to)
    except Exception as exc:
        err = str(exc).splitlines()[0][:60]
    head = None
    size = 0
    if os.path.exists(to):
        size = os.path.getsize(to)
        with open(to, "rb") as f:
            head = f.read(4)
    good = head == b"fLaC" or head == b"OggS"
    for p in (ts, to):
        for _ in range(4):
            try:
                if os.path.exists(p):
                    os.remove(p)
                break
            except OSError:
                time.sleep(0.4)
    return good, head.hex() if head else (err or "无产物"), size


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    src = sys.argv[1]
    if not os.path.exists(src) or os.path.getsize(src) == 0:
        print("源文件不存在或为 0 字节:", src)
        return 1

    orig_size = os.path.getsize(src)
    os.makedirs(BACKUP, exist_ok=True)
    bak = os.path.join(BACKUP, os.path.basename(src))
    shutil.copyfile(src, bak)
    print(f"源文件 {orig_size:,} B，已备份到 {bak}")

    ensure_client()
    session = frida.attach("QQMusic.exe")
    with open(HOOK, encoding="utf-8") as f:
        script = session.create_script(f.read())
    script.on("message", lambda m, d: None)
    try:
        script.set_log_handler(lambda lv, t: None)
    except Exception:
        pass
    script.load()
    time.sleep(1.5)

    tmpdir = tempfile.mkdtemp(prefix="pt_")

    print("\n[A] 播放前")
    ok1, h1, s1 = decrypt_once(script, src, tmpdir, "before")
    print(f"    {'OK' if ok1 else 'BAD'}  head={h1}  out={s1:,} B")

    print("\n[B] 播放该文件（让客户端加载 ekey）")
    os.startfile(src)
    time.sleep(18)
    now = os.path.getsize(src) if os.path.exists(src) else -1
    print(f"    源文件现在 {now:,} B" if now >= 0 else "    源文件消失了")
    if now == 0:
        shutil.copyfile(bak, src)
        print("    ⚠️ 源文件被客户端截断，已从备份还原")

    print("\n[C] 播放后")
    ok2, h2, s2 = decrypt_once(script, src, tmpdir, "after")
    print(f"    {'OK' if ok2 else 'BAD'}  head={h2}  out={s2:,} B")

    print("\n[D] 再等 10s 复测（ekey 可能有延迟）")
    time.sleep(10)
    ok3, h3, s3 = decrypt_once(script, src, tmpdir, "after2")
    print(f"    {'OK' if ok3 else 'BAD'}  head={h3}  out={s3:,} B")

    final = os.path.getsize(src) if os.path.exists(src) else -1
    print(f"\n=== 结论: 播放前 {'OK' if ok1 else 'BAD'} -> 播放后 "
          f"{'OK' if (ok2 or ok3) else 'BAD'} ===")
    print(f"    源文件最终 {final:,} B（原始 {orig_size:,} B）")

    shutil.rmtree(tmpdir, ignore_errors=True)
    session.detach()
    return 0


if __name__ == "__main__":
    sys.exit(main())
