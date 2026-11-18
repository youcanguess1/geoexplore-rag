"""Unit tests for offline evaluation metric arithmetic."""

from eval.metrics import (
    accuracy,
    classification_report,
    hit_at_k,
    mrr,
    percentile,
    precision_at_k,
    recall_at_k,
)


def test_accuracy_empty_pairs_is_zero() -> None:
    assert accuracy([]) == 0.0


def test_accuracy_all_correct() -> None:
    assert accuracy([("answer", "answer"), ("refusal", "refusal")]) == 1.0


def test_accuracy_partial() -> None:
    assert accuracy([("answer", "answer"), ("refusal", "unsupported")]) == 0.5


# --- precision@k ------------------------------------------------------------


def test_precision_at_k_empty_retrieval() -> None:
    assert precision_at_k({"a"}, [], 3) == 0.0


def test_precision_at_k_counts_only_top_k() -> None:
    # top-3 = a, b, c -> 2 of 3 are relevant
    assert precision_at_k({"a", "c"}, ["a", "b", "c", "d"], 3) == 2 / 3


def test_precision_at_k_when_k_exceeds_length() -> None:
    assert precision_at_k({"a", "b"}, ["a", "b"], 10) == 1.0


# --- recall@k ---------------------------------------------------------------


def test_recall_at_k_without_relevant_set() -> None:
    assert recall_at_k(set(), ["a"], 1) == 0.0


def test_recall_at_k_only_scans_top_k() -> None:
    # relevant "b" sits at rank 3, so k=2 must miss it
    assert recall_at_k({"b"}, ["a", "x", "b"], 2) == 0.0
    assert recall_at_k({"b"}, ["a", "x", "b"], 3) == 1.0


# --- hit@k ------------------------------------------------------------------


def test_hit_at_k_true_on_any_overlap() -> None:
    assert hit_at_k({"z"}, ["a", "z"], 2) == 1.0


def test_hit_at_k_false_outside_window() -> None:
    assert hit_at_k({"z"}, ["a", "z"], 1) == 0.0


# --- MRR --------------------------------------------------------------------


def test_mrr_first_position() -> None:
    assert mrr({"a"}, ["a", "b"]) == 1.0


def test_mrr_second_position() -> None:
    assert mrr({"b"}, ["a", "b"]) == 0.5


def test_mrr_without_hit() -> None:
    assert mrr({"z"}, ["a", "b"]) == 0.0


# --- percentile -------------------------------------------------------------


def test_percentile_empty_is_zero() -> None:
    assert percentile([], 95) == 0.0


def test_percentile_single_value() -> None:
    assert percentile([42.0], 50) == 42.0


def test_percentile_endpoints_are_min_and_max() -> None:
    values = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert percentile(values, 0) == 10.0
    assert percentile(values, 100) == 50.0


def test_percentile_picks_nearest_index() -> None:
    values = [1.0, 2.0, 3.0, 4.0]
    # round(0.5 * 3) == 2 under banker's rounding -> ordered[2]
    assert percentile(values, 50) == 3.0


# --- classification_report --------------------------------------------------


def test_classification_report_groups_by_gold_label() -> None:
    report = classification_report(
        [("answer", "answer"), ("answer", "unsupported"), ("refusal", "refusal")]
    )
    assert report == {"answer": 0.5, "refusal": 1.0}


def test_classification_report_empty() -> None:
    assert classification_report([]) == {}
