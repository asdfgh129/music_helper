"""批量查一批文件的加密类型，找出不需要外部 ekey 的样本。

`EncAndDesMediaFile::GetEncType` 是静态函数，只读文件头、不需要 ekey，最安全。
QMC 各代在客户端里的枚举值不同：内嵌 ekey 的旧版能直接 Open 成功；需要外部 ekey
的新版（qmc2 / mflac1）则要 mmkv 或 19.51 及以下客户端下载才有 key。

用途：如果库里还有旧版文件，frida 通道可以立刻验证端到端；否则说明必须走密钥路线。

用法：
    python tests/manual/manual_frida_enctype.py <目录> [最多检查几个]
"""

import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

QQ_EXE = r"C:\Program Files (x86)\Tencent\QQMusic\QQMusic.exe"

JS = r"""
var dll = Process.findModuleByName("QQMusicCommon.dll");
if (!dll) throw new Error("找不到 QQMusicCommon.dll");
var addr = null;
dll.enumerateExports().forEach(function (e) {
    if (e.name === "?GetEncType@EncAndDesMediaFile@@SA?AW4EncType@1@PB_W@Z") addr = e.address;
});
if (!addr) throw new Error("找不到 GetEncType");

var GetEncType = new NativeFunction(addr, "int", ["pointer"], "stdcall");
var OUT = [];
for (var i = 0; i < RPC_FILES.length; i++) {
    var p = Memory.allocUtf16String(RPC_FILES[i]);
    var t;
    try { t = GetEncType(p); } catch (e) { t = "throw:" + String(e.message || e); }
    OUT.push({ file: RPC_FILES[i], encType: t });
}
send(OUT);
"""


def main():
    if len(sys.argv) < 2:
        print("用法: python tests/manual/manual_frida_enctype.py <目录> [数量]")
        return 1
    root = os.path.abspath(sys.argv[1])
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 30

    files = []
    for name in sorted(os.listdir(root)):
        if name.lower().endswith((".mflac", ".mgg")):
            full = os.path.join(root, name)
            if os.path.getsize(full) > 512 * 1024:
                files.append(full)
        if len(files) >= limit:
            break
    if not files:
        print("没找到 .mflac/.mgg")
        return 1
    print(f"[enctype] 检查 {len(files)} 个文件")

    import frida

    pid = None
    for proc in frida.get_local_device().enumerate_processes():
        if proc.name.lower().startswith("qqmusic"):
            pid = proc.pid
            break
    if pid is None:
        print("[enctype] 启动客户端…")
        subprocess.Popen([QQ_EXE], close_fds=True)
        deadline = time.time() + 10
        while time.time() < deadline and pid is None:
            time.sleep(0.5)
            for proc in frida.get_local_device().enumerate_processes():
                if proc.name.lower().startswith("qqmusic"):
                    pid = proc.pid
                    break
    if pid is None:
        print("[enctype] 找不到 QQMusic 进程")
        return 2

    session = frida.attach(pid)
    # 路径含中文和反斜杠，必须走 json 序列化，直接用 repr 拼会破坏 JS 字符串
    head = "var RPC_FILES = " + json.dumps(files, ensure_ascii=False) + ";\n"
    script = session.create_script(head + JS)
    rows = []

    def on_message(message, data):
        if message.get("type") == "send":
            rows.extend(message.get("payload") or [])
        else:
            print("[enctype] 脚本消息:", message.get("description") or message)

    script.on("message", on_message)
    script.load()
    time.sleep(3)

    from collections import Counter

    counter = Counter(str(r["encType"]) for r in rows)
    print("\n=== EncType 分布 ===")
    for value, count in counter.most_common():
        print(f"  {value}: {count} 个")

    print("\n=== 明细（前 15 个）===")
    for r in rows[:15]:
        print(f"  {r['encType']}  {os.path.basename(r['file'])}")

    session.detach()
    return 0


if __name__ == "__main__":
    sys.exit(main())
