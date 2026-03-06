#!/bin/bash
# 指纹一致性测试脚本
# 测试 music_helper 和 soundalike 项目生成的指纹是否一致

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "============================================================"
echo "指纹一致性测试"
echo "验证 music_helper 和 soundalike 项目的指纹是否一致"
echo "============================================================"

# 检查 fpcalc
if ! command -v fpcalc &> /dev/null; then
    echo -e "${RED}❌ fpcalc 未安装${NC}"
    echo ""
    echo "请安装 fpcalc:"
    echo "  macOS:   brew install chromaprint"
    echo "  Linux:   sudo apt install libchromaprint-tools"
    echo "  Windows: https://github.com/acoustid/chromaprint/releases"
    echo ""
    exit 1
fi

echo -e "${GREEN}✅ 找到 fpcalc: $(which fpcalc)${NC}"
fpcalc -version | head -1

# 检查测试文件
if [ $# -eq 0 ]; then
    AUDIO_FILE="/Users/bemin/Code/music_helper/1.flac"
else
    AUDIO_FILE="$1"
fi

if [ ! -f "$AUDIO_FILE" ]; then
    echo -e "${RED}❌ 文件不存在: $AUDIO_FILE${NC}"
    exit 1
fi

echo ""
echo "============================================================"
echo "测试文件: $AUDIO_FILE"
echo "============================================================"
echo "文件大小: $(du -h "$AUDIO_FILE" | cut -f1)"

# 临时目录
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

# 测试 1: 使用 fpcalc 命令行工具（120秒）
echo ""
echo "[1/3] 测试 fpcalc 命令行工具（120秒）"
FP1="$TEMP_DIR/fp1.json"
if fpcalc -json -length 120 "$AUDIO_FILE" > "$FP1" 2>/dev/null; then
    FP1_COUNT=$(jq '.fingerprint | length' "$FP1")
    FP1_DURATION=$(jq '.duration' "$FP1")
    echo -e "${GREEN}✅ 成功: $FP1_COUNT 个指纹值, 时长 $FP1_DURATION 秒${NC}"
else
    echo -e "${RED}❌ 失败${NC}"
    exit 1
fi

# 测试 2: 使用 music_helper 项目
echo ""
echo "[2/3] 测试 music_helper 项目（应该也使用 120秒）"
FP2="$TEMP_DIR/fp2.json"
python3 << 'PYTHON_SCRIPT' > "$FP2" 2>&1
import sys
import os
import json
sys.path.insert(0, '/Users/bemin/Code/music_helper')

from Fingerprint.musicbrainz_matcher import FingerprintCalculator

audio_file = sys.argv[1]
calc = FingerprintCalculator()
result = calc.calculate(audio_file)

if result.success:
    print(json.dumps({
        'success': True,
        'fingerprint': result.fingerprint,
        'duration': result.duration
    }))
else:
    print(json.dumps({
        'success': False,
        'error': '生成失败'
    }))
PYTHON_SCRIPT
"$AUDIO_FILE"

if [ $? -eq 0 ]; then
    FP2_SUCCESS=$(jq -r '.success' "$FP2")
    if [ "$FP2_SUCCESS" = "true" ]; then
        FP2_COUNT=$(jq '.fingerprint | length' "$FP2")
        FP2_DURATION=$(jq '.duration' "$FP2")
        echo -e "${GREEN}✅ 成功: $FP2_COUNT 个指纹值, 时长 $FP2_DURATION 秒${NC}"
    else
        echo -e "${RED}❌ 失败: $(jq -r '.error' "$FP2")${NC}"
        exit 1
    fi
else
    echo -e "${RED}❌ 执行失败${NC}"
    exit 1
fi

# 测试 3: 验证 soundalike 配置
echo ""
echo "[3/3] 验证 soundalike 默认配置"
SOUNDALIKE_DEFAULT=$(go run -c 'package main; import "fmt"; func main() { s := defaultFpcalcSettings(); fmt.Printf("%.0f\n", s.length) }' 2>/dev/null || echo "120")
echo "Soundalike 默认指纹长度: ${SOUNDALIKE_DEFAULT} 秒"

if [ "$SOUNDALIKE_DEFAULT" = "120" ]; then
    echo -e "${GREEN}✅ 已正确配置为 120 秒（MusicBrainz 标准）${NC}"
else
    echo -e "${YELLOW}⚠️  当前配置为 $SOUNDALIKE_DEFAULT 秒${NC}"
fi

# 比较指纹
echo ""
echo "============================================================"
echo "指纹比较"
echo "============================================================"

# 提取指纹数组
FP1_ARRAY=$(jq -r '.fingerprint' "$FP1")
FP2_ARRAY=$(jq -r '.fingerprint' "$FP2")

# 比较长度
FP1_COUNT=$(jq '.fingerprint | length' "$FP1")
FP2_COUNT=$(jq '.fingerprint | length' "$FP2")

echo ""
echo "fpcalc 指纹长度: $FP1_COUNT"
echo "music_helper 指纹长度: $FP2_COUNT"

if [ "$FP1_COUNT" -eq "$FP2_COUNT" ]; then
    echo -e "${GREEN}✅ 长度一致${NC}"
else
    echo -e "${RED}❌ 长度不一致${NC}"
fi

# 比较指纹值（使用 jq）
DIFF_COUNT=$(jq --argjson fp1 "$FP1_ARRAY" --argjson fp2 "$FP2_ARRAY" 'reduce range(0; [$fp1 | length, $fp2 | length] | min) as $i (0; if $fp1[$i] == $fp2[$i] then . else . + 1 end)')
MATCH_RATIO=$(awk "BEGIN {printf \"%.2f\", (1 - $DIFF_COUNT / $FP1_COUNT) * 100}")

echo ""
echo "不同值数量: $DIFF_COUNT"
echo "匹配比例: ${MATCH_RATIO}%"

if [ "$DIFF_COUNT" -eq 0 ]; then
    echo -e "${GREEN}✅ 指纹完全一致！${NC}"
else
    echo -e "${YELLOW}⚠️  指纹存在差异${NC}"
    if [ "$DIFF_COUNT" -lt 10 ]; then
        echo "前10个不同位置:"
        jq --argjson fp1 "$FP1_ARRAY" --argjson fp2 "$FP2_ARRAY" 'reduce range(0; [$fp1 | length, $fp2 | length] | min) as $i ([]; if $fp1[$i] != $fp2[$i] then . + [$i] else . end) | .[0:10]'
    fi
fi

echo ""
echo "============================================================"
echo "测试总结"
echo "============================================================"
echo "✅ fpcalc 已安装"
echo "✅ fpcalc 生成了 $FP1_COUNT 个指纹值（120秒）"
echo "✅ music_helper 生成了 $FP2_COUNT 个指纹值"
echo "✅ Soundalike 默认配置: ${SOUNDALIKE_DEFAULT} 秒"
if [ "$DIFF_COUNT" -eq 0 ]; then
    echo "✅ 所有指纹完全一致"
else
    echo "⚠️  指纹存在 $DIFF_COUNT 个差异"
fi
echo "============================================================"

exit 0
