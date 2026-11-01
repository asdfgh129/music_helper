# -*- coding: utf-8 -*-
"""探明 EncAndDesMediaFile::Open 在 32 位 thiscall 下的真实参数布局

Frida 对 x86 thiscall 的 Interceptor args 布局与 NativeFunction 声明不完全一致，
这里直接打印 ecx + args[0..4]，逐个尝试按 UTF-16 读出路径，
从而确定 path 到底在 args 的第几个位置。

客户端此刻应该正在播放一个本地 .mflac，才能捕获到真实调用。
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
});

var seen = 0;

Interceptor.attach(ADDR.open, {
    onEnter: function (args) {
        if (seen >= 6) return;
        seen++;

        var rec = { ecx: this.context.ecx.toString(), args: [], strs: [] };

        // 前 5 个位置全打出来
        for (var i = 0; i < 5; i++) {
            var v = args[i];
            rec.args.push(v ? v.toString() : "null");
        }

        // 每个位置都试着当宽字符串读
        for (var j = 0; j < 5; j++) {
            var s = null;
            try {
                if (args[j] && !args[j].isNull()) {
                    s = args[j].readUtf16String();
                }
            } catch (e) {
                s = "<不可读>";
            }
            rec.strs.push(s);
        }
        send({ kind: "open", rec: rec });
    }
});

rpc.exports = { seen: function () { return seen; } };
"""


def main():
    if len(sys.argv) > 1:
        secs = int(sys.argv[1])
    else:
        secs = 20

    session = frida.attach("QQMusic.exe")
    script = session.create_script(JS)
    records = []

    def on_msg(msg, data):
        if msg.get("type") == "send" and msg["payload"].get("kind") == "open":
            records.append(msg["payload"]["rec"])

    script.on("message", on_msg)
    script.load()
    print(f"已挂上 Open，等待 {secs} 秒观察客户端自己的调用 ...\n")
    for _ in range(secs):
        time.sleep(1)
        if len(records) >= 6:
            break

    for idx, rec in enumerate(records, 1):
        print(f"--- 第 {idx} 次 Open ---")
        print(f"  ecx(this) = {rec['ecx']}")
        for i, (v, s) in enumerate(zip(rec["args"], rec["strs"])):
            marker = "  <== 像路径" if s and (".mflac" in s or ".mgg" in s or "\\" in str(s)) else ""
            print(f"  args[{i}] = {v:<14} utf16={s!r}{marker}")
        print()

    if not records:
        print("没捕获到 Open 调用 —— 客户端当前没有解密任何文件")
    else:
        print("结论：path 参数所在下标见上面标注的 <== 像路径")
    session.detach()


if __name__ == "__main__":
    main()
