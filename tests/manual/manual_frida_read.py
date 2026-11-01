"""在「能打开」的参数组合上试读，判断读出的是明文还是密文。

上一轮矩阵的结论：`Open(path, 0, 0)` 能让 `IsOpen` 为真且 `GetSize` 返回正确的 18099835；
第 2 个 bool 传 1 就会抛 `system error`——所以那个参数不是「是否解密」。
这一轮固定 `(0, 0)` 打开，再用 `SetDealDecrypt` 的开/关分别读文件头：
读出 `fLaC` 说明已经是明文，读出一串随机字节说明还需要解密。

用法：
    python tests/manual/manual_frida_read.py <某个.mflac>
"""

import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

QQ_EXE = r"C:\Program Files (x86)\Tencent\QQMusic\QQMusic.exe"

JS = r"""
var dll = Process.findModuleByName("QQMusicCommon.dll");
if (!dll) throw new Error("找不到 QQMusicCommon.dll");
var exp = {};
dll.enumerateExports().forEach(function (e) { exp[e.name] = e.address; });
function A(n) { if (!exp[n]) throw new Error("缺少 " + n); return exp[n]; }

var Ctor = new NativeFunction(A("??0EncAndDesMediaFile@@QAE@XZ"), "pointer", ["pointer"], "thiscall");
var Dtor = new NativeFunction(A("??1EncAndDesMediaFile@@QAE@XZ"), "void", ["pointer"], "thiscall");
var GetSize = new NativeFunction(A("?GetSize@EncAndDesMediaFile@@QAEKXZ"), "uint32", ["pointer"], "thiscall");
var IsOpen = new NativeFunction(A("?IsOpen@EncAndDesMediaFile@@QAE_NXZ"), "bool", ["pointer"], "thiscall");
var Open2 = new NativeFunction(A("?Open@EncAndDesMediaFile@@QAE_NPB_W_N1@Z"),
                               "bool", ["pointer", "pointer", "bool", "bool"], "thiscall");
var Read = new NativeFunction(A("?Read@EncAndDesMediaFile@@QAEKPAEK_J@Z"),
                              "uint32", ["pointer", "pointer", "uint32", "int64"], "thiscall");
var SetDeal = new NativeFunction(A("?SetDealDecrypt@EncAndDesMediaFile@@QAEX_N@Z"),
                                 "void", ["pointer", "bool"], "thiscall");

function hexdumpFew(ptr, n) {
    var out = [];
    for (var i = 0; i < n; i++) {
        out.push(("0" + ptr.add(i).readU8().toString(16)).slice(-2));
    }
    return out.join(" ");
}

var OUT = [];

function run(label, deal /* null / 0 / 1 */) {
    var o = Memory.alloc(0x100);
    var rec = { label: label };
    try {
        Ctor(o);
        if (deal !== null) { SetDeal(o, deal); rec.deal = String(deal); }
        var w = Memory.allocUtf16String(RPC_PATH);
        var r = Open2(o, w, 0, 0);
        rec.openRet = String(r);
        rec.isOpen = IsOpen(o) ? "true" : "false";
        var sz = GetSize(o);
        rec.size = String(sz);
        if (rec.isOpen === "true" && sz > 0) {
            var buf = Memory.alloc(64);
            var got = Read(o, buf, 64, 0);
            rec.readBytes = String(got);
            rec.head = hexdumpFew(buf, 16);
        }
        Dtor(o);
    } catch (e) {
        rec.error = "throw: " + String(e.message || e);
    }
    OUT.push(rec);
}

run("默认(SetDeal 未调用)", null);
run("SetDealDecrypt(true)", 1);
run("SetDealDecrypt(false)", 0);

send(OUT);
"""


def main():
    if len(sys.argv) < 2:
        print("用法: python tests/manual/manual_frida_read.py <文件路径>")
        return 1
    target = os.path.abspath(sys.argv[1])

    import frida

    pid = None
    for proc in frida.get_local_device().enumerate_processes():
        if proc.name.lower().startswith("qqmusic"):
            pid = proc.pid
            break
    if pid is None:
        print("[read] 启动客户端…")
        subprocess.Popen([QQ_EXE], close_fds=True)
        deadline = time.time() + 10
        while time.time() < deadline and pid is None:
            time.sleep(0.5)
            for proc in frida.get_local_device().enumerate_processes():
                if proc.name.lower().startswith("qqmusic"):
                    pid = proc.pid
                    break
    if pid is None:
        print("[read] 找不到 QQMusic 进程")
        return 2
    print(f"[read] PID={pid}  文件={os.path.basename(target)}")

    session = frida.attach(pid)
    head = "var RPC_PATH = " + repr(target).replace("'", '"') + ";\n"
    script = session.create_script(head + JS)
    rows = []

    def on_message(message, data):
        if message.get("type") == "send":
            rows.extend(message.get("payload") or [])
        else:
            print("[read] 脚本消息:", message.get("description") or message)

    script.on("message", on_message)
    script.load()
    time.sleep(3)

    for r in rows:
        print(f"\n--- {r['label']} ---")
        for k in ("deal", "openRet", "isOpen", "size", "readBytes", "head", "error"):
            if k in r:
                print(f"  {k:10s}: {r[k]}")

    session.detach()
    return 0


if __name__ == "__main__":
    sys.exit(main())
