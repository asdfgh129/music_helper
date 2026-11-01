# -*- coding: utf-8 -*-
"""QQ 音乐客户端环境准备：检测安装 → 启动 → 确认登录

为什么解密前要先确认这几件事：

* **必须装着客户端**——Windows 的解密走 Frida 注入运行中的 `QQMusic.exe`，向
  `QQMusicCommon.dll` 的 `EncAndDesMediaFile` 要明文。没有客户端就没有这个 DLL。
  客户端版本过高/过低都会让导出名对不上，所以未安装时统一装 19.51 并打屏蔽更新补丁。
* **必须登录**——未登录时 `EncAndDesMediaFile::Open(path, true, false)` 会直接抛
  `system error`，连文件都打不开；登录后 Open 才成功。所以登录态是可判定的。
* **登录态探测**——用 Frida 对一份**临时副本**做一次 Open：抛异常视为未登录，返回
  成功视为已登录。副本用完即删，源文件绝不直接交给 Open（Open 会截断源文件）。

macOS 的差异：QQ 音乐 Mac 版是 Mach-O，没有 `QQMusicCommon.dll` 也没有 MSVC 名字
修饰的导出符号，Frida 注入无从定位，因此 macOS 固定走 `um` 离线解密。安装/启动/
打补丁这些仍然能做，但登录态无法用同一套方式探测，只能提示用户自行确认。
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Windows 常见安装位置：注册表读不到时的兜底
_WIN_GUESS = (
    r"C:\Program Files (x86)\Tencent\QQMusic\QQMusic.exe",
    r"C:\Program Files\Tencent\QQMusic\QQMusic.exe",
    r"D:\Program Files (x86)\Tencent\QQMusic\QQMusic.exe",
    r"D:\Program Files\Tencent\QQMusic\QQMusic.exe",
)

_WIN_REG_KEYS = (
    r"SOFTWARE\WOW6432Node\Tencent\QQMusic",
    r"SOFTWARE\Tencent\QQMusic",
)

_MAC_APP = "/Applications/QQMusic.app"
_MAC_BIN = "/Applications/QQMusic.app/Contents/MacOS/QQMusic"

# 探测登录态用的精简 Frida 脚本：只 Open + 读 4 字节，不写任何输出
_PROBE_JS = r"""
const mod = Process.findModuleByName("QQMusicCommon.dll");
if (!mod) throw new Error("QQMusicCommon.dll 未加载");

const ex = {};
mod.enumerateExports().forEach(function (e) {
    if (e.name === "??0EncAndDesMediaFile@@QAE@XZ") ex.ctor = e.address;
    if (e.name === "??1EncAndDesMediaFile@@QAE@XZ") ex.dtor = e.address;
    if (e.name === "?Open@EncAndDesMediaFile@@QAE_NPB_W_N1@Z") ex.open = e.address;
    if (e.name === "?GetSize@EncAndDesMediaFile@@QAEKXZ") ex.size = e.address;
});
["ctor", "dtor", "open", "size"].forEach(function (k) {
    if (!ex[k]) throw new Error("缺少导出: " + k);
});

const ctor = new NativeFunction(ex.ctor, "pointer", ["pointer"], "thiscall");
const dtor = new NativeFunction(ex.dtor, "void", ["pointer"], "thiscall");
const open = new NativeFunction(ex.open, "bool",
    ["pointer", "pointer", "bool", "bool"], "thiscall");
const getSize = new NativeFunction(ex.size, "uint32", ["pointer"], "thiscall");

