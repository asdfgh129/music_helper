# AGENTS.md

给在这个仓库里工作的 AI 代理的速查表。**详细规则以 `docs/` 为准**，本文只列不可违反的约束
和最容易踩的坑。

## 项目是什么

Python 音乐库流水线：解密 → 去重 → 补标签 → 检查 → 分流 → 归档 → 人工确认入库。
入口 `python main.py`。主要目标平台 Windows（QQ 解密依赖 Frida 注入客户端），Python 3.11+。
QQ 解密前的客户端安装 / 启动 / 登录检查在 `decrypto/qq_client.py`，改动解密流程时先看它。

## 必读

| 场景 | 文档 |
|---|---|
| 改代码前 | [docs/architecture.md](docs/architecture.md)（分层与唯一实现原则） |
| 改判定规则前 | [docs/rules.md](docs/rules.md)（文件名/标签/重复/歌词/归档） |
| 改自检逻辑/读报告前 | [docs/self-check.md](docs/self-check.md)（流程、级别、局限、误判排查） |
| 改流程顺序前 | [docs/workflow.md](docs/workflow.md)（端到端状态迁移） |
| 加命令行参数 | [docs/usage.md](docs/usage.md)（参数优先级顺序敏感） |
| 改配置项 | [docs/configuration.md](docs/configuration.md) |
| 写文档/移动文档 | [docs/README.md](docs/README.md)、[CONTRIBUTING.md](CONTRIBUTING.md) |
| 推不上 GitHub | [docs/git-proxy.md](docs/git-proxy.md)（`scripts/git_uplink.py`） |

## 常用命令

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -p 'test_*.py'   # 不装 pytest 也能跑
python -m pytest -q                                  # 全量测试，必须全绿
python -m ruff check .                               # 静态检查（CI lint job 同款）
python -m compileall -q core services tagger music_tagger decrypto fingerprint scripts tests main.py config.py utils.py
python -c "import config, utils, main"               # 导入冒烟
python scripts/check_docs.py                         # 文档校验：链接 / 路径 / 命令
python main.py --check --dry-run                     # 用真实配置预览
```

## 硬约束

1. **`core/` 不碰副作用**：不做网络请求、不调用外部程序、不删用户文件。破坏性动作只有
   `core.ops.Plan` 一个出口；`Plan` 里移动成功后清理源文件（`os.unlink`）属于「移动」的一部分，
   不得用来做删除——删除一律移入 `log/_trash/`。
2. **破坏性动作只能走 `core.ops.Plan`**：`add_move` / `add_rename` / `add_trash`，必须带 `reason`，
   必须支持 `dry_run`。删除 = 移入 `log/_trash/`。`rename` 撞车必须失败并写 journal，
   不许自动加 `_1` 后缀造出查不出来的重复文件。
3. **一个功能只有一处实现**：命名规则 `core/naming.py`、标签 `core/tags.py`（含一次读三件事的
   `read_meta`）、重复 `core/dedupe.py`、归档 `core/organize.py`、歌词 `core/lyrics.py`。
   不要在别处再写一套。
4. **`config.py` 只放数据**，不许 `import core` / `import services` / `import tagger`（会重演循环导入事故）。
   配置优先级固定为环境变量 > `config.ini` > 默认值。
5. **可选依赖延迟导入 + 降级**：缺 `requests`/`mutagen`/`fpcalc` 只降级能力，`import main` 不许失败。
6. **`--fix` 不要扩大移动范围**：只有 `severe`（歌曲名/歌手缺失、文件名与标签矛盾）才移文件；
   缺封面/专辑/年份只报告。否则一次 `--fix` 能把整个库搬空。
7. **加密原文件去向**由 `ENCRYPTED_SOURCE_MODE` 控制（默认 `return` 搬回 VIP 目录），
   只处理本次移入暂存区的文件，不许遍历目录批量搬运。
8. **待补全判定只在 `core.check.readiness_problems()`**：歌曲名/歌手/专辑/年份齐全且
   文件名与标签不矛盾；封面和歌词不参与。不要在 `main.py` 另写一套。
9. **外部二进制统一放 `tools/`**：同一程序的多个平台产物用 Go 的 `<名字>-<GOOS>-<GOARCH>`
   区分（`soundalike-darwin-arm64`、`um-darwin-amd64`），路径由 `config.py` 的 `_default_*()`
   按平台挑、支持环境变量覆盖；执行前一律用 `utils.tool_problem()` 预检（缺文件 / 缺
   `chmod +x` / 平台不匹配），业务模块不要自己写 `sys.platform` 分支。
   **它们的源码在 `third_party/`**（见 [third_party/README.md](third_party/README.md)）：
   改 `tools/` 里的产物必须同步改对应源码，否则下次重建就把改动弄丢了。`um` 的源码只能从
   `GOPROXY=https://goproxy.cn` 取（GitHub 仓库因 DMCA 整站 451）。
10. **新增音频格式要成对改**：`config.AUDIO_EXTENSIONS` 与 `core/tags.py` 的 `_READERS` /
    `_COVER_READERS`。只加扩展名不加读取器，整类文件会被判成「缺标签」搬进 `INCOMPLETE_DIR`；
    `tests/test_tags.py` 会拦住这种漏改。

## 测试

- 单元测试不得触碰真实音乐库、网络、外部 exe；一律用 `tempfile`。
- 需要真实网络的脚本放 `tests/manual/`、以 `manual_` 开头，不参与自动收集。
- 改行为必须补用例；不接受「已知失败」。
- 新增/移动测试文件后，同步 `pyproject.toml` 的 `testpaths`（当前 `tests`）。

## 提交

Conventional Commits：`fix(core/dedupe): ...`、`docs: ...`。一次提交一件事。
改了行为同步 `docs/rules.md` + `CHANGELOG.md`；改了流程同步 `docs/workflow.md`；
改了配置同步 `docs/configuration.md`。

## 历史包袱（知道就好，别再引入）

- 旧模块 `file_operations.py` / `tag_updater.py` / `archive.py` / `duplicate.py` / `lrc.py` /
  `metadata.py` / `vip_decrypt.py` / `soundalike.py` 已删除，逻辑合并进 `core/`、`services/`。
  看到引用它们的代码或文档，说明是过期的。
- `Doc/` 目录已不存在，内容并入 `docs/`。
- `Decrypto/`、`Fingerprint/` 已改名为小写 `decrypto/`、`fingerprint/`（0.5.0）。
- 外部程序已从各包目录移到 `tools/`（0.6.0）；旧文档里写在 `decrypto/`、`fingerprint/`
  下的 exe 路径都已过期。
- `test/` 已改名为 `tests/`（0.6.0）。
- 旧名 `MAIN_DIR`、`TEMP_COMPLETED_DIR`、`TEMP_MOVE_DIR`、`TEMP_REVIEW_DIR` 仅作兼容别名，
  新代码用 `LIBRARY_DIR`、`WORKSPACE_DIR`、`DUPLICATE_DIR`、`INCOMPLETE_DIR`。
- 历史文档在 `docs/history/`，只读，不要照着里面的模块名写代码。
