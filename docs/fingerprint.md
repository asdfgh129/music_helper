# 指纹匹配（AcoustID / MusicBrainz）

`fingerprint/` 回答一个问题：**这个音频文件在 MusicBrainz 里是哪一首？**
答案用来补标签——不依赖文件名，也不依赖已有标签，所以对「文件名乱、标签空」的库最有效。

## 1. 工作原理

```
音频文件 ──fpcalc──► 声学指纹 + 时长
                        │
                        ▼
              AcoustID API（按指纹模糊查找）
                        │  返回候选 recording + 相似度分数
                        ▼
              MusicBrainz（补全 release / artist / 年份）
                        │
                        ▼
              打分排序 → 最优结果 → 标签字段
```

- **指纹**是音频信号本身的特征，跟文件格式、码率、文件名无关；
- `fpcalc` 采样长度为 `FPCALC_LENGTH`（默认 120 秒），**必须与声纹库一致**，否则比对失效；
- AcoustID 负责「像不像」，MusicBrainz 负责「是哪张专辑、哪一年」。

## 2. 依赖

| 依赖 | 用途 | 缺失后果 |
|---|---|---|
| `fpcalc`（Chromaprint） | 计算指纹 | 声纹匹配直接不可用，降级为在线平台查询 |
| `acoustid` / `requests` | 调用 API | 同上（本模块内部用 `urllib`，不强制 `requests`） |
| `opencc` | 繁简转换 | 繁体标题不转换，匹配率略降 |
| 网络 | 访问 acoustid.org / musicbrainz.org | 查询失败，返回 `MatchResult(success=False)` |

安装 `fpcalc`：

```bash
# Windows: 下载 chromaprint-fpcalc 解压后加入 PATH
# macOS
brew install chromaprint
# Ubuntu / Debian
sudo apt install libchromaprint-tools
```

## 3. 作为库使用

```python
from fingerprint import FingerprintMatcher

matcher = FingerprintMatcher()                 # fpcalc 不在 PATH 时传 fpcalc_path=...
result = matcher.match_file('song.flac')

if result.success and result.recordings:
    best = max(result.recordings, key=lambda r: r.get('score', 0))
    print(best['score'], best.get('title'), best.get('artist'))
else:
    print('未匹配:', result.error)
```

常用成员：

| 成员 | 说明 |
|---|---|
| `FingerprintMatcher(fpcalc_path=None, client_version=None, debug_mode=False)` | 主入口 |
| `.match_file(path, metadata=None)` | 返回 `MatchResult` |
| `MatchResult.success / recordings / best_match / error` | `recordings` 是按分数排好序的 dict 列表 |
| `format_recording_info(recording)` | 把一条 recording 格式化成可读文本 |
| `FingerprintCalculator(fpcalc_path)` | 只算指纹，不查网络 |
| `AcoustIDClient` | 只查 AcoustID，不算指纹 |

在项目里不需要直接调用——`tagger/__init__.py` 已经封装好降级与阈值判断：

```python
# tagger/__init__.py 内部
match = matcher.match_file(track.path)
if match.success and match.recordings:
    best = max(match.recordings, key=lambda r: r.get('score', 0))
    if float(best.get('score') or 0) >= config.FINGERPRINT_THRESHOLD:
        ...  # 只填补空缺标签
```

## 4. 评分与阈值

- AcoustID 的原始分数是 0–1 的概率值；`fingerprint/` 在合并多个来源后会归一化为
  **0–100 的百分制**，`tagger/` 直接与 `config.FINGERPRINT_THRESHOLD`（默认 50）比较；
- 多个候选时取分数最高的一条；
- 低于阈值视为「没匹配上」，转由在线平台查询（`tagger/__init__.py` 第二步）。

阈值调低会补更多标签，但也更容易张冠李戴；调高则宁可留空。默认 50 是「能补上、又不至于
把现场版当成录音室版」的折中。

> `FINGERPRINT_THRESHOLD` **只用于标签匹配**，不参与查重。查重是否执行由
> `--skip-fingerprint` 控制，移动目标由 `soundalike` 的交互确认决定。

## 5. 已知限制

