# -*- coding: utf-8 -*-
"""music_helper Web UI 包。

- `api.py`：FastAPI 路由（六步向导 + 保留的只读/检查/计划接口）
- `tasks.py`：单工作者串行任务队列，带逐条进度与实时日志
- `static/`：Vue 3 六步向导（无构建链，Vue 运行时在 `static/vendor/`）
- `index.html`：旧版单页仪表盘，仍在 `/legacy` 提供

本包不实现任何业务规则：判定在 `core/`，编排在 `services/steps.py`，
破坏性动作只经 `core.ops.Plan`。
"""
