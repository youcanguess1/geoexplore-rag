"""Explicit dense ingestion helpers, outside the production BM25 path."""

from __future__ import annotations

import asyncio
import logging

from app.config.settings import Settings, get_settings
from app.providers.base import EmbeddingProvider
from app.retrieval.bm25 import BM25Retriever
from app.retrieval.ingest import KnowledgeIngestor
from app.retrieval.vector import InMemoryVectorStore, QdrantVectorStore, VectorRecord, build_records
from app.schemas.retrieval import RetrievedChunk


class VectorKnowledgeIngestor(KnowledgeIngestor):
    def __init__(
        self,
        knowledge_dir: str,
        embedder: EmbeddingProvider | None = None,
        settings: Settings | None = None,
        manifest_path: str | None = None,
    ) -> None:
        super().__init__(knowledge_dir, settings=settings, manifest_path=manifest_path)
        self._embedder = embedder

    async def build_vector_records(self, chunks: list[RetrievedChunk]) -> list[VectorRecord]:
        """Embed already parsed chunks for evaluation or an explicit dense path."""
        if not chunks:
            return []
        if self._embedder is None:
            raise ValueError("an embedding provider is required to build vector records")
        embeddings = await self._embedder.embed([chunk.content for chunk in chunks])
        return build_records(chunks, embeddings)

    async def load(self) -> tuple[list[RetrievedChunk], list[VectorRecord]]:
        """Load shared chunks and build experimental vector records."""
        chunks = await self.load_chunks()
        return chunks, await self.build_vector_records(chunks)


async def ingest_to_memory(
    knowledge_dir: str,
    embedder: EmbeddingProvider,
    settings: Settings | None = None,
    manifest_path: str | None = None,
) -> tuple[BM25Retriever, InMemoryVectorStore, list[RetrievedChunk]]:
    ingestor = VectorKnowledgeIngestor(
        knowledge_dir,
        embedder,
        settings=settings,
        manifest_path=manifest_path,
    )
    chunks, records = await ingestor.load()
    bm25 = BM25Retriever(chunks, corpus_identity=ingestor.corpus_identity)
    store = InMemoryVectorStore()
    store.upsert(records)
    return bm25, store, chunks


async def ingest_knowledge(
    knowledge_dir: str,
    embedder: EmbeddingProvider,
    *,
    settings: Settings | None = None,
    qdrant_url: str = "",
    qdrant_collection: str = "cs_knowledge",
    embedding_dim: int = 512,
    manifest_path: str | None = None,
) -> tuple[BM25Retriever, InMemoryVectorStore | QdrantVectorStore, list[RetrievedChunk]]:
    """Prefer Qdrant when configured; fall back to memory if Qdrant is down."""
    logger = logging.getLogger(__name__)
    resolved = settings or get_settings()
    ingestor = VectorKnowledgeIngestor(
        knowledge_dir,
        embedder,
        settings=resolved,
        manifest_path=manifest_path,
    )
    chunks, records = await ingestor.load()
    bm25 = BM25Retriever(chunks, corpus_identity=ingestor.corpus_identity)
    if qdrant_url:
        store = QdrantVectorStore(qdrant_url, qdrant_collection, embedding_dim)
        try:
            await asyncio.to_thread(store.ensure_collection)
            await asyncio.to_thread(store.upsert, records)
            return bm25, store, chunks
        except Exception:
            logger.warning("qdrant_ingest_failed_using_memory")
    memory = InMemoryVectorStore()
    memory.upsert(records)
    return bm25, memory, chunks