rpc.exports = {
    probe: function (path) {
        var obj = Memory.alloc(0x100);
        for (var i = 0; i < 0x100; i++) obj.add(i).writeU8(0);
        ctor(obj);
        var wide = Memory.allocUtf16String(path);
        var r = { open: 0, size: 0 };
        try {
            r.open = open(obj, wide, 1, 0) ? 1 : 0;
        } catch (e) {
            r.open = -1;
            r.err = e.message;
        }
        try {
            r.size = getSize(obj);
        } catch (e) {
            r.sizeErr = e.message;
        }
        try {
            dtor(obj);
        } catch (e) {}
        return r;
    }
};
"""


# --------------------------------------------------------------------------
# 安装检测
# --------------------------------------------------------------------------

def _config_value(name, default=None):
    """读 config 里的可选覆盖项，读不到就用默认值"""
    try:
        import config
        return getattr(config, name, default)
    except Exception:
        return default


def find_windows():
    """返回 QQMusic.exe 的绝对路径；未安装返回 None

    优先 config.QQ_CLIENT_EXE（手工指定），再查注册表 `Install` 值，
    最后按常见安装路径兜底。
    """
    override = _config_value("QQ_CLIENT_EXE", "")
    if override and os.path.exists(override):
        return override

    try:
        import winreg
    except ImportError:
        winreg = None

    if winreg:
        for key in _WIN_REG_KEYS:
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    with winreg.OpenKey(hive, key) as handle:
                        install, _ = winreg.QueryValueEx(handle, "Install")
                except OSError:
                    continue
                if not install:
                    continue
                exe = os.path.join(str(install).strip().rstrip("\\"), "QQMusic.exe")
                if os.path.exists(exe):
                    return exe

    for path in _WIN_GUESS:
        if os.path.exists(path):
            return path
    return None


def find_macos():
    """macOS 版 QQ 音乐的可执行文件路径；未安装返回 None"""
    if os.path.exists(_MAC_BIN):
        return _MAC_BIN
    return None


def find_client():
    """按当前平台返回客户端可执行文件路径"""
    if sys.platform == "darwin":
        return find_macos()
    if os.name == "nt":
        return find_windows()
    return None


def install_dir(exe):
    """从可执行文件路径推出安装目录（Windows 打补丁要用）"""
    return os.path.dirname(exe) if exe else ""


# --------------------------------------------------------------------------
# 进程检测与启动
# --------------------------------------------------------------------------

def _process_alive(name):
    if os.name == "nt":
        result = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV"],
                                capture_output=True, text=True, errors="replace")
        return name.lower() in (result.stdout or "").lower()
    result = subprocess.run(["pgrep", "-x", name], capture_output=True, text=True)
    return result.returncode == 0


def is_running():
    """客户端是否已在运行"""
    if sys.platform == "darwin":
        return _process_alive("QQMusic")
    return _process_alive("QQMusic.exe")


def start(exe, wait=40):
    """启动客户端并等进程出现；返回是否成功"""
    if not exe or not os.path.exists(exe):
        return False
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-a", _MAC_APP])
        else:
            subprocess.Popen([exe], cwd=os.path.dirname(exe))
    except OSError:
        return False

    for _ in range(wait):
        time.sleep(1)
        if is_running():
            time.sleep(6)      # 给 UI 和登录态恢复留点时间
            return True
    return False


# --------------------------------------------------------------------------
# 安装 19.51 + 屏蔽更新补丁
# --------------------------------------------------------------------------

def installer_path():
    """19.51 安装包路径（Windows 为 .exe，macOS 为 .dmg）"""
    if sys.platform == "darwin":
        return _config_value("QQ_MAC_DMG", os.path.join(_PROJECT_DIR, "tools",
                                                       "QQMusicMac_Mgr_8.8.0_20230903.dmg"))
    return _config_value("QQ_INSTALLER", os.path.join(_PROJECT_DIR, "tools",
                                                     "QQMusic_Setup_1951.exe"))


def patch_path():
    """屏蔽更新补丁（Windows 为 zip，macOS 为 tar.gz）"""
    if sys.platform == "darwin":
        return _config_value("QQ_MAC_PATCH", os.path.join(_PROJECT_DIR, "tools",
                                                          "QQ 音乐 Mac 屏蔽升级.tar.gz"))
    return _config_value("QQ_UPDATE_PATCH", os.path.join(_PROJECT_DIR, "tools",
                                                        "Q音屏蔽更新.zip"))


def install_windows(logger, timeout=None):
    """运行 19.51 安装包

    安装器是 GUI 程序，`/S` 静默参数不保证被支持，因此先尝试静默，失败后
    退回普通启动并提示用户手动完成。
    """
    exe = installer_path()
    if not os.path.exists(exe):
        logger.error(f"未找到 19.51 安装包：{exe}")
        return False

    logger.info(f"安装 QQ 音乐 19.51：{exe}")
    timeout = timeout or 900
    try:
        done = subprocess.run([exe, "/S"], timeout=timeout)
        if done.returncode == 0 and find_windows():
            logger.info("静默安装完成")
            return True
    except subprocess.TimeoutExpired:
        logger.warning("静默安装超时，转为交互安装")
    except OSError as exc:
        logger.warning(f"静默安装启动失败（{exc}），转为交互安装")

    logger.warning("请在弹出的安装向导里完成安装（默认下一步即可）")
    try:
        subprocess.run([exe], timeout=timeout)
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.error(f"安装未完成：{exc}")
        return False
    return bool(find_windows())


def install_macos(logger):
    """挂载 8.8.0 的 dmg 并拷贝到 /Applications"""
    dmg = installer_path()
    if not os.path.exists(dmg):
        logger.error(f"未找到 macOS 安装包：{dmg}")
        return False

    logger.info(f"安装 QQ 音乐 8.8.0：{dmg}")
    mounted = subprocess.run(["hdiutil", "attach", dmg, "-nobrowse", "-plist"],
                             capture_output=True, text=True)
    if mounted.returncode != 0:
        logger.error(f"挂载 dmg 失败：{mounted.stderr.strip()}")
        return False

    volume = ""
    for line in mounted.stdout.splitlines():
        text = line.strip()
        if text.startswith("<string>/Volumes/"):
            volume = text[len("<string>"):-len("</string>")]
            break
    if not volume:
        logger.error("未能识别 dmg 挂载点")
        return False

    try:
        source = os.path.join(volume, "QQMusic.app")
        if not os.path.isdir(source):
            logger.error(f"dmg 里没有 QQMusic.app：{volume}")
            return False
        if os.path.isdir(_MAC_APP):
            shutil.rmtree(_MAC_APP, ignore_errors=True)
        copied = subprocess.run(["cp", "-R", source, "/Applications/"],
                                capture_output=True, text=True)
        if copied.returncode != 0:
            logger.error(f"拷贝失败（可能需要管理员权限）：{copied.stderr.strip()}")
            return False
    finally:
        subprocess.run(["hdiutil", "detach", volume, "-quiet"],
                       capture_output=True)

    logger.info("安装完成")
    return bool(find_macos())


def apply_patch_windows(logger):
    """把假更新器 QQMusicUp.exe 覆盖进安装目录，阻止客户端自动升级

    升级会让导出符号变化，Frida 脚本随之失效，所以这一步和解密能力直接相关。
    """
    exe = find_windows()
    if not exe:
        logger.error("先安装客户端再打补丁")
        return False

    archive = patch_path()
    if not os.path.exists(archive):
        logger.error(f"未找到屏蔽更新补丁：{archive}")
        return False

    target_dir = install_dir(exe)
    try:
        with zipfile.ZipFile(archive) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".exe")]
            if not names:
                logger.error("补丁包里没有可执行文件")
                return False
            for name in names:
                dest = os.path.join(target_dir, os.path.basename(name))
                with zf.open(name) as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out)
                logger.info(f"已覆盖：{dest}")
    except (OSError, zipfile.BadZipFile) as exc:
        logger.error(f"打补丁失败（可能需要管理员权限）：{exc}")
        return False

    return True


def apply_patch_macos(logger):
    """阻止 Mac 版升级：改 Info.plist 版本号 + 重新签名 + 去 quarantine

    与 Windows 思路一致——让客户端自检版本时认为「已是最新」，不再拉新版。
    """
    if not os.path.isdir(_MAC_APP):
        logger.error("未找到 /Applications/QQMusic.app")
        return False

    plist = os.path.join(_MAC_APP, "Contents", "Info.plist")
    commands = [
        ["sed", "-i.bak", "s#<string>8.8.0</string>#<string>88.8.0</string>#", plist],
        ["codesign", "--force", "--deep", "--sign", "-", _MAC_APP],
        ["xattr", "-d", "com.apple.quarantine", _MAC_APP],
    ]
    for cmd in commands:
        done = subprocess.run(cmd, capture_output=True, text=True)
        if done.returncode != 0:
            # xattr 在文件没有 quarantine 属性时会报错，属正常情况
            if cmd[0] == "xattr":
                continue
            logger.error(f"补丁步骤失败：{' '.join(cmd[:2])} -> {done.stderr.strip()}")
            return False
    logger.info("macOS 屏蔽升级补丁已应用")
    return True


def install_client(logger):
    """按平台安装客户端并打补丁"""
    if sys.platform == "darwin":
        if not install_macos(logger):
            return False
        return apply_patch_macos(logger)
    if os.name == "nt":
        if not install_windows(logger):
            return False
        return apply_patch_windows(logger)
    logger.error(f"不支持的平台：{sys.platform}")
    return False


# --------------------------------------------------------------------------
# 登录态探测
# --------------------------------------------------------------------------

def probe_sample(dirs=None):
    """挑一个用于登录探测的加密文件

    只认 `.mflac`：`.mgg` 在已登录状态下也可能 Open 失败，用它判断会误报。
    """
    if dirs is None:
        dirs = [_config_value("QQ_STAGING_DIR", ""), _config_value("QQ_VIP_DIR", "")]
    for directory in dirs:
        if not directory or not os.path.isdir(directory):
            continue
        for name in sorted(os.listdir(directory)):
            if not name.lower().endswith(".mflac"):
                continue
            path = os.path.join(directory, name)
            try:
                if os.path.getsize(path) > 1_000_000:
                    return path
            except OSError:
                continue
    return None


def probe_login(sample=None, logger=None):
    """用 Frida 判断客户端是否已登录

    返回 True=已登录，False=未登录/正在登录，None=无法判断（未运行、无 frida、
    没有样本文件等）。
    """
    if sys.platform == "darwin" or os.name != "nt":
        return None
    sample = sample or probe_sample()
    if not sample or not os.path.exists(sample):
        return None
    if not is_running():
        return None
    try:
        import frida
    except ImportError:
        return None

    workdir = tempfile.mkdtemp(prefix="qqlogin_")
    copy = os.path.join(workdir, "probe" + os.path.splitext(sample)[1])
    try:
        shutil.copyfile(sample, copy)   # 必须是副本：Open 会截断传入的文件
    except OSError:
        shutil.rmtree(workdir, ignore_errors=True)
        return None

    session = None
    try:
        session = frida.attach("QQMusic.exe")
        script = session.create_script(_PROBE_JS)
        script.on("message", lambda _m, _d: None)
        try:
            script.set_log_handler(lambda _lv, _t: None)
        except Exception:
            pass
        script.load()
        result = script.exports_sync.probe(copy)
    except Exception as exc:  # noqa: BLE001 - 探测失败一律当作“未知”
        if logger:
            logger.debug(f"登录探测失败：{exc}")
        return None
    finally:
        if session:
            try:
                session.detach()
            except Exception:
                pass
        shutil.rmtree(workdir, ignore_errors=True)

    if result.get("open") == 1:
        return True
    if result.get("open") == 0:
        return False
    return False        # open == -1：抛异常，视为未登录


def wait_login(logger, timeout=300, interval=5, sample=None):
    """轮询等待登录完成

    返回 True=已登录，False=超时仍未登录，None=无法探测（缺 frida/样本）。
    """
    state = probe_login(sample, logger)
    if state is True:
        return True
    if state is None:
        return None

    logger.warning("检测到 QQ 音乐未登录，请在客户端左上角点击「登录」完成扫码登录")
    deadline = time.time() + timeout
    started = time.time()
    while time.time() < deadline:
        time.sleep(interval)
        if probe_login(sample, logger) is True:
            logger.info(f"已确认登录（等待 {time.time() - started:.0f}s）")
            return True
    logger.error(f"等待登录超时（{timeout}s），解密可能全部失败")
    return False


# --------------------------------------------------------------------------
# 总入口
# --------------------------------------------------------------------------

def supports_frida():
    """只有 Windows 客户端有可注入的导出符号"""
    return os.name == "nt" and sys.platform != "darwin"


def ensure_ready(logger, auto_install=True, wait_login_enabled=True,
                 login_timeout=None):
    """解密前的环境准备

    顺序：检测安装 → （必要时）安装并打补丁 → 启动 → 确认登录。

    返回 True 表示环境可用于解密；False 表示前置条件没满足（调用方应直接放弃，
    否则会拿到一堆 `system error`）。
    """
    if login_timeout is None:
        login_timeout = _config_value("QQ_LOGIN_TIMEOUT", 300)
    exe = find_client()

    if not exe:
        logger.warning("未检测到 QQ 音乐客户端")
        if not auto_install:
            logger.error("已禁用自动安装，请手动安装后重试")
            return False
        if not install_client(logger):
            logger.error("客户端安装未完成，跳过 QQ 解密")
            return False
        exe = find_client()
        if not exe:
            logger.error("安装后仍未定位到客户端，跳过 QQ 解密")
            return False
        logger.info(f"已安装：{exe}")
    else:
        logger.info(f"已检测到客户端：{exe}")

    if not supports_frida():
        logger.info("macOS 走 um 离线解密；如需旧版密钥请使用 8.8.0(20230903) 客户端")
        if not is_running():
            logger.warning("建议先启动 QQ 音乐并登录，才能拿到 qmc 凭据")
        return True

    if not is_running():
        logger.info("启动 QQ 音乐客户端…")
        if not start(exe):
            logger.error("客户端启动失败，跳过 QQ 解密")
            return False

    if not wait_login_enabled:
        return True

    state = wait_login(logger, timeout=login_timeout)
    if state is None:
        logger.warning("无法自动判断登录状态（缺少 frida 或样本文件），"
                       "请确认客户端已登录后再解密")
        return True
    if not state:
        return False
    logger.info("登录状态正常，开始解密")
    return True
