"""Synthetic ingestion for HTTP API tests; no corpus files or providers are used."""

import hashlib
from unittest.mock import AsyncMock

import httpx
import pytest

from app.retrieval.bm25 import BM25Retriever
from app.retrieval.corpus_identity import attach_corpus_identity
from app.schemas.geological import CorpusIdentity
from app.schemas.retrieval import RetrievedChunk
from app.services import container as container_module


@pytest.fixture(autouse=True)
def synthetic_api_corpus(monkeypatch):
    chunks = []
    for document_type in ("paper", "report"):
        content = f"Synthetic {document_type}: seismic survey workflow steps are planning and acquisition."
        chunks.append(
            RetrievedChunk(
                chunk_id=f"synthetic-{document_type}-0",
                document_id=f"synthetic-{document_type}",
                title=f"Synthetic {document_type}",
                content=content,
                score=0.0,
                metadata={
                    "source_file": f"synthetic-{document_type}.md",
                    "page_number": "1",
                    "document_type": document_type,
                    "language": "en",
                    "sha256": hashlib.sha256(content.encode()).hexdigest(),
                },
            )
        )
    identity = CorpusIdentity(
        corpus_id="geoexplore-api-test",
        corpus_fingerprint=hashlib.sha256(
            "".join(chunk.content for chunk in chunks).encode()
        ).hexdigest(),
        parser_backend="synthetic",
        parser_version="test",
        chunking_version="synthetic-test-v1",
        document_count=2,
        chunk_count=2,
    )
    attach_corpus_identity(chunks, identity)

    async def synthetic_ingest(*args, **kwargs):
        return BM25Retriever(chunks, corpus_identity=identity), chunks

    outbound = AsyncMock(side_effect=AssertionError("API tests must not make outbound HTTP calls"))
    monkeypatch.setattr(container_module, "ingest_bm25", synthetic_ingest)
    monkeypatch.setattr(httpx.AsyncClient, "send", outbound)
    yield
    outbound.assert_not_called()
