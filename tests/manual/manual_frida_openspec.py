# -*- coding: utf-8 -*-
"""精确区分 Open 失败的两种原因：文件打不开 vs ekey 拿不到

对同一个真实文件测 4 种 Open 组合，每种都读出前 16 字节，
看是 fLaC（明文，不需要 ekey）还是随机字节（密文，需要 ekey）。

用法:
    python tests/manual/manual_frida_openspec.py <加密文件路径>
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

JS = r"""
var dll = Process.findModuleByName("QQMusicCommon.dll");
if (!dll) throw new Error("QQMusicCommon.dll 未找到");

var NEED = {
    ctor: "??0EncAndDesMediaFile@@QAE@XZ",
    dtor: "??1EncAndDesMediaFile@@QAE@XZ",
    open: "?Open@EncAndDesMediaFile@@QAE_NPB_W_N1@Z",
    size: "?GetSize@EncAndDesMediaFile@@QAEKXZ",
    read: "?Read@EncAndDesMediaFile@@QAEKPAEK_J@Z",
    isopen: "?IsOpen@EncAndDesMediaFile@@QAE_NXZ"
};

var A = {};
dll.enumerateExports().forEach(function (e) {
    for (var k in NEED) {
        if (e.name === NEED[k]) A[k] = e.address;
    }
});

var api = {
    ctor: new NativeFunction(A.ctor, "pointer", ["pointer"], "thiscall"),
    dtor: new NativeFunction(A.dtor, "void", ["pointer"], "thiscall"),
    open: new NativeFunction(A.open, "bool", ["pointer", "pointer", "bool", "bool"], "thiscall"),
    size: new NativeFunction(A.size, "uint32", ["pointer"], "thiscall"),
    read: new NativeFunction(A.read, "uint", ["pointer", "pointer", "uint32", "uint64"], "thiscall")
};
if (A.isopen) {
    api.isopen = new NativeFunction(A.isopen, "bool", ["pointer"], "thiscall");
}

rpc.exports = {
    hasisopen: function () { return !!A.isopen; },

    // 一次调用内完成 open->size->read，避免对象被别处释放
    probe: function (path, flag1, flag2) {
        var obj = Memory.alloc(0x28);
        api.ctor(obj);
        var err = null, opened = null, isopen = null, size = null, head = null;

        try {
            opened = api.open(obj, Memory.allocUtf16String(path), flag1 ? 1 : 0, flag2 ? 1 : 0);
        } catch (e) {
            err = String(e.message || e);
        }

        if (!err) {
            try { if (api.isopen) isopen = api.isopen(obj); } catch (e) { isopen = "ERR:" + e; }
            try { size = api.size(obj); } catch (e) { size = "ERR:" + e; }
            if (typeof size === "number" && size > 0) {
                try {
                    var buf = Memory.alloc(Math.min(size, 64));
                    var n = api.read(obj, buf, Math.min(size, 64), 0);
                    head = { n: n, hex: buf.readByteArray(16) ? Array.from(new Uint8Array(buf.readByteArray(16))).map(function (b) {
                        return ("0" + b.toString(16)).slice(-2);
                    }).join("") : null };
                } catch (e) {
                    head = "ERR:" + String(e.message || e);
                }
            }
        }

        try { api.dtor(obj); } catch (e) {}

        return { err: err, opened: opened, isopen: isopen, size: size, head: head };
    }
};
"""


def start_client():
    r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq QQMusic.exe"],
                       capture_output=True, text=True, errors="replace")
    if "QQMusic.exe" in (r.stdout or ""):
        return
    subprocess.Popen([EXE], cwd=os.path.dirname(EXE))
    for _ in range(25):
        time.sleep(1)
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq QQMusic.exe"],
                           capture_output=True, text=True, errors="replace")
        if "QQMusic.exe" in (r.stdout or ""):
            time.sleep(6)
            return
    raise RuntimeError("启动失败")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    src = sys.argv[1]
    if os.path.getsize(src) == 0:
        print("源文件 0 字节，换一个")
        return 1

    start_client()
    session = frida.attach("QQMusic.exe")
    script = session.create_script(JS)
    script.on("message", lambda m, d: print("[JS]", m.get("payload") or m.get("description")))
    script.load()
    time.sleep(1)

    print("IsOpen 可用:", script.exports_sync.hasisopen())

    # 复制到纯 ASCII 临时路径，排除中文路径干扰
    tmpdir = tempfile.mkdtemp(prefix="probe_")
    ascii_path = os.path.join(tmpdir, hashlib.md5(b"x").hexdigest() + ".mflac")
    shutil.copyfile(src, ascii_path)

    combos = [(1, 0), (0, 0), (1, 1), (0, 1)]
    print(f"\n{'flag1':>6} {'flag2':>6} | {'err':<22} {'opened':>7} {'isopen':>7} {'size':>12}  head16")
    print("-" * 92)
    for f1, f2 in combos:
        r = script.exports_sync.probe(ascii_path, f1, f2)
        head = r.get("head")
        hh = head.get("hex") if isinstance(head, dict) else head
        print(f"{f1:>6} {f2:>6} | {str(r.get('err') or '-'):<22} {str(r.get('opened')):>7} "
              f"{str(r.get('isopen')):>7} {str(r.get('size')):>12}  {hh}")

    session.detach()
    shutil.rmtree(tmpdir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
