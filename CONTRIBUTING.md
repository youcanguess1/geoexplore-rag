# 贡献指南

## 依赖与实验范围

依赖来源为 `pyproject.toml`，`uv.lock` 保存锁定版本。修改依赖时需要同步锁文件；使用 `uv lock` 更新，用 `uv lock --check` 检查声明与锁是否一致。

```bash
uv sync --locked --extra dev
uv lock --check
uv sync --locked --extra dev --extra vector
```

`postgres` 提供可选异步 PostgreSQL 驱动，`vector` 提供实验 Qdrant SDK，`rerank` 和 `docs` 保留研究或额外解析依赖。Redis 是正式缓存/限流支持的一部分，保留在基础依赖。默认 dev 环境没有 Qdrant SDK，只有对应的 SDK 映射测试会明确跳过；安装 `dev,vector` 后应执行该测试。安装 `rerank` 不会使正式路径启用 Dense/Hybrid 或 reranker；正式入口与未完成研究模块见 [实验边界](app/experiments/README.md)。

## 检查入口与现状

仓库配置了 Ruff、mypy、pytest 及 Python 3.11/3.12 的 CI 工作流。以下是检查入口，不是已经全量通过的声明；工作流文件本身也不构成托管 CI 成功证据。

```bash
python -m ruff format --check .
python -m ruff check .
python -m mypy
python -m compileall -q app eval scripts
python -m pytest -q
```

当前全量 unit 收集存在两项既存错误：`tests/unit/test_guardrails.py` 引用缺失的 `app.guardrails.boundary`；`tests/unit/test_metrics.py` 引用缺失的 `eval.runner`。这些错误仍未修复，不应将下面可运行子集的通过写成全套通过。

```bash
python -m pytest tests/unit/test_geological_eval.py tests/unit/test_geological_eval_v2.py tests/unit/test_geological_generation_eval.py -q
python -m pytest tests/unit/test_geological_chain.py tests/unit/test_geological_manifest.py tests/unit/test_metadata_filters.py tests/unit/test_production_bm25.py tests/unit/test_runtime_isolation.py -q
```

上述 `python` 检查应在 `.venv` 激活后执行，或使用 `.venv` 的解释器。依赖分组与容器约定见[依赖与配置说明](docs/dependencies-and-configuration.md)。

这些命令使用本地数据或合成替身，不需要真实 Provider，也不证明六份 PDF 的完整语料已启动或浏览器 E2E 已完成。CI 配置中的 70% 覆盖率门槛仍是待验证的门槛。

## 变更与评测记录

保持现有分层，通过 schema 传递数据；只修改当前任务需要的部分。不要提交 `.env`、密钥、数据库、模型缓存或个人工作区记录。

冻结题集与历史结果应原样保留。新增评测先阅读[协议](docs/evaluation-protocol.md)，显式指定新的 `output/` 路径；不要使用会覆盖历史文件的默认输出。Acceptance、Day 3 与 retrieval-only 分开报告，人工判断与自动指标分开说明。历史结论与已知失败见[评测摘要](docs/evaluation-summary.md)。
