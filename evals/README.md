# GeoExplore 评测资产索引

本目录保留冻结题集和最小历史证据，评测实现位于 `eval/`，命令入口位于 `scripts/`。题集未因发布整理而重写；schema 与用途不同，不能互换分母。

| 文件 | 题数 | Schema / 用途 |
| --- | ---: | --- |
| [dev_questions.json](dev_questions.json) | 8 | legacy retrieval 列表，`eval.geological.load_questions` |
| [acceptance_questions.json](acceptance_questions.json) | 16 | 同一 legacy retrieval schema，不是十题生成验收 |
| [retrieval_dev_questions.json](retrieval_dev_questions.json) | 7 | generation schema 字典，检索诊断 |
| [generation_dev_questions.json](generation_dev_questions.json) | 6 | generation schema，开发集 |
| [generation_acceptance_questions.json](generation_acceptance_questions.json) | 10 | generation schema，显式 gate 验收集 |
| [v2/dev_questions.json](v2/dev_questions.json) | 8 | research retrieval v2，`eval.geological_v2.load_questions` |
| [v2/acceptance_questions.json](v2/acceptance_questions.json) | 16 | 同一 research v2 schema |
| [Day 3 questions.json](results/2026-10-26-day3-new-question-check-154705/questions.json) | 8 | generation schema，`split=dev`，同语料新题 |

## 实现与运行入口

- [eval/geological.py](../eval/geological.py)、[geological_v2.py](../eval/geological_v2.py)：对应 schema 的加载、检查与评分 helper；不是现成的端到端 retrieval CLI。
- [geological_generation.py](../eval/geological_generation.py)：generation schema、canonical 哈希、split 分离与自动检查。
- [metrics.py](../eval/metrics.py)：通用指标 helper；不代表缺失的历史 `eval.runner` 已恢复。
- [run_generation_eval.py](../scripts/run_generation_eval.py)：带 Acceptance gate 的正式 BM25 生成评测。
- [diagnose_generation_retrieval.py](../scripts/diagnose_generation_retrieval.py)：检索/上下文诊断。
- [run_day3_new_question_eval.py](../scripts/run_day3_new_question_eval.py)：冻结新题的 retrieval 与 generation 分阶段入口。

真实运行需要完整且身份匹配的 PDF；生成还需要 Provider。新输出须使用忽略的 `output/` 和新路径，避免 runner 的历史默认输出覆盖已有证据。执行细节见[协议](../docs/evaluation-protocol.md)，结论见[摘要](../docs/evaluation-summary.md)。

## 保留与归档边界

[results 索引](results/README.md)列出两份 Acceptance 和完整 Day 3 五文件证据包。中间开发/消融结果、本机 API/浏览器准备记录、旧 Dense/Hybrid 配置和旧交付清单已原样移入本地忽略归档。它们不再是公开导航依赖，也不代表本版本启用 Dense/Hybrid。原题集与所有 `eval/` 实现保持原字节。
