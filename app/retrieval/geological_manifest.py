"""Loading and validating the geological document manifest."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.schemas.geological import GeologicalCorpusManifest, GeologicalDocumentManifest


@dataclass(frozen=True)
class ResolvedGeologicalDocument:
    manifest: GeologicalDocumentManifest
    path: Path


@dataclass(frozen=True)
class ResolvedGeologicalCorpus:
    manifest: GeologicalCorpusManifest
    documents: tuple[ResolvedGeologicalDocument, ...]


def installed_pypdf_version() -> str:
    """Return the installed distribution version rather than a module attribute."""
    try:
        return version("pypdf")
    except PackageNotFoundError as exc:
        raise RuntimeError("manifest requires pypdf but it is not installed") from exc


def load_geological_manifest(path: str | Path) -> GeologicalCorpusManifest:
    manifest_path = Path(path)
    if not manifest_path.is_file():
        raise FileNotFoundError(f"geological manifest not found: {manifest_path}")
    try:
        payload: Any = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = GeologicalCorpusManifest.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid geological manifest: {manifest_path}") from exc
    records = manifest.documents
    filenames = [record.filename for record in records]
    document_ids = [record.document_id for record in records]
    if len(set(filenames)) != len(filenames):
        raise ValueError("geological manifest contains duplicate filenames")
    if len(set(document_ids)) != len(document_ids):
        raise ValueError("geological manifest contains duplicate document_ids")
    for record in records:
        filename = Path(record.filename)
        if filename.name != record.filename or filename.suffix.lower() != ".pdf":
            raise ValueError(
                f"geological manifest filename must be a PDF basename: {record.filename}"
            )
    return manifest


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_geological_documents(
    knowledge_dir: str | Path,
    manifest_path: str | Path,
) -> ResolvedGeologicalCorpus:
    manifest = load_geological_manifest(manifest_path)
    if manifest.parser.backend != "pypdf" or manifest.parser.package != "pypdf":
        raise ValueError("geological manifest must declare the pypdf parser package")
    actual_parser_version = installed_pypdf_version()
    if manifest.parser.version != actual_parser_version:
        raise RuntimeError(
            "pypdf version mismatch: "
            f"manifest requires {manifest.parser.version}, installed {actual_parser_version}"
        )
    records = manifest.documents
    directory = Path(knowledge_dir)
    if not directory.is_dir():
        raise FileNotFoundError(f"geological knowledge directory not found: {directory}")

    expected = {record.filename for record in records}
    actual_pdf_names = {
        path.name
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() == ".pdf" and not path.name.startswith(".")
    }
    unregistered = sorted(actual_pdf_names - expected)
    if unregistered:
        names = ", ".join(unregistered)
        raise ValueError(f"unregistered geological PDF files: {names}")

    resolved: list[ResolvedGeologicalDocument] = []
    for record in records:
        document_path = directory / record.filename
        if not document_path.is_file():
            raise FileNotFoundError(f"manifested geological document missing: {document_path}")
        actual_sha256 = sha256_file(document_path)
        if actual_sha256.lower() != record.sha256.lower():
            raise ValueError(
                f"sha256 mismatch for {record.filename}: "
                f"expected {record.sha256.lower()}, got {actual_sha256}"
            )
        resolved.append(ResolvedGeologicalDocument(manifest=record, path=document_path))
    return ResolvedGeologicalCorpus(manifest=manifest, documents=tuple(resolved))
