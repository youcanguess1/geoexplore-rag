"""Shared corpus loading and production BM25 ingestion."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Literal

from app.config.settings import Settings, get_settings
from app.core.enums import DocumentCategory
from app.retrieval.bm25 import BM25Retriever
from app.retrieval.chunking import document_id_from_path
from app.retrieval.cleaning import dedupe_chunks
from app.retrieval.corpus_identity import attach_corpus_identity, build_corpus_identity
from app.retrieval.geological_manifest import resolve_geological_documents
from app.retrieval.unstructured_parser import list_knowledge_files, parse_path
from app.schemas.geological import CorpusIdentity
from app.schemas.retrieval import RetrievedChunk


def category_for_stem(stem: str) -> DocumentCategory:
    """Retain a neutral category for non-geological compatibility callers."""
    del stem
    return DocumentCategory.GENERAL


class KnowledgeIngestor:
    def __init__(
        self,
        knowledge_dir: str,
        *,
        settings: Settings | None = None,
        manifest_path: str | None = None,
    ) -> None:
        self._knowledge_dir = Path(knowledge_dir)
        self._settings = settings or get_settings()
        self._manifest_path = manifest_path
        self.corpus_identity: CorpusIdentity | None = None

    async def load_chunks(self) -> list[RetrievedChunk]:
        """Parse, manifest-validate, enrich, and deduplicate source chunks."""
        chunks: list[RetrievedChunk] = []
        corpus_manifest = None
        sources: list[tuple[Path, str, str, str, dict[str, Any], Literal["auto", "pypdf"]]]
        if self._manifest_path:
            resolved_corpus = resolve_geological_documents(self._knowledge_dir, self._manifest_path)
            corpus_manifest = resolved_corpus.manifest
            sources = [
                (
                    document.path,
                    document.manifest.document_id,
                    document.manifest.title,
                    document.manifest.filename,
                    document.manifest.model_dump(mode="json"),
                    document.manifest.parser,
                )
                for document in resolved_corpus.documents
            ]
        else:
            sources = [
                (path, document_id_from_path(path), path.stem, str(path), {}, "auto")
                for path in list_knowledge_files(self._knowledge_dir)
            ]
        for path, document_id, title, source_file, manifest_metadata, parser_backend in sources:
            category = category_for_stem(path.stem)
            file_chunks = await asyncio.to_thread(
                parse_path,
                path,
                document_id=document_id,
                title=title,
                category=category,
                settings=self._settings,
                parser_backend=parser_backend,
                policy_version=(
                    corpus_manifest.chunking.policy_version if corpus_manifest is not None else "v1"
                ),
                max_chunk_chars=(
                    corpus_manifest.chunking.max_chunk_chars if corpus_manifest is not None else 500
                ),
                overlap_chars=(
                    corpus_manifest.chunking.overlap_chars if corpus_manifest is not None else 60
                ),
            )
            if manifest_metadata:
                for chunk in file_chunks:
                    metadata = {
                        "source": source_file,
                        "source_file": source_file,
                        "data_type": str(manifest_metadata["data_type"]),
                        "document_type": str(manifest_metadata["document_type"]),
                        "language": str(manifest_metadata["language"]),
                        "sha256": str(manifest_metadata["sha256"]),
                        "parser": chunk.metadata.get("parser", ""),
                        "page_number": chunk.metadata.get("page_number", ""),
                    }
                    if manifest_metadata.get("source"):
                        metadata["manifest_source"] = str(manifest_metadata["source"])
                    chunk.metadata.update(metadata)
            chunks.extend(file_chunks)
        chunks = dedupe_chunks(chunks)
        if corpus_manifest is not None:
            self.corpus_identity = build_corpus_identity(corpus_manifest, chunks)
            attach_corpus_identity(chunks, self.corpus_identity)
        return chunks


async def ingest_bm25(
    knowledge_dir: str,
    *,
    settings: Settings | None = None,
    manifest_path: str | None = None,
) -> tuple[BM25Retriever, list[RetrievedChunk]]:
    """Build the production lexical index without constructing vector records."""
    ingestor = KnowledgeIngestor(
        knowledge_dir,
        settings=settings,
        manifest_path=manifest_path,
    )
    chunks = await ingestor.load_chunks()
    return BM25Retriever(chunks, corpus_identity=ingestor.corpus_identity), chunks
