from __future__ import annotations

from app.retrieval.bm25 import BM25Retriever
from app.retrieval.filters import matches_retrieval_filters
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


def test_filters_are_or_within_field_and_and_across_fields() -> None:
    filters = RetrievalFilters(document_types=["paper", "review"], languages=["EN"])

    assert filters.document_types == ["paper", "review"]
    assert filters.languages == ["en"]
    assert matches_retrieval_filters(_chunk("paper"), filters)
    assert matches_retrieval_filters(_chunk("review", document_type="review"), filters)
    assert not matches_retrieval_filters(_chunk("zh", language="zh"), filters)
    assert not matches_retrieval_filters(_chunk("report", document_type="report"), filters)


def test_duplicate_filter_values_are_normalised() -> None:
    filters = RetrievalFilters(
        document_ids=[" doc-1", "doc-1"],
        document_types=["paper", "paper"],
        languages=["EN", "en"],
    )

    assert filters.document_ids == ["doc-1"]
    assert filters.document_types == ["paper"]
    assert filters.languages == ["en"]


def test_technical_report_is_a_supported_manifest_filter() -> None:
    filters = RetrievalFilters(document_types=["technical_report"])

    assert filters.document_types == ["technical_report"]


def test_bm25_filters_before_top_k() -> None:
    paper = _chunk("paper", document_type="paper")
    report = _chunk("report", document_type="report")
    retriever = BM25Retriever([paper, report])

    class _Scores:
        @staticmethod
        def get_scores(tokens: list[str]) -> list[float]:
            return [100.0, 1.0]

    retriever._bm25 = _Scores()  # type: ignore[assignment]
    hits = retriever.search(
        "BLIMP",
        top_k=1,
        filters=RetrievalFilters(document_types=["report"]),
    )

    assert [hit.chunk_id for hit in hits] == ["report"]
