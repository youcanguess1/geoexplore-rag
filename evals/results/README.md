# 历史评测证据索引

此目录保留七份原始证据文件，未改写其字节。它们记录不同时间、不同目的的运行，不能混合统计。此处的 README 与 SHA256SUMS 是后加导航及校验文件，不属于七份历史证据。

| 文件 | 角色与限制 |
| --- | --- |
| [Acceptance first-run](2026-10-22-generation-acceptance-first-run.json) | 首次生成验收的网络失败背景；单独保留，不与后一次合计 |
| [Acceptance after-egress-fix](2026-10-22-generation-acceptance-after-egress-fix.json) | 十题修复后运行；8/10 状态匹配，原验收未通过，PDF 人工复核字段仍 pending |
| [Day 3 questions](2026-10-26-day3-new-question-check-154705/questions.json) | 八道冻结题及标签、证据；同语料、非盲测 |
| [Day 3 run-manifest](2026-10-26-day3-new-question-check-154705/run-manifest.json) | 环境、语料、运行参数、题集和历史文件哈希 |
| [Day 3 retrieval-results](2026-10-26-day3-new-question-check-154705/retrieval-results.json) | 原始候选、扩展与上下文覆盖；不是生成答案质量评分 |
| [Day 3 generation-results](2026-10-26-day3-new-question-check-154705/generation-results.json) | 实际响应、引用、Provider 调用、usage 与耗时 |
| [Day 3 report](2026-10-26-day3-new-question-check-154705/report.md) | 历史人工核对、独立分母与局限 |

[SHA256SUMS](SHA256SUMS)中的路径相对此目录，覆盖恰好七份历史证据；不是当前全仓库校验清单。[协议](../../docs/evaluation-protocol.md)给出 PowerShell 校验方法和新运行的独立输出规则。

原始 manifest / report 的旧文件路径、工作区状态或 Git 信息属于当时快照，不表示这些旧文件在当前副本仍存在。报告将 `geo-day3-006` 的证据写作 `geo-day3-006_61`；对应原始检索数据的实际 chunk ID 为 `geo-of12-1191_61`。保留报告字节，通过[评测摘要](../../docs/evaluation-summary.md)说明差异。Acceptance 的历史 6/8 人工正确性汇总也不能解释成其 JSON 的 pending 字段已完成。

中间结果、旧研究配置和本机交付流水已原样移入本地忽略归档，不作为发布运行依赖。当前目录不提供浏览器 E2E 通过证明。题集与实现的完整入口见[上级索引](../README.md)。
