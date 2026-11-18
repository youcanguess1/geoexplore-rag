import hashlib
import json
from pathlib import Path

import pytest

from app.agents.geological import citation_for_chunk
from app.config.settings import Settings
from app.retrieval import ingest as ingest_module
from app.retrieval.chunking import document_id_from_path
from app.retrieval.corpus_identity import build_corpus_identity
from app.retrieval.geological_manifest import (
    installed_pypdf_version,
    load_geological_manifest,
    resolve_geological_documents,
    sha256_file,
)
from app.retrieval.ingest import KnowledgeIngestor
from app.schemas.geological import GeologicalCorpusManifest
from app.schemas.retrieval import RetrievedChunk


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _manifest_payload(*, sha256: str, filename: str = "1996-21.pdf") -> dict:
    return {
        "corpus_id": "geoexplore-test-v1",
        "parser": {
            "backend": "pypdf",
            "package": "pypdf",
            "version": installed_pypdf_version(),
        },
        "chunking": {
            "policy_version": "v1",
            "max_chunk_chars": 500,
            "overlap_chars": 60,
        },
        "documents": [
            {
                "document_id": "geo-1996-21",
                "filename": filename,
                "title": "A Simple Algorithm for Band-Limited Impedance Inversion",
                "sha256": sha256,
                "parser": "pypdf",
                "data_type": "02_Academic",
                "document_type": "paper",
                "language": "en",
            }
        ],
    }


def _write_manifest(path: Path, *, sha256: str, filename: str = "1996-21.pdf") -> None:
    path.write_text(
        json.dumps(_manifest_payload(sha256=sha256, filename=filename)),
        encoding="utf-8",
    )


def test_manifest_parses_valid_record_and_uses_stable_id(tmp_path: Path) -> None:
    source = b"same PDF bytes"
    manifest_path = tmp_path / "geological_documents.json"
    _write_manifest(manifest_path, sha256=_sha256(source))

    corpus = load_geological_manifest(manifest_path)

    assert corpus.corpus_id == "geoexplore-test-v1"
    assert corpus.parser.version == installed_pypdf_version()
    assert corpus.documents[0].document_id == "geo-1996-21"
    assert corpus.documents[0].parser == "pypdf"
    assert corpus.documents[0].data_type == "02_Academic"
    assert document_id_from_path(Path("1996-21.pdf")) != "geo-1996-21"


def test_legacy_array_manifest_is_rejected(tmp_path: Path) -> None:
    manifest_path = tmp_path / "geological_documents.json"
    manifest_path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid geological manifest"):
        load_geological_manifest(manifest_path)


def test_same_file_in_different_directory_resolves_to_same_manifest_id(tmp_path: Path) -> None:
    source = b"same PDF bytes"
    manifest_path = tmp_path / "geological_documents.json"
    _write_manifest(manifest_path, sha256=_sha256(source))
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    (first_dir / "1996-21.pdf").write_bytes(source)
    (second_dir / "1996-21.pdf").write_bytes(source)

    first = resolve_geological_documents(first_dir, manifest_path)
    second = resolve_geological_documents(second_dir, manifest_path)

    assert first.documents[0].manifest.document_id == second.documents[0].manifest.document_id == "geo-1996-21"
    assert sha256_file(first.documents[0].path) == sha256_file(second.documents[0].path)


def test_sha256_mismatch_fails_before_ingest(tmp_path: Path) -> None:
    manifest_path = tmp_path / "geological_documents.json"
    _write_manifest(manifest_path, sha256=_sha256(b"expected"))
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    (knowledge_dir / "1996-21.pdf").write_bytes(b"actual")

    with pytest.raises(ValueError, match="sha256 mismatch"):
        resolve_geological_documents(knowledge_dir, manifest_path)


def test_missing_manifest_fails_explicitly(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="geological manifest not found"):
        resolve_geological_documents(tmp_path / "knowledge", tmp_path / "missing.json")


def test_unregistered_pdf_fails_explicitly(tmp_path: Path) -> None:
    source = b"same PDF bytes"
    manifest_path = tmp_path / "geological_documents.json"
    _write_manifest(manifest_path, sha256=_sha256(source))
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    (knowledge_dir / "1996-21.pdf").write_bytes(source)
    (knowledge_dir / "unregistered.pdf").write_bytes(b"other")

    with pytest.raises(ValueError, match="unregistered geological PDF files"):
        resolve_geological_documents(knowledge_dir, manifest_path)


