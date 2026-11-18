# GeoExplore

GeoExplore is a geological PDF question-answering prototype adapted from an existing open-source application foundation. It is a scoped demonstration project, not a claim that the entire underlying application was written from scratch.

## Current Release Scope

The formal query path in this release is **BM25-only**:

1. PDFs are parsed with `pypdf` and split into fixed 500-character chunks with 60-character overlap.
2. Document metadata filters are applied before lexical retrieval.
3. BM25 returns the top 5 seed chunks.
4. The current production assembler extends retrieval with predecessor overlap, then limits model context to at most 4 chunks and at most 900 characters per chunk.
5. The generation response carries source metadata used to display a document ID and physical PDF page citation.

Dense retrieval, hybrid retrieval, vector storage, and reranking code may remain as inactive research or compatibility modules in this repository. They are **not integrated into the formal GeoExplore production query path**.

See [the experimental code boundary](app/experiments/README.md) for retained research modules, relocated APIs, and their limitations.

## Corpus Identity

This release expects the following frozen corpus identity:

- Documents: 6
- Chunks: 1006
- Corpus fingerprint: `07931977ad3ff8a5ae743b5ed96ea92d0c87f0b4a8fb6a1aaa1be7e72ef2575f`
- Parser: `pypdf`
- Chunk policy: 500 characters with 60-character overlap

The document manifest is [data/manifests/geological_documents.json](data/manifests/geological_documents.json). Original PDFs are intentionally not included in this release copy unless their redistribution permissions have been independently verified. Obtain them from the sources named in that manifest, verify the listed SHA-256 values, then place them in the configured geological knowledge directory before running corpus-dependent commands.

## Setup

Requirements: Python 3.11+, Node.js 20.19+ or 22.12+, and `npm`.

```powershell
python -m pip install uv==0.13.1
uv sync --locked --extra dev
Copy-Item .env.example .env
```

The locked development install includes the formal BM25 runtime and test tools. Qdrant and PostgreSQL drivers are separate extras; local dense/rerank and additional parsing dependencies remain optional. See [dependencies and configuration](docs/dependencies-and-configuration.md) for the supported choices.

Set `DEEPSEEK_API_KEY` only in your local `.env`. Never commit it. The service needs an available, verified geological corpus to answer questions; an API key is not required for static checks or offline unit tests.

Start the API on the documented local port:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.asgi:app --host 127.0.0.1 --port 9101 --log-level info
```

In a second terminal, start the web client:

```powershell
Set-Location frontend
npm ci
npm run dev
```

The Vite development server uses `http://127.0.0.1:5180` and proxies `/api` to `http://127.0.0.1:9101`. The frontend client ID is a local browser identifier, not authentication; do not expose the prototype to untrusted users without an authentication layer.

## Verification

The release copy is designed to support local static and unit validation without calling a model provider:

```powershell
.\.venv\Scripts\python.exe -m compileall -q app eval scripts
.\.venv\Scripts\python.exe -m pytest tests/unit/test_geological_chain.py tests/unit/test_geological_manifest.py tests/unit/test_metadata_filters.py tests/unit/test_production_bm25.py tests/unit/test_runtime_isolation.py tests/unit/test_geological_generation_eval.py
Set-Location frontend
npm run build
```

See [docs/02-getting-started.md](docs/02-getting-started.md) for local data preparation and [docs/release-scope.md](docs/release-scope.md) for provenance, evaluation evidence, and known limitations.

## Evaluation Evidence And Limits

The preserved 10-question Acceptance evaluation did **not** pass as a whole:

- Expected-status results: 8/10
- Answerable questions with correct, complete answers: 6/8
- Correct refusals: 2/2
- `accept-007` and `accept-008` retain evidence-recall or final-context coverage gaps.

These results must not be restated as a passing Acceptance result or production-readiness claim. The 6/8 correctness figure is a historical manual-summary claim; the preserved result JSON still marks PDF-based human review as pending. This release preparation did not repeat that review. See the [evaluation summary](docs/evaluation-summary.md) for the distinction between automatic status checks and manual judgments.

A separate Day 3 check used eight newly frozen questions against the same six-document corpus. It recorded 8/8 expected outcomes: 6/6 answerable questions were judged complete and 2/2 refusal cases were correct. This was a small same-corpus check, not blind testing, not evidence of new-document generalization, and not a score that may be combined with the historical Acceptance figures.

## Provenance And License

This repository retains the upstream [MIT License](LICENSE). GeoExplore adapts an existing open-source application foundation into a constrained geological PDF RAG prototype. This release does not assert sole authorship of the upstream foundation. The source URLs and copyright or redistribution status of every PDF must be checked independently before publishing any corpus files.

## Non-Goals

This release does not provide a production deployment, authentication boundary, hybrid retrieval, dense retrieval, reranking in the formal query path, or a claim that the historical Acceptance suite passed. It should be evaluated within the corpus and validation limits described above.

## Documentation

| Entry | Purpose |
| --- | --- |
| [Local setup](docs/02-getting-started.md) | Environment, corpus preparation, and available checks |
| [Dependencies and configuration](docs/dependencies-and-configuration.md) | Locked installs, extras, SQLite/Redis, and container settings |
| [Architecture](docs/ARCHITECTURE.md) | Active request path and experimental boundary |
| [Evaluation summary](docs/evaluation-summary.md) | Independent historical outcomes and known failures |
| [Evaluation assets](evals/README.md) | Frozen question sets, schemas, and scoring code |
| [Evaluation protocol](docs/evaluation-protocol.md) | Preconditions, scoring rules, and separate rerun outputs |
| [Evidence index](evals/results/README.md) | Preserved result files and integrity checks |
| [Local demonstration](docs/project-delivery.md) | Demonstration steps and interpretation limits |

The commands above cover a runnable subset, not a passing full test suite. Two existing legacy modules fail full unit-test collection because `app.guardrails.boundary` and `eval.runner` are missing. The checked-in CI workflow is configuration, not evidence of a successful hosted CI run. See [CONTRIBUTING.md](CONTRIBUTING.md) for the current validation boundary.
