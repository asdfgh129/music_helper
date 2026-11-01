"""对 `EncAndDesMediaFile::Open` 做参数矩阵测试，定位它抛 system error 的原因。

推断链：
1. `GetEncType` 返回 2、`GetLargeFileSize` 与实际字节数一致 → DLL 调用链和文件本身都没问题；
2. 构造函数各种对象尺寸都成功 → 不是类布局越界；
3. 只剩 `Open` 抛异常 → 要么参数语义变了，要么它内部取 ekey 失败。

所以把 `Open` 的两种重载、以及 bool 参数的各种组合、`SetDealDecrypt` 开关都试一遍。
`(path, 0, 0)` 若能打开而 `(path, 1, 0)` 不行，就说明卡在 ekey 而不是文件。

用法：
    python tests/manual/manual_frida_matrix.py <某个.mflac>
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
var Open4 = new NativeFunction(A("?Open@EncAndDesMediaFile@@QAE_NPB_WKKK@Z"),
                               "bool", ["pointer", "pointer", "uint32", "uint32", "uint32"], "thiscall");
var SetDeal = new NativeFunction(A("?SetDealDecrypt@EncAndDesMediaFile@@QAEX_N@Z"),
                                 "void", ["pointer", "bool"], "thiscall");

var OUT = [];

function trial(label, fn) {
    var obj = Memory.alloc(0x100);
    var rec = { label: label };
    try {
        Ctor(obj);
        try {
            var r = fn(obj);
            rec.open = (r === true || r === 1) ? "true" : String(r);
            try { rec.isOpen = IsOpen(obj) ? "true" : "false"; } catch (e4) { rec.isOpen = "throw"; }
            try { rec.size = String(GetSize(obj)); } catch (e5) { rec.size = "throw"; }
        } catch (e2) {
            rec.open = "throw: " + String(e2.message || e2);
        }
        try { Dtor(obj); } catch (e3) { rec.dtor = "throw"; }
    } catch (e1) {
        rec.open = "ctor throw: " + String(e1.message || e1);
    }
    OUT.push(rec);
}

function P() { return Memory.allocUtf16String(RPC_PATH); }

// A. 两个 bool 参数的组合
trial("Open2(path,0,0)", function (o) { return Open2(o, P(), 0, 0); });
trial("Open2(path,1,0)", function (o) { return Open2(o, P(), 1, 0); });
trial("Open2(path,0,1)", function (o) { return Open2(o, P(), 0, 1); });
trial("Open2(path,1,1)", function (o) { return Open2(o, P(), 1, 1); });

// B. 三个 uint 参数的重载
trial("Open4(path,0,0,0)", function (o) { return Open4(o, P(), 0, 0, 0); });
trial("Open4(path,1,0,0)", function (o) { return Open4(o, P(), 1, 0, 0); });

// C. 先关掉解密再打开
trial("SetDeal(false)->Open2(p,1,0)", function (o) { SetDeal(o, 0); return Open2(o, P(), 1, 0); });
trial("SetDeal(true)->Open2(p,1,0)", function (o) { SetDeal(o, 1); return Open2(o, P(), 1, 0); });

// D. 相对路径 vs 反斜杠 vs 正斜杠
trial("Open2(正斜杠,1,0)", function (o) {
    return Open2(o, Memory.allocUtf16String(RPC_PATH.replace(/\\/g, "/")), 1, 0);
});

send(OUT);
"""


def main():
    if len(sys.argv) < 2:
        print("用法: python tests/manual/manual_frida_matrix.py <文件路径>")
        return 1
    target = os.path.abspath(sys.argv[1])
    if not os.path.exists(target):
        print("文件不存在: " + target)
        return 1

    import frida

    pid = None
    for proc in frida.get_local_device().enumerate_processes():
        if proc.name.lower().startswith("qqmusic"):
            pid = proc.pid
            break
    if pid is None:
        print("[matrix] 启动客户端…")
        subprocess.Popen([QQ_EXE], close_fds=True)
        deadline = time.time() + 10
        while time.time() < deadline and pid is None:
            time.sleep(0.5)
            for proc in frida.get_local_device().enumerate_processes():
                if proc.name.lower().startswith("qqmusic"):
                    pid = proc.pid
                    break
    if pid is None:
        print("[matrix] 找不到 QQMusic 进程")
        return 2
    print(f"[matrix] PID={pid}  文件={os.path.basename(target)}")

    session = frida.attach(pid)
    head = "var RPC_PATH = " + repr(target).replace("'", '"') + ";\n"
    script = session.create_script(head + JS)
    rows = []

    def on_message(message, data):
        if message.get("type") == "send":
            rows.extend(message.get("payload") or [])
        else:
            print("[matrix] 脚本消息:", message.get("description") or message)

    script.on("message", on_message)
    script.load()
    time.sleep(3)

    print("\n%-26s %-24s %-8s %s" % ("调用方式", "open", "isOpen", "size"))
    print("-" * 76)
    for r in rows:
        print("%-26s %-24s %-8s %s" % (r["label"], r.get("open", ""),
                                       r.get("isOpen", ""), r.get("size", "")))

    session.detach()
    return 0


if __name__ == "__main__":
    sys.exit(main())
