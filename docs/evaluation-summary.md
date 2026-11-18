# GeoExplore 评测汇总与证据边界

## 范围与读法

本页汇总保留的历史运行，不代表本次清理重新执行了评测。Acceptance、Day 3 和 retrieval-only 的目的与分母不同，不能合并为总体准确率。正式链路为 BM25-only；没有已验证的 Dense/Hybrid 正式能力。

历史受控语料为 `geoexplore-v1`：6 份文档、1006 个 chunks，fingerprint `07931977ad3ff8a5ae743b5ed96ea92d0c87f0b4a8fb6a1aaa1be7e72ef2575f`。基线使用 `pypdf` 6.20.0、500 字符分块、60 字符重叠；BM25 top-5 seeds、同文档前序扩展，最终最多 4 chunks、每块最多 900 字符。PDF 不随本仓库分发，本次未重新核验完整语料。

`answered` 只是返回状态，不等于事实正确。引用文档和页码匹配不等于事实受到充分支持。人工核对、自动检查和执行完成需要分别报告；缺失 usage 应记为 unknown。

## Acceptance：原门槛未通过

保留[首次运行](../evals/results/2026-10-22-generation-acceptance-first-run.json)与[出站网络修复后运行](../evals/results/2026-10-22-generation-acceptance-after-egress-fix.json)。两者是独立运行；首次运行保留网络失败背景，不与后一次拼接。后一次结果如下：

| 指标 | 结果 | 证据边界 |
| --- | ---: | --- |
| 执行完成 | 10/10 | 产生最终响应，不判断事实质量 |
| 预期状态匹配 | 8/10 | 可由原 JSON 的题目与响应状态复核 |
| 可回答题正确且完整 | 6/8 | 历史人工汇总口径，见下述待复核限制 |
| 正确拒答 | 2/2 | 仅指冻结题集的两个应拒答范围 |
| 自动引用文档/页码正确率 | 1.0 | 机械校验，不能替代人工事实支持判断 |
| 过滤违规率 / 执行失败率 | 0 / 0 | 仅限该次记录 |

**人工复核限制：** 原结果 JSON 的 `manual_response_review` 仍为 `pending PDF-based human review`。6/8 正确且完整来自历史人工汇总，不能说成该字段已完成或自动 JSON 已证明事实正确。本次没有 PDF 复核，也没有修改原字段。模型记录为 `deepseek-flash`、`llm_max_retries=1`；Acceptance runtime 未记录 temperature，不能补写为已确认的 0.0。

`accept-007`、`accept-008` 是已知的证据召回或最终上下文覆盖缺口：本应可回答却返回证据不足。执行完成和引用机械检查通过都不能消除这些失败。该题集已多次用于诊断，后续宜作为回归材料，不再视为新的盲测。

修复后文件 SHA-256 为 `31a0b791bea3e34aff38747b6fe092f23b733b4c0cc7550c44d1dcbf5da989c0`；首次运行 SHA-256 为 `b2ff15f990203b48deb71c02a91fda4b9fca8c44c7a2ed26d252683ec1a30200`。

## Day 3：同语料新题检查

[完整五文件证据包](../evals/results/2026-10-26-day3-new-question-check-154705/report.md)保留冻结题集、manifest、retrieval、generation 和人工报告。题目来自人工看过的同一组 PDF / parsed chunks；先冻结再运行不等于盲测或新文档泛化。

| 指标 | 结果 | 分母与含义 |
| --- | ---: | --- |
| 执行完成 / 状态匹配 | 8/8 / 8/8 | 八道冻结题 |
| 可回答题正确且完整 | 6/6 | 历史报告的人工核对结论 |
| 正确拒答 | 2/2 | 限定语料或过滤范围内的两个案例 |
| Gold evidence raw top-5 覆盖 | 6/7 | 七个预标注证据块，不是七道题 |
| 扩展候选 / 最终上下文覆盖 | 7/7 / 7/7 | 说明预标注证据进入模型可见范围 |
| 所需事实在最终上下文中 | 6/6 | 六道可回答题 |
| 引用支持与物理页核对 | 6/6 | 已回答题的历史人工检查 |
| 过滤 / 上下文预算违规 | 0/8 / 0/8 | 最多四块，每块最多 900 字符 |

`geo-day3-006` 的证据块实际 ID 是 `geo-of12-1191_61`：raw BM25 排第六，经前序扩展进入上下文。原历史 report 中出现 `geo-day3-006_61` 的写法；本页说明正确 ID，同时保留原报告字节。

| Provider 遥测 | 历史记录 |
| --- | ---: |
| 模型 / temperature / max attempts | `deepseek-flash` / 0.0 / 1 |
| primary / repair / observed retry | 8 / 0 / 0 |
| usage 已知 | 8/8 |
| prompt / completion / total tokens | 6635 / 961 / 7596 |
| Provider 调用耗时合计 | 10280.173 ms |

耗时是调用之和，不是用户可见端到端延迟。题集 canonical SHA-256 为 `ef8c2c26bd0526abfe6500731584dbbac3b31589e98e8831e1f3517b6dfeb032`，原始题集文件 SHA-256 为 `64edcb85b9711137dc92f41b2bedf12ff62a3249bcf8511b39f8e6b9deec9686`，两种哈希口径不可混用。

## 评分器、其他记录与限制

`40-Hz`、`40 Hz` 与 `40-Hertz` 的有边界等价匹配用于修复评分假阴性；`140-Hz` 和 `40-kHz` 不应匹配。这个评分器修复不代表检索或模型提升，也不反向改写历史 JSON。

中间检索实验、Day 1 本机 API readiness、两次未完成提交的 Day 2 浏览器尝试及旧交付哈希已移入本地忽略归档。公开摘要不再引用缺失的浏览器截图或手工记录，也不据此声称浏览器 E2E 通过。原始 Day 3 manifest 的工作区/提交信息是历史快照，不是当前文件存在或可逐字重现模型输出的承诺。

新运行应遵守[评测协议](evaluation-protocol.md)，使用单独输出并记录语料与题集身份。完整题集与代码见[评测索引](../evals/README.md)，七份历史文件的作用与哈希见[证据索引](../evals/results/README.md)。
