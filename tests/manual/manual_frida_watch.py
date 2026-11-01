# -*- coding: utf-8 -*-
"""监听客户端自身的 EncAndDesMediaFile::Open / Read 调用

目的：判断 QQ 音乐自己播放本地加密文件时，Open 是成功还是失败。
  - 客户端调用成功 → ekey 可用，问题在我的调用方式
  - 客户端也失败 / 从不调用 → 环境问题（登录态、VIP、或播放的是在线流）

用法:
    python tests/manual/manual_frida_watch.py [监听秒数]
"""

import sys
import time

import frida

JS = r"""
var dll = Process.findModuleByName("QQMusicCommon.dll");
if (!dll) throw new Error("QQMusicCommon.dll 未找到");

var ADDR = {};
dll.enumerateExports().forEach(function (e) {
    if (e.name === "?Open@EncAndDesMediaFile@@QAE_NPB_W_N1@Z") ADDR.open = e.address;
    if (e.name === "?Read@EncAndDesMediaFile@@QAEKPAEK_J@Z") ADDR.read = e.address;
    if (e.name === "?SetEkey@EncAndDesMediaFile@@QAE_NPBDH@Z") ADDR.setekey = e.address;
});

var stats = { open: 0, openOk: 0, read: 0, setekey: 0 };

function readWide(p) {
    try {
        if (p.isNull()) return null;
        return p.readUtf16String();
    } catch (e) {
        return "<读不出:" + e.message + ">";
    }
}

if (ADDR.open) {
    Interceptor.attach(ADDR.open, {
        onEnter: function (args) {
            stats.open++;
            var p = readWide(args[1]);
            if (p) send({ kind: "open", path: p, f2: args[2].toInt32(), f3: args[3].toInt32() });
        },
        onLeave: function (ret) {
            if (ret.toInt32() !== 0) stats.openOk++;
        }
    });
}

if (ADDR.read) {
    Interceptor.attach(ADDR.read, {
        onEnter: function (args) { stats.read++; }
    });
}

if (ADDR.setekey) {
    Interceptor.attach(ADDR.setekey, {
        onEnter: function (args) {
            stats.setekey++;
            var s = null;
            try { s = args[1].readUtf8String(); } catch (e) {}
            send({ kind: "setekey", ekey: s ? s.slice(0, 64) : null, len: args[2].toInt32() });
        }
    });
}

rpc.exports = {
    stats: function () { return stats; },
    hasOpen: function () { return !!ADDR.open; }
};
"""


def main():
    secs = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    session = frida.attach("QQMusic.exe")
    script = session.create_script(JS)
    lines = []

    def on_msg(msg, data):
        if msg.get("type") == "send":
            p = msg["payload"]
            if p.get("kind") == "open":
                lines.append(f"    Open: {p['path']}  flags=({p['f2']},{p['f3']})")
            elif p.get("kind") == "setekey":
                lines.append(f"    SetEkey: len={p['len']} ekey={p['ekey']}")
        elif msg.get("type") == "error":
            lines.append("    JS-ERR: " + str(msg.get("description"))[:200])

    script.on("message", on_msg)
    script.load()
    print("Open 地址可用:", script.exports_sync.hasOpen())
    print(f"监听 {secs} 秒，请让 QQ 音乐播放一首下载的 VIP 歌 ...\n")

    for i in range(secs):
        time.sleep(1)
        if lines:
            for line in lines:
                print(line)
            lines.clear()

    s = script.exports_sync.stats()
    print("\n=== 汇总 ===")
    print(f"  Open 调用   : {s['open']} 次（成功 {s['openOk']} 次）")
    print(f"  Read 调用   : {s['read']} 次")
    print(f"  SetEkey 调用: {s['setekey']} 次")
    session.detach()


if __name__ == "__main__":
    main()
