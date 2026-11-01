# -*- coding: utf-8 -*-
"""对照实验：明文 flac vs 加密 mflac，在 Open 的不同参数下表现

⚠️ 强制先复制到临时目录再探测。EncAndDesMediaFile::Open 在处理加密文件时
   会截断/重写传入路径，直接传源文件会把源文件清成 0 字节（已实测踩坑）。

判断依据：
  明文能开、加密不能开  -> 加密文件被授权层拒绝（VIP/登录相关）
  两者都不能开          -> 接口/对象构造层面的问题，与 VIP 无关
"""

import os
import shutil
import sys
import tempfile

import frida

JS = r"G:/music_helper/tests/manual/probe_open_variants.js"
PLAIN = r"G:/QQMusic/&TEAM - Back to Life.flac"
ENC_DIR = r"G:/QQMusic/VipSongsDownload"

VARIANTS = [(1, 0), (0, 0), (1, 1), (0, 1)]


def pick_enc():
    files = [f for f in os.listdir(ENC_DIR) if f.lower().endswith((".mflac", ".mgg"))]
    files = [f for f in files if os.path.getsize(os.path.join(ENC_DIR, f)) > 1000000]
    files.sort(key=lambda f: os.path.getsize(os.path.join(ENC_DIR, f)))
    return [os.path.join(ENC_DIR, f) for f in files[:2]]


def main():
    if not os.path.exists(PLAIN):
        print("缺少明文样本:", PLAIN)
        return 1

    session = frida.attach("QQMusic.exe")
    with open(JS, encoding="utf-8") as f:
        script = session.create_script(f.read())
    script.on("message", lambda m, d: print("[js]", m.get("description") if m.get("type") == "error" else m))
    try:
        script.set_log_handler(lambda lv, t: None)
    except Exception:
        pass
    script.load()

    targets = [("PLAIN", PLAIN)] + [("ENC", p) for p in pick_enc()]
    if len(sys.argv) > 1:
        targets = [("CUSTOM", p) for p in sys.argv[1:]]

    tmpdir = tempfile.mkdtemp(prefix="probe_")
    for kind, path in targets:
        print(f"\n=== {kind}: {os.path.basename(path)} "
              f"({os.path.getsize(path):,} B) ===")
        # 必须用临时副本，Open 会破坏传入路径
        try:
            tpath = os.path.join(tmpdir, os.path.basename(path))
            shutil.copyfile(path, tpath)
        except OSError as exc:
            print("  复制失败:", exc)
            continue
        for a, b in VARIANTS:
            try:
                r = script.exports_sync.probe(tpath, a, b)
            except Exception as exc:
                print(f"  Open({a},{b})  RPC异常: {str(exc).splitlines()[0][:80]}")
                continue
            if "openErr" in r:
                print(f"  Open({a},{b})  调用异常: {r['openErr'][:70]}")
                continue
            print(f"  Open({a},{b})  ret={r.get('open')}  "
                  f"GetLastError={r.get('lasterr')}  "
                  f"size={r.get('size')}  read={r.get('readN')}  "
                  f"head={r.get('head') or '-'}"
                  + ("  " + r.get("sizeErr", "") if "sizeErr" in r else "")
                  + ("  " + r.get("readErr", "") if "readErr" in r else ""))
        if os.path.getsize(path) == 0:
            print("  ⚠️ 源文件已为 0 字节（非本次造成）")

    shutil.rmtree(tmpdir, ignore_errors=True)
    session.detach()
    return 0


if __name__ == "__main__":
    sys.exit(main())
