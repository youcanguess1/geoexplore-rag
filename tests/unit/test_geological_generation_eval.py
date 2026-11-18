from __future__ import annotations

import copy
from pathlib import Path

import pytest

from app.schemas.geological import CorpusIdentity
from eval.geological_generation import (
    automatic_review,
    load_question_set,
    summarize_rows,
    validate_split_independence,
)
from scripts.run_generation_eval import _select_questions, run

ROOT = Path(__file__).resolve().parents[2]
DEV_PATH = ROOT / "evals" / "generation_dev_questions.json"
ACCEPTANCE_PATH = ROOT / "evals" / "generation_acceptance_questions.json"


def _sets() -> tuple[dict, dict]:
    dev = load_question_set(DEV_PATH, expected_split="dev")
    acceptance = load_question_set(ACCEPTANCE_PATH, expected_split="acceptance")
    return dev, acceptance


def _identity() -> CorpusIdentity:
    return CorpusIdentity.model_validate(_sets()[0]["corpus_identity"])


def test_generation_sets_are_frozen_to_the_current_corpus_and_independent() -> None:
    dev, acceptance = _sets()

    assert len(dev["questions"]) == 6
    assert len(acceptance["questions"]) == 10
    assert dev["corpus_identity"]["chunk_count"] == 1006
    assert acceptance["corpus_identity"] == dev["corpus_identity"]
    validate_split_independence(dev, acceptance)


def test_generation_sets_reject_shared_gold_physical_pages() -> None:
    dev, acceptance = _sets()
    changed = copy.deepcopy(acceptance)
    changed["questions"][0]["gold_physical_pages"] = [2]
    changed["questions"][0]["gold_evidence"] = [
        {"document_id": "geo-fs11503", "physical_page": 2}
    ]

    with pytest.raises(ValueError, match="gold physical pages overlap"):
        validate_split_independence(dev, changed)


def test_automatic_review_marks_context_filter_and_fingerprint_violations() -> None:
    dev, _ = _sets()
    question = dev["questions"][0]
    response = {
        "status": "answered",
        "answer": "Diversions occurred from May through September and repairs occurred from October through April.",
        "citations": [
            {
                "document_id": "geo-of12-1191",
                "title": "Wrong document",
                "chunk_id": "wrong_1",
                "page_number": 17,
                "document_type": "report",
                "language": "en",
                "corpus_fingerprint": "0" * 64,
            }
        ],
        "latency": {"total_ms": 5.0},
    }
    review = automatic_review(
        question=question,
        response=response,
        bounded_context=[
            {
                "chunk_id": "geo-fs11503_4",
                "document_id": "geo-fs11503",
                "physical_page": 2,
            }
        ],
        corpus_identity=_identity(),
    )

    citation = review["citation_checks"][0]
    assert citation["in_bounded_context"] is False
    assert citation["matches_filters"] is False
    assert citation["matches_corpus_fingerprint"] is False
    assert citation["document_page_correct"] is False
    assert review["citation_filter_compliant"] is False


def test_execution_failure_is_not_a_correct_insufficient_evidence_refusal() -> None:
    dev, _ = _sets()
    question = dev["questions"][4]
    response = {
        "status": "execution_failed",
        "answer": "provider failed",
        "citations": [],
        "latency": {"total_ms": 10.0},
    }
    review = automatic_review(
        question=question,
        response=response,
        bounded_context=[],
        corpus_identity=_identity(),
    )
    summary = summarize_rows(
        [
            {
                "question_type": question["question_type"],
                "expected_status": question["expected_status"],
                "usage_state": "unknown",
                "response": response,
                "automatic_review": review,
            }
        ]
    )

    assert review["status_correct"] is False
    assert summary["overall"]["insufficient_evidence_recall"] == 0.0
    assert summary["overall"]["execution_failure_rate"] == 1.0
    assert summary["overall"]["usage_missing_rate"] == 1.0


@pytest.mark.parametrize(
    "answer",
    [
        "The line used 40-Hertz geophones.",
        "The line used 40 Hz geophones.",
        "The line used 40 hErTz geophones.",
        "The line used 40-hZ geophones.",
    ],
)
def test_automatic_review_treats_hz_and_hertz_frequency_forms_as_equivalent(
    answer: str,
) -> None:
    dev, _ = _sets()
    question = copy.deepcopy(dev["questions"][0])
    question["required_fact_keywords"] = [["40-Hz"]]

    review = automatic_review(
        question=question,
        response={"status": "answered", "answer": answer, "citations": []},
        bounded_context=[],
        corpus_identity=_identity(),
    )

    assert review["required_fact_keyword_signals"] == [True]


@pytest.mark.parametrize(
    "answer",
    [
        "The line used 140-Hz geophones.",
        "The line used 40-kHz geophones.",
    ],
)
def test_automatic_review_keeps_frequency_keyword_boundaries(answer: str) -> None:
    dev, _ = _sets()
    question = copy.deepcopy(dev["questions"][0])
    question["required_fact_keywords"] = [["40-Hz"]]

    review = automatic_review(
        question=question,
        response={"status": "answered", "answer": answer, "citations": []},
        bounded_context=[],
        corpus_identity=_identity(),
    )

    assert review["required_fact_keyword_signals"] == [False]


def test_automatic_review_preserves_ordinary_and_multi_group_keyword_matching() -> None:
    dev, _ = _sets()
    question = copy.deepcopy(dev["questions"][0])
    question["required_fact_keywords"] = [["diversions"], ["october", "april"]]

    review = automatic_review(
        question=question,
        response={
            "status": "answered",
            "answer": "Diversions occurred before OCTOBER and continued through April.",
            "citations": [],
        },
        bounded_context=[],
        corpus_identity=_identity(),
    )

    assert review["required_fact_keyword_signals"] == [True, True]


@pytest.mark.asyncio
async def test_acceptance_execution_requires_explicit_opt_in(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="acceptance execution requires --allow-acceptance"):
        await run(
            split="acceptance",
            output=tmp_path / "must-not-exist.json",
        )


def test_single_question_selection_rejects_unknown_id_without_runtime_setup() -> None:
    dev, _ = _sets()

    selected = _select_questions(dev, "geo-gen-dev-001")
    assert [question["question_id"] for question in selected] == ["geo-gen-dev-001"]

    with pytest.raises(ValueError, match="question is not in the selected split"):
        _select_questions(dev, "geo-gen-dev-unknown")
