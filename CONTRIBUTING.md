# 贡献指南

## 安装与依赖

依赖声明在 `pyproject.toml`，版本锁定在 `uv.lock`。变更依赖时同步锁文件；基础开发环境不需要真实 Provider、PDF、Qdrant 或模型下载。

```bash
uv sync --locked --extra dev
uv lock --check
```

`postgres` 提供可选数据库驱动；`vector`、`rerank` 和 `docs` 用于显式实验。安装这些分组不会改变正式 BM25 路径。实验范围见[说明](app/experiments/README.md)。

## 检查

```bash
uv run --no-sync python -m ruff format --check .
uv run --no-sync python -m ruff check .
uv run --no-sync python -m mypy
uv run --no-sync python -m pytest -q --cov=app --cov=eval --cov-fail-under=70
```

前端在 `frontend` 目录执行 `npm ci`、`npm test`、`npm run build`。CI 对 Python 3.11 / 3.12 和前端分别执行检查；托管结果以 Actions 为准。

`tests/unit` 检查当前存在的组件和指标。早期测试中针对未提供的通用业务边界与旧评测 runner 的断言已移除，提示词拦截和指标计算的有效测试保留。`tests/e2e` 是 HTTP API 集成测试：只替换语料入口，使用合成 chunk、服务端语料身份与内存 SQLite，经过真实应用生命周期、检索、路由和 JSON/SSE 序列化，并禁止出站异步 HTTP。它不替代真实 PDF、真实 Provider 或浏览器验证。

默认 dev 环境未安装 Qdrant SDK 时，其本地 payload 映射测试明确跳过；可用 `uv sync --locked --extra dev --extra vector` 安装后执行。该测试不连接真实 Qdrant 服务。

## 变更与证据

保留既有分层，避免将实验实现写成正式功能。不要提交 PDF、`.env`、密钥、数据库、缓存或个人工作区记录。

冻结题集与历史结果原样保留。新增评测先阅读[协议](docs/evaluation-protocol.md)，使用新的 `output/` 路径。Acceptance、Day 3 与 retrieval-only 分开报告，人工判断与自动指标分开说明；结果与局限见[评测摘要](docs/evaluation-summary.md)。
