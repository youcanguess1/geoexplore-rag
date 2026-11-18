"""Pure helpers for the fixed geological retrieval evaluation."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from app.retrieval.filters import matches_retrieval_filters
from app.schemas.retrieval import RetrievalFilters, RetrievedChunk

REQUIRED_QUESTION_FIELDS = {
    "id",
    "question",
    "language",
    "answerability",
    "expected_status",
    "allowed_document_ids",
    "gold_sources",
    "filter",
    "reason",
}


def load_questions(path: str | Path) -> list[dict[str, Any]]:
    """Load and validate one frozen JSON question set."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise ValueError("evaluation question set must be a non-empty JSON list")
    questions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in payload:
        if not isinstance(item, dict) or not REQUIRED_QUESTION_FIELDS <= item.keys():
            raise ValueError("each evaluation question is missing required fields")
        question_id = item["id"]
        if not isinstance(question_id, str) or not question_id or question_id in seen:
            raise ValueError("question IDs must be non-empty and unique")
        if item["answerability"] not in {"answerable", "unanswerable"}:
            raise ValueError(f"invalid answerability for {question_id}")
        if item["expected_status"] not in {"evidence_only", "insufficient_evidence"}:
            raise ValueError(f"invalid expected_status for {question_id}")
        if not isinstance(item["allowed_document_ids"], list):
            raise ValueError(f"allowed_document_ids must be a list for {question_id}")
        if not isinstance(item["gold_sources"], list):
            raise ValueError(f"gold_sources must be a list for {question_id}")
        for source in item["gold_sources"]:
            if (
                not isinstance(source, dict)
                or not isinstance(source.get("document_id"), str)
                or not isinstance(source.get("page_number"), int)
                or source["page_number"] < 1
            ):
                raise ValueError(f"invalid gold source for {question_id}")
        if not isinstance(item["filter"], dict):
            raise ValueError(f"filter must be an object for {question_id}")
        required_chunk_ids = item.get("required_chunk_ids", [])
        if (
            not isinstance(required_chunk_ids, list)
            or any(not isinstance(chunk_id, str) or not chunk_id for chunk_id in required_chunk_ids)
            or len(required_chunk_ids) != len(set(required_chunk_ids))
        ):
            raise ValueError(
                f"required_chunk_ids must contain unique non-empty strings: {question_id}"
            )
        if required_chunk_ids and item["answerability"] != "answerable":
            raise ValueError(f"unanswerable question cannot require evidence chunks: {question_id}")
        seen.add(question_id)
        questions.append(item)
    return questions


def filters_for_question(question: dict[str, Any]) -> RetrievalFilters | None:
    """Translate the dataset's explicit filter object into the shared schema."""
    payload = question.get("filter") or {}
    if not payload:
        return None
    return RetrievalFilters(**payload)


def _source_pairs(question: dict[str, Any]) -> set[tuple[str, int]]:
    return {(source["document_id"], source["page_number"]) for source in question["gold_sources"]}


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


def classify_failure(
    question: dict[str, Any],
    results: list[RetrievedChunk],
    *,
    execution_failed: bool = False,
    filters: RetrievalFilters | None = None,
) -> str:
    """Classify one result without treating a backend exception as a refusal."""
    if execution_failed:
        return "execution_failed"
    if any(not matches_retrieval_filters(chunk, filters) for chunk in results):
        return "filter_violation"
    if not results:
        return "none" if question["answerability"] == "unanswerable" else "retrieval_miss"
    if question["answerability"] == "unanswerable":
        return "insufficient_evidence_misclassified"
    gold_documents = set(question["allowed_document_ids"])
    result_documents = {chunk.document_id for chunk in results}
    if not result_documents & gold_documents:
        return "wrong_document"
    gold_pages = _source_pairs(question)
    result_pairs = {
        (chunk.document_id, page) for chunk in results if (page := _result_page(chunk)) is not None
    }
    if not result_pairs & gold_pages:
        return "wrong_page"
    required_chunk_ids = set(question.get("required_chunk_ids", []))
    if required_chunk_ids and not required_chunk_ids <= {chunk.chunk_id for chunk in results}:
        return "incomplete_evidence"
    return "none"


