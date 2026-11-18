"""Retrieved chunk, citation, and explicit retrieval-filter schemas."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import DocumentCategory


def _normalise_values(value: object) -> object:
    if value is None:
        return []
    if not isinstance(value, list | tuple):
        return value
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            result.append(item)  # type: ignore[arg-type]
            continue
        cleaned = item.strip()
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result


class RetrievalFilters(BaseModel):
    """Allow-list filters applied consistently across every retrieval boundary."""

    model_config = ConfigDict(extra="forbid")

    document_ids: list[str] = Field(default_factory=list, max_length=20)
    data_types: list[Literal["01_Documents", "02_Academic"]] = Field(default_factory=list)
    document_types: list[
        Literal["report", "standard", "textbook", "paper", "review", "technical_report"]
    ] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("document_ids", "data_types", "document_types", "languages", mode="before")
    @classmethod
    def normalise_list_values(cls, value: object) -> object:
        return _normalise_values(value)

    @field_validator("languages")
    @classmethod
    def normalise_languages(cls, value: list[str]) -> list[str]:
        result: list[str] = []
        for item in value:
            language = item.lower()
            if language not in result:
                result.append(language)
        return result

    @field_validator("document_ids")
    @classmethod
    def reject_blank_document_ids(cls, value: list[str]) -> list[str]:
        if any(not item for item in value):
            raise ValueError("document_ids must not contain blank values")
        return value

    def is_empty(self) -> bool:
        return not any((self.document_ids, self.data_types, self.document_types, self.languages))


class RetrievedChunk(BaseModel):
    chunk_id: str
    document_id: str
    title: str
    content: str
    score: float
    rank: int | None = None
    source: str = "hybrid"
    category: DocumentCategory = DocumentCategory.GENERAL
    section: str | None = None
    chunk_index: int = 0
    policy_version: str = "v1"
    metadata: dict[str, str] = Field(default_factory=dict)


class Citation(BaseModel):
    document_id: str
    title: str
    chunk_id: str
    section: str | None = None
    source_file: str = ""
    page_number: int | None = None
    excerpt: str = ""
    data_type: str = ""
    document_type: str = ""
    language: str = ""
    document_sha256: str = ""
    corpus_fingerprint: str = ""


class RetrievalRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)
    category: DocumentCategory | None = None
