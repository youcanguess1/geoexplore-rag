from __future__ import annotations

import pytest

from app.experiments.qdrant_filters import qdrant_filter
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.vector import InMemoryVectorStore, VectorRecord
from app.schemas.retrieval import RetrievalFilters, RetrievedChunk


def _chunk(
    chunk_id: str,
    *,
    document_id: str = "doc-1",
    data_type: str = "02_Academic",
    document_type: str = "paper",
    language: str = "en",
    content: str = "BLIMP workflow evidence",
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=document_id,
        title=chunk_id,
        content=content,
        score=0.0,
        metadata={
            "data_type": data_type,
            "document_type": document_type,
            "language": language,
        },
    )


def test_in_memory_vector_filters_before_similarity_top_k() -> None:
    store = InMemoryVectorStore()
    store.upsert(
        [
            VectorRecord(_chunk("paper"), [1.0, 0.0]),
            VectorRecord(_chunk("report", document_type="report"), [0.8, 0.0]),
        ]
    )

    hits = store.search(
        [1.0, 0.0],
        top_k=1,
        filters=RetrievalFilters(document_types=["report"]),
    )

    assert [hit.chunk_id for hit in hits] == ["report"]


def test_qdrant_filter_maps_fields_to_native_payload_conditions() -> None:
    pytest.importorskip("qdrant_client", reason="requires the vector extra")
    payload = qdrant_filter(
        RetrievalFilters(
            document_ids=["doc-1", "doc-2"],
            data_types=["02_Academic"],
            document_types=["paper", "review"],
            languages=["en"],
        )
    ).model_dump(exclude_none=True)

    conditions = {condition["key"]: condition["match"]["any"] for condition in payload["must"]}
    assert conditions == {
        "document_id": ["doc-1", "doc-2"],
        "data_type": ["02_Academic"],
        "document_type": ["paper", "review"],
        "language": ["en"],
    }


@pytest.mark.asyncio
async def test_hybrid_passes_identical_filters_to_both_retrievers() -> None:
    filters = RetrievalFilters(document_types=["report"])
    calls: list[RetrievalFilters | None] = []

    class _BM25:
        def search(self, query: str, *, top_k: int, filters: RetrievalFilters | None = None):
            calls.append(filters)
            return [_chunk("report", document_type="report")]

    class _Vector:
        embedder = type("Embedder", (), {"backend": "test"})()

        async def search(self, query: str, *, top_k: int, filters: RetrievalFilters | None = None):
            calls.append(filters)
            return [_chunk("report", document_type="report")]

    hits = await HybridRetriever(_BM25(), _Vector(), rrf_k=60).retrieve(
        "BLIMP",
        top_k=1,
        filters=filters,  # type: ignore[arg-type]
    )

    assert [hit.chunk_id for hit in hits] == ["report"]
    assert calls == [filters, filters]


@pytest.mark.asyncio
async def test_non_empty_filters_bypass_cache() -> None:
    class _Cache:
        def __init__(self) -> None:
            self.get_calls = 0
            self.set_calls = 0

        async def get(self, query: str, top_k: int):
            self.get_calls += 1
            return [_chunk("paper")]

        async def set(self, query: str, top_k: int, chunks: list[RetrievedChunk]) -> None:
            self.set_calls += 1

    class _BM25:
        def search(self, query: str, *, top_k: int, filters: RetrievalFilters | None = None):
            return [_chunk("report", document_type="report")]

    class _Vector:
        embedder = type("Embedder", (), {"backend": "test"})()

        async def search(self, query: str, *, top_k: int, filters: RetrievalFilters | None = None):
            return []

    cache = _Cache()
    retriever = HybridRetriever(_BM25(), _Vector(), rrf_k=60, cache=cache)  # type: ignore[arg-type]
    hits = await retriever.retrieve(
        "BLIMP", top_k=1, filters=RetrievalFilters(document_types=["report"])
    )

    assert [hit.chunk_id for hit in hits] == ["report"]
    assert cache.get_calls == 0
    assert cache.set_calls == 0
