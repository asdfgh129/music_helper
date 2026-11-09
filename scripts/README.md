# scripts —— 开发期工具

**这里的脚本都不参与音乐库流水线**，删除任何一个都不影响 `main.py` / `web/` 运行。
主流程的代码在 `core/`、`services/`、`tagger/`、`decrypto/`、`fingerprint/`。

| 脚本 | 用途 | 属于 | 用不到时的影响 |
|---|---|---|---|
| [check_docs.py](check_docs.py) | 校验 `docs/` 里的相对链接、代码路径、命令是否仍然存在 | 文档维护 | 文档里的链接会静默腐烂 |
| [build_docs_index.py](build_docs_index.py) | 生成 `docs/index.html`：覆盖全仓 Markdown 的可搜索索引；`--check` 检查是否过期 | 文档维护 | 新增文档后索引会静默过期 |
| [gen_web_guide_images.py](gen_web_guide_images.py) | 生成 `docs/images/` 里的八步向导配图 | 文档维护 | 配图与界面可能不一致 |
| [git_uplink.py](git_uplink.py) | 本机 `github.com:443` 被重置时，临时起本地代理给 git 用 | 开发同步 | 只能 push 不了代码，与程序无关 |

## 约定

- 脚本只依赖标准库，或已在本机安装的第三方包；不引入新的 `requirements.txt` 条目。
- 输出路径一律相对项目根目录，不依赖当前工作目录。
- 新增脚本时先问一句：它会在 `main.py` 或 `web/api.py` 里被导入吗？会的话它不属于这里。

最后一条规则的由来：`git_uplink.py` 曾经因为「看起来像项目工具」被误认为运行时依赖。
它实际上只在开发机 push 时用，见文件头部的说明。
