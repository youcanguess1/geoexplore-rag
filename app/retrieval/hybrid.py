"""Hybrid retriever fusing BM25 and dense vectors with RRF."""

from __future__ import annotations

import logging
import time

from app.core.exceptions import RetrievalError
from app.retrieval.bm25 import BM25Retriever
from app.retrieval.cache import RetrievalCache
from app.retrieval.filters import effective_filters
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.vector import VectorRetriever
from app.schemas.retrieval import RetrievalFilters, RetrievedChunk

logger = logging.getLogger(__name__)


class HybridRetriever:
    """BM25 + dense search, fused with RRF.

    Each retriever is allowed to fail independently. If both fail, raise.
    """

    def __init__(
        self,
        bm25: BM25Retriever,
        vector: VectorRetriever,
        *,
        rrf_k: int,
        cache: RetrievalCache | None = None,
    ) -> None:
        self._bm25 = bm25
        self._vector = vector
        self._rrf_k = rrf_k
        self._cache = cache

    @property
    def backend(self) -> str:
        embedding_backend = getattr(self._vector.embedder, "backend", "unknown")
        return f"hybrid-bm25+{embedding_backend}"

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int,
        filters: RetrievalFilters | None = None,
    ) -> list[RetrievedChunk]:
        filters = effective_filters(filters)
        cacheable = filters is None
        if self._cache is not None and cacheable:
            cached = await self._cache.get(query, top_k)
            if cached is not None:
                return cached
        started = time.perf_counter()
        lexical: list[RetrievedChunk] = []
        dense: list[RetrievedChunk] = []
        lexical_error: Exception | None = None
        dense_error: Exception | None = None
        try:
            if filters is None:
                lexical = self._bm25.search(query, top_k=top_k)
            else:
                lexical = self._bm25.search(query, top_k=top_k, filters=filters)
        except Exception as exc:  # BM25 is in-process; unexpected errors still isolated
            lexical_error = exc
            logger.exception("bm25_failed")
        try:
            if filters is None:
                dense = await self._vector.search(query, top_k=top_k)
            else:
                dense = await self._vector.search(query, top_k=top_k, filters=filters)
        except Exception as exc:
            dense_error = exc
            logger.exception("vector_search_failed")
        if not lexical and not dense and (lexical_error or dense_error):
            raise RetrievalError("both lexical and dense retrievers failed") from (
                dense_error or lexical_error
            )
        fused = reciprocal_rank_fusion([lexical, dense], k=self._rrf_k)
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "hybrid_retrieval_completed",
            extra={
                "top_k": top_k,
                "lexical": len(lexical),
                "dense": len(dense),
                "fused": len(fused),
                "latency_ms": round(elapsed_ms, 2),
            },
        )
        trimmed = fused[:top_k]
        if self._cache is not None and cacheable:
            await self._cache.set(query, top_k, trimmed)
        return trimmed
