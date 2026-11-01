"""挂上 SetEkey / Open，观察客户端自己在播放时怎么拿 ekey。

背景：冷启动后 `GetSize` 恒为 0，但客户端运行一段时间（自动恢复播放）后某个瞬间
能返回真实大小——说明 ekey 是「播放时才加载到内存」的，21.92 不落盘。
所以先监听客户端自己的 `?SetEkey@EncAndDesMediaFile@@QAE_NPBDH@Z`（设置 ekey）和
`?Open@...` 调用，把真实 ekey 抓出来，再决定能不能做离线解密。

用法：
    python tests/manual/manual_frida_ekey.py            # 只监听 30 秒
    python tests/manual/manual_frida_ekey.py 60         # 监听 60 秒
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
function A(n) { return exp[n]; }

// SetEkey(const char* ekey, int len) —— 抓到就是明文 ekey
var setEkeyAddr = A("?SetEkey@EncAndDesMediaFile@@QAE_NPBDH@Z");
if (setEkeyAddr) {
    Interceptor.attach(setEkeyAddr, {
        onEnter: function (args) {
            var p = args[1];
            var len = args[2].toInt32();
            if (len > 0 && len < 512) {
                try {
                    var s = p.readUtf8String(len);
                    send({ kind: "ekey", ekey: s, len: len });
                } catch (e) {
                    send({ kind: "ekey-raw", hex: hexdump(p, { length: Math.min(len, 64), ansi: false }) });
                }
            } else {
                send({ kind: "ekey-len", len: len });
            }
        }
    });
    send({ kind: "hooked", what: "SetEkey" });
}

// Open(const wchar_t*, bool, bool) —— 看客户端自己传什么参数
var openAddr = A("?Open@EncAndDesMediaFile@@QAE_NPB_W_N1@Z");
if (openAddr) {
    Interceptor.attach(openAddr, {
        onEnter: function (args) {
            try {
                var path = args[1].readUtf16String();
                send({ kind: "open", path: path, arg2: args[2].toInt32(), arg3: args[3].toInt32() });
            } catch (e) {}
        }
    });
    send({ kind: "hooked", what: "Open" });
}

// GetSize 返回非 0 说明 ekey 就绪，顺手记下来
var getSizeAddr = A("?GetSize@EncAndDesMediaFile@@QAEKXZ");
if (getSizeAddr) {
    Interceptor.attach(getSizeAddr, {
        onEnter: function () { this.obj = this.context.ecx; },
        // 回调名是 onLeave；写成 onExit 会抛 "expected at least one callback"
        onLeave: function () {
            var v = this.retval.toInt32();
            if (v > 0) send({ kind: "getsize", value: v });
        }
    });
}
"""


def main():
    seconds = int(sys.argv[1]) if len(sys.argv) > 1 else 30

    import frida

    pid = None
    for proc in frida.get_local_device().enumerate_processes():
        if proc.name.lower().startswith("qqmusic"):
            pid = proc.pid
            break
    if pid is None:
        print("[ekey] 启动客户端…")
        subprocess.Popen([QQ_EXE], close_fds=True)
        deadline = time.time() + 10
        while time.time() < deadline and pid is None:
            time.sleep(0.5)
            for proc in frida.get_local_device().enumerate_processes():
                if proc.name.lower().startswith("qqmusic"):
                    pid = proc.pid
                    break
    if pid is None:
        print("[ekey] 找不到 QQMusic 进程")
        return 2
    print(f"[ekey] PID={pid}，监听 {seconds} 秒…")

    session = frida.attach(pid)
    script = session.create_script(JS)
    stats = {"ekey": [], "open": [], "getsize": [], "hooked": []}

    def on_message(message, data):
        if message.get("type") != "send":
            return
        payload = message.get("payload") or {}
        kind = payload.get("kind")
        if kind == "ekey":
            stats["ekey"].append(payload)
            print(f"  [EKEY] {payload.get('ekey')}  (len={payload.get('len')})")
        elif kind == "ekey-raw":
            print(f"  [EKEY-raw] {payload.get('hex')}")
        elif kind == "ekey-len":
            print(f"  [EKEY] 长度为 {payload.get('len')} 的非常规调用")
        elif kind == "open":
            stats["open"].append(payload)
            if len(stats["open"]) <= 8:
                p = payload.get("path") or ""
                print(f"  [OPEN] {os.path.basename(p)} arg2={payload.get('arg2')} arg3={payload.get('arg3')}")
        elif kind == "getsize":
            stats["getsize"].append(payload)
            if len(stats["getsize"]) <= 8:
                print(f"  [SIZE] {payload.get('value')}")
        elif kind == "hooked":
            print(f"  [hook] 已挂 {payload.get('what')}")

    script.on("message", on_message)
    script.load()
    time.sleep(seconds)

    print("\n=== 汇总 ===")
    print(f"  SetEkey 调用: {len(stats['ekey'])} 次")
    for e in stats["ekey"][:5]:
        print(f"     {e.get('ekey')}")
    print(f"  Open 调用   : {len(stats['open'])} 次")
    for o in stats["open"][:5]:
        print(f"     {os.path.basename(o.get('path') or '')} arg2={o.get('arg2')} arg3={o.get('arg3')}")
    print(f"  GetSize>0   : {len(stats['getsize'])} 次")
    for g in stats["getsize"][:5]:
        print(f"     {g.get('value')}")

    session.detach()
    return 0


if __name__ == "__main__":
    sys.exit(main())
