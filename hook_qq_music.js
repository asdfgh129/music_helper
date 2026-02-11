const TARGET_DLL = "QQMusicCommon.dll";

var dllModule = Process.findModuleByName(TARGET_DLL);
if (!dllModule) {
    console.log("警告: " + TARGET_DLL + " 未找到，尝试枚举所有模块...");
    Process.enumerateModules().forEach(function (module) {
        if (module.name.toLowerCase().includes("qqmusic")) {
            console.log("找到 QQ 音乐相关模块: " + module.name + " @ " + module.base);
        }
    });
    throw new Error("无法找到 " + TARGET_DLL + " 模块");
}

console.log("找到目标 DLL: " + TARGET_DLL + " @ " + dllModule.base);

// 枚举导出来查找函数地址
var exports = dllModule.enumerateExports();
console.log("DLL 导出数量: " + exports.length);

var targetFunctions = [
    "??0EncAndDesMediaFile@@QAE@XZ",
    "??1EncAndDesMediaFile@@QAE@XZ",
    "?Open@EncAndDesMediaFile@@QAE_NPB_W_N1@Z",
    "?GetSize@EncAndDesMediaFile@@QAEKXZ",
    "?Read@EncAndDesMediaFile@@QAEKPAEK_J@Z"
];

var addresses = {};
for (var i = 0; i < exports.length; i++) {
    var exp = exports[i];
    for (var j = 0; j < targetFunctions.length; j++) {
        if (exp.name === targetFunctions[j]) {
            addresses[targetFunctions[j]] = exp.address;
            console.log("找到函数: " + exp.name + " @ " + exp.address);
        }
    }
}

// 检查所有函数是否找到
var missingFunctions = [];
for (var k = 0; k < targetFunctions.length; k++) {
    if (!addresses[targetFunctions[k]]) {
        missingFunctions.push(targetFunctions[k]);
    }
}

if (missingFunctions.length > 0) {
    console.log("未找到以下函数: " + missingFunctions.join(", "));
    throw new Error("无法找到必需的函数");
}

console.log("所有必需的函数都已找到，继续创建 NativeFunction 对象...");

// 构造函数 - 使用找到的地址
try {
    var EncAndDesMediaFileConstructor = new NativeFunction(
        addresses["??0EncAndDesMediaFile@@QAE@XZ"], "pointer", ["pointer"], "thiscall"
    );
    console.log("Constructor NativeFunction 创建成功");
} catch (e) {
    console.log("Constructor NativeFunction 创建失败: " + e.message);
    throw e;
}

try {
    var EncAndDesMediaFileDestructor = new NativeFunction(
        addresses["??1EncAndDesMediaFile@@QAE@XZ"], "void", ["pointer"], "thiscall"
    );
    console.log("Destructor NativeFunction 创建成功");
} catch (e) {
    console.log("Destructor NativeFunction 创建失败: " + e.message);
    throw e;
}

try {
    var EncAndDesMediaFileOpen = new NativeFunction(
        addresses["?Open@EncAndDesMediaFile@@QAE_NPB_W_N1@Z"], "bool", ["pointer", "pointer", "bool", "bool"], "thiscall"
    );
    console.log("Open NativeFunction 创建成功");
} catch (e) {
    console.log("Open NativeFunction 创建失败: " + e.message);
    throw e;
}

try {
    var EncAndDesMediaFileGetSize = new NativeFunction(
        addresses["?GetSize@EncAndDesMediaFile@@QAEKXZ"], "uint32", ["pointer"], "thiscall"
    );
    console.log("GetSize NativeFunction 创建成功");
} catch (e) {
    console.log("GetSize NativeFunction 创建失败: " + e.message);
    throw e;
}

try {
    var EncAndDesMediaFileRead = new NativeFunction(
        addresses["?Read@EncAndDesMediaFile@@QAEKPAEK_J@Z"], "uint", ["pointer", "pointer", "uint32", "uint64"], "thiscall"
    );
    console.log("Read NativeFunction 创建成功");
} catch (e) {
    console.log("Read NativeFunction 创建失败: " + e.message);
    throw e;
}

console.log("所有 NativeFunction 对象创建成功");

// Windows API: CreateDirectoryW - 使用正确的API
var kernel32Module = Process.findModuleByName("kernel32.dll");
var kernel32Exports = kernel32Module.enumerateExports();
var createDirectoryAddr = null;

for (var i = 0; i < kernel32Exports.length; i++) {
    if (kernel32Exports[i].name === "CreateDirectoryW") {
        createDirectoryAddr = kernel32Exports[i].address;
        break;
    }
}

if (!createDirectoryAddr) {
    throw new Error("无法找到 CreateDirectoryW");
}

var CreateDirectoryW = new NativeFunction(
    createDirectoryAddr,
    "bool", ["pointer", "pointer"]
);

console.log("CreateDirectoryW NativeFunction 创建成功");

// 递归创建路径
function ensureDirRecursively(pathStr) {
    const parts = pathStr.split(/[\/]/);
    let current = parts[0] === "" ? parts[0] + "\\" : parts[0];
    for (let i = 1; i < parts.length; i++) {
        current += "\\" + parts[i];
        const wide = Memory.allocUtf16String(current);
        CreateDirectoryW(wide, ptr(0));
    }
}

rpc.exports = {
    decrypt: function (srcFileName, tmpFileName) {
        console.log("开始解密: " + srcFileName + " -> " + tmpFileName);

        try {
            // 构造对象
            var EncAndDesMediaFileObject = Memory.alloc(0x28);
            EncAndDesMediaFileConstructor(EncAndDesMediaFileObject);
            console.log("EncAndDesMediaFile 对象已创建");

            var fileNameUtf16 = Memory.allocUtf16String(srcFileName);
            var opened = EncAndDesMediaFileOpen(EncAndDesMediaFileObject, fileNameUtf16, 1, 0);
            if (!opened) {
                EncAndDesMediaFileDestructor(EncAndDesMediaFileObject);
                throw new Error("打开失败: " + srcFileName);
            }
            console.log("文件已打开: " + srcFileName);

            // 读取数据
            var fileSize = EncAndDesMediaFileGetSize(EncAndDesMediaFileObject);
            console.log("文件大小: " + fileSize + " 字节");

            if (fileSize === 0) {
                EncAndDesMediaFileDestructor(EncAndDesMediaFileObject);
                throw new Error("文件大小为 0: " + srcFileName);
            }

            var buffer = Memory.alloc(fileSize);
            var bytesRead = EncAndDesMediaFileRead(EncAndDesMediaFileObject, buffer, fileSize, 0);
            console.log("已读取字节数: " + bytesRead);

            var data = buffer.readByteArray(fileSize);
            EncAndDesMediaFileDestructor(EncAndDesMediaFileObject);
            console.log("对象已销毁");

            // 创建输出目录（递归）
            var lastSlash = tmpFileName.lastIndexOf("\\");
            if (lastSlash !== -1) {
                var dirPath = tmpFileName.substring(0, lastSlash);
                ensureDirRecursively(dirPath);
            }

            // 写入文件
            var tmpFile = new File(tmpFileName, "wb");
            tmpFile.write(data);
            tmpFile.flush();
            tmpFile.close();
            console.log("解密完成: " + tmpFileName);

        } catch (error) {
            console.log("解密过程中出错: " + error.message);
            throw error;
        }
    }
};