def score_results(
    question: dict[str, Any],
    results: list[RetrievedChunk],
    *,
    top_k: int,
    execution_failed: bool = False,
    filters: RetrievalFilters | None = None,
) -> dict[str, Any]:
    """Calculate document/page/source metrics for one question and retriever."""
    top = results[:top_k]
    gold_documents = set(question["allowed_document_ids"])
    gold_sources = _source_pairs(question)
    result_documents = {chunk.document_id for chunk in top}
    result_sources = {
        (chunk.document_id, page) for chunk in top if (page := _result_page(chunk)) is not None
    }
    filter_violation = any(not matches_retrieval_filters(chunk, filters) for chunk in top)
    citation_validity = bool(top) and all(
        _has_provenance(chunk) and matches_retrieval_filters(chunk, filters) for chunk in top
    )
    if execution_failed:
        retrieval_status = "execution_failed"
    elif not top:
        retrieval_status = "insufficient_evidence"
    else:
        retrieval_status = "evidence_only"
    source_recall = len(result_sources & gold_sources) / len(gold_sources) if gold_sources else None
    required_chunk_ids = set(question.get("required_chunk_ids", []))
    evidence_coverage = (
        len(required_chunk_ids & {chunk.chunk_id for chunk in top}) / len(required_chunk_ids)
        if required_chunk_ids
        else None
    )
    return {
        "retrieval_status": retrieval_status,
        "document_hit": bool(result_documents & gold_documents) if gold_documents else None,
        "page_hit": bool(result_sources & gold_sources) if gold_sources else None,
        "source_recall": source_recall,
        "evidence_coverage": evidence_coverage,
        "filter_violation": filter_violation,
        "citation_validity": citation_validity if top else None,
        "failure_type": classify_failure(
            question,
            top,
            execution_failed=execution_failed,
            filters=filters,
        ),
        "top_results": [
            {
                "rank": chunk.rank,
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "page_number": _result_page(chunk),
                "score": round(float(chunk.score), 8),
                "source": chunk.source,
            }
            for chunk in top
        ],
    }


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate rows while keeping answerable and unanswerable denominators explicit."""
    answerable = [row for row in rows if row["answerability"] == "answerable"]

    def values(key: str, source: list[dict[str, Any]]) -> list[float]:
        return [float(row[key]) for row in source if row.get(key) is not None]

    failures = Counter(
        row["failure_type"] for row in rows if row.get("failure_type") not in {None, "none"}
    )
    document_hits = values("document_hit", answerable)
    page_hits = values("page_hit", answerable)
    source_recalls = values("source_recall", answerable)
    evidence_coverages = values("evidence_coverage", answerable)
    filter_violations = values("filter_violation", rows)
    citation_validities = values("citation_validity", rows)
    status_rows = [row for row in rows if row.get("retrieval_status") != "execution_failed"]
    return {
        "n": len(rows),
        "answerable_n": len(answerable),
        "document_hit_at_5": _mean(document_hits),
        "document_hit_n": len(document_hits),
        "page_hit_at_5": _mean(page_hits),
        "page_hit_n": len(page_hits),
        "source_recall": _mean(source_recalls),
        "source_recall_n": len(source_recalls),
        "evidence_coverage": _mean(evidence_coverages),
        "evidence_coverage_n": len(evidence_coverages),
        "filter_violation_rate": _mean(filter_violations),
        "filter_violation_n": len(filter_violations),
        "citation_validity": _mean(citation_validities),
        "citation_validity_n": len(citation_validities),
        "status_accuracy": _mean(
            [float(row["retrieval_status"] == row["expected_status"]) for row in status_rows]
        ),
        "status_accuracy_n": len(status_rows),
        "failure_counts": dict(sorted(failures.items())),
    }
