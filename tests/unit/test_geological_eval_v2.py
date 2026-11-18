from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config.settings import Settings
from app.providers.embeddings import BgeM3EmbeddingProvider, HashEmbeddingProvider
from app.schemas.retrieval import RetrievedChunk
from eval.geological_v2 import (
    assert_real_dense_provider,
    filters_for_question,
    load_questions,
    score_results,
    summarise_by_scope,
    validate_split_independence,
)

ROOT = Path(__file__).resolve().parents[2]


def _question(
    *,
    scope: str = "unfiltered",
    answerability: str = "answerable",
    allowed_document_ids: list[str] | None = None,
    gold_sources: list[dict[str, object]] | None = None,
    filter_payload: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "id": "v2-q-1",
        "question": "What is tested?",
        "language": "en",
        "scope": scope,
        "answerability": answerability,
        "allowed_document_ids": allowed_document_ids or [],
        "gold_sources": gold_sources or [],
        "filter": filter_payload or {},
        "reason": "test",
    }


def _chunk(
    chunk_id: str = "c-1",
    *,
    document_id: str = "doc-1",
    page_number: int = 3,
    document_type: str = "paper",
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
            "language": "en",
        },
    )


class _FakeSentenceTransformer:
    device = "cpu"

    def get_sentence_embedding_dimension(self) -> int:
        return 4


def _settings(**overrides: object) -> Settings:
    defaults = {
        "app_env": "development",
        "local_embedding_enabled": True,
        "embedding_dim": 4,
        "local_embedding_model": "BAAI/bge-small-en-v1.5",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def test_v2_question_sets_are_valid_and_have_independent_gold_pages() -> None:
    development = load_questions(ROOT / "evals" / "v2" / "dev_questions.json")
    acceptance = load_questions(ROOT / "evals" / "v2" / "acceptance_questions.json")

    validate_split_independence(development, acceptance)
    assert len(development) == 8
    assert len(acceptance) == 16
    assert (
        sum(q["scope"] == "unfiltered" and q["answerability"] == "answerable" for q in acceptance)
        == 6
    )
    assert (
        sum(
            q["scope"] == "type_filtered" and q["answerability"] == "answerable" for q in acceptance
        )
        == 4
    )
    assert (
        sum(
            q["scope"] == "document_scoped" and q["answerability"] == "answerable"
            for q in acceptance
        )
        == 4
    )


def test_v2_rejects_overlap_and_scope_contract(tmp_path: Path) -> None:
    development = [
        _question(
            allowed_document_ids=["doc-1"],
            gold_sources=[{"document_id": "doc-1", "page_number": 3}],
        )
    ]
    acceptance = [
        _question(
            allowed_document_ids=["doc-1"],
            gold_sources=[{"document_id": "doc-1", "page_number": 3}],
        )
    ]
    with pytest.raises(ValueError, match="overlap"):
        validate_split_independence(development, acceptance)

    invalid = _question(
        scope="type_filtered",
        allowed_document_ids=["doc-1"],
        gold_sources=[{"document_id": "doc-1", "page_number": 3}],
    )
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps([invalid]), encoding="utf-8")
    with pytest.raises(ValueError, match="document_types"):
        load_questions(path)


def test_v2_uses_shared_filter_schema() -> None:
    question = _question(
        scope="type_filtered",
        allowed_document_ids=["doc-1"],
        gold_sources=[{"document_id": "doc-1", "page_number": 3}],
        filter_payload={"document_types": ["paper"]},
    )

    filters = filters_for_question(question)

    assert filters is not None
    assert filters.document_types == ["paper"]


def test_score_results_records_mrr_and_provenance() -> None:
    question = _question(
        allowed_document_ids=["doc-1"],
        gold_sources=[{"document_id": "doc-1", "page_number": 3}],
    )

    scored = score_results(question, [_chunk()], top_k=5)

    assert scored["document_hit"] is True
    assert scored["page_hit"] is True
    assert scored["source_recall"] == 1.0
    assert scored["mrr_at_5"] == 1.0
    assert scored["provenance_validity"] is True
    assert scored["failure_type"] == "none"


def test_filter_violation_and_execution_failure_are_explicit() -> None:
    question = _question(
        scope="type_filtered",
        allowed_document_ids=["doc-1"],
        gold_sources=[{"document_id": "doc-1", "page_number": 3}],
        filter_payload={"document_types": ["report"]},
    )
    filters = filters_for_question(question)

    violation = score_results(question, [_chunk()], top_k=5, filters=filters)
    failed = score_results(question, [], top_k=5, execution_failed=True, filters=filters)

    assert violation["filter_violation"] is True
    assert violation["provenance_validity"] is False
    assert violation["failure_type"] == "filter_violation"
    assert failed["execution_failed"] is True
    assert failed["failure_type"] == "execution_failed"


def test_unanswerable_candidate_is_reported_without_retrieval_failure() -> None:
    question = _question(answerability="unanswerable")

    scored = score_results(question, [_chunk()], top_k=5)

    assert scored["candidate_returned"] is True
    assert scored["document_hit"] is None
    assert scored["mrr_at_5"] is None
    assert scored["failure_type"] == "none"


def test_summary_is_scoped_and_excludes_unanswerable_from_hit_metrics() -> None:
    rows = [
        {
            "scope": "unfiltered",
            "answerability": "answerable",
            "execution_failed": False,
            "document_hit": True,
            "page_hit": True,
            "source_recall": 1.0,
            "mrr_at_5": 1.0,
            "filter_violation": False,
            "provenance_validity": True,
            "candidate_returned": None,
            "failure_type": "none",
        },
        {
            "scope": "unfiltered",
            "answerability": "unanswerable",
            "execution_failed": False,
            "document_hit": None,
            "page_hit": None,
            "source_recall": None,
            "mrr_at_5": None,
            "filter_violation": False,
            "provenance_validity": True,
            "candidate_returned": True,
            "failure_type": "none",
        },
    ]

    summary = summarise_by_scope(rows)

    assert summary["unfiltered"]["page_hit_at_5"] == 1.0
    assert summary["unfiltered"]["page_hit_n"] == 1
    assert summary["unfiltered"]["candidate_returned_rate"] == 1.0
    assert "status_accuracy" not in summary["overall"]
    assert "citation_validity" not in summary["overall"]


def test_real_dense_guard_rejects_hash_and_records_model_runtime() -> None:
    with pytest.raises(RuntimeError, match="hash fallback"):
        assert_real_dense_provider(HashEmbeddingProvider())

    provider = BgeM3EmbeddingProvider(_settings(), model=_FakeSentenceTransformer())
    assert assert_real_dense_provider(provider) is provider
    assert provider.model_id == "BAAI/bge-small-en-v1.5"
    assert provider.device == "cpu"
