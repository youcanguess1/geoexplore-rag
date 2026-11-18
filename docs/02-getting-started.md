# GeoExplore Local Setup

## Prerequisites

- Python 3.11 or later
- Node.js 20.19 or later, or Node.js 22.12 or later
- The six permitted geological PDFs, only when their source and redistribution terms allow local use

Create a target-local environment. Do not point commands at another checkout's virtual environment, database, cache, or absolute paths.

```powershell
python -m pip install uv==0.13.1
uv sync --locked --extra dev
Copy-Item .env.example .env
```

The command creates `.venv` from the existing lock without upgrading it. For optional drivers, alternative installation, and container settings, see [dependencies and configuration](dependencies-and-configuration.md).

Set `DEEPSEEK_API_KEY` in the local `.env` only when a generation run is explicitly authorized. Static checks and unit tests do not need it.

## Corpus Preparation

The manifest at `data/manifests/geological_documents.json` identifies six expected PDFs and their SHA-256 hashes. Store permitted source PDFs under the local directory selected by `GEOLOGICAL_KNOWLEDGE_DIR` (default: `data/local/geological_knowledge`). The corpus identity for the evaluated baseline is:

```text
6 documents
1006 chunks
07931977ad3ff8a5ae743b5ed96ea92d0c87f0b4a8fb6a1aaa1be7e72ef2575f
```

The release excludes PDF binaries pending separate verification of redistribution terms. A missing corpus prevents corpus-dependent retrieval or generation validation; it does not justify substituting different source files.

## Run Locally

Start the API:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.asgi:app --host 127.0.0.1 --port 9101 --log-level info
```

Start the frontend in another terminal:

```powershell
Set-Location frontend
npm ci
npm run dev
```

Open `http://127.0.0.1:5180`. The client proxies `/api` to the local API at port 9101. This prototype has no end-user authentication layer.

## Verify Without A Provider

```powershell
.\.venv\Scripts\python.exe -m compileall -q app eval scripts
.\.venv\Scripts\python.exe -m pytest tests/unit/test_geological_chain.py tests/unit/test_geological_manifest.py tests/unit/test_metadata_filters.py tests/unit/test_production_bm25.py tests/unit/test_geological_generation_eval.py
Set-Location frontend
npm run build
```

These checks do not prove that a configured provider, a local corpus, or browser interaction is working. Do not treat an HTTP health check as a generation or citation validation.

## Validation Boundary And Evaluation

The full test command is `uv run --no-sync python -m pytest -q`. Unit tests and HTTP API integration tests use synthetic data without PDFs or real providers. The API fixture replaces ingestion and uses an in-memory database while retaining the application lifecycle and request path. See [CONTRIBUTING.md](../CONTRIBUTING.md) for coverage and optional SDK checks; hosted CI status is shown in Actions.

The evaluation helper tests can be run without PDFs or provider calls:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_geological_eval.py tests/unit/test_geological_eval_v2.py tests/unit/test_geological_generation_eval.py -q
```

Synthetic runtime tests check local behavior with substituted data and responses; they do not validate startup with the six original PDFs. Historical results are described in the [evaluation summary](evaluation-summary.md). Before any corpus-dependent retrieval or generation run, follow the [evaluation protocol](evaluation-protocol.md), use a fresh output path, and keep the preserved evidence unchanged. The protocol commands are instructions for a separately authorized run; publishing this copy does not require making provider calls.