| 限制 | 说明 |
|---|---|
| AcoustID 密钥是内置的公共 key | `AcoustIDConfig.ACOUSTID_KEY = 'v8pQ6oyB'`，有速率限制；高频使用请自行申请 |
| 只有网络请求、没有本地缓存 | 同一文件重复查询会重复请求；批量处理时建议先用 `FINGERPRINT_THRESHOLD` 过滤 |
| SSL | 代码对 macOS 使用了 `ssl._create_unverified_context()` 规避证书问题，安全性上属于妥协 |
| 中文匹配 | 依赖 `opencc` 做繁简统一，未安装时繁体标题匹配率下降 |
| 时长偏差 | 现场版、混音版与原版指纹可能相近，最终仍要看分数 |

## 6. 同曲不同版本的碰撞

结论：**声纹会误判，但场景可枚举。指纹只能证明「音频很像」，不能证明「是同一版本」。**
因此查重不能只看指纹，必须叠加时长、版本标记与元数据。

### 6.1 常见误判场景

| 场景 | 指纹表现 | 处理 |
|---|---|---|
| 同一录音换格式/码率 | 几乎相同 | 判重复（期望行为） |
| 同一录音收在不同专辑 | 几乎相同 | 判重复 |
| Remaster（重新母带） | 高度相似 | 倾向判重复 |
| 现场版 vs 录音室版 | 可能高度相似 | 版本标记不同 → 人工 |
| 伴奏版 / instrumental | 可能相似 | 版本标记不同 → 人工 |
| 不同歌手同一伴奏（翻唱/KTV） | 可能相似 | 版本标记不同 → 人工 |
| feat. 版本（加一段 verse） | 大部分相同 | 版本标记不同 → 人工 |
| 短片段、纯音乐、重复节奏 | 易碰撞 | 时长过滤 + 人工 |

### 6.2 判定矩阵

| 指纹 | 版本标记 | 时长差 | 结论 |
|---|---|---|---|
| 高相似 | 同类 | ≤ `DURATION_TOLERANCE` | 重复，保留质量最高者 |
| 高相似 | 不同类 | 任意 | 疑似不同版本 → 人工复核 |
| 高相似 | 一方缺失标记 | ≤ `DURATION_TOLERANCE` | 重复候选 → 人工复核 |
| 低相似 | 同类 | ≤ `DURATION_TOLERANCE` | 疑似同名不同版 → 人工复核 |
| 低相似 | 不同类 | 任意 | 不同文件，保留 |

关键一条：**「指纹像 + 版本标记不同」永远不自动移入 `DUPLICATE_DIR`。**

### 6.3 现有实现

- 本地查重键由 `core/naming.py: version_key()` 生成，保留 Live/Remix/伴奏等标记。
  `晴天 (Live)` 与 `晴天` 不会进入同一个标签桶；
- `core/dedupe.py` 在键相同后再按时长聚类，时长未知的候选会被标注；
- `soundalike` 是外部黑盒，项目无法读取它的相似度分数，只能通过
  `-move-interactive` 由人工确认每一次移动；
- `soundalike` 的移动目标固定为 `DUPLICATE_DIR`，不会进入回收站；
  `--trash-dup` 只作用于本地查重阶段。

### 6.4 提高准确率的做法

1. 声纹查重前先按「版本感知的去重键」分桶，只对同桶做比对；
2. 版本标记不同的候选写进报告，不自动移动；
3. 重复清单保留「指纹来源 / 时长差 / 版本标记 / 保留理由」，便于回滚；
4. 两个阈值不要混用：`FINGERPRINT_THRESHOLD` 只决定标签匹配，
   `DURATION_TOLERANCE` 只决定查重聚类。

## 7. 调试

```bash
# 提高日志级别看每一步请求与响应
python -c "
from fingerprint import FingerprintMatcher
m = FingerprintMatcher(debug_mode=True)
print(m.match_file('tests/fixtures/1.flac').recordings[:1])
"
```

`tests/manual/manual_musicbrainz.py` 是现成的手工验证脚本（需要真实网络与 AcoustID key）：
`--mode match` 跑全链路，`--mode api` 只打裸接口用来区分网络问题与匹配链路问题，
用法见 [troubleshooting.md](troubleshooting.md)。
