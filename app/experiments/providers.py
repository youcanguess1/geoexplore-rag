"""Deterministic embedding provider for explicit experimental tests."""

from app.providers.embeddings import HashEmbeddingProvider


class FakeEmbeddingProvider(HashEmbeddingProvider):
    pass
