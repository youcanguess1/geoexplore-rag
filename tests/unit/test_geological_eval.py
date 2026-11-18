from __future__ import annotations

import json

import pytest

from app.schemas.retrieval import RetrievalFilters, RetrievedChunk
from eval.geological import (
    classify_failure,
    filters_for_question,
    load_questions,
    score_results,
    summarise,
)


def _question(
    *,
    answerability: str = "answerable",
    allowed_document_ids: list[str] | None = None,
    gold_sources: list[dict[str, object]] | None = None,
    filter_payload: dict[str, object] | None = None,
    required_chunk_ids: list[str] | None = None,
) -> dict[str, object]:
    return {
        "id": "q-1",
        "question": "What is tested?",
        "language": "en",
        "answerability": answerability,
        "expected_status": "evidence_only"
        if answerability == "answerable"
        else "insufficient_evidence",
        "allowed_document_ids": allowed_document_ids or [],
        "gold_sources": gold_sources or [],
        "filter": filter_payload or {},
        "required_chunk_ids": required_chunk_ids or [],
        "reason": "test",
    }


def _chunk(
    chunk_id: str = "c-1",
    *,
    document_id: str = "doc-1",
    page_number: int = 3,
    document_type: str = "paper",
    language: str = "en",
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=document_id,
        title="title",
        content="content",
        score=1.0,
        rank=1,
        metadata={
            "source_file": "source.pdf",
            "page_number": str(page_number),
            "sha256": "a" * 64,
            "data_type": "02_Academic",
            "document_type": document_type,
            "language": language,
        },
    )


def test_load_questions_validates_shape_and_unique_ids(tmp_path) -> None:
    path = tmp_path / "questions.json"
    path.write_text(json.dumps([_question()]), encoding="utf-8")

    loaded = load_questions(path)

    assert loaded[0]["id"] == "q-1"
    with pytest.raises(ValueError, match="unique"):
        path.write_text(json.dumps([_question(), _question()]), encoding="utf-8")
        load_questions(path)


def test_filters_for_question_uses_shared_filter_schema() -> None:
    question = _question(filter_payload={"document_types": ["paper"], "languages": ["EN"]})

    filters = filters_for_question(question)

    assert filters == RetrievalFilters(document_types=["paper"], languages=["en"])
    assert filters_for_question(_question()) is None


def test_score_results_records_document_page_and_source_recall() -> None:
    question = _question(
        allowed_document_ids=["doc-1"],
        gold_sources=[{"document_id": "doc-1", "page_number": 3}],
    )

    scored = score_results(question, [_chunk()], top_k=5)

    assert scored["document_hit"] is True
    assert scored["page_hit"] is True
    assert scored["source_recall"] == 1.0
    assert scored["citation_validity"] is True
    assert scored["failure_type"] == "none"


def test_page_hit_can_still_fail_required_evidence_coverage() -> None:
    question = _question(
        allowed_document_ids=["doc-1"],
        gold_sources=[{"document_id": "doc-1", "page_number": 3}],
        required_chunk_ids=["c-10", "c-11"],
    )

    partial = score_results(question, [_chunk("c-11")], top_k=5)
    complete = score_results(question, [_chunk("c-11"), _chunk("c-10")], top_k=5)

    assert partial["page_hit"] is True
    assert partial["evidence_coverage"] == 0.5
    assert partial["failure_type"] == "incomplete_evidence"
    assert complete["evidence_coverage"] == 1.0
    assert complete["failure_type"] == "none"


def test_filter_violation_is_reported() -> None:
    question = _question(
        allowed_document_ids=["doc-1"],
        gold_sources=[{"document_id": "doc-1", "page_number": 3}],
    )
    filters = RetrievalFilters(document_types=["report"])

    scored = score_results(question, [_chunk()], top_k=5, filters=filters)

    assert scored["filter_violation"] is True
    assert scored["citation_validity"] is False
    assert scored["failure_type"] == "filter_violation"


def test_execution_failed_is_not_correct_insufficient_evidence() -> None:
    question = _question(answerability="unanswerable")

    scored = score_results(question, [], top_k=5, execution_failed=True)

    assert scored["retrieval_status"] == "execution_failed"
    assert scored["failure_type"] == "execution_failed"


def test_empty_result_is_insufficient_evidence() -> None:
    question = _question(answerability="unanswerable")

    scored = score_results(question, [], top_k=5)

    assert scored["retrieval_status"] == "insufficient_evidence"
    assert scored["failure_type"] == "none"


def test_unanswerable_question_with_results_is_misclassified() -> None:
    question = _question(answerability="unanswerable")

    assert classify_failure(question, [_chunk()]) == "insufficient_evidence_misclassified"
    assert score_results(question, [_chunk()], top_k=5)["failure_type"] == (
        "insufficient_evidence_misclassified"
    )


def test_summarise_keeps_answerable_denominator_and_failure_counts() -> None:
    rows = [
        {
            "answerability": "answerable",
            "document_hit": True,
            "page_hit": False,
            "source_recall": 0.5,
            "filter_violation": False,
            "citation_validity": True,
            "retrieval_status": "evidence_only",
            "expected_status": "evidence_only",
            "failure_type": "wrong_page",
        },
        {
            "answerability": "unanswerable",
            "document_hit": None,
            "page_hit": None,
            "source_recall": None,
            "filter_violation": False,
            "citation_validity": None,
            "retrieval_status": "insufficient_evidence",
            "expected_status": "insufficient_evidence",
            "failure_type": "none",
        },
        {
            "answerability": "answerable",
            "document_hit": None,
            "page_hit": None,
            "source_recall": None,
            "filter_violation": False,
            "citation_validity": None,
            "retrieval_status": "execution_failed",
            "expected_status": "evidence_only",
            "failure_type": "execution_failed",
        },
    ]

    summary = summarise(rows)

    assert summary["n"] == 3
    assert summary["answerable_n"] == 2
    assert summary["document_hit_at_5"] == 1.0
    assert summary["document_hit_n"] == 1
    assert summary["filter_violation_rate"] == 0.0
    assert summary["status_accuracy"] == 1.0
    assert summary["status_accuracy_n"] == 2
    assert summary["failure_counts"] == {"execution_failed": 1, "wrong_page": 1}
