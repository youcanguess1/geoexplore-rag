from __future__ import annotations

import pytest

from app.config.settings import Settings
from app.experiments.ingest import VectorKnowledgeIngestor, ingest_knowledge, ingest_to_memory
from app.experiments.providers import FakeEmbeddingProvider
from app.retrieval.ingest import KnowledgeIngestor


@pytest.mark.asyncio
@pytest.mark.parametrize("ingest", [ingest_to_memory, ingest_knowledge])
async def test_experimental_ingest_reuses_shared_chunks_without_network(tmp_path, ingest) -> None:
    (tmp_path / "seismic.md").write_text(
        "# Seismic evidence\n\nRefraction constrains seismic velocity.", encoding="utf-8"
    )
    settings = Settings(_env_file=None, app_env="testing", unstructured_enabled=False)
    expected = await KnowledgeIngestor(str(tmp_path), settings=settings).load_chunks()

    bm25, store, chunks = await ingest(
        str(tmp_path), FakeEmbeddingProvider(dim=16), settings=settings
    )

    assert chunks
    assert [chunk.model_dump() for chunk in chunks] == [chunk.model_dump() for chunk in expected]
    assert bm25.search("seismic", top_k=1)
    embeddings = await FakeEmbeddingProvider(dim=16).embed([chunks[0].content])
    hits = store.search(embeddings[0], top_k=1)
    assert hits[0].chunk_id == chunks[0].chunk_id


@pytest.mark.asyncio
async def test_experimental_vectorization_requires_an_explicit_embedder(tmp_path) -> None:
    (tmp_path / "seismic.md").write_text("Seismic refraction evidence.", encoding="utf-8")
    ingestor = VectorKnowledgeIngestor(
        str(tmp_path),
        settings=Settings(_env_file=None, app_env="testing", unstructured_enabled=False),
    )
    chunks = await ingestor.load_chunks()

    assert chunks
    with pytest.raises(ValueError, match="embedding provider is required"):
        await ingestor.build_vector_records(chunks)