@pytest.mark.asyncio
async def test_manifest_metadata_reaches_chunks_and_citations(tmp_path: Path, monkeypatch) -> None:
    source = b"same PDF bytes"
    manifest_path = tmp_path / "geological_documents.json"
    _write_manifest(manifest_path, sha256=_sha256(source))
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    (knowledge_dir / "1996-21.pdf").write_bytes(source)

    def fake_parse_path(path: Path, **kwargs) -> list[RetrievedChunk]:
        assert kwargs["parser_backend"] == "pypdf"
        return [
            RetrievedChunk(
                chunk_id=f"{kwargs['document_id']}_00",
                document_id=kwargs["document_id"],
                title=kwargs["title"],
                content="BLIMP evidence",
                score=0.0,
                metadata={"parser": "pypdf", "page_number": "3"},
            )
        ]

    monkeypatch.setattr(ingest_module, "parse_path", fake_parse_path)
    ingestor = KnowledgeIngestor(
        str(knowledge_dir),
        settings=Settings(app_env="testing", unstructured_force=True),
        manifest_path=str(manifest_path),
    )

    chunks = await ingestor.load_chunks()
    citation = citation_for_chunk(chunks[0])

    assert chunks[0].document_id == "geo-1996-21"
    assert chunks[0].title == "A Simple Algorithm for Band-Limited Impedance Inversion"
    assert chunks[0].metadata["parser"] == "pypdf"
    assert chunks[0].metadata["page_number"] == "3"
    assert chunks[0].metadata["source"] == "1996-21.pdf"
    assert chunks[0].metadata["source_file"] == "1996-21.pdf"
    assert chunks[0].metadata["data_type"] == "02_Academic"
    assert chunks[0].metadata["document_type"] == "paper"
    assert chunks[0].metadata["language"] == "en"
    assert chunks[0].metadata["sha256"] == _sha256(source)
    assert chunks[0].metadata["corpus_fingerprint"] == ingestor.corpus_identity.corpus_fingerprint
    assert citation.data_type == "02_Academic"
    assert citation.document_type == "paper"
    assert citation.language == "en"
    assert citation.document_sha256 == _sha256(source)
    assert citation.corpus_fingerprint == ingestor.corpus_identity.corpus_fingerprint


@pytest.mark.asyncio
async def test_manifest_fixed_pypdf_identity_is_stable_across_repeated_builds(
    tmp_path: Path, monkeypatch
) -> None:
    source = b"same PDF bytes"
    manifest_path = tmp_path / "geological_documents.json"
    _write_manifest(manifest_path, sha256=_sha256(source))
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    (knowledge_dir / "1996-21.pdf").write_bytes(source)

    def fake_parse_path(path: Path, **kwargs) -> list[RetrievedChunk]:
        assert kwargs["parser_backend"] == "pypdf"
        return [
            RetrievedChunk(
                chunk_id=f"{kwargs['document_id']}_00",
                document_id=kwargs["document_id"],
                title=kwargs["title"],
                content="same evidence",
                score=0.0,
                metadata={"parser": "pypdf", "page_number": "3"},
            )
        ]

    monkeypatch.setattr(ingest_module, "parse_path", fake_parse_path)
    settings = Settings(app_env="testing", unstructured_force=True)
    first = KnowledgeIngestor(
        str(knowledge_dir),
        settings=settings,
        manifest_path=str(manifest_path),
    )
    second = KnowledgeIngestor(
        str(knowledge_dir),
        settings=settings,
        manifest_path=str(manifest_path),
    )

    await first.load_chunks()
    await second.load_chunks()

    assert first.corpus_identity is not None
    assert second.corpus_identity is not None
    assert first.corpus_identity == second.corpus_identity
    assert first.corpus_identity.parser_backend == "pypdf"


