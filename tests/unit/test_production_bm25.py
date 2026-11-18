from __future__ import annotations

import pytest

from app.config.settings import Settings
from app.retrieval.bm25 import (
    AsyncBM25Retriever,
    BM25Retriever,
    _embedded_query_term_count,
)
from app.retrieval.ingest import KnowledgeIngestor, ingest_bm25
from app.schemas.retrieval import RetrievalFilters, RetrievedChunk
from app.services import container as container_module


def _chunk(
    chunk_id: str,
    *,
    document_id: str | None = None,
    chunk_index: int = 0,
    page_number: str = "3",
    content: str = "BLIMP seismic evidence",
    document_type: str = "paper",
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=document_id or f"doc-{chunk_id}",
        title=chunk_id,
        content=content,
        score=0.0,
        chunk_index=chunk_index,
        metadata={
            "data_type": "02_Academic",
            "document_type": document_type,
            "language": "en",
            "page_number": page_number,
        },
    )


@pytest.mark.asyncio
async def test_production_retrieval_builds_bm25_without_embedding_provider(monkeypatch) -> None:
    async def fake_ingest(*args, **kwargs):
        chunks = [_chunk("paper")]
        return BM25Retriever(chunks), chunks

    def fail_if_called(*args, **kwargs):
        raise AssertionError("production BM25 startup must not construct an embedding provider")

    monkeypatch.setattr(container_module, "ingest_bm25", fake_ingest)
    monkeypatch.setattr(container_module, "build_embedding_provider", fail_if_called, raising=False)

    retriever = await container_module.build_retrieval(Settings(app_env="testing"), redis=None)

    assert isinstance(retriever, AsyncBM25Retriever)
    assert retriever.backend == "bm25"


@pytest.mark.asyncio
async def test_bm25_ingest_does_not_build_vector_records(monkeypatch) -> None:
    async def fake_load_chunks(self):
        return [_chunk("paper")]

    async def fail_if_vectorized(self, chunks):
        raise AssertionError("production BM25 ingest must not build vector records")

    monkeypatch.setattr(KnowledgeIngestor, "load_chunks", fake_load_chunks)
    monkeypatch.setattr(
        KnowledgeIngestor, "build_vector_records", fail_if_vectorized, raising=False
    )

    bm25, chunks = await ingest_bm25("unused", settings=Settings(app_env="testing"))

    assert [chunk.chunk_id for chunk in chunks] == ["paper"]
    assert [chunk.chunk_id for chunk in bm25.search("BLIMP", top_k=1)] == ["paper"]


@pytest.mark.asyncio
async def test_bm25_adapter_bypasses_cache_for_non_empty_filters() -> None:
    class Cache:
        def __init__(self) -> None:
            self.get_calls = 0
            self.set_calls = 0

        async def get(self, query: str, top_k: int):
            self.get_calls += 1
            return [_chunk("paper")]

        async def set(self, query: str, top_k: int, chunks: list[RetrievedChunk]) -> None:
            self.set_calls += 1

    cache = Cache()
    retriever = AsyncBM25Retriever(
        BM25Retriever([_chunk("paper"), _chunk("report", document_type="report")]),
        cache=cache,  # type: ignore[arg-type]
    )

    hits = await retriever.retrieve(
        "BLIMP",
        top_k=1,
        filters=RetrievalFilters(document_types=["report"]),
    )

    assert [hit.chunk_id for hit in hits] == ["report"]
    assert cache.get_calls == 0
    assert cache.set_calls == 0


def test_context_expansion_adds_overlapping_predecessor_within_limit() -> None:
    overlap = "overlapping procedure evidence that crosses the fixed window"
    predecessor = _chunk(
        "doc_10",
        document_id="doc",
        chunk_index=10,
        content=f"steps one through four {overlap}",
    )
    current = _chunk(
        "doc_11",
        document_id="doc",
        chunk_index=11,
        content=f"{overlap} steps five through nine",
    )
    other = _chunk("other_01", chunk_index=1)
    bm25 = BM25Retriever([predecessor, current, other])

    expanded = bm25.expand_overlapping_predecessors([current, other], limit=2)

    assert [chunk.chunk_id for chunk in expanded] == ["doc_11", "doc_10"]
    assert expanded[1].source == "bm25-adjacent"
    assert expanded[1].rank is None


def test_bm25_recovers_english_terms_embedded_by_pdf_whitespace_loss() -> None:
    fused = _chunk(
        "fused",
        content=("The seismicrefraction profile follows a dippingboundary for a singlearray."),
    )
    clean = _chunk(
        "clean",
        content="A seismic refraction survey describes a dipping boundary.",
    )
    retriever = BM25Retriever([fused, clean])

    hits = retriever.search("dipping seismic refraction boundary single array", top_k=2)

    assert [chunk.chunk_id for chunk in hits] == ["fused", "clean"]
    assert (
        _embedded_query_term_count(
            ["dipping", "seismic", "refraction", "boundary", "single", "array"],
            ["seismicrefraction", "dippingboundary", "singlearray"],
        )
        == 6
    )


def test_bm25_embedded_term_bonus_ignores_short_and_exact_tokens() -> None:
    assert _embedded_query_term_count(["for", "seismic", "array"], ["for", "seismic", "array"]) == 0


def test_context_expansion_never_crosses_page_or_filter_boundary() -> None:
    overlap = "overlapping procedure evidence that crosses the fixed window"
    predecessor = _chunk(
        "doc_10",
        document_id="doc",
        chunk_index=10,
        page_number="2",
        content=f"prefix {overlap}",
        document_type="report",
    )
    current = _chunk(
        "doc_11",
        document_id="doc",
        chunk_index=11,
        page_number="3",
        content=f"{overlap} suffix",
    )
    bm25 = BM25Retriever([predecessor, current])

    expanded = bm25.expand_overlapping_predecessors(
        [current],
        limit=2,
        filters=RetrievalFilters(document_types=["paper"]),
    )

    assert [chunk.chunk_id for chunk in expanded] == ["doc_11"]

    filtered_predecessor = predecessor.model_copy(
        update={"metadata": {**predecessor.metadata, "page_number": "3"}}
    )
    filtered_bm25 = BM25Retriever([filtered_predecessor, current])

    filtered = filtered_bm25.expand_overlapping_predecessors(
        [current],
        limit=2,
        filters=RetrievalFilters(document_types=["paper"]),
    )

    assert [chunk.chunk_id for chunk in filtered] == ["doc_11"]
