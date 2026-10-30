# 指纹匹配（AcoustID / MusicBrainz）

`Fingerprint/` 回答一个问题：**这个音频文件在 MusicBrainz 里是哪一首？**
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
from Fingerprint import FingerprintMatcher

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

在项目里不需要直接调用——`services/tagger.py` 已经封装好降级与阈值判断：

```python
# services/tagger.py 内部
match = matcher.match_file(track.path)
if match.success and match.recordings:
    best = max(match.recordings, key=lambda r: r.get('score', 0))
    if float(best.get('score') or 0) >= config.FINGERPRINT_THRESHOLD:
        ...  # 只填补空缺标签
```

## 4. 评分与阈值

- AcoustID 返回的 `score` 是 0–1 的概率值，本项目统一乘 100 后与
  `FINGERPRINT_THRESHOLD`（默认 50）比较；
- 多个候选时取分数最高的一条；
- 低于阈值视为「没匹配上」，转由在线平台查询（`services/tagger.py` 第二步）。

阈值调低会补更多标签，但也更容易张冠李戴；调高则宁可留空。默认 50 是「能补上、又不至于
把现场版当成录音室版」的折中。

## 5. 已知限制

| 限制 | 说明 |
|---|---|
| AcoustID 密钥是内置的公共 key | `AcoustIDConfig.ACOUSTID_KEY = 'v8pQ6oyB'`，有速率限制；高频使用请自行申请 |
| 只有网络请求、没有本地缓存 | 同一文件重复查询会重复请求；批量处理时建议先用 `FINGERPRINT_THRESHOLD` 过滤 |
| SSL | 代码对 macOS 使用了 `ssl._create_unverified_context()` 规避证书问题，安全性上属于妥协 |
| 中文匹配 | 依赖 `opencc` 做繁简统一，未安装时繁体标题匹配率下降 |
| 时长偏差 | 现场版、混音版与原版指纹可能相近，最终仍要看分数 |

## 6. 调试

```bash
# 提高日志级别看每一步请求与响应
python -c "
from Fingerprint import FingerprintMatcher
m = FingerprintMatcher(debug_mode=True)
print(m.match_file('1.flac').recordings[:1])
"
```

`Fingerprint/` 下的 `fingerprint_matcher_example.py`、`auto_match_example.py`、
`example_full_release.py` 是可直接运行的示例脚本。
