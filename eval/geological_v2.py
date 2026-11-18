"""Helpers for the frozen v2 geological retrieval evaluation protocol."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from app.providers.embeddings import BgeM3EmbeddingProvider, HashEmbeddingProvider
from app.retrieval.filters import matches_retrieval_filters
from app.schemas.retrieval import RetrievalFilters, RetrievedChunk

REQUIRED_QUESTION_FIELDS = {
    "id",
    "question",
    "language",
    "scope",
    "answerability",
    "allowed_document_ids",
    "gold_sources",
    "filter",
    "reason",
}
SCOPES = {"unfiltered", "type_filtered", "document_scoped"}


def load_questions(path: str | Path) -> list[dict[str, Any]]:
    """Load one v2 question set and enforce its audit contract."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise ValueError("evaluation question set must be a non-empty JSON list")

    questions: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in payload:
        if not isinstance(item, dict) or not REQUIRED_QUESTION_FIELDS <= item.keys():
            raise ValueError("each v2 question is missing required fields")
        question_id = item["id"]
        if not isinstance(question_id, str) or not question_id or question_id in seen_ids:
            raise ValueError("question IDs must be non-empty and unique")
        if item["scope"] not in SCOPES:
            raise ValueError(f"invalid scope for {question_id}")
        if item["answerability"] not in {"answerable", "unanswerable"}:
            raise ValueError(f"invalid answerability for {question_id}")
        if not isinstance(item["allowed_document_ids"], list):
            raise ValueError(f"allowed_document_ids must be a list for {question_id}")
        if not isinstance(item["gold_sources"], list):
            raise ValueError(f"gold_sources must be a list for {question_id}")
        if not isinstance(item["filter"], dict):
            raise ValueError(f"filter must be an object for {question_id}")
        for source in item["gold_sources"]:
            if (
                not isinstance(source, dict)
                or not isinstance(source.get("document_id"), str)
                or not isinstance(source.get("page_number"), int)
                or source["page_number"] < 1
            ):
                raise ValueError(f"invalid gold source for {question_id}")

        filters = filters_for_question(item)
        _validate_question_contract(item, filters)
        seen_ids.add(question_id)
        questions.append(item)
    return questions


def _validate_question_contract(question: dict[str, Any], filters: RetrievalFilters | None) -> None:
    question_id = question["id"]
    answerable = question["answerability"] == "answerable"
    gold_sources = question["gold_sources"]
    allowed_document_ids = question["allowed_document_ids"]
    if answerable:
        if not gold_sources or not allowed_document_ids:
            raise ValueError(
                f"answerable question needs gold sources and document IDs: {question_id}"
            )
        if any(source["document_id"] not in allowed_document_ids for source in gold_sources):
            raise ValueError(f"gold source is outside allowed documents: {question_id}")
    elif gold_sources or allowed_document_ids:
        raise ValueError(f"unanswerable question must not have gold sources: {question_id}")

    scope = question["scope"]
    if scope == "unfiltered" and filters is not None:
        raise ValueError(f"unfiltered question has a filter: {question_id}")
    if scope == "type_filtered":
        if filters is None or not filters.document_types or filters.document_ids:
            raise ValueError(f"type_filtered question needs document_types only: {question_id}")
    if scope == "document_scoped" and (filters is None or not filters.document_ids):
        raise ValueError(f"document_scoped question needs document_ids: {question_id}")


def filters_for_question(question: dict[str, Any]) -> RetrievalFilters | None:
    """Translate explicit dataset filters through the shared schema."""
    payload = question.get("filter") or {}
    if not payload:
        return None
    filters = RetrievalFilters(**payload)
    return None if filters.is_empty() else filters


def source_pairs(question: dict[str, Any]) -> set[tuple[str, int]]:
    """Return physical-PDF source pairs registered for one question."""
    return {(source["document_id"], source["page_number"]) for source in question["gold_sources"]}


def validate_split_independence(
    development: list[dict[str, Any]], acceptance: list[dict[str, Any]]
) -> None:
    """Ensure no gold physical page is shared across frozen v2 splits."""
    development_pairs = set().union(*(source_pairs(question) for question in development))
    acceptance_pairs = set().union(*(source_pairs(question) for question in acceptance))
    overlap = development_pairs & acceptance_pairs
    if overlap:
        rendered = ", ".join(f"{document_id}:{page}" for document_id, page in sorted(overlap))
        raise ValueError(f"development and acceptance gold sources overlap: {rendered}")


def assert_real_dense_provider(provider: object) -> BgeM3EmbeddingProvider:
    """Reject fallback providers before a result can be labeled real dense."""
    if isinstance(provider, HashEmbeddingProvider) or getattr(provider, "backend", "") == "hash":
        raise RuntimeError("real dense evaluation must not use hash fallback")
    if not isinstance(provider, BgeM3EmbeddingProvider):
        raise RuntimeError("real dense evaluation requires BgeM3EmbeddingProvider")
    if not provider.available:
        raise RuntimeError(
            f"real dense model failed to load: {provider.load_error or 'unknown error'}"
        )
    return provider


def _result_page(chunk: RetrievedChunk) -> int | None:
    raw = chunk.metadata.get("page_number", "")
    try:
        return int(raw) if raw else None
    except (TypeError, ValueError):
        return None


