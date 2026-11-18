# GeoExplore · 地学文献 RAG 问答

面向地学 PDF 的问答原型：按文档类型、语言和文档 ID 筛选资料，通过 BM25 检索与受限上下文生成回答，并展示来源文档和物理 PDF 页码。后端使用 FastAPI / LangGraph，前端使用 React / TypeScript。

## 项目看点

- **检索范围可控**：先应用元数据过滤，再进行 BM25 检索；同文档前序块扩展补足跨块证据。
- **答案可以核对来源**：保留文档、chunk、物理页码和语料指纹，前端展示引用。
- **区分回答与证据**：配置模型时生成结构化答案；未配置模型时返回检索证据，证据不足与执行失败有独立状态。
- **完整交互链路**：支持 JSON / SSE、会话持久化和前端历史记录。

## 核心链路

```text
React → FastAPI → 元数据过滤 → BM25 top-5
      → 同文档前序块扩展 → 上下文预算 → 结构化回答 / 引用
                              ↘ JSON / SSE → 会话持久化
```

历史基线采用 `pypdf`、500 字符分块与 60 字符重叠；生成上下文最多 4 个块，每块最多 900 字符。正式路径使用 BM25；Dense、Hybrid 和 reranker 的兼容实验代码不作为已完成的正式功能展示。实现与边界见[架构说明](docs/ARCHITECTURE.md)。

## 本地启动

需要 Python 3.11+、Node.js 20.19+ 或 22.12+。以下命令在仓库根目录运行，示例使用 PowerShell：

```powershell
python -m pip install uv==0.13.1
uv sync --locked --extra dev
Copy-Item .env.example .env
```

仓库**不附带 PDF**。后端启动需要按[语料说明](data/README.md)自行取得允许使用的资料，核对 manifest 中的哈希。历史基线为 6 份文档 / 1006 个块；manifest 不等于已提供语料。需要真实生成时，仅在本机 `.env` 填写 `DEEPSEEK_API_KEY`。

启动 API：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.asgi:app --host 127.0.0.1 --port 9101
```

另开终端启动前端：

```powershell
Set-Location frontend
npm ci
npm run dev
```

打开 `http://127.0.0.1:5180`，前端将 `/api` 转发至 `127.0.0.1:9101`。前端可独立启动查看界面，真实问答需要可用后端与已验证语料。本项目定位为本机演示原型，浏览器 client ID 不提供用户认证。

## 离线验证

无需 PDF 或真实模型服务即可运行单元测试及使用合成语料的 HTTP API 集成测试：

```powershell
uv run --no-sync python -m ruff format --check .
uv run --no-sync python -m ruff check .
uv run --no-sync python -m mypy
uv run --no-sync python -m pytest -q --cov=app --cov=eval --cov-fail-under=70
```

前端在 `frontend` 目录执行 `npm test` 和 `npm run build`。CI 覆盖 Python 3.11 / 3.12 的格式、类型和测试检查，以及前端测试与构建；实际运行状态见仓库的 Actions 页面。

## 阅读入口

| 内容 | 入口 |
| --- | --- |
| 环境、语料与配置 | [快速开始](docs/02-getting-started.md) · [依赖与配置](docs/dependencies-and-configuration.md) |
| 正式请求路径与实验边界 | [架构](docs/ARCHITECTURE.md) · [实验代码说明](app/experiments/README.md) |
| 本地演示与发布范围 | [演示指南](docs/project-delivery.md) · [发布范围](docs/release-scope.md) |

## 来源与许可

本项目基于既有开源应用基础改造成地学文献 RAG 原型，保留原 [MIT License](LICENSE)。本仓库展示正式 BM25 问答链路、元数据过滤、引用与语料身份及前端交互；不将继承的全部基础代码声明为从零原创。PDF 的来源与再分发权限需独立核实。
