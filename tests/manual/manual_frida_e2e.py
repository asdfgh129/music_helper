"""端到端跑一次 QQ 音乐解密，并把「为什么失败」定位到具体环节。

背景（2026-11-01 实测结论）：
- frida 17.3.2 注入正常；17.25.0 会报 `Unable to locate the ntdll loader TLS routines` 崩掉；
- `GetEncType`（静态）、`GetLargeFileSize`（静态）都能正常返回 → DLL 调用链没问题；
- `Open(path, 0, 0)` 能让 `IsOpen` 为真，但 `GetSize` 冷启动时恒为 0；
- Windows 客户端没有 `MMKVStreamEncryptId`（只有 `mmkv.default` 配置库）→ ekey 不落盘。

所以 `GetSize==0` 就是「ekey 不在内存」的信号。本脚本在等待期间监听 `SetEkey`，
判断客户端到底有没有加载过 ekey——把「客户端没调用」和「调用了但没解出来」区分开。

用法：
    python tests/manual/manual_frida_e2e.py <文件> [等待秒数]
"""

import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

QQ_EXE = r"C:\Program Files (x86)\Tencent\QQMusic\QQMusic.exe"

# 监听 + 解密一体：先挂观察器，等一段时间，再试解
JS = r"""
var dll = Process.findModuleByName("QQMusicCommon.dll");
if (!dll) throw new Error("找不到 QQMusicCommon.dll");
var exp = {};
dll.enumerateExports().forEach(function (e) { exp[e.name] = e.address; });
function A(n) { return exp[n]; }

var STATE = { ekeyCalls: 0, lastEkey: null, openCalls: 0, sizeHits: 0 };

var se = A("?SetEkey@EncAndDesMediaFile@@QAE_NPBDH@Z");
if (se) {
    Interceptor.attach(se, {
        onEnter: function (args) {
            STATE.ekeyCalls++;
            var len = args[2].toInt32();
            if (len > 0 && len < 512) {
                try { STATE.lastEkey = args[1].readUtf8String(len); } catch (e) {}
            }
        }
    });
}
var op = A("?Open@EncAndDesMediaFile@@QAE_NPB_W_N1@Z");
if (op) {
    Interceptor.attach(op, { onEnter: function () { STATE.openCalls++; } });
}
var gs = A("?GetSize@EncAndDesMediaFile@@QAEKXZ");
if (gs) {
    // 注意是 onLeave，不是 onExit——写错会让 Interceptor.attach 抛
    // "expected at least one callback"，并连带后面 rpc.exports 都不执行
    Interceptor.attach(gs, { onLeave: function () { if (this.retval.toInt32() > 0) STATE.sizeHits++; } });
}

rpc.exports = {
    state: function () { return STATE; },
    decrypt: function (src, out) {
        var Ctor = new NativeFunction(A("??0EncAndDesMediaFile@@QAE@XZ"), "pointer", ["pointer"], "thiscall");
        var Dtor = new NativeFunction(A("??1EncAndDesMediaFile@@QAE@XZ"), "void", ["pointer"], "thiscall");
        var Open = new NativeFunction(A("?Open@EncAndDesMediaFile@@QAE_NPB_W_N1@Z"),
                                      "bool", ["pointer", "pointer", "bool", "bool"], "thiscall");
        var IsOpen = new NativeFunction(A("?IsOpen@EncAndDesMediaFile@@QAE_NXZ"),
                                        "bool", ["pointer"], "thiscall");
        var GetSize = new NativeFunction(A("?GetSize@EncAndDesMediaFile@@QAEKXZ"),
                                         "uint32", ["pointer"], "thiscall");
        var Read = new NativeFunction(A("?Read@EncAndDesMediaFile@@QAEKPAEK_J@Z"),
                                      "uint32", ["pointer", "pointer", "uint32", "int64"], "thiscall");

        var obj = Memory.alloc(0x100);
        Ctor(obj);
        var ret = Open(obj, Memory.allocUtf16String(src), 0, 0);
        var opened = IsOpen(obj);
        var size = opened ? GetSize(obj) : 0;
        var info = { openRet: ret, isOpen: opened, size: size };

        if (opened && size > 0) {
            var buf = Memory.alloc(size);
            var got = Read(obj, buf, size, 0);
            info.read = got;
            var data = buf.readByteArray(got);
            var f = new File(out, "wb");
            f.write(data); f.flush(); f.close();
            info.magic = Array.from(new Uint8Array(data.slice(0, 4)))
                .map(function (b) { return String.fromCharCode(b); }).join("");
        }
        Dtor(obj);
        return info;
    }
};
"""


def main():
    if len(sys.argv) < 2:
        print("用法: python tests/manual/manual_frida_e2e.py <文件> [等待秒数]")
        return 1
    target = os.path.abspath(sys.argv[1])
    wait = int(sys.argv[2]) if len(sys.argv) > 2 else 45
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
        print("[e2e] 启动客户端…")
        subprocess.Popen([QQ_EXE], close_fds=True)
        deadline = time.time() + 10
        while time.time() < deadline and pid is None:
            time.sleep(0.5)
            for proc in frida.get_local_device().enumerate_processes():
                if proc.name.lower().startswith("qqmusic"):
                    pid = proc.pid
                    break
    if pid is None:
        print("[e2e] 找不到 QQMusic 进程")
        return 2

    print(f"[e2e] PID={pid}")
    print(f"[e2e] 文件={os.path.basename(target)}")
    print(f"[e2e] 先观察 {wait} 秒，看客户端是否自己加载 ekey…")

    session = frida.attach(pid)
    script = session.create_script(JS)
    script.on("message", lambda m, d: print("  [js]", m.get("description") or m.get("payload")))
    script.load()
    time.sleep(wait)

    state = script.exports_sync.state()
    print("\n=== 观察结果 ===")
    print(f"  SetEkey 调用 : {state['ekeyCalls']} 次")
    print(f"  最近一次 ekey: {state['lastEkey']}")
    print(f"  Open 调用    : {state['openCalls']} 次")
    print(f"  GetSize>0    : {state['sizeHits']} 次")

    out = os.path.join(os.environ.get("TEMP", "."), "frida_e2e_out.flac")
    print("\n=== 尝试解密 ===")
    try:
        info = script.exports_sync.decrypt(target, out)
        print(f"  Open 返回 {info['openRet']}, IsOpen={info['isOpen']}, GetSize={info['size']}")
        if info.get("size", 0) > 0:
            print(f"  已读出 {info.get('read')} 字节，文件头={info.get('magic')!r}")
            if info.get("magic") == "fLaC":
                print(f"  成功：明文 FLAC -> {out}")
            else:
                print("  读到了数据但不是 FLAC 头，可能仍是密文")
        else:
            print("  GetSize 为 0 → ekey 不在内存，这一步解不了")
    except Exception as exc:  # noqa: BLE001 - 探测脚本要打出全部原因
        print(f"  解密异常: {type(exc).__name__}: {exc}")

    session.detach()
    return 0


if __name__ == "__main__":
    sys.exit(main())
