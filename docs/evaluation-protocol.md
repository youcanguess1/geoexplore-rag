# GeoExplore 评测协议

## 输入身份与执行边界

本协议区分静态/单元检查、retrieval-only 与真实生成。发布整理只整理已有证据，没有发起真实 Provider 请求、模型下载或六 PDF 语料重建。

语料准备见[本地启动](02-getting-started.md)与[数据说明](../data/README.md)。按 manifest 检查允许使用的 PDF，再确认基线身份：6 文档、1006 chunks，fingerprint `07931977ad3ff8a5ae743b5ed96ea92d0c87f0b4a8fb6a1aaa1be7e72ef2575f`。缺少 PDF 时停止语料相关验证，不能替换其他 PDF 后继续沿用历史结论。

记录解析器版本、500/60 分块与重叠、BM25 top-5、同文档前序扩展、4 chunks / 900 chars 上下文预算、过滤条件、模型、temperature、重试语义、运行环境、题集哈希与代码状态。新运行不应把历史缺失字段补成已知值。

## 题集、分母与人工核对

[评测索引](../evals/README.md)列出不同 schema。Generation dev 六题用于开发；generation Acceptance 十题使用显式 gate。旧 retrieval Acceptance 十六题不是同一个集合。Day 3 八题在 generation schema 中仍标记 `split=dev`，不能据此称为新的独立 Acceptance。

Generation loader 校验 schema、split、题目与语料标识；`validate_split_independence` 检查 dev/Acceptance 的分离。这个程序检查不等同于无题目泄漏的统计证明。Day 3 来源已被人工阅读，不是盲测，不与旧 Acceptance 计算合并分数。

分别记录：执行完成、状态匹配、可回答题事实正确且完整、应拒答题的正确拒答、gold chunks 在 raw/expanded/final context 的覆盖、引用对事实的支持和物理页、过滤及上下文预算违规。回答状态或文档/页码机械匹配不能替代 PDF 人工核对。保存人工结论及其完成状态，不能把 pending 宣称为已完成。

usage 缺失记 unknown；tokens 与 Provider 调用耗时按记录汇总，调用时间之和不等于端到端延迟。评分器 `40-Hz` / `40-Hertz` 等价规则修复不代表模型能力提升；历史结果不回写。

## 文件哈希与证据保全

原文件 SHA-256 针对完整字节；canonical SHA-256 针对 `json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))` 的 UTF-8 编码。两者不同。每次记录具体口径，不能只写一个无定义的题集哈希。

七份历史证据的清单为 [SHA256SUMS](../evals/results/SHA256SUMS)，路径相对 `evals/results`，可从仓库根目录检查：

```powershell
Get-Content -LiteralPath 'evals/results/SHA256SUMS' | ForEach-Object {
    $artifactParts = $_ -split '  ', 2
    $artifactPath = Join-Path 'evals/results' $artifactParts[1]
    $actualHash = (Get-FileHash -LiteralPath $artifactPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $artifactParts[0]) { throw "Hash mismatch: $artifactPath" }
}
```

该清单不覆盖整个发布副本。两份 Acceptance 均保留，因为 Day 3 runner 的 manifest 会记录它们的哈希；运行背景失败与修复后结果不得拼接。

## 新 Generation 运行

以下命令只是供另行开展真实评测时使用；它们会读取本机 PDF 并调用已配置 Provider。先取得所需授权和配置，在仓库根目录使用模块入口。runner 的默认路径仍是历史日期文件，且没有拒绝覆盖保护，因此必须显式指定全新输出并先检查：

```powershell
$evalOutput = 'output/generation-dev-run.json'
if (Test-Path -LiteralPath $evalOutput) { throw 'Choose a new output file.' }
.\.venv\Scripts\python.exe -m scripts.run_generation_eval --split dev --output $evalOutput
```

正式 Acceptance 使用另一个新路径，并显式打开 gate：

```powershell
$acceptanceOutput = 'output/generation-acceptance-run.json'
if (Test-Path -LiteralPath $acceptanceOutput) { throw 'Choose a new output file.' }
.\.venv\Scripts\python.exe -m scripts.run_generation_eval --split acceptance --allow-acceptance --output $acceptanceOutput
```

runner 校验题集与语料身份，使用内存 SQLite、关闭 Redis 并固定一次 Provider attempt。环境、模型输出和人工复核仍须单独记录，不能承诺逐字复现历史模型回答。

## Day 3 的两阶段运行

使用原冻结题集的新副本，不改旧 bundle。retrieval 阶段需要 PDF、构建 BM25，但不调用模型；generation 阶段需要真实 Provider 且要求对应的 retrieval 题集哈希匹配。两阶段各自保留结果：

```powershell
$day3Output = 'output/day3-rerun'
if (Test-Path -LiteralPath $day3Output) { throw 'Choose a new output directory.' }
New-Item -ItemType Directory -Path $day3Output -Force | Out-Null
Copy-Item -LiteralPath 'evals/results/2026-10-26-day3-new-question-check-154705/questions.json' -Destination "$day3Output/questions.json"
.\.venv\Scripts\python.exe -m scripts.run_day3_new_question_eval --phase retrieval --output-dir $day3Output
.\.venv\Scripts\python.exe -m scripts.run_day3_new_question_eval --phase generation --output-dir $day3Output
```

runner 拒绝覆盖已有对应结果；manifest 记录运行环境、语料与题集身份、历史 Acceptance 哈希及可获得的 Git 状态。没有 Git 仓库时部分字段可为空，不能据此编造提交。新输出位于忽略的 `output/`；审核后再决定发布哪些新证据。

## 当前可验证范围

无需 PDF 或 Provider 的评分器检查见 [CONTRIBUTING](../CONTRIBUTING.md)。这些检查不等于全套 pytest、真实语料重跑或浏览器成功。旧中间结果与本机交付流水只在忽略的本地归档保留，公开说明和上述命令不依赖该归档。保留结果的结论与限制见[摘要](evaluation-summary.md)。
