"""Deterministic identity for a fully materialized geological corpus."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable

from app.schemas.geological import CorpusIdentity, GeologicalCorpusManifest
from app.schemas.retrieval import RetrievedChunk

_CITATION_METADATA_KEYS = (
    "data_type",
    "document_type",
    "language",
    "sha256",
    "source_file",
)


def content_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def build_corpus_identity(
    manifest: GeologicalCorpusManifest,
    chunks: Iterable[RetrievedChunk],
) -> CorpusIdentity:
    """Hash canonical corpus facts only; local paths and runtime state are excluded."""
    ordered_chunks = sorted(chunks, key=lambda chunk: (chunk.document_id, chunk.chunk_index, chunk.chunk_id))
    document_records = sorted(
        (
            {"document_id": document.document_id, "sha256": document.sha256.lower()}
            for document in manifest.documents
        ),
        key=lambda item: item["document_id"],
    )
    payload = {
        "corpus_id": manifest.corpus_id,
        "parser": manifest.parser.model_dump(mode="json"),
        "chunking": manifest.chunking.model_dump(mode="json"),
        "documents": document_records,
        "chunks": [
            {
                "document_id": chunk.document_id,
                "chunk_id": chunk.chunk_id,
                "chunk_index": chunk.chunk_index,
                "title": chunk.title,
                "page_number": chunk.metadata.get("page_number", ""),
                "content_sha256": content_sha256(chunk.content),
                "section": chunk.section or "",
                "citation_metadata": {
                    key: chunk.metadata.get(key, "") for key in _CITATION_METADATA_KEYS
                },
            }
            for chunk in ordered_chunks
        ],
    }
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return CorpusIdentity(
        corpus_id=manifest.corpus_id,
        corpus_fingerprint=fingerprint,
        parser_backend=manifest.parser.backend,
        parser_version=manifest.parser.version,
        chunking_version=manifest.chunking.policy_version,
        document_count=len(manifest.documents),
        chunk_count=len(ordered_chunks),
    )


def attach_corpus_identity(chunks: Iterable[RetrievedChunk], identity: CorpusIdentity) -> None:
    """Attach server-generated provenance that travels with retrieval and citations."""
    for chunk in chunks:
        chunk.metadata.update(
            {
                "corpus_id": identity.corpus_id,
                "corpus_fingerprint": identity.corpus_fingerprint,
                "parser_backend": identity.parser_backend,
                "parser_version": identity.parser_version,
                "chunking_version": identity.chunking_version,
            }
        )
