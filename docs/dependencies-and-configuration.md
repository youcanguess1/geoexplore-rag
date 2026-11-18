# 依赖与配置说明

## 锁定安装

`pyproject.toml` 定义依赖范围，`uv.lock` 固定完整解析结果（包含可选组）。本阶段调整了分组并同步锁文件，没有请求整体升级依赖。锁中出现某个模型 SDK 不表示默认安装会安装或调用它。

从仓库根目录安装开发环境：

```powershell
python -m pip install uv==0.13.1
uv sync --locked --extra dev
```

`uv` 创建本仓库的 `.venv`，`--locked` 防止安装时悄悄改锁。只安装正式 BM25 runtime 时使用 `uv sync --locked --no-dev`。若使用 `python -m pip install -e ".[dev]"`，它会按声明范围解析，不承诺使用 `uv.lock` 的版本；复现验证优先使用锁定安装。

修改依赖后执行 `uv lock`、`uv lock --check`，再在新环境安装和检查。仅更改依赖分组不应顺带升级评分器、解析器或模型参数。

## 分组与理由

| 分组 | 内容与理由 |
| --- | --- |
| 基础 runtime | FastAPI/Uvicorn、Pydantic/settings、HTTPX、SQLAlchemy/greenlet/aiosqlite/Alembic、LangGraph/langchain-core、pypdf、rank-bm25、jieba、序列化、日志、重试、指标及 SSE 支持 |
| 基础 runtime：Redis | 正式容器确有 Redis 检索缓存和限流实现；空 URL 时使用内存实现。保留 SDK 不意味着必须启动 Redis 服务 |
| `dev` | pytest、asyncio/cov 插件、Ruff、mypy 等开发工具 |
| `postgres` | `asyncpg`，只在另行使用异步 PostgreSQL URL 时需要；默认 SQLite 不需要 |
| `vector` | `qdrant-client`，仅用于保留的实验 vector store / payload filter |
| `rerank` | `sentence-transformers`，用于显式调用的本地 embedding / cross-encoder 实验，可能下载权重；不属于正式路径 |
| `docs` | `unstructured` 及额外格式解析支持；正式地学 manifest 选择 `pypdf` 并绕过该 auto-parser 路径 |

ModelScope 在保留的应用、评测、脚本和测试中没有导入或动态调用，因此移除其未使用的直接声明。保留 `greenlet` 是因为 SQLAlchemy 异步桥接与 `run_sync` 需要它；不能仅因没有直接 import 就删除。

按需要显式安装附加组：

```powershell
uv sync --locked --extra dev --extra vector
uv sync --locked --extra dev --extra postgres
```

每次 `uv sync` 都按本次选定的 extras 同步，未选的额外包可能被移除。研究时确需多个组，应在同一条命令全部列出。`vector` 只安装 SDK，不启用正式路径的 Dense/Hybrid；`rerank` / `docs` 同理。不要为完成基础安装而安装全部 extras 或下载模型。

## 本机配置

[.env.example](../.env.example)仅保留值为空的密钥变量。非敏感默认配置定义在 [app/config/settings.py](../app/config/settings.py)，需要覆盖时只在本机 `.env` 中填写相应变量。`.env` 及其本机变体不得提交，Provider 密钥只在本机填写。`DEEPSEEK_API_KEY` 为空时选择离线 Provider，不能产生真实模型答案；语料解析与验证仍需允许使用的 PDF。

| 配置 | 默认行为 |
| --- | --- |
| `DATABASE_URL` | SQLite + aiosqlite，数据在 `data/local/app.db`；内存 SQLite 可用于测试 |
| `REDIS_URL` | 空值使用进程内缓存与限流；配置后尝试连接 Redis，连接不可用时回退本机实现 |
| `GEOLOGICAL_KNOWLEDGE_DIR` / manifest | 依照 manifest 核验 PDF；没有 PDF 时不等于真实语料已验证 |
| `GEOLOGICAL_TOP_K` / context bounds | 5 个 seeds，最多 4 chunks、每块最多 900 字符；改变后不能直接沿用历史身份与结论 |
| embedding / cross-encoder / Qdrant / auto-parser settings | 保留给显式实验或通用解析调用；它们不会让正式容器自动切换到向量或混合路径 |

`postgres` 只提供异步 runtime 驱动，不自动准备数据库服务或迁移配置。Alembic 读取 `alembic.ini` 中独立的同步 URL，默认仍为 SQLite；不能把安装 asyncpg 等同于 PostgreSQL 迁移已验证。

## 容器与 CI

[Dockerfile](../Dockerfile)使用固定版本 uv 和 `uv sync --locked --no-dev --no-editable`，按锁只安装基础 runtime，并复制 LICENSE。`uv.lock` 不再只是被复制但没有使用。默认 [Compose](../docker-compose.yml) 仅提供本机 API：SQLite 持久化挂载、显式关闭 Redis URL、只读 PDF 子挂载、127.0.0.1:9101 端口。该 Compose 配置不包含前端、PostgreSQL 或 Qdrant 服务；前端按[本地启动](02-getting-started.md)另行运行。

Compose 显式的 SQLite/Redis 值覆盖 `.env` 中同名设置，便于保持这份本机演示配置的含义。若要连接外部数据库或缓存，需要自行维护单独的 Compose override，并为镜像安装相应 extras；本仓库不将其当作已验证部署。

[.dockerignore](../.dockerignore)排除本地审计归档和 `output/`，避免它们进入镜像构建上下文。CI 使用锁定 dev 环境，检查命令经 `uv run --no-sync` 使用该环境；这不消除既存测试错误，也不证明 GitHub 托管检查已成功。

## 验证边界

基础 dev 安装应不含 Qdrant、asyncpg、sentence-transformers、torch、Unstructured 或 ModelScope。现有 runtime isolation 测试在合成语料和响应下验证正式入口、JSON/SSE、过滤与持久化，同时拒绝研究 SDK 的导入。默认环境对 Qdrant filter SDK 测试明确跳过；加装 `vector` 后再核对其本地 payload 映射，不接触真实 Qdrant 服务。

这类验证不调用真实 Provider、不下载模型，也不证明六 PDF 启动、浏览器 E2E、PostgreSQL/Redis 外部服务或容器部署通过。全量 unit 收集仍有 `app.guardrails.boundary` 和 `eval.runner` 两项既存缺失导入；参见 [CONTRIBUTING](../CONTRIBUTING.md)。评测结论继续以[历史摘要](evaluation-summary.md)为准。
