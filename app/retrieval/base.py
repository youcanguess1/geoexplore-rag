"""Minimal retrieval contract shared by production and evaluation backends."""

from __future__ import annotations

from typing import Protocol

from app.schemas.retrieval import RetrievalFilters, RetrievedChunk


class Retriever(Protocol):
    """Retrieve metadata-constrained chunks for one query."""

    @property
    def backend(self) -> str: ...

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int,
        filters: RetrievalFilters | None = None,
    ) -> list[RetrievedChunk]: ...
