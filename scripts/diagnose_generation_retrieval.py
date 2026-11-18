"""Inspect frozen generation-question evidence without calling a model."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.agents.geological import _bounded_chunks
from app.config.settings import Settings
from app.retrieval.filters import matches_retrieval_filters
from app.retrieval.ingest import ingest_bm25
from app.schemas.retrieval import RetrievalFilters
from eval.geological_generation import canonical_sha256, load_question_set, question_filters

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = ROOT / "evals" / "generation_dev_questions.json"
DEFAULT_OUTPUT = ROOT / "evals" / "results" / "2026-10-22-generation-dev-retrieval-baseline.json"


def _page(chunk: Any) -> int | None:
    value = chunk.metadata.get("page_number", "")
    return int(value) if value else None


def _chunk_row(chunk: Any) -> dict[str, object]:
    return {
        "chunk_id": chunk.chunk_id,
        "document_id": chunk.document_id,
        "chunk_index": chunk.chunk_index,
        "physical_page": _page(chunk),
        "score": round(chunk.score, 6),
        "rank": chunk.rank,
        "content_length": len(chunk.content),
    }


def _context_row(
    chunk: Any, *, position: int, filters: RetrievalFilters | None, excerpt_chars: int
) -> dict[str, object]:
    excerpt = chunk.content[:excerpt_chars]
    row = _chunk_row(chunk)
    row.update(
        {
            "context_position": position,
            "excerpt_chars": len(excerpt),
            "excerpt_truncated": len(chunk.content) > excerpt_chars,
            "excerpt": excerpt,
            "matches_filters": matches_retrieval_filters(chunk, filters),
        }
    )
    return row


def _keyword_signals(
    chunks: list[Any],
    *,
    keyword_groups: list[list[str]],
    excerpt_chars: int | None = None,
) -> list[dict[str, object]]:
    signals: list[dict[str, object]] = []
    for chunk in chunks:
        text = chunk.content if excerpt_chars is None else chunk.content[:excerpt_chars]
        lowered = text.lower()
        signals.append(
            {
                "chunk_id": chunk.chunk_id,
                "keyword_groups_present": [
                    all(keyword.lower() in lowered for keyword in group) for group in keyword_groups
                ],
            }
        )
    return signals


def _aggregate_keyword_coverage(signals: list[dict[str, object]], group_count: int) -> list[bool]:
    return [
        any(row["keyword_groups_present"][index] for row in signals) for index in range(group_count)
    ]


def _git_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def _resolve_questions_path(path: str | Path) -> Path:
    source = Path(path)
    return source if source.is_absolute() else ROOT / source


def _load_dataset(path: str | Path) -> tuple[dict[str, Any], Path, dict[str, object]]:
    source = _resolve_questions_path(path)
    raw = source.read_bytes()
    dataset = load_question_set(source, expected_split="dev")
    provenance = {
        "path": str(source.relative_to(ROOT)),
        "question_count": len(dataset["questions"]),
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "canonical_sha256": canonical_sha256(dataset),
    }
    return dataset, source, provenance


def _diagnose_question(
    question: dict[str, Any], *, bm25: Any, chunks: list[Any], settings: Settings
) -> dict[str, object]:
    filters: RetrievalFilters | None = question_filters(question)
    ranked = bm25.search(question["question"], top_k=len(chunks), filters=filters)
    returned = bm25.search(question["question"], top_k=settings.geological_top_k, filters=filters)
    returned = bm25.expand_overlapping_predecessors(
        returned, limit=settings.geological_top_k, filters=filters
    )
    bounded = _bounded_chunks(
        {"retrieved_chunks": returned, "retrieval_filters": filters}, settings
    )
    gold_pages = set(question["gold_physical_pages"])
    gold_chunk_ids = set(question.get("gold_chunk_ids", []))
    gold_page_chunks = [
        chunk
        for chunk in chunks
        if chunk.document_id in question["gold_document_ids"]
        and _page(chunk) in gold_pages
        and (not gold_chunk_ids or chunk.chunk_id in gold_chunk_ids)
    ]
    keyword_groups = question["required_fact_keywords"]
    bounded_signals = _keyword_signals(
        bounded,
        keyword_groups=keyword_groups,
        excerpt_chars=settings.geological_context_chars,
    )
    gold_signals = _keyword_signals(gold_page_chunks, keyword_groups=keyword_groups)
    gold_pairs = {
        (evidence["document_id"], evidence["physical_page"])
        for evidence in question["gold_evidence"]
    }
    return {
        "question_id": question["question_id"],
        "question_type": question["question_type"],
        "expected_status": question["expected_status"],
        "model_called": False,
        "filters": question["filters"],
        "manual_evidence_note": question["manual_evidence_note"],
        "gold_chunk_ids": sorted(gold_chunk_ids),
        "filtered_candidate_count": len(ranked),
        "gold_page_chunks": [_chunk_row(chunk) for chunk in gold_page_chunks],
        "gold_page_ranked_candidates": [
            _chunk_row(chunk) for chunk in ranked if _page(chunk) in gold_pages
        ],
        "top_20_filtered_candidates": [_chunk_row(chunk) for chunk in ranked[:20]],
        "gold_page_keyword_signals": gold_signals,
        "top_k_after_predecessor_expansion": [_chunk_row(chunk) for chunk in returned],
        "bounded_context": [
            _context_row(
                chunk,
                position=position,
                filters=filters,
                excerpt_chars=settings.geological_context_chars,
            )
            for position, chunk in enumerate(bounded, start=1)
        ],
        "gold_chunk_ranked_candidates": [
            _chunk_row(chunk) for chunk in ranked if chunk.chunk_id in gold_chunk_ids
        ],
        "gold_chunk_in_top_k_seeds": any(
            chunk.chunk_id in gold_chunk_ids
            for chunk in bm25.search(
                question["question"], top_k=settings.geological_top_k, filters=filters
            )
        ),
        "gold_chunk_in_expanded_candidates": any(
            chunk.chunk_id in gold_chunk_ids for chunk in returned
        ),
        "gold_chunk_in_bounded_context": any(chunk.chunk_id in gold_chunk_ids for chunk in bounded),
        "gold_evidence_in_filtered_candidates": any(
            (chunk.document_id, _page(chunk)) in gold_pairs for chunk in ranked
        ),
        "gold_evidence_in_production_top_k": any(
            (chunk.document_id, _page(chunk)) in gold_pairs for chunk in returned
        ),
        "gold_evidence_in_bounded_context": any(
            (chunk.document_id, _page(chunk)) in gold_pairs for chunk in bounded
        ),
        "bounded_excerpt_keyword_signals": bounded_signals,
        "bounded_required_fact_coverage": _aggregate_keyword_coverage(
            bounded_signals, len(keyword_groups)
        ),
        "all_top_k_chunks_match_filters": all(
            matches_retrieval_filters(chunk, filters) for chunk in returned
        ),
        "all_bounded_chunks_match_filters": all(
            matches_retrieval_filters(chunk, filters) for chunk in bounded
        ),
    }


async def run(question_id: str, *, questions_path: str | Path = QUESTIONS) -> dict[str, object]:
    """Retain the focused single-question diagnostic for local investigation."""
    dataset, _, _ = _load_dataset(questions_path)
    question = next(
        (item for item in dataset["questions"] if item["question_id"] == question_id), None
    )
    if question is None:
        raise ValueError(f"unknown dev question: {question_id}")
    settings = Settings()
    bm25, chunks = await ingest_bm25(
        settings.geological_knowledge_dir,
        settings=settings,
        manifest_path=settings.geological_manifest_path,
    )
    return _diagnose_question(question, bm25=bm25, chunks=chunks, settings=settings)


async def run_all(*, questions_path: str | Path = QUESTIONS) -> dict[str, object]:
    """Audit every frozen dev question using production BM25 without an LLM call."""
    dataset, _, dataset_provenance = _load_dataset(questions_path)
    settings = Settings()
    bm25, chunks = await ingest_bm25(
        settings.geological_knowledge_dir,
        settings=settings,
        manifest_path=settings.geological_manifest_path,
    )
    identity = bm25.corpus_identity
    if identity is None:
        raise RuntimeError("BM25 ingest did not return corpus identity")
    if identity.model_dump(mode="json") != dataset["corpus_identity"]:
        raise RuntimeError("runtime corpus identity does not match frozen dev question set")
    return {
        "protocol": "geoexplore-generation-retrieval-diagnostic-v1",
        "run_started_at": datetime.now(UTC).isoformat(),
        "evaluation_code_commit": _git_commit(),
        "dataset": dataset_provenance,
        "corpus_identity": identity.model_dump(mode="json"),
        "runtime": {
            "retrieval_backend": "bm25",
            "geological_top_k": settings.geological_top_k,
            "geological_context_chunks": settings.geological_context_chunks,
            "geological_context_chars": settings.geological_context_chars,
        },
        "model_called": False,
        "executed_question_ids": [item["question_id"] for item in dataset["questions"]],
        "rows": [
            _diagnose_question(question, bm25=bm25, chunks=chunks, settings=settings)
            for question in dataset["questions"]
        ],
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question-id")
    parser.add_argument("--all-dev", action="store_true")
    parser.add_argument("--questions", type=Path, default=QUESTIONS)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    if args.question_id and args.all_dev:
        raise SystemExit("use either --question-id or --all-dev")
    if not args.question_id and not args.all_dev:
        raise SystemExit("provide --question-id or --all-dev")
    payload = asyncio.run(
        run(args.question_id, questions_path=args.questions)
        if args.question_id
        else run_all(questions_path=args.questions)
    )
    if args.output:
        output = args.output if args.output.is_absolute() else ROOT / args.output
        if output.exists():
            raise SystemExit(f"refusing to overwrite existing output: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        print(f"wrote {output.relative_to(ROOT)}")
    else:
        print(json.dumps(payload, indent=2, ensure_ascii=True))
