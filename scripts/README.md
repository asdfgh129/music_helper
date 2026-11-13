# scripts —— 开发期工具

**这里的脚本都不参与音乐库流水线**，删除任何一个都不影响 `main.py` / `web/` 运行。
主流程的代码在 `core/`、`services/`、`tagger/`、`decrypto/`、`fingerprint/`。

| 脚本 | 用途 | 属于 | 用不到时的影响 |
|---|---|---|---|
| [check_docs.py](check_docs.py) | 校验相对链接、代码路径、命令是否仍然存在；跳过 `dist/` 与 `build/` 等生成产物 | 文档维护 | 文档里的链接会静默腐烂 |
| [build_docs_index.py](build_docs_index.py) | 生成 `docs/index.html`：侧栏导航 + 首页总览 + 文档状态的单文件离线文档站；正文内嵌、逐篇标注校验结果，只收录项目自身文档（`third_party/` 下上游自带文档不纳入）；`--check` 检查是否过期 | 文档维护 | 新增文档后索引会静默过期 |
| [gen_web_guide_images.py](gen_web_guide_images.py) | 生成 `docs/images/` 里的八步向导配图 | 文档维护 | 配图与界面可能不一致 |
| [git_uplink.py](git_uplink.py) | 本机 `github.com:443` 被重置时，临时起本地代理给 git 用 | 开发同步 | 只能 push 不了代码，与程序无关 |
| [build_exe.py](build_exe.py) | 生成 `dist/` 免 Python 绿色包：PyInstaller onedir + 外部程序 / Web 资源 / 配置 / 启动脚本 / 产物自检；根目录 `build_exe.bat` 可双击 | 分发打包 | 目标机器没装 Python 时只能跑源码模式 |

## 约定

- 脚本只依赖标准库，或已在本机安装的第三方包；不引入新的 `requirements.txt` 条目。
- 构建期依赖单独放 [../requirements-build.txt](../requirements-build.txt)（PyInstaller），
  产物运行不需要它；`build_exe.py` 缺依赖时会自动安装并给出提示。
- 输出路径一律相对项目根目录，不依赖当前工作目录；`dist/` 是生成产物，不要手工编辑。
- 新增项目文档时给 `build_docs_index.py` 的 `DOC_CATEGORY_OF` 补分类映射，并登记到
  [../docs/README.md](../docs/README.md) 的分类表；漏配会在索引里显示「未分类」并在生成时告警。
- 新增脚本时先问一句：它会在 `main.py` 或 `web/api.py` 里被导入吗？会的话它不属于这里。

最后一条规则的由来：`git_uplink.py` 曾经因为「看起来像项目工具」被误认为运行时依赖。
它实际上只在开发机 push 时用，见文件头部的说明。