def test_citations_keep_same_content_sources_distinct() -> None:
    first = RetrievedChunk(
        chunk_id="doc-a_00",
        document_id="doc-a",
        title="Source A",
        content="same evidence",
        score=0.0,
        metadata={"source_file": "a.pdf", "page_number": "3"},
    )
    second = first.model_copy(
        update={
            "chunk_id": "doc-b_00",
            "document_id": "doc-b",
            "title": "Source B",
            "metadata": {"source_file": "b.pdf", "page_number": "8"},
        }
    )

    first_citation = citation_for_chunk(first)
    second_citation = citation_for_chunk(second)

    assert first_citation.document_id == "doc-a"
    assert first_citation.source_file == "a.pdf"
    assert second_citation.document_id == "doc-b"
    assert second_citation.source_file == "b.pdf"


def _fingerprint_chunk(
    *, content: str = "BLIMP evidence", page_number: str = "3", source: str = "C:/local/a.pdf"
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="geo-1996-21_10",
        document_id="geo-1996-21",
        title="BLIMP",
        content=content,
        score=0.0,
        chunk_index=10,
        section="body",
        metadata={
            "page_number": page_number,
            "source": source,
            "source_file": "1996-21.pdf",
            "data_type": "02_Academic",
            "document_type": "paper",
            "language": "en",
            "sha256": _sha256(b"source"),
        },
    )


def _fingerprint_manifest() -> GeologicalCorpusManifest:
    return GeologicalCorpusManifest.model_validate(_manifest_payload(sha256=_sha256(b"source")))


def test_corpus_fingerprint_is_stable_and_excludes_absolute_paths() -> None:
    manifest = _fingerprint_manifest()
    first = build_corpus_identity(manifest, [_fingerprint_chunk(source="C:/one/source.pdf")])
    second = build_corpus_identity(manifest, [_fingerprint_chunk(source="D:/two/source.pdf")])

    assert first.corpus_fingerprint == second.corpus_fingerprint
    assert first.document_count == 1
    assert first.chunk_count == 1


def test_corpus_fingerprint_changes_for_chunk_content_page_or_chunking_version() -> None:
    manifest = _fingerprint_manifest()
    baseline = build_corpus_identity(manifest, [_fingerprint_chunk()])
    changed_content = build_corpus_identity(manifest, [_fingerprint_chunk(content="changed evidence")])
    changed_page = build_corpus_identity(manifest, [_fingerprint_chunk(page_number="4")])
    changed_title = build_corpus_identity(
        manifest,
        [_fingerprint_chunk().model_copy(update={"title": "Changed BLIMP title"})],
    )
    changed_policy = build_corpus_identity(
        manifest.model_copy(update={"chunking": manifest.chunking.model_copy(update={"policy_version": "v2"})}),
        [_fingerprint_chunk()],
    )

    assert baseline.corpus_fingerprint != changed_content.corpus_fingerprint
    assert baseline.corpus_fingerprint != changed_page.corpus_fingerprint
    assert baseline.corpus_fingerprint != changed_title.corpus_fingerprint
    assert baseline.corpus_fingerprint != changed_policy.corpus_fingerprint


def test_corpus_fingerprint_ignores_document_and_chunk_input_order() -> None:
    payload = _manifest_payload(sha256=_sha256(b"source"))
    second_document = payload["documents"][0] | {
        "document_id": "geo-other",
        "filename": "other.pdf",
        "sha256": _sha256(b"other"),
    }
    payload["documents"].append(second_document)
    manifest = GeologicalCorpusManifest.model_validate(payload)
    reversed_manifest = manifest.model_copy(update={"documents": list(reversed(manifest.documents))})
    first_chunk = _fingerprint_chunk()
    second_chunk = first_chunk.model_copy(
        update={"document_id": "geo-other", "chunk_id": "geo-other_00", "chunk_index": 0}
    )

    first = build_corpus_identity(manifest, [first_chunk, second_chunk])
    second = build_corpus_identity(reversed_manifest, [second_chunk, first_chunk])

    assert first.corpus_fingerprint == second.corpus_fingerprint


def test_manifest_pypdf_version_mismatch_fails_before_file_parsing(tmp_path: Path) -> None:
    source = b"same PDF bytes"
    manifest_path = tmp_path / "geological_documents.json"
    payload = _manifest_payload(sha256=_sha256(source))
    payload["parser"]["version"] = "0.0.0"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    (knowledge_dir / "1996-21.pdf").write_bytes(source)

    with pytest.raises(RuntimeError, match="pypdf version mismatch"):
        resolve_geological_documents(knowledge_dir, manifest_path)
