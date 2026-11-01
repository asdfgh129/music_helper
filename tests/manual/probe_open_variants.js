// Open 变体探测：只调用 Open/GetSize，不写文件
// 用于区分「加密文件被拒」与「接口不可用」

const TARGET_DLL = "QQMusicCommon.dll";
const mod = Process.findModuleByName(TARGET_DLL);
if (!mod) throw new Error("找不到 " + TARGET_DLL);

const ex = {};
mod.enumerateExports().forEach(function (e) {
    if (e.name === "??0EncAndDesMediaFile@@QAE@XZ") ex.ctor = e.address;
    if (e.name === "??1EncAndDesMediaFile@@QAE@XZ") ex.dtor = e.address;
    if (e.name === "?Open@EncAndDesMediaFile@@QAE_NPB_W_N1@Z") ex.open = e.address;
    if (e.name === "?GetSize@EncAndDesMediaFile@@QAEKXZ") ex.size = e.address;
    if (e.name === "?Read@EncAndDesMediaFile@@QAEKPAEK_J@Z") ex.read = e.address;
});
["ctor", "dtor", "open", "size", "read"].forEach(function (k) {
    if (!ex[k]) throw new Error("缺少导出: " + k);
});

const ctor = new NativeFunction(ex.ctor, "pointer", ["pointer"], "thiscall");
const dtor = new NativeFunction(ex.dtor, "void", ["pointer"], "thiscall");
const open = new NativeFunction(ex.open, "bool", ["pointer", "pointer", "bool", "bool"], "thiscall");
const getSize = new NativeFunction(ex.size, "uint32", ["pointer"], "thiscall");
const getRead = new NativeFunction(ex.read, "uint", ["pointer", "pointer", "uint32", "uint64"], "thiscall");
const k32 = Process.getModuleByName("kernel32.dll");
const GetLastError = new NativeFunction(k32.getExportByName("GetLastError"), "uint32", []);

rpc.exports = {
    probe: function (path, a, b) {
        var r = { path: path, a: a, b: b };
        var obj = Memory.alloc(0x100);
        for (var i = 0; i < 0x100; i++) obj.add(i).writeU8(0);
        try {
            ctor(obj);
            r.ctor = "ok";
        } catch (e) {
            r.ctor = "ERR " + e.message;
            return r;
        }
        var wide = Memory.allocUtf16String(path);
        try {
            r.open = open(obj, wide, a ? 1 : 0, b ? 1 : 0) ? 1 : 0;
            r.lasterr = GetLastError();
        } catch (e) {
            r.openErr = e.message;
        }
        try {
            r.size = getSize(obj);
        } catch (e) {
            r.sizeErr = e.message;
        }
        // 读 4 字节看头部
        try {
            var buf = Memory.alloc(16);
            var n = getRead(obj, buf, 4, 0);
            r.readN = n;
            var hs = "";
            if (n > 0) {
                for (var k = 0; k < 4; k++) {
                    var v = buf.add(k).readU8();
                    hs += (v < 16 ? "0" : "") + v.toString(16);
                }
            }
            r.head = hs;
        } catch (e) {
            r.readErr = e.message;
        }
        try {
            dtor(obj);
        } catch (e) {
            r.dtorErr = e.message;
        }
        return r;
    }
};
