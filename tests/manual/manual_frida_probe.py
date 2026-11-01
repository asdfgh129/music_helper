"""手工探测 Frida 与 QQ 音乐客户端是否匹配（不进自动收集）。

用法（PowerShell 或 cmd 里，需要在用户桌面会话）：
    python tests/manual/manual_frida_probe.py            # 只 attach + 加载脚本
    python tests/manual/manual_frida_probe.py <mflac>    # 顺带试解一个文件

为什么单独写：QQ 音乐启动后可能在几十秒内自行退出，必须"启动→立刻 attach"一气呵成，
所以把这套动作放进同一个进程里。项目不允许自动测试碰真实进程，故放 manual/。
"""

import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from decrypto import qq  # noqa: E402

QQ_EXE = r"C:\Program Files (x86)\Tencent\QQMusic\QQMusic.exe"


def ensure_running(wait=8):
    """启动客户端并等到进程真的可枚举；已运行就直接用"""
    import frida

    def find():
        for proc in frida.get_local_device().enumerate_processes():
            if proc.name.lower().startswith("qqmusic"):
                return proc.pid
        return None

    pid = find()
    if pid:
        print(f"[probe] 已在运行 PID={pid}")
        return pid

    print("[probe] 启动客户端…")
    subprocess.Popen([QQ_EXE], close_fds=True)
    deadline = time.time() + wait
    while time.time() < deadline:
        time.sleep(0.5)
        pid = find()
        if pid:
            print(f"[probe] 已启动 PID={pid}")
            return pid
    print("[probe] 启动后仍未枚举到进程")
    return None


def main():
    try:
        import frida
    except ImportError:
        print("[probe] 没装 frida：python -m pip install frida")
        return 1

    print(f"[probe] frida {frida.__version__}")
    pid = ensure_running()
    if not pid:
        return 2

    session = frida.attach(pid)
    print("[probe] attach OK")

    messages = []

    def on_message(message, data):
        messages.append(message)

    hook = qq._hook_path()
    print(f"[probe] 脚本 {hook}")
    with open(hook, encoding="utf-8") as handle:
        script = session.create_script(handle.read())
    script.on("message", on_message)
    script.load()
    print("[probe] 脚本已加载")

    time.sleep(3)
    errors = [m for m in messages if m.get("type") == "error"]
    if errors:
        print("[probe] 脚本报错：")
        for err in errors[:5]:
            print("   ", err.get("description"))
            print("   ", (err.get("stack") or "").splitlines()[:3])
    else:
        print("[probe] 脚本无报错（DLL 与 5 个导出函数都找到了）")

    if len(sys.argv) > 1:
        src = os.path.abspath(sys.argv[1])
        out = os.path.join(os.environ.get("TEMP", "."), "frida_probe_out.flac")
        print(f"[probe] 试解 {src} -> {out}")
        try:
            script.exports_sync.decrypt(src, out)
            print(f"[probe] 解密完成，{os.path.getsize(out)} 字节")
            with open(out, "rb") as handle:
                print(f"[probe] 输出头: {handle.read(4)}")
        except Exception as exc:  # noqa: BLE001 - 探测脚本，把原因全打出来
            print(f"[probe] 解密失败: {type(exc).__name__}: {exc}")

    session.detach()
    print("[probe] detached")
    return 0


if __name__ == "__main__":
    sys.exit(main())
