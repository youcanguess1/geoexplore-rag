"""Shared retrieval-filter semantics for lexical, dense, and citation boundaries."""

from __future__ import annotations

from app.schemas.retrieval import RetrievalFilters, RetrievedChunk


def effective_filters(filters: RetrievalFilters | None) -> RetrievalFilters | None:
    """Treat an omitted or empty filter object as an unrestricted query."""
    if filters is None or filters.is_empty():
        return None
    return filters


def _metadata_value(chunk: RetrievedChunk, field: str) -> str:
    return str(chunk.metadata.get(field, "")).strip()


def matches_retrieval_filters(
    chunk: RetrievedChunk,
    filters: RetrievalFilters | None,
) -> bool:
    """Return whether one chunk satisfies OR-within-fields and AND-across-fields."""
    filters = effective_filters(filters)
    if filters is None:
        return True
    return all(
        (
            not allowed
            or actual in allowed
        )
        for allowed, actual in (
            (filters.document_ids, chunk.document_id),
            (filters.data_types, _metadata_value(chunk, "data_type")),
            (filters.document_types, _metadata_value(chunk, "document_type")),
            (filters.languages, _metadata_value(chunk, "language").lower()),
        )
    )
