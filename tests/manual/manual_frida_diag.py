"""诊断 QQ 音乐 hook：对象大小、静态函数、Open 返回值（不进自动收集）。

为什么单独写：`EncAndDesMediaFile` 是 C++ 类，`Memory.alloc(0x28)` 是按旧版类布局猜的。
新版客户端如果成员变多，构造时会写越界，之后 Open 读 vtable 就崩，frida 只报
"system error"，看不出原因。这个脚本按大小递增试，并先用不需要 this 的静态函数
`GetEncType` 确认「DLL 调用链本身是通的」，把问题范围缩小到对象布局上。

用法：
    python tests/manual/manual_frida_diag.py <某个.mflac>
"""

import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

QQ_EXE = r"C:\Program Files (x86)\Tencent\QQMusic\QQMusic.exe"

# 逐步探测：先用静态函数（不需要 this，最安全），再按对象大小试构造函数
JS = r"""
var dll = Process.findModuleByName("QQMusicCommon.dll");
if (!dll) throw new Error("找不到 QQMusicCommon.dll");

var exp = {};
dll.enumerateExports().forEach(function (e) { exp[e.name] = e.address; });

function need(name) {
    if (!exp[name]) throw new Error("缺少导出: " + name);
    return exp[name];
}

var RESULT = { encType: null, sizes: [] };

// 1) 静态函数：EncType GetEncType(const wchar_t*)，不需要 this 指针
try {
    var GetEncType = new NativeFunction(
        need("?GetEncType@EncAndDesMediaFile@@SA?AW4EncType@1@PB_W@Z"), "int", ["pointer"], "stdcall");
    var p = Memory.allocUtf16String(RPC_PATH);
    RESULT.encType = GetEncType(p);
} catch (e) {
    RESULT.encTypeError = String(e.message || e);
}

// 2) 静态函数：int64 GetLargeFileSize(const wchar_t*)
try {
    var GetLargeFileSize = new NativeFunction(
        need("?GetLargeFileSize@EncAndDesMediaFile@@SA_JPB_W@Z"), "int64", ["pointer"], "stdcall");
    var p2 = Memory.allocUtf16String(RPC_PATH);
    RESULT.staticSize = String(GetLargeFileSize(p2));
} catch (e) {
    RESULT.staticSizeError = String(e.message || e);
}

// 3) 逐个大小试构造 + Open，找出不崩的最小对象尺寸
var Ctor = new NativeFunction(need("??0EncAndDesMediaFile@@QAE@XZ"), "pointer", ["pointer"], "thiscall");
var Dtor = new NativeFunction(need("??1EncAndDesMediaFile@@QAE@XZ"), "void", ["pointer"], "thiscall");
var OpenFn = new NativeFunction(need("?Open@EncAndDesMediaFile@@QAE_NPB_W_N1@Z"),
                                "bool", ["pointer", "pointer", "bool", "bool"], "thiscall");

var sizes = [0x28, 0x40, 0x60, 0x80, 0x100, 0x200];
for (var i = 0; i < sizes.length; i++) {
    var sz = sizes[i];
    var entry = { size: sz };
    try {
        var obj = Memory.alloc(sz);
        Ctor(obj);
        entry.ctor = "ok";
        try {
            var wpath = Memory.allocUtf16String(RPC_PATH);
            var ok = OpenFn(obj, wpath, 1, 0);
            entry.open = ok ? "true" : "false";
        } catch (e2) {
            entry.open = "throw: " + String(e2.message || e2);
        }
        try { Dtor(obj); entry.dtor = "ok"; } catch (e3) { entry.dtor = "throw: " + String(e3.message || e3); }
    } catch (e1) {
        entry.ctor = "throw: " + String(e1.message || e1);
    }
    RESULT.sizes.push(entry);
}

send(RESULT);
"""


def main():
    if len(sys.argv) < 2:
        print("用法: python tests/manual/manual_frida_diag.py <文件路径>")
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
        print("[diag] 启动客户端…")
        subprocess.Popen([QQ_EXE], close_fds=True)
        deadline = time.time() + 10
        while time.time() < deadline and pid is None:
            time.sleep(0.5)
            for proc in frida.get_local_device().enumerate_processes():
                if proc.name.lower().startswith("qqmusic"):
                    pid = proc.pid
                    break
    if pid is None:
        print("[diag] 找不到 QQMusic 进程")
        return 2
    print(f"[diag] 目标 PID={pid}  文件={target}")

    session = frida.attach(pid)
    script = session.create_script("var RPC_PATH = " + repr(target).replace("'", '"') + ";\n" + JS)
    result = {}

    def on_message(message, data):
        if message.get("type") == "send":
            result.update(message.get("payload") or {})
        else:
            print("[diag] 脚本消息:", message.get("description") or message)

    script.on("message", on_message)
    script.load()
    time.sleep(3)

    print("\n=== 静态函数 ===")
    print("  GetEncType     :", result.get("encType"), result.get("encTypeError", ""))
    print("  GetLargeFileSize:", result.get("staticSize"), result.get("staticSizeError", ""))

    print("\n=== 对象大小探测 ===")
    print("  %-8s %-10s %-22s %s" % ("size", "ctor", "open", "dtor"))
    for entry in result.get("sizes", []):
        print("  0x%-6x %-10s %-22s %s" % (entry["size"], entry["ctor"],
                                           entry["open"], entry.get("dtor", "")))

    session.detach()
    return 0


if __name__ == "__main__":
    sys.exit(main())
