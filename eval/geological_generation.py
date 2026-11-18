"""Audit helpers for the frozen GeoExplore generation-evaluation protocol."""

from __future__ import annotations

import hashlib
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.retrieval.filters import matches_retrieval_filters
from app.schemas.geological import CorpusIdentity
from app.schemas.retrieval import Citation, RetrievalFilters, RetrievedChunk

SCHEMA_VERSION = "geoexplore-generation-v1"
EXPECTED_STATUSES = {"answered", "insufficient_evidence"}
QUESTION_TYPES = {
    "single_chunk",
    "adjacent_chunk",
    "condition_parameter",
    "filter_insufficient",
    "corpus_insufficient",
}
REQUIRED_QUESTION_FIELDS = {
    "question_id",
    "question",
    "question_type",
    "filters",
    "expected_status",
    "gold_document_ids",
    "gold_physical_pages",
    "gold_evidence",
    "required_facts",
    "required_fact_keywords",
    "forbidden_claims",
    "manual_evidence_note",
}


def canonical_sha256(payload: Any) -> str:
    """Hash JSON with a stable encoding for auditable input identities."""
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_question_set(path: str | Path, *, expected_split: str | None = None) -> dict[str, Any]:
    """Load and validate one manually authored generation question set."""
    source = Path(path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("generation question set must be a JSON object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported generation question-set schema")
    split = payload.get("split")
    if split not in {"dev", "acceptance"}:
        raise ValueError("generation question set has invalid split")
    if expected_split is not None and split != expected_split:
        raise ValueError(f"expected {expected_split} question set, got {split}")
    try:
        identity = CorpusIdentity.model_validate(payload["corpus_identity"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("generation question set has invalid corpus identity") from exc
    questions = payload.get("questions")
    if not isinstance(questions, list) or not questions:
        raise ValueError("generation question set must contain questions")

    seen_ids: set[str] = set()
    for question in questions:
        _validate_question(question, identity, seen_ids)
        seen_ids.add(question["question_id"])
    return payload


def question_filters(question: dict[str, Any]) -> RetrievalFilters | None:
    filters = RetrievalFilters.model_validate(question["filters"])
    return None if filters.is_empty() else filters


def validate_split_independence(dev: dict[str, Any], acceptance: dict[str, Any]) -> None:
    """Reject shared answer evidence and facts between tuning and held-out sets."""
    if dev["corpus_identity"] != acceptance["corpus_identity"]:
        raise ValueError("dev and acceptance corpus identities must be identical")
    dev_ids = {question["question_id"] for question in dev["questions"]}
    acceptance_ids = {question["question_id"] for question in acceptance["questions"]}
    if dev_ids & acceptance_ids:
        raise ValueError("dev and acceptance question IDs overlap")
    dev_pages = _all_source_pairs(dev["questions"])
    acceptance_pages = _all_source_pairs(acceptance["questions"])
    if dev_pages & acceptance_pages:
        raise ValueError("dev and acceptance gold physical pages overlap")
    dev_facts = _all_normalized_facts(dev["questions"])
    acceptance_facts = _all_normalized_facts(acceptance["questions"])
    if dev_facts & acceptance_facts:
        raise ValueError("dev and acceptance required facts overlap")


def automatic_review(
    *,
    question: dict[str, Any],
    response: dict[str, Any],
    bounded_context: list[dict[str, Any]],
    corpus_identity: CorpusIdentity,
) -> dict[str, Any]:
    """Return mechanical boundary checks without asserting factual support."""
    filters = question_filters(question)
    citations = [Citation.model_validate(item) for item in response.get("citations", [])]
    context_ids = {str(item["chunk_id"]) for item in bounded_context}
    gold_pages = {
        (evidence["document_id"], evidence["physical_page"])
        for evidence in question["gold_evidence"]
    }
    answer = str(response.get("answer") or "")
    keyword_signals = [
        all(_required_keyword_matches(keyword, answer) for keyword in group)
        for group in question["required_fact_keywords"]
    ]
    forbidden_hits = [
        claim
        for claim in question["forbidden_claims"]
        if _normalise_text(claim) in _normalise_text(answer)
    ]
    citation_rows = [
        {
            "chunk_id": citation.chunk_id,
            "in_bounded_context": citation.chunk_id in context_ids,
            "matches_filters": _citation_matches_filters(citation, filters),
            "matches_corpus_fingerprint": (
                citation.corpus_fingerprint == corpus_identity.corpus_fingerprint
            ),
            "document_page_correct": (
                (citation.document_id, citation.page_number) in gold_pages
                if gold_pages
                else citation is None
            ),
        }
        for citation in citations
    ]
    return {
        "status_correct": response.get("status") == question["expected_status"],
        "answerable_coverage": (
            response.get("status") == "answered"
            if question["expected_status"] == "answered"
            else None
        ),
        "required_fact_keyword_signals": keyword_signals,
        "required_fact_candidate_coverage": (
            sum(keyword_signals) / len(keyword_signals) if keyword_signals else None
        ),
        "forbidden_claim_candidate_hits": forbidden_hits,
        "citation_checks": citation_rows,
        "citation_in_context": all(item["in_bounded_context"] for item in citation_rows),
        "citation_filter_compliant": all(item["matches_filters"] for item in citation_rows),
        "citation_fingerprint_compliant": all(
            item["matches_corpus_fingerprint"] for item in citation_rows
        ),
        "citation_document_page_correct": (
            all(item["document_page_correct"] for item in citation_rows)
            if gold_pages
            else not citations
        ),
        "human_review": {
            "required_fact_support": "pending",
            "unsupported_claims": "pending",
            "citation_pdf_page_correctness": "pending",
        },
    }


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize automatic signals overall and by question type."""
    return {
        "overall": _summarize_group(rows),
        "by_question_type": {
            question_type: _summarize_group(group)
            for question_type, group in sorted(_group_by_type(rows).items())
        },
    }


def _validate_question(
    question: object,
    identity: CorpusIdentity,
    seen_ids: set[str],
) -> None:
    if not isinstance(question, dict) or not REQUIRED_QUESTION_FIELDS <= question.keys():
        raise ValueError("generation question is missing required fields")
    question_id = question["question_id"]
    if not isinstance(question_id, str) or not question_id or question_id in seen_ids:
        raise ValueError("generation question IDs must be non-empty and unique")
    if not isinstance(question["question"], str) or not question["question"].strip():
        raise ValueError(f"generation question must have text: {question_id}")
    if question["question_type"] not in QUESTION_TYPES:
        raise ValueError(f"invalid question type: {question_id}")
    if question["expected_status"] not in EXPECTED_STATUSES:
        raise ValueError(f"invalid expected status: {question_id}")
    question_filters(question)
    documents = question["gold_document_ids"]
    pages = question["gold_physical_pages"]
    evidence = question["gold_evidence"]
    facts = question["required_facts"]
    keywords = question["required_fact_keywords"]
    if not all(isinstance(value, list) for value in (documents, pages, evidence, facts, keywords)):
        raise ValueError(f"generation question lists are invalid: {question_id}")
    if question["expected_status"] == "answered":
        if not documents or not pages or not evidence or not facts or not keywords:
            raise ValueError(f"answerable question lacks manual evidence: {question_id}")
        if set(documents) != {item.get("document_id") for item in evidence}:
            raise ValueError(f"gold document IDs do not match evidence: {question_id}")
        if set(pages) != {item.get("physical_page") for item in evidence}:
            raise ValueError(f"gold pages do not match evidence: {question_id}")
        if any(
            not isinstance(item, dict)
            or not isinstance(item.get("document_id"), str)
            or not isinstance(item.get("physical_page"), int)
            or item["physical_page"] < 1
            for item in evidence
        ):
            raise ValueError(f"gold evidence is invalid: {question_id}")
        if any(not isinstance(group, list) or not group for group in keywords):
            raise ValueError(f"required keyword groups are invalid: {question_id}")
    elif documents or pages or evidence or facts or keywords:
        raise ValueError(
            f"insufficient-evidence question must not register gold facts: {question_id}"
        )
    if not isinstance(question["forbidden_claims"], list):
        raise ValueError(f"forbidden claims are invalid: {question_id}")
    if not isinstance(question["manual_evidence_note"], str):
        raise ValueError(f"manual evidence note is invalid: {question_id}")
    if (
        question.get("corpus_fingerprint", identity.corpus_fingerprint)
        != identity.corpus_fingerprint
    ):
        raise ValueError(f"question corpus fingerprint is not frozen: {question_id}")


def _all_source_pairs(questions: list[dict[str, Any]]) -> set[tuple[str, int]]:
    return {
        (evidence["document_id"], evidence["physical_page"])
        for question in questions
        for evidence in question["gold_evidence"]
    }


def _all_normalized_facts(questions: list[dict[str, Any]]) -> set[str]:
    return {_normalise_text(fact) for question in questions for fact in question["required_facts"]}


def _citation_matches_filters(citation: Citation, filters: RetrievalFilters | None) -> bool:
    chunk = RetrievedChunk(
        chunk_id=citation.chunk_id,
        document_id=citation.document_id,
        title=citation.title,
        content="",
        score=0.0,
        metadata={
            "data_type": citation.data_type,
            "document_type": citation.document_type,
            "language": citation.language,
        },
    )
    return matches_retrieval_filters(chunk, filters)


def _normalise_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _normalise_frequency_units(value: str) -> str:
    normalised = _normalise_text(value)
    return re.sub(
        r"(?<![\w.])(\d+(?:\.\d+)?)\s*[- ]?\s*(?:hertz|hz)\b",
        r"\1 hz",
        normalised,
    )


def _required_keyword_matches(keyword: str, answer: str) -> bool:
    normalised_keyword = _normalise_frequency_units(keyword)
    normalised_answer = _normalise_frequency_units(answer)
    if re.fullmatch(r"\d+(?:\.\d+)? hz", normalised_keyword):
        return bool(
            re.search(
                rf"(?<![\w.]){re.escape(normalised_keyword)}(?![\w.])",
                normalised_answer,
            )
        )
    return normalised_keyword in normalised_answer


def _group_by_type(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row["question_type"])].append(row)
    return groups


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _summarize_group(rows: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(rows)
    expected_answerable = [row for row in rows if row["expected_status"] == "answered"]
    expected_insufficient = [
        row for row in rows if row["expected_status"] == "insufficient_evidence"
    ]
    returned_insufficient = [
        row for row in rows if row["response"]["status"] == "insufficient_evidence"
    ]
    reviews = [row["automatic_review"] for row in rows]
    citation_rows = [citation for review in reviews for citation in review["citation_checks"]]
    fact_signals = [
        signal for review in reviews for signal in review["required_fact_keyword_signals"]
    ]
    latencies = [float(row["response"]["latency"]["total_ms"]) for row in rows]
    return {
        "question_count": count,
        "status_accuracy": _rate(sum(review["status_correct"] for review in reviews), count),
        "answerable_coverage": _rate(
            sum(row["response"]["status"] == "answered" for row in expected_answerable),
            len(expected_answerable),
        ),
        "insufficient_evidence_precision": _rate(
            sum(row["expected_status"] == "insufficient_evidence" for row in returned_insufficient),
            len(returned_insufficient),
        ),
        "insufficient_evidence_recall": _rate(
            sum(
                row["response"]["status"] == "insufficient_evidence"
                for row in expected_insufficient
            ),
            len(expected_insufficient),
        ),
        "required_fact_candidate_coverage": _rate(sum(fact_signals), len(fact_signals)),
        "unsupported_claim_candidate_count": sum(
            len(review["forbidden_claim_candidate_hits"]) for review in reviews
        ),
        "citation_document_page_correctness": _rate(
            sum(citation["document_page_correct"] for citation in citation_rows),
            len(citation_rows),
        ),
        "filter_violation_rate": _rate(
            sum(not review["citation_filter_compliant"] for review in reviews), count
        ),
        "execution_failure_rate": _rate(
            sum(row["response"]["status"] == "execution_failed" for row in rows), count
        ),
        "median_latency_ms": statistics.median(latencies) if latencies else None,
        "usage_missing_rate": _rate(sum(row["usage_state"] == "unknown" for row in rows), count),
    }
