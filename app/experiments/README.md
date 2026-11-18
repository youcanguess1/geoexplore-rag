# Experimental code boundary

The supported GeoExplore runtime is `app.asgi:app`. Its container builds a BM25 retriever and passes it directly to the geological graph. It does not construct a reranker or import dense, vector, hybrid, rewrite, self-RAG, or experimental memory implementations.

## Explicit entry points

| Previous API | Explicit experimental API |
| --- | --- |
| `app.retrieval.ingest.KnowledgeIngestor(..., embedder).load()` | `app.experiments.ingest.VectorKnowledgeIngestor(..., embedder).load()` |
| `app.retrieval.ingest.ingest_to_memory` | `app.experiments.ingest.ingest_to_memory` |
| `app.retrieval.ingest.ingest_knowledge` | `app.experiments.ingest.ingest_knowledge` |
| `app.retrieval.filters.qdrant_filter` | `app.experiments.qdrant_filters.qdrant_filter` |
| `app.providers.fake.FakeEmbeddingProvider` | `app.experiments.providers.FakeEmbeddingProvider` |

Production `KnowledgeIngestor.load_chunks()` remains the shared parser, manifest validator, metadata assembler, deduplicator, and corpus identity builder. Experimental vector ingestion subclasses it and embeds the resulting chunks. `build_retrieval()` now returns a single `AsyncBM25Retriever`; `ChatService` no longer accepts a reranker.

The `app.providers` package exports LLM providers and shared protocols. Import experimental implementations from their defining modules explicitly; the package no longer re-exports embedding or reranking implementations.

## Retained research modules

These implementations remain at their existing paths for research callers. Retention does not make them supported production features:

- `app/providers/embeddings.py`, `device.py`, `reranker.py`: dense embedding and reranking implementations.
- `app/retrieval/vector.py`, `hybrid.py`, `fusion.py`, `reranker.py`: vector stores, hybrid retrieval, RRF, and reranking.
- `app/retrieval/query_rewrite.py`, `self_rag.py`, `app/memory/`, and `app/guardrails/hallucination.py`: experimental rewrite, retrieval grading, summary memory, and faithfulness logic.

The last group references missing `app.prompts` modules (`query_rewrite`, `self_rag`, `summary`, and `faithfulness`). These experimental paths are incomplete and are not enabled or repaired by this separation. Database conversation persistence in the production service is separate from experimental summary memory.

The base install excludes the Qdrant SDK and PostgreSQL driver. Install the `vector` extra for Qdrant experiments, `postgres` for the optional async database driver, `rerank` for local sentence-transformers, and `docs` for generic Unstructured parsing. The unused ModelScope declaration has been removed. See [dependencies and configuration](../../docs/dependencies-and-configuration.md). Experimental Qdrant ingestion can contact a configured server; dense providers can load models or call APIs when explicitly used. Production currently does none of those through these modules.

## Regression checks

`tests/unit/test_runtime_isolation.py` starts a fresh Python process for offline and canned-generation modes, rejects experimental module and SDK imports, enters the real FastAPI lifespan with synthetic BM25 ingestion and an in-memory database, then checks JSON, filters, persistence across turns, and SSE output. Outbound async HTTP is blocked. This is a synthetic runtime regression, not a six-PDF corpus startup or a real provider evaluation.

`test_experimental_ingest.py` checks the relocated in-memory vector entry points with deterministic embeddings and temporary Markdown. `test_experimental_filters.py` retains vector, Qdrant filter translation, hybrid filter propagation, and hybrid cache tests. The Qdrant translation test uses only local SDK models.
