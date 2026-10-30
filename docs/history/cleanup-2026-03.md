# 历史归档：2026-03 文件清理记录

> **归档说明**：本文合并自 `CLEANUP_SUMMARY.md` 与 `PROJECT_CLEANUP_SUMMARY.md`（两份内容高度重复）。
> 记录的是重构前（`0.2.0` 之前）的一次文件整理，其中的模块名和目录结构已不适用，
> 仅作历史追溯保留，不再更新。

## 整理日期

2026-03-06

## 整理范围

- `music_helper`（Python）
- `soundalike`（Go，独立项目）

---

## music_helper

### 已删除

**根目录临时测试脚本**

- `test_mb_direct.py`
- `simple_test.py`
- `verify_musicbrainz.py`

**根目录临时文档**

- `FINGERPRINT_LENGTH_CONFIG.md`
- `FINGERPRINT_LENGTH_SUMMARY.md`
- `MUSIC_TAGGER_EXAMPLE_UPDATE.md`
- `MATCHER_IMPROVEMENTS.md`

**`test/` 目录临时产物**

- 测试报告：`FINGERPRINT_*.md`、`README_TEST.md`、`FINGERPRINT_CONSISTENCY_REPORT.md`、
  `FINGERPRINT_SOUNDALIKE_FIX.md`、`FINGERPRINT_TEST_GUIDE.md`、`FINGERPRINT_TEST_REPORT_20260306.md`
- JSON 报告：`fingerprint_test_report_20260306_*.json`
- 临时脚本：`test_fingerprint_*.py`、`test_fingerprint_*.sh`、`test_fingerprint_config.py`

### 新增

- `test/test_musicbrainz_connection.py`：MusicBrainz 连接测试
- `test/test_musicbrainz_direct.py`：MusicBrainz 直连 API 测试

> 这两个脚本在 `0.2.0` 重构中改名为 `test/manual_musicbrainz_*.py`，
> 因为它们需要真实网络，不应参与自动测试。

### 保留

- 核心文档：`README.md`、`Doc/FEATURES.md`、`Doc/QUICKSTART.md`、
  `Doc/FINGERPRINT_MATCHER_README.md`、`Doc/TAG_UPDATE_README.md`、`Doc/CHANGELOG.md`
- 核心测试：`test/test_*.py`（12 个文件）

以上文档在 `0.3.0` 中已全部整合进 `docs/`，`Doc/` 目录不再存在。

---

## soundalike

### 已删除

- 临时文档：`DUAL_CONNECTION_METHOD.md`、`GO_VERSION_FIXED.md`、`MUSICBRAINZ_TEST_SUMMARY.md`、
  `TEST_MUSICBRAINZ_FINAL.md`、`MUSICBRAINZ_LOOKUP_TEST.md`、
  `DATABASE_UPGRADE_COMPRESSED_FINGERPRINT.md`、`FINGERPRINT_LENGTH_UPDATE.md`
- 临时脚本：`test_api_connection.sh`、`test_musicbrainz_full.sh`、`test_musicbrainz_python.py`、
  `test_musicbrainz_complete.py`、`test_musicbrainz_final.py`
- 临时 Go 文件：`test_fingerprint_consistency.go.bak`、`test_musicbrainz_demo.go`、
  `test_musicbrainz_demo.go.bak`、`test_musicbrainz_full_lookup.go`、
  `test_musicbrainz_lookup.go`、`test_musicbrainz_mock.go`
- 临时二进制：`soundalike.bak`、`test_musicbrainz_demo`、`test_musicbrainz_fixed`、
  `test_musicbrainz_full_lookup`、`test_musicbrainz_lookup`、`test_musicbrainz_mock`

### 新增

- `test/` 目录与 `test/test_musicbrainz.go`

### 保留

- 核心代码：`main.go`、`fpcalc.go`、`scan.go`、`db.go`、`lookup.go`、`move.go` 及全部 `*_test.go`
- 文档：`README.md`、`FEATURES.md`、`QUICKSTART.md`、`AGENTS.md`、`LICENSE`

---

## 当时的技术改进

1. **SSL 证书修复**：`musicbrainz_matcher.py` 增加 SSL 上下文，解决 macOS 验证失败。
2. **OpenCC 集成**：支持繁体转简体，提升中文匹配率。
3. **测试标准化**：测试代码统一放 `test/`，临时产物不入库。

## 验证

- MusicBrainz 连接测试通过
- 测试文件组织规范
- 临时文件清理完成

## 遗留项（后续在 0.2.0 / 0.3.0 处理）

| 当时列出的下一步 | 最终处理 |
|---|---|
| 定期清理临时文件 | `.gitignore` 收紧，`log/`、`*.log`、`.pytest_cache/` 不再入库 |
| 完善单元测试覆盖 | 0.2.0 重建测试体系，pytest + CI |
| 持续更新 CHANGELOG | CHANGELOG 迁到仓库根目录，纳入发版清单 |
| 使用 Git 标签管理版本 | 改为语义化版本 + `git tag`，见 CHANGELOG |
