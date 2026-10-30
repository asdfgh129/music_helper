# AGENTS.md

给在这个仓库里工作的 AI 代理的速查表。**详细规则以 `docs/` 为准**，本文只列不可违反的约束
和最容易踩的坑。

## 项目是什么

Python 音乐库流水线：解密 → 去重 → 标签 → 检查 → 归档。入口 `python main.py`。
主要目标平台 Windows（QQ 解密依赖 Frida），Python 3.11+。

## 必读

| 场景 | 文档 |
|---|---|
| 改代码前 | [docs/architecture.md](docs/architecture.md)（分层与唯一实现原则） |
| 改判定规则前 | [docs/features.md](docs/features.md)（现成的规则与边界） |
| 加命令行参数 | [docs/usage.md](docs/usage.md)（参数优先级顺序敏感） |
| 改配置项 | [docs/configuration.md](docs/configuration.md) |
| 写文档/移动文档 | [docs/README.md](docs/README.md)、[CONTRIBUTING.md](CONTRIBUTING.md) |

## 常用命令

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q                                  # 全量测试，必须全绿
python -m compileall -q core services main.py        # 语法检查
python -c "import config, utils, main"               # 导入冒烟
python scripts/check_docs.py                         # 文档链接检查
python main.py --check --dry-run                     # 用真实配置预览
```

## 硬约束

1. **`core/` 不碰副作用**：不做网络请求、不调用外部程序、不 `os.remove`、不直接 `shutil.move`。
2. **破坏性动作只能走 `core.ops.Plan`**：`add_move` / `add_rename` / `add_trash`，必须带 `reason`，
   必须支持 `dry_run`。删除 = 移入 `log/_trash/`。
3. **一个功能只有一处实现**：命名规则 `core/naming.py`、标签 `core/tags.py`、重复 `core/dedupe.py`、
   归档 `core/organize.py`、歌词 `core/lyrics.py`。不要在别处再写一套。
4. **`config.py` 只放数据**，不许 `import core` / `import services`（会重演循环导入事故）。
5. **可选依赖延迟导入 + 降级**：缺 `requests`/`mutagen`/`fpcalc` 只降级能力，`import main` 不许失败。
6. **`--fix` 不要扩大移动范围**：只有 `severe`（歌曲名/歌手缺失、文件名与标签矛盾）才移文件；
   缺封面/专辑/年份只报告。否则一次 `--fix` 能把整个库搬空。
7. **加密原文件去向**由 `ENCRYPTED_SOURCE_MODE` 控制（默认 `return` 搬回 VIP 目录），
   只处理本次移入临时目录的文件，不许遍历目录批量搬运。

## 测试

- 单元测试不得触碰真实音乐库、网络、外部 exe；一律用 `tempfile`。
- 需要真实网络的脚本命名 `test/manual_*.py`，不参与自动收集。
- 改行为必须补用例；不接受「已知失败」。

## 提交

Conventional Commits：`fix(core/dedupe): ...`、`docs: ...`。一次提交一件事。
改了行为同步 `docs/features.md` + `CHANGELOG.md`。

## 历史包袱（知道就好，别再引入）

- 旧模块 `file_operations.py` / `tag_updater.py` / `archive.py` / `duplicate.py` / `lrc.py` /
  `metadata.py` / `vip_decrypt.py` / `soundalike.py` 已删除，逻辑合并进 `core/`、`services/`。
  看到引用它们的代码或文档，说明是过期的。
- `Doc/` 目录已不存在，内容并入 `docs/`。
- 历史文档在 `docs/history/`，只读，不要照着里面的模块名写代码。
