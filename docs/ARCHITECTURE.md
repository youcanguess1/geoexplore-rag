# GeoExplore Architecture

## Active Request Path

```text
React / Vite client (127.0.0.1:5180)
  -> /api proxy -> FastAPI app.asgi:app (127.0.0.1:9101)
  -> service container -> ChatService -> geological graph
  -> metadata-filtered BM25 top-5 seeds
  -> same-document predecessor overlap extension
  -> bounded context: at most 4 chunks, 900 characters per chunk
  -> structured generation -> citation metadata
  -> JSON or SSE response, with conversation persistence
```

The implementation entry points are [container.py](../app/services/container.py), [chat_service.py](../app/services/chat_service.py), [the geological graph](../app/agents/geological.py), and [chat routes](../app/api/routes/chat.py). The frontend client ID identifies a local conversation owner; it is not authentication.

## Corpus And Retrieval

The [document manifest](../data/manifests/geological_documents.json) records six source documents and expected hashes. The evaluated baseline used `pypdf` 6.20.0, 500-character chunks, and 60-character overlap. Its recorded identity is six documents, 1006 chunks, and fingerprint `07931977ad3ff8a5ae743b5ed96ea92d0c87f0b4a8fb6a1aaa1be7e72ef2575f`.

Document, type, and language filters constrain retrieval. BM25 seeds may bring in a predecessor from the same document before final context selection; source document, chunk ID, and physical PDF page travel with the evidence. A matching citation ID and page are mechanical checks, not proof that every factual claim is supported.

PDF binaries are excluded from this release. The manifest and historical identity do not establish that a new local corpus has been rebuilt or verified. Obtain permitted sources and check identity before corpus-dependent validation.

## Generation, Persistence, And Offline Checks

The container selects DeepSeek when configured and otherwise selects `OfflineLLMProvider`. Missing provider configuration does not bypass corpus ingestion or provide a real geological answer. The geological graph structures answers and evidence-insufficient responses; `ChatService` orchestrates execution, streaming, and database persistence. Redis is optional; local rate limiting and retrieval caching have memory implementations.

[Runtime isolation tests](../tests/unit/test_runtime_isolation.py) use synthetic ingestion, canned responses, and an in-memory database while blocking outbound async HTTP. They check composition, filters, conversation persistence, and JSON/SSE behavior. They do not establish six-PDF startup, real-provider answer quality, or browser E2E success.

## Experimental Boundary

The formal runtime builds a BM25 retriever. Dense, hybrid, vector, reranking, query rewriting, self-RAG, and experimental summary-memory implementations are outside this path. Some retained research modules reference missing prompt modules; retaining them does not make them supported features. See [the experimental code boundary](../app/experiments/README.md).

[Release scope](release-scope.md) defines the public boundary; [evaluation protocol](evaluation-protocol.md) and [evaluation summary](evaluation-summary.md) separate historical evidence from current validation.
