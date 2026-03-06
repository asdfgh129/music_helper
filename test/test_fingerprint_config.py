#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
指纹配置验证测试

验证 music_helper 和 soundalike 项目的指纹长度配置是否一致。
"""

import os
import re
import sys
from pathlib import Path

# 添加项目路径
MUSIC_HELPER_ROOT = Path(__file__).parent.parent
SOUNDALIKE_ROOT = Path("/Users/bemin/Code/soundalike")


def check_music_helper_config():
    """检查 music_helper 项目的配置"""
    print("\n" + "=" * 70)
    print("[1/2] 检查 music_helper 项目配置")
    print("=" * 70)
    
    config_file = MUSIC_HELPER_ROOT / "config.py"
    if not config_file.exists():
        print("❌ config.py 不存在")
        return False, None
    
    content = config_file.read_text(encoding='utf-8')
    
    # 查找 FPCALC_LENGTH
    match = re.search(r'FPCALC_LENGTH\s*=\s*(\d+)', content)
    if match:
        length = int(match.group(1))
        print(f"✅ 找到 FPCALC_LENGTH = {length}")
        
        if length == 120:
            print(f"✅ 配置正确：{length} 秒（MusicBrainz 标准）")
            return True, length
        else:
            print(f"⚠️  配置为 {length} 秒，不是标准的 120 秒")
            return False, length
    else:
        print("❌ 未找到 FPCALC_LENGTH 配置")
        return False, None


def check_soundalike_config():
    """检查 soundalike 项目的配置"""
    print("\n" + "=" * 70)
    print("[2/2] 检查 soundalike 项目配置")
    print("=" * 70)
    
    fpcalc_file = SOUNDALIKE_ROOT / "fpcalc.go"
    if not fpcalc_file.exists():
        print("❌ fpcalc.go 不存在")
        return False, None
    
    content = fpcalc_file.read_text(encoding='utf-8')
    
    # 查找 defaultFpcalcSettings 中的 length 值
    match = re.search(r'length:\s*(\d+),?', content)
    if match:
        length = int(match.group(1))
        print(f"✅ 找到默认指纹长度: {length}")
        
        if length == 120:
            print(f"✅ 配置正确：{length} 秒（MusicBrainz 标准）")
            return True, length
        else:
            print(f"⚠️  配置为 {length} 秒，不是标准的 120 秒")
            return False, length
    else:
        print("❌ 未找到指纹长度配置")
        return False, None


def check_documentation_consistency():
    """检查文档中的指纹长度说明是否一致"""
    print("\n" + "=" * 70)
    print("检查文档一致性")
    print("=" * 70)
    
    # 需要检查的文档
    docs = [
        (SOUNDALIKE_ROOT / "README.md", 15, 120, "15秒说明"),
        (SOUNDALIKE_ROOT / "FEATURES.md", 15, 120, "15秒说明"),
        (SOUNDALIKE_ROOT / "AGENTS.md", 15, 120, "15秒说明"),
        (MUSIC_HELPER_ROOT / "FINGERPRINT_LENGTH_CONFIG.md", 15, 120, "15秒说明"),
        (MUSIC_HELPER_ROOT / "FINGERPRINT_LENGTH_SUMMARY.md", 15, 120, "15秒说明"),
    ]
    
    all_ok = True
    for doc_path, old_pattern, new_value, description in docs:
        if not doc_path.exists():
            print(f"⚠️  文档不存在: {doc_path.name}")
            continue
        
        content = doc_path.read_text(encoding='utf-8')
        
        # 检查是否还有旧的 15 秒说明
        if str(old_pattern) in content and "15" in content:
            # 检查是否在合理的上下文中（比如性能对比表）
            # 这里简化处理，只检查是否有明确的 "15 秒默认" 这样的说明
            if "default" in content.lower() and "15" in content:
                print(f"⚠️  {doc_path.name} 可能还有旧的 {description}")
                all_ok = False
            else:
                print(f"✅ {doc_path.name}: 文档已更新")
        else:
            print(f"✅ {doc_path.name}: 文档已更新")
    
    return all_ok


def check_fpcalc_available():
    """检查 fpcalc 是否可用"""
    import shutil
    fpcalc_path = shutil.which('fpcalc')
    if fpcalc_path:
        print(f"✅ fpcalc 已安装: {fpcalc_path}")
        
        # 获取版本信息
        try:
            result = subprocess.run(
                ['fpcalc', '-version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            version = result.stdout.strip().split('\n')[0]
            print(f"   版本: {version}")
        except:
            print(f"   (无法获取版本信息)")
        
        return True
    else:
        print("❌ fpcalc 未安装")
        print("\n   安装方法:")
        print("   macOS:   brew install chromaprint")
        print("   Linux:   sudo apt install libchromaprint-tools")
        print("   Windows: https://github.com/acoustid/chromaprint/releases")
        return False


def main():
    """主函数"""
    print("=" * 70)
    print("指纹配置验证测试")
    print("验证 music_helper 和 soundalike 项目的配置是否一致")
    print("=" * 70)
    
    results = []
    
    # 1. 检查 music_helper 配置
    mh_ok, mh_length = check_music_helper_config()
    results.append(('music_helper', mh_ok, mh_length))
    
    # 2. 检查 soundalike 配置
    sa_ok, sa_length = check_soundalike_config()
    results.append(('soundalike', sa_ok, sa_length))
    
    # 3. 检查文档一致性
    docs_ok = check_documentation_consistency()
    
    # 4. 检查 fpcalc
    print("\n" + "=" * 70)
    print("检查依赖工具")
    print("=" * 70)
    fpcalc_ok = check_fpcalc_available()
    
    # 总结
    print("\n" + "=" * 70)
    print("测试总结")
    print("=" * 70)
    
    for name, ok, length in results:
        if ok:
            print(f"✅ {name:15s} 配置正确 ({length} 秒)")
        else:
            if length:
                print(f"❌ {name:15s} 配置为 {length} 秒（应为 120 秒）")
            else:
                print(f"❌ {name:15s} 配置未找到")
    
    if docs_ok:
        print("✅ 文档一致性    文档已全部更新")
    else:
        print("⚠️  文档一致性    可能需要进一步检查")
    
    if fpcalc_ok:
        print("✅ fpcalc        已安装（可以运行完整测试）")
    else:
        print("❌ fpcalc        未安装（需要先安装）")
    
    print("=" * 70)
    
    # 判断整体结果
    all_config_ok = all(ok for _, ok, _ in results)
    
    if all_config_ok and fpcalc_ok:
        print("\n✅ 所有配置正确，fpcalc 已安装")
        print("   可以运行完整的一致性测试:")
        print("   python test/test_fingerprint_consistency.py <音频文件>")
    elif all_config_ok:
        print("\n✅ 配置正确，但 fpcalc 未安装")
        print("   安装 fpcalc 后可以运行完整测试")
    else:
        print("\n❌ 存在配置问题，请先修复")
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
