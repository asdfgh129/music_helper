#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
指纹一致性测试（简化版）

验证 music_helper 项目中指纹生成的一致性。
由于需要 fpcalc 工具，此脚本主要用于展示测试框架。
"""

import os
import sys
from pathlib import Path

# 添加项目路径
MUSIC_HELPER_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(MUSIC_HELPER_ROOT))


def check_fpcalc():
    """检查 fpcalc 是否安装"""
    import shutil
    fpcalc_path = shutil.which('fpcalc')
    if fpcalc_path:
        print(f"✅ 找到 fpcalc: {fpcalc_path}")
        return True
    else:
        print("❌ 未找到 fpcalc")
        return False


def print_fpcalc_install_guide():
    """打印 fpcalc 安装指南"""
    print("\n" + "=" * 70)
    print("fpcalc 安装指南")
    print("=" * 70)
    print("\nmacOS:")
    print("  brew install chromaprint")
    print("\nLinux (Ubuntu/Debian):")
    print("  sudo apt install libchromaprint-tools")
    print("\nWindows:")
    print("  1. 下载: https://github.com/acoustid/chromaprint/releases")
    print("  2. 解压后将 fpcalc.exe 放到 PATH 中")
    print("\n验证安装:")
    print("  fpcalc -version")
    print("=" * 70 + "\n")


def test_framework_demo():
    """
    演示测试框架（无需 fpcalc）
    """
    print("\n" + "=" * 70)
    print("指纹一致性测试框架")
    print("=" * 70)
    print("\n此测试需要以下组件:")
    print("  1. ✅ music_helper 项目")
    print("  2. ✅ soundalike 项目（已修改为 120 秒）")
    print("  3. ❌ fpcalc 工具（未安装）")
    print("\n安装 fpcalc 后，可以测试以下内容:")
    print("  - fpcalc 命令行工具生成的指纹")
    print("  - music_helper 项目生成的指纹")
    print("  - soundalike 项目生成的指纹")
    print("\n所有三个应该完全一致，因为:")
    print("  - music_helper 使用: fpcalc -length 120")
    print("  - soundalike 使用:  fpcalc -length 120 (默认)")
    print("=" * 70)


def main():
    """主函数"""
    print("指纹一致性测试")
    print("验证 music_helper 和 soundalike 项目的指纹是否一致\n")
    
    # 检查 fpcalc
    has_fpcalc = check_fpcalc()
    
    if not has_fpcalc:
        print("\n⚠️  fpcalc 未安装，无法运行完整测试")
        print_fpcalc_install_guide()
        test_framework_demo()
        
        print("\n如果已安装 fpcalc，请运行完整测试:")
        print("  python test/test_fingerprint_consistency.py")
        return
    
    # 如果有 fpcalc，运行完整测试
    print("\n✅ fpcalc 已安装，运行完整测试...")
    from test_fingerprint_consistency import main as run_full_test
    run_full_test()


if __name__ == '__main__':
    main()
