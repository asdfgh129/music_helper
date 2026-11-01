# -*- coding: utf-8 -*-
"""让客户端打开加密文件，观察它自己的 Open 是否成功

先 attach 装好 hook，再用 ShellExecute 把 .mflac 交给 QQ 音乐打开，
然后看客户端有没有调用 Open、成功还是失败。

用法:
    python tests/manual/manual_frida_playtest.py <加密文件路径> [等待秒数]
"""

import os
import subprocess
import sys
import time

import frida

EXE = r"C:\Program Files (x86)\Tencent\QQMusic\QQMusic.exe"

JS = r"""
var dll = Process.findModuleByName("QQMusicCommon.dll");
if (!dll) throw new Error("QQMusicCommon.dll 未找到");

var ADDR = {};
dll.enumerateExports().forEach(function (e) {
    if (e.name === "?Open@EncAndDesMediaFile@@QAE_NPB_W_N1@Z") ADDR.open = e.address;
    if (e.name === "?Read@EncAndDesMediaFile@@QAEKPAEK_J@Z") ADDR.read = e.address;
    if (e.name === "?SetEkey@EncAndDesMediaFile@@QAE_NPBDH@Z") ADDR.setekey = e.address;
    if (e.name === "?GetSize@EncAndDesMediaFile@@QAEKXZ") ADDR.size = e.address;
});

var stats = { open: 0, openOk: 0, read: 0, setekey: 0, sizeHit: 0 };

if (ADDR.open) {
    Interceptor.attach(ADDR.open, {
        onEnter: function (args) {
            stats.open++;
            var p = null;
            try { p = args[1].isNull() ? null : args[1].readUtf16String(); } catch (e) {}
            send({ kind: "open", path: p, f2: args[2].toInt32(), f3: args[3].toInt32() });
        },
        onLeave: function (ret) {
            var v = ret.toInt32();
            if (v !== 0) stats.openOk++;
            send({ kind: "openret", ret: v });
        }
    });
}
if (ADDR.size) {
    Interceptor.attach(ADDR.size, {
        onLeave: function (ret) {
            if (ret.toInt32() > 0) stats.sizeHit++;
        }
    });
}
if (ADDR.read) {
    Interceptor.attach(ADDR.read, { onEnter: function () { stats.read++; } });
}
if (ADDR.setekey) {
    Interceptor.attach(ADDR.setekey, {
        onEnter: function (args) {
            stats.setekey++;
            var s = null;
            try { s = args[1].readUtf8String(); } catch (e) {}
            send({ kind: "setekey", ekey: s ? s.slice(0, 48) : null, len: args[2].toInt32() });
        }
    });
}

rpc.exports = {
    stats: function () { return stats; },
    has: function () {
        return { open: !!ADDR.open, read: !!ADDR.read, setekey: !!ADDR.setekey, size: !!ADDR.size };
    }
};
"""


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    target = sys.argv[1]
    wait = int(sys.argv[2]) if len(sys.argv) > 2 else 25

    if not os.path.isfile(target):
        print("文件不存在:", target)
        return 1

    # 确保客户端在运行
    r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq QQMusic.exe"],
                       capture_output=True, text=True, errors="replace")
    if "QQMusic.exe" not in (r.stdout or ""):
        print("客户端未运行，先启动 ...")
        subprocess.Popen([EXE], cwd=os.path.dirname(EXE))
        time.sleep(20)

    session = frida.attach("QQMusic.exe")
    script = session.create_script(JS)

    events = []

    def on_msg(msg, data):
        if msg.get("type") == "send":
            events.append(msg["payload"])
        elif msg.get("type") == "error":
            events.append({"kind": "err", "msg": str(msg.get("description"))[:200]})

    script.on("message", on_msg)
    script.load()
    print("挂载函数:", script.exports_sync.has())
    print(f"触发客户端打开: {os.path.basename(target)}")

    # 交给系统默认程序（.mflac 关联 QQ 音乐时会被客户端接手）
    try:
        os.startfile(target)
    except Exception as exc:
        print("startfile 失败:", exc)

    print(f"等待 {wait} 秒观察 ...\n")
    for _ in range(wait):
        time.sleep(1)
        for ev in events:
            if ev.get("kind") == "open":
                print(f"    [Open] {ev.get('path')}  flags=({ev.get('f2')},{ev.get('f3')})")
            elif ev.get("kind") == "openret":
                print(f"    [Open 返回] {ev.get('ret')}  ({'成功' if ev.get('ret') else '失败'})")
            elif ev.get("kind") == "setekey":
                print(f"    [SetEkey] len={ev.get('len')} ekey={ev.get('ekey')}")
            elif ev.get("kind") == "err":
                print(f"    [JS-ERR] {ev.get('msg')}")
        events.clear()

    s = script.exports_sync.stats()
    print("\n=== 汇总 ===")
    print(f"  Open 调用    : {s['open']}（成功 {s['openOk']}）")
    print(f"  GetSize 命中 : {s['sizeHit']}")
    print(f"  Read 调用    : {s['read']}")
    print(f"  SetEkey 调用 : {s['setekey']}")
    if s["open"] == 0:
        print("\n客户端没有调用 Open —— 它没去解密这个文件（可能在播在线流或忽略了这个文件）")
    elif s["openOk"] == 0:
        print("\n客户端自己调 Open 也全失败 —— 确认是 ekey 层面取不到，与脚本无关")
    else:
        print("\n客户端自己调 Open 成功了 —— ekey 可用，问题在调用方式")
    session.detach()
    return 0


if __name__ == "__main__":
    sys.exit(main())
