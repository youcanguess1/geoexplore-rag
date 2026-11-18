# GeoExplore Release Scope

## Origin And Public Contents

GeoExplore is a focused geological PDF RAG prototype adapted from an existing open-source application foundation. The retained [MIT license](../LICENSE) preserves the upstream terms; the repository does not assert sole authorship of every retained component.

The public copy contains the FastAPI application, React frontend, BM25 runtime, tests and synthetic fixtures, source manifest, frozen evaluation question sets, evaluation helpers, rerun scripts, and a small historical evidence set. Retained research implementations are identified in the [architecture](ARCHITECTURE.md) and [experimental boundary](../app/experiments/README.md).

Personal-machine handoff records, intermediate evaluation results, old dense/hybrid configurations, and obsolete delivery hash lists have been moved out of public navigation into an ignored local audit archive. Public instructions do not depend on that archive. Source PDFs, local credentials, databases, generated indexes, and model caches are not required public assets.

## Formal Retrieval Path

The evaluated path is metadata-filtered BM25 over fixed `pypdf` chunks: top-5 seeds, same-document predecessor overlap extension, and at most four context chunks with at most 900 characters per chunk. Citation metadata identifies a source document and physical PDF page. Dense, hybrid, vector, and reranking implementations are not enabled features of this path.

## Data Distribution

PDF binaries are omitted pending independent verification of source terms and redistribution permission. The [manifest](../data/manifests/geological_documents.json) supplies expected filenames, hashes, and source descriptions. Obtain permitted sources independently and check their hashes before corpus construction. The historical six-document / 1006-chunk identity has not been rebuilt from PDFs during release preparation.

## Evaluation Record

The preserved 10-question Acceptance suite did not pass: status matched on 8/10 questions; historical manual summaries report 6/8 correct and complete answerable responses and 2/2 correct refusals. The raw JSON still marks PDF-based human review as pending. The 6/8 manual claim was not independently rechecked during release preparation. `accept-007` and `accept-008` retain evidence-recall or final-context gaps.

Day 3 is a separate eight-question same-corpus check: 8/8 status outcomes, with 6/6 answerable responses judged complete in its report and 2/2 correct refusals. Its source corpus had been inspected when labeling the questions. It is not blind testing, new-document generalization, or a replacement for Acceptance. These scores must not be aggregated.

The [summary](evaluation-summary.md), [protocol](evaluation-protocol.md), and [evidence index](../evals/results/README.md) define the denominators, review limits, and file roles. The [SHA256SUMS](../evals/results/SHA256SUMS) file verifies only the seven retained historical evidence files, not the whole release.

## Validation And Release Limits

Unit tests and synthetic HTTP API integration checks run without source PDFs or a real provider. Stale assertions against the absent general-purpose boundary and old evaluation runner have been removed while retaining injection and metric tests. Incomplete unused prompt-dependent research modules have also been removed. The API integration fixture substitutes ingestion and uses an in-memory database; it does not replace real-provider evaluation or browser E2E. See [CONTRIBUTING.md](../CONTRIBUTING.md) for commands and scope. Hosted CI results are recorded by Actions; this release does not provide a browser screenshot evidence bundle.

This is a local demonstration and controlled-validation baseline. It does not establish production readiness, a public authentication boundary, a passing Acceptance suite, or performance beyond the recorded corpus. New retrieval or context-planning experiments require independent outputs and fresh evidence.
