"""Schemas for the explicit geological corpus specification."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class GeologicalDocumentManifest(BaseModel):
    """Stable identity and audit metadata for one geological source file."""

    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1)
    filename: str = Field(min_length=1)
    title: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    parser: Literal["pypdf"]
    data_type: Literal["01_Documents", "02_Academic"]
    document_type: Literal[
        "report",
        "standard",
        "textbook",
        "paper",
        "review",
        "technical_report",
    ]
    language: str = Field(min_length=1)
    source: str = Field(default="", min_length=0)


class GeologicalParserSpec(BaseModel):
    """The parser implementation whose output defines this corpus."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    backend: Literal["pypdf"]
    package: Literal["pypdf"]
    version: str = Field(min_length=1)


class GeologicalChunkingSpec(BaseModel):
    """The active fixed-window parameters used by the PDF parser."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_version: str = Field(min_length=1)
    max_chunk_chars: int = Field(gt=0)
    overlap_chars: int = Field(ge=0)


class GeologicalCorpusManifest(BaseModel):
    """A complete, versioned specification of one auditable geological corpus."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    corpus_id: str = Field(min_length=1)
    parser: GeologicalParserSpec
    chunking: GeologicalChunkingSpec
    documents: list[GeologicalDocumentManifest] = Field(min_length=1)


class CorpusIdentity(BaseModel):
    """Read-only identity of the material actually ingested at runtime."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    corpus_id: str
    corpus_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    parser_backend: str
    parser_version: str
    chunking_version: str
    document_count: int = Field(ge=0)
    chunk_count: int = Field(ge=0)
