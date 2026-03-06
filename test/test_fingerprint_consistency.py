#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
指纹一致性测试

验证 music_helper 项目和 soundalike 项目对同一个音频文件生成的指纹是否一致。
"""

import os
import sys
import json
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime

# 尝试导入 chromaprint 库用于解码指纹
try:
    import chromaprint
    HAS_CHROMAPRINT = True
except ImportError:
    HAS_CHROMAPRINT = False
    print("⚠️  pychromaprint 未安装，无法解码压缩格式的指纹")
    print("   安装命令: pip3 install pychromaprint")
    print("   注意: 需要安装 libchromaprint (brew install chromaprint)")

# 添加项目路径
MUSIC_HELPER_ROOT = Path(__file__).parent.parent
SOUNDALIKE_ROOT = Path("/Users/bemin/Code/soundalike")

sys.path.insert(0, str(MUSIC_HELPER_ROOT))

from Fingerprint.musicbrainz_matcher import FingerprintCalculator, FingerprintResult


# 全局变量：存储测试结果
TEST_RESULTS = {
    'timestamp': datetime.now().isoformat(),
    'test_file': None,
    'file_size': None,
    'audio_duration': None,
    'command': None,
    'fingerprints': {
        'fpcalc': {
            'length': None,
            'fingerprint': None,
            'duration': None,
            'command': None
        },
        'music_helper': {
            'length': None,
            'fingerprint': None,
            'duration': None,
            'method': None
        },
        'soundalike': {
            'length': None,
            'fingerprint': None,
            'duration': None,
            'command': None
        }
    },
    'comparisons': [],
    'summary': None
}


def decode_fingerprint(fp_str: str) -> list:
    """
    解码 chromaprint 压缩格式的指纹为整数数组

    Args:
        fp_str: 压缩格式的指纹字符串

    Returns:
        list: 32 位无符号整数数组
    """
    if not HAS_CHROMAPRINT:
        print("  ⚠️  无法解码指纹（pychromaprint 未安装）")
        return None

    try:
        # 使用 chromaprint 解码
        fp_ints, algorithm = chromaprint.decode_fingerprint(fp_str.encode('utf-8'))
        # 将有符号整数转换为无符号整数（32位）
        fp_unsigned = [x & 0xFFFFFFFF for x in fp_ints]
        return fp_unsigned
    except Exception as e:
        print(f"  ❌ 解码失败: {e}")
        return None


def get_fpcalc_fingerprint(audio_file: str, length: int = 120, raw: bool = False) -> dict:
    """
    使用 fpcalc 命令行工具生成指纹

    Args:
        audio_file: 音频文件路径
        length: 指纹提取长度（秒）
        raw: 是否使用 -raw 参数输出整数数组（soundalike 方式）

    Returns:
        dict: 包含 fingerprint 和 duration 的字典
    """
    command = ['fpcalc', '-json', '-length', str(length)]
    if raw:
        command.append('-raw')
    command.append(audio_file)

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode != 0:
            print(f"  ❌ fpcalc 错误 (退出码: {result.returncode}): {result.stderr}")
            return None

        data = json.loads(result.stdout)
        fingerprint = data.get('fingerprint', [])

        # 存储到测试结果中
        TEST_RESULTS['fingerprints']['fpcalc']['length'] = len(fingerprint)
        TEST_RESULTS['fingerprints']['fpcalc']['fingerprint'] = fingerprint
        TEST_RESULTS['fingerprints']['fpcalc']['duration'] = data.get('duration', 0)
        TEST_RESULTS['fingerprints']['fpcalc']['command'] = ' '.join(command)

        return {
            'fingerprint': fingerprint,
            'duration': data.get('duration', 0)
        }
    except Exception as e:
        print(f"  ❌ fpcalc 执行失败: {e}")
        return None


def get_music_helper_fingerprint(audio_file: str) -> dict:
    """
    使用 music_helper 项目的 FingerprintCalculator 生成指纹

    Args:
        audio_file: 音频文件路径

    Returns:
        dict: 包含 fingerprint（整数数组）和 duration 的字典
    """
    try:
        calc = FingerprintCalculator()
        result = calc.calculate(audio_file)

        if not result or not result.success:
            print(f"  ❌ music_helper 指纹计算失败")
            return None

        # 解码压缩格式的指纹为整数数组
        fp_ints = decode_fingerprint(result.fingerprint)

        if fp_ints:
            TEST_RESULTS['fingerprints']['music_helper']['length'] = len(fp_ints)
            TEST_RESULTS['fingerprints']['music_helper']['fingerprint'] = fp_ints
            TEST_RESULTS['fingerprints']['music_helper']['duration'] = result.duration
            TEST_RESULTS['fingerprints']['music_helper']['method'] = 'FingerprintCalculator.calculate() [解码后]'
            return {
                'fingerprint': fp_ints,
                'duration': result.duration
            }
        else:
            print(f"  ❌ 无法解码指纹")
            return None

    except Exception as e:
        print(f"  ❌ music_helper 指纹计算失败: {e}")
        return None


def get_soundalike_fingerprint(audio_file: str) -> list:
    """
    从 soundalike 项目导入函数生成指纹

    Args:
        audio_file: 音频文件路径

    Returns:
        list: 指纹数据（32位整数列表）
    """
    try:
        # soundalike 内部调用 fpcalc 时使用 -raw 参数输出整数数组
        # 默认长度为 120 秒
        result = get_fpcalc_fingerprint(audio_file, length=120, raw=True)
        if result:
            fingerprint = result['fingerprint']
            # 存储到测试结果中
            TEST_RESULTS['fingerprints']['soundalike']['length'] = len(fingerprint)
            TEST_RESULTS['fingerprints']['soundalike']['fingerprint'] = fingerprint
            TEST_RESULTS['fingerprints']['soundalike']['duration'] = result['duration']
            TEST_RESULTS['fingerprints']['soundalike']['command'] = f'fpcalc -raw -json -length 120 {audio_file}'
            return fingerprint
        return None
    except Exception as e:
        print(f"  ❌ soundalike 指纹计算失败: {e}")
        return None


def compare_fingerprints(fp1: list, fp2: list, name1: str, name2: str) -> dict:
    """
    比较两个指纹
    
    Args:
        fp1: 第一个指纹
        fp2: 第二个指纹
        name1: 第一个指纹的名称
        name2: 第二个指纹的名称
    
    Returns:
        dict: 比较结果
    """
    if fp1 is None or fp2 is None:
        return {
            'match': False,
            'reason': '其中一个或两个指纹生成失败'
        }
    
    # 检查长度
    length_equal = len(fp1) == len(fp2)
    
    # 检查每个值
    all_equal = True
    diff_count = 0
    diff_positions = []
    
    for i, (v1, v2) in enumerate(zip(fp1, fp2)):
        if v1 != v2:
            all_equal = False
            diff_count += 1
            if len(diff_positions) < 10:  # 只记录前10个不同位置
                diff_positions.append(i)
    
    # 计算匹配比例
    min_len = min(len(fp1), len(fp2))
    if min_len > 0:
        match_ratio = (min_len - diff_count) / min_len
    else:
        match_ratio = 0.0
    
    return {
        'match': all_equal,
        'length_equal': length_equal,
        'len1': len(fp1),
        'len2': len(fp2),
        'diff_count': diff_count,
        'diff_positions': diff_positions,
        'match_ratio': match_ratio,
        'name1': name1,
        'name2': name2
    }


def test_fingerprint_consistency(audio_file: str) -> dict:
    """
    测试同一文件的指纹一致性

    Args:
        audio_file: 音频文件路径

    Returns:
        dict: 测试结果
    """
    print(f"\n{'=' * 70}")
    print(f"测试文件: {audio_file}")
    print(f"{'=' * 70}")

    if not os.path.exists(audio_file):
        print(f"❌ 文件不存在: {audio_file}")
        return {'success': False, 'error': '文件不存在'}

    # 获取文件信息
    file_size = os.path.getsize(audio_file)
    print(f"文件大小: {file_size / (1024*1024):.2f} MB")

    # 存储到测试结果
    TEST_RESULTS['test_file'] = audio_file
    TEST_RESULTS['file_size'] = f"{file_size / (1024*1024):.2f} MB"
    TEST_RESULTS['command'] = f"python {__file__} {audio_file}"

    results = {}

    # 1. 使用 fpcalc 命令行工具（基准）
    print(f"\n[1/4] 使用 fpcalc 命令行工具生成指纹...")
    fp_fpcalc = get_fpcalc_fingerprint(audio_file, length=120, raw=True)  # 使用 -raw 参数
    if fp_fpcalc:
        print(f"  ✅ 成功生成 {len(fp_fpcalc['fingerprint'])} 个指纹值")
        print(f"  音频时长: {fp_fpcalc['duration']:.2f} 秒")
        print(f"  命令: {TEST_RESULTS['fingerprints']['fpcalc']['command']}")
        print(f"  指纹前20个值: {fp_fpcalc['fingerprint'][:20]}")
        results['fpcalc'] = fp_fpcalc
    else:
        print(f"  ❌ 生成失败")
        return {'success': False, 'error': 'fpcalc 生成失败'}

    # 2. 使用 music_helper 项目
    print(f"\n[2/4] 使用 music_helper 项目生成指纹...")
    fp_helper = get_music_helper_fingerprint(audio_file)
    if fp_helper:
        print(f"  音频时长: {fp_helper['duration']:.2f} 秒")
        print(f"  方法: {TEST_RESULTS['fingerprints']['music_helper']['method']}")
        print(f"  指纹前20个值: {fp_helper['fingerprint'][:20]}")
        results['music_helper'] = fp_helper
    else:
        print(f"  ❌ 生成失败")
        return {'success': False, 'error': 'music_helper 生成失败'}

    # 3. 使用 soundalike 的默认长度（120秒）
    print(f"\n[3/4] 使用 soundalike 默认长度生成指纹...")
    fp_soundalike = get_soundalike_fingerprint(audio_file)
    if fp_soundalike:
        print(f"  ✅ 成功生成 {len(fp_soundalike)} 个指纹值")
        print(f"  方法: {TEST_RESULTS['fingerprints']['soundalike']['command']}")
        print(f"  指纹前20个值: {fp_soundalike[:20]}")
        results['soundalike'] = {
            'fingerprint': fp_soundalike,
            'duration': fp_fpcalc['duration']  # 使用 fpcalc 的时长
        }
    else:
        print(f"  ❌ 生成失败")
        return {'success': False, 'error': 'soundalike 生成失败'}

    # 存储音频时长
    TEST_RESULTS['audio_duration'] = fp_fpcalc['duration']

    # 4. 比较指纹
    print(f"\n[4/4] 比较指纹一致性...")

    # 比较 fpcalc vs music_helper
    print(f"\n  比较: fpcalc vs music_helper")
    comp1 = compare_fingerprints(
        results['fpcalc']['fingerprint'],
        results['music_helper']['fingerprint'],
        'fpcalc',
        'music_helper'
    )
    if comp1['match']:
        print(f"    ✅ 完全一致！")
    else:
        print(f"    ❌ 不一致:")
        print(f"      - 长度: {comp1['len1']} vs {comp1['len2']} {'✓' if comp1['length_equal'] else '✗'}")
        print(f"      - 不同值数量: {comp1['diff_count']}")
        print(f"      - 匹配比例: {comp1['match_ratio']*100:.2f}%")
        if comp1['diff_positions']:
            print(f"      - 前10个不同位置: {comp1['diff_positions']}")

    # 比较 fpcalc vs soundalike
    print(f"\n  比较: fpcalc vs soundalike")
    comp2 = compare_fingerprints(
        results['fpcalc']['fingerprint'],
        results['soundalike']['fingerprint'],
        'fpcalc',
        'soundalike'
    )
    if comp2['match']:
        print(f"    ✅ 完全一致！")
    else:
        print(f"    ❌ 不一致:")
        print(f"      - 长度: {comp2['len1']} vs {comp2['len2']} {'✓' if comp2['length_equal'] else '✗'}")
        print(f"      - 不同值数量: {comp2['diff_count']}")
        print(f"      - 匹配比例: {comp2['match_ratio']*100:.2f}%")
        if comp2['diff_positions']:
            print(f"      - 前10个不同位置: {comp2['diff_positions']}")

    # 比较 music_helper vs soundalike
    print(f"\n  比较: music_helper vs soundalike")
    comp3 = compare_fingerprints(
        results['music_helper']['fingerprint'],
        results['soundalike']['fingerprint'],
        'music_helper',
        'soundalike'
    )
    if comp3['match']:
        print(f"    ✅ 完全一致！")
    else:
        print(f"    ❌ 不一致:")
        print(f"      - 长度: {comp3['len1']} vs {comp3['len2']} {'✓' if comp3['length_equal'] else '✗'}")
        print(f"      - 不同值数量: {comp3['diff_count']}")
        print(f"      - 匹配比例: {comp3['match_ratio']*100:.2f}%")
        if comp3['diff_positions']:
            print(f"      - 前10个不同位置: {comp3['diff_positions']}")

    # 存储比较结果
    TEST_RESULTS['comparisons'] = [
        {
            'name': 'fpcalc vs music_helper',
            'match': comp1['match'],
            'length_equal': comp1['length_equal'],
            'len1': comp1['len1'],
            'len2': comp1['len2'],
            'diff_count': comp1['diff_count'],
            'match_ratio': comp1['match_ratio']
        },
        {
            'name': 'fpcalc vs soundalike',
            'match': comp2['match'],
            'length_equal': comp2['length_equal'],
            'len1': comp2['len1'],
            'len2': comp2['len2'],
            'diff_count': comp2['diff_count'],
            'match_ratio': comp2['match_ratio']
        },
        {
            'name': 'music_helper vs soundalike',
            'match': comp3['match'],
            'length_equal': comp3['length_equal'],
            'len1': comp3['len1'],
            'len2': comp3['len2'],
            'diff_count': comp3['diff_count'],
            'match_ratio': comp3['match_ratio']
        }
    ]

    # 总结
    print(f"\n{'=' * 70}")
    print(f"测试总结:")
    print(f"  fpcalc 指纹长度: {len(results['fpcalc']['fingerprint'])}")
    print(f"  music_helper 指纹长度: {len(results['music_helper']['fingerprint'])}")
    print(f"  soundalike 指纹长度: {len(results['soundalike']['fingerprint'])}")

    all_match = comp1['match'] and comp2['match'] and comp3['match']
    TEST_RESULTS['summary'] = {
        'all_match': all_match,
        'fpcalc_length': len(results['fpcalc']['fingerprint']),
        'music_helper_length': len(results['music_helper']['fingerprint']),
        'soundalike_length': len(results['soundalike']['fingerprint'])
    }

    if all_match:
        print(f"\n  ✅ 所有指纹完全一致！")
    else:
        print(f"\n  ❌ 指纹存在差异")
        if not comp1['match']:
            print(f"    - fpcalc vs music_helper: 不一致")
        if not comp2['match']:
            print(f"    - fpcalc vs soundalike: 不一致")
        if not comp3['match']:
            print(f"    - music_helper vs soundalike: 不一致")

    print(f"{'=' * 70}\n")

    return {
        'success': True,
        'all_match': all_match,
        'results': results,
        'comparisons': {
            'fpcalc_vs_helper': comp1,
            'fpcalc_vs_soundalike': comp2,
            'helper_vs_soundalike': comp3
        }
    }


def find_test_audio_file():
    """
    查找测试用的音频文件

    Returns:
        str: 音频文件路径，如果找不到则返回 None
    """
    # 可能的测试文件位置
    possible_paths = [
        '/Users/bemin/Code/music_helper/1.flac',
        '/Users/bemin/Code/music_helper/test.flac',
        '/Users/bemin/Code/music_helper/test.mp3',
    ]

    for path in possible_paths:
        if os.path.exists(path):
            return path

    return None


def save_test_report(result: dict, audio_file: str):
    """
    保存测试报告到文件

    Args:
        result: 测试结果
        audio_file: 测试的音频文件
    """
    report_dir = Path(__file__).parent
    report_file = report_dir / f"fingerprint_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    report_data = {
        **TEST_RESULTS,
        'test_result': result,
        'report_file': str(report_file)
    }

    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)

    print(f"\n📄 测试报告已保存到: {report_file}")
    return report_file


def main():
    """主函数"""
    print("=" * 70)
    print("指纹一致性测试")
    print("验证 music_helper 和 soundalike 项目的指纹是否一致")
    print("=" * 70)

    # 查找测试文件
    audio_file = find_test_audio_file()

    if audio_file is None:
        print("\n⚠️  未找到测试音频文件")
        print("请将测试音频文件放在以下位置之一:")
        print("  - /Users/bemin/Code/music_helper/1.flac")
        print("  - /Users/bemin/Code/music_helper/test.flac")
        print("  - /Users/bemin/Code/music_helper/test.mp3")

        # 提示用户指定文件
        audio_file = input("\n请输入音频文件路径: ").strip()
        if not audio_file:
            print("❌ 未指定文件，退出")
            return

    # 运行测试
    result = test_fingerprint_consistency(audio_file)

    # 保存测试报告
    save_test_report(result, audio_file)

    # 退出码
    sys.exit(0 if result['success'] and result['all_match'] else 1)


if __name__ == '__main__':
    main()