def _has_provenance(chunk: RetrievedChunk) -> bool:
    return bool(
        chunk.document_id
        and chunk.metadata.get("source_file")
        and chunk.metadata.get("page_number")
        and chunk.metadata.get("sha256")
    )


def _failure_type(
    question: dict[str, Any],
    top: list[RetrievedChunk],
    *,
    execution_failed: bool,
    filters: RetrievalFilters | None,
) -> str:
    if execution_failed:
        return "execution_failed"
    if any(not matches_retrieval_filters(chunk, filters) for chunk in top):
        return "filter_violation"
    if question["answerability"] == "unanswerable":
        return "none"
    if not top:
        return "retrieval_miss"
    gold_documents = set(question["allowed_document_ids"])
    result_documents = {chunk.document_id for chunk in top}
    if not result_documents & gold_documents:
        return "wrong_document"
    gold_pairs = source_pairs(question)
    result_pairs = {
        (chunk.document_id, page) for chunk in top if (page := _result_page(chunk)) is not None
    }
    if not result_pairs & gold_pairs:
        return "wrong_page"
    return "none"


def score_results(
    question: dict[str, Any],
    results: list[RetrievedChunk],
    *,
    top_k: int,
    execution_failed: bool = False,
    filters: RetrievalFilters | None = None,
) -> dict[str, Any]:
    """Score Top-K retrieval without assigning an answer-generation status."""
    top = results[:top_k]
    filter_violation = any(not matches_retrieval_filters(chunk, filters) for chunk in top)
    provenance_validity = bool(top) and all(
        _has_provenance(chunk) and matches_retrieval_filters(chunk, filters) for chunk in top
    )
    output: dict[str, Any] = {
        "execution_failed": execution_failed,
        "candidate_returned": bool(top) if question["answerability"] == "unanswerable" else None,
        "document_hit": None,
        "page_hit": None,
        "source_recall": None,
        "mrr_at_5": None,
        "filter_violation": filter_violation,
        "provenance_validity": provenance_validity if top else None,
        "failure_type": _failure_type(
            question,
            top,
            execution_failed=execution_failed,
            filters=filters,
        ),
        "top_results": [
            {
                "rank": rank,
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "page_number": _result_page(chunk),
                "score": round(float(chunk.score), 8),
                "source": chunk.source,
            }
            for rank, chunk in enumerate(top, start=1)
        ],
    }
    if question["answerability"] == "unanswerable" or execution_failed:
        return output

    gold_documents = set(question["allowed_document_ids"])
    gold_pairs = source_pairs(question)
    result_documents = {chunk.document_id for chunk in top}
    result_pairs = {
        (chunk.document_id, page) for chunk in top if (page := _result_page(chunk)) is not None
    }
    first_gold_rank = next(
        (
            rank
            for rank, chunk in enumerate(top, start=1)
            if (chunk.document_id, _result_page(chunk)) in gold_pairs
        ),
        None,
    )
    output.update(
        {
            "document_hit": bool(result_documents & gold_documents),
            "page_hit": bool(result_pairs & gold_pairs),
            "source_recall": len(result_pairs & gold_pairs) / len(gold_pairs),
            "mrr_at_5": 1.0 / first_gold_rank if first_gold_rank else 0.0,
        }
    )
    return output


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarise a scope while keeping retrieval and unanswerable rows separate."""
    answerable = [
        row for row in rows if row["answerability"] == "answerable" and not row["execution_failed"]
    ]
    unanswerable = [row for row in rows if row["answerability"] == "unanswerable"]

    def values(key: str, source: list[dict[str, Any]]) -> list[float]:
        return [float(row[key]) for row in source if row.get(key) is not None]

    failures = Counter(
        row["failure_type"] for row in rows if row.get("failure_type") not in {None, "none"}
    )
    return {
        "n": len(rows),
        "answerable_n": len(answerable),
        "unanswerable_n": len(unanswerable),
        "document_hit_at_5": _mean(values("document_hit", answerable)),
        "document_hit_n": len(values("document_hit", answerable)),
        "page_hit_at_5": _mean(values("page_hit", answerable)),
        "page_hit_n": len(values("page_hit", answerable)),
        "source_recall_at_5": _mean(values("source_recall", answerable)),
        "source_recall_n": len(values("source_recall", answerable)),
        "mrr_at_5": _mean(values("mrr_at_5", answerable)),
        "mrr_at_5_n": len(values("mrr_at_5", answerable)),
        "filter_violation_rate": _mean(values("filter_violation", rows)),
        "filter_violation_n": len(values("filter_violation", rows)),
        "provenance_validity": _mean(values("provenance_validity", rows)),
        "provenance_validity_n": len(values("provenance_validity", rows)),
        "execution_failure_rate": _mean(values("execution_failed", rows)),
        "execution_failure_n": len(rows),
        "candidate_returned_rate": _mean(values("candidate_returned", unanswerable)),
        "candidate_returned_n": len(values("candidate_returned", unanswerable)),
        "failure_counts": dict(sorted(failures.items())),
    }


def summarise_by_scope(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return overall and fixed scope summaries for one retrieval system."""
    return {
        "unfiltered": summarise([row for row in rows if row["scope"] == "unfiltered"]),
        "type_filtered": summarise([row for row in rows if row["scope"] == "type_filtered"]),
        "document_scoped": summarise([row for row in rows if row["scope"] == "document_scoped"]),
        "overall": summarise(rows),
    }
