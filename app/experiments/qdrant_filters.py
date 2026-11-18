"""Native Qdrant filter translation for experimental vector retrieval."""

from __future__ import annotations

from typing import Any

from app.retrieval.filters import effective_filters
from app.schemas.retrieval import RetrievalFilters


def qdrant_filter(filters: RetrievalFilters | None) -> Any:
    """Build a native Qdrant payload filter without client-side post-filtering."""
    filters = effective_filters(filters)
    if filters is None:
        return None
    from qdrant_client.models import FieldCondition, Filter, MatchAny

    fields = (
        ("document_id", filters.document_ids),
        ("data_type", filters.data_types),
        ("document_type", filters.document_types),
        ("language", filters.languages),
    )
    return Filter(
        must=[
            FieldCondition(key=key, match=MatchAny(any=list(values)))
            for key, values in fields
            if values
        ]
    )
