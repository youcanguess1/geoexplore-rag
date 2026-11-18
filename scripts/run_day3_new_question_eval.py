"""Run a frozen Day 3 same-corpus evaluation through the production services."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from app.core.ids import new_trace_id
from app.retrieval.filters import matches_retrieval_filters
from app.schemas.chat import ChatRequest
from app.schemas.retrieval import RetrievedChunk
from app.services.chat_service import ChatService
from app.services.container import build_container
from eval.geological_generation import canonical_sha256, load_question_set, question_filters
from run_generation_eval import (
    InstrumentedLLM,
    _physical_page,
    _response_payload,
    _runtime_settings,
    _usage_state,
)

ROOT = Path(__file__).resolve().parents[1]


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _chunk(chunk: RetrievedChunk) -> dict[str, Any]:
    return {
        "chunk_id": chunk.chunk_id,
        "document_id": chunk.document_id,
        "physical_page": _physical_page(chunk),
        "chunk_index": chunk.chunk_index,
        "score": chunk.score,
        "rank": chunk.rank,
        "source": chunk.source,
        "content_chars": len(chunk.content),
        "document_type": chunk.metadata.get("document_type", ""),
        "language": chunk.metadata.get("language", ""),
    }


class CapturingRetriever:
    """Observe the production retriever without changing its search semantics."""

    def __init__(self, retriever: Any, context_chunks: int) -> None:
        self._retriever = retriever
        self.backend = getattr(retriever, "backend", "unknown")
        self.corpus_identity = getattr(retriever, "corpus_identity", None)
        self.context_chunks = context_chunks
        self.seeds: list[RetrievedChunk] = []
        self.expanded: list[RetrievedChunk] = []

    def begin_question(self) -> None:
        self.seeds = []
        self.expanded = []

    async def retrieve(self, query: str, *, top_k: int, filters=None) -> list[RetrievedChunk]:
        # Calls the current production BM25Retriever and AsyncBM25Retriever objects.
        self.seeds = self._retriever._bm25.search(query, top_k=top_k, filters=filters)
        self.expanded = await self._retriever.retrieve(query, top_k=top_k, filters=filters)
        return self.expanded

    def bounded(self) -> list[RetrievedChunk]:
        chunks = list(self.expanded[: self.context_chunks])
        order: dict[str, int] = {}
        for chunk in chunks:
            order.setdefault(chunk.document_id, len(order))
        return sorted(chunks, key=lambda chunk: (order[chunk.document_id], chunk.chunk_index))


def _retrieval_audit(question: dict[str, Any], retriever: CapturingRetriever) -> dict[str, Any]:
    filters = question_filters(question)
    corpus = list(retriever._retriever._bm25._chunks)
    filtered = [chunk for chunk in corpus if matches_retrieval_filters(chunk, filters)]
    full = retriever._retriever._bm25.search(question["question"], top_k=len(filtered), filters=filters)
    ranks = {chunk.chunk_id: chunk.rank for chunk in full}
    bounded = retriever.bounded()
    seed_ids = {chunk.chunk_id for chunk in retriever.seeds}
    expanded_ids = {chunk.chunk_id for chunk in retriever.expanded}
    bounded_ids = {chunk.chunk_id for chunk in bounded}
    gold_ids = list(question.get("gold_chunk_ids", []))
    return {
        "filtered_corpus_chunk_count": len(filtered),
        "gold_evidence_in_filtered_corpus": {
            chunk_id: any(chunk.chunk_id == chunk_id for chunk in filtered) for chunk_id in gold_ids
        },
        "gold_full_filtered_rank": {chunk_id: ranks.get(chunk_id) for chunk_id in gold_ids},
        "seed_chunks": [_chunk(chunk) for chunk in retriever.seeds],
        "expanded_chunks": [_chunk(chunk) for chunk in retriever.expanded],
        "final_bounded_context": [_chunk(chunk) for chunk in bounded],
        "gold_in_top_k_seed": {chunk_id: chunk_id in seed_ids for chunk_id in gold_ids},
        "gold_in_expanded_candidates": {chunk_id: chunk_id in expanded_ids for chunk_id in gold_ids},
        "gold_in_final_bounded_context": {chunk_id: chunk_id in bounded_ids for chunk_id in gold_ids},
        "final_context_supports_all_preannotated_gold_chunks": bool(gold_ids)
        and all(chunk_id in bounded_ids for chunk_id in gold_ids),
        "filter_compliant": all(matches_retrieval_filters(chunk, filters) for chunk in bounded),
        "context_chunk_count": len(bounded),
        "context_chunk_limit": retriever.context_chunks,
        "per_chunk_character_cap": 900,
        "context_chars": {chunk.chunk_id: min(900, len(chunk.content)) for chunk in bounded},
        "truncated": {chunk.chunk_id: len(chunk.content) > 900 for chunk in bounded},
    }


def _manifest(dataset: dict[str, Any], question_path: Path, settings: Any) -> dict[str, Any]:
    historic = [
        "evals/results/2026-10-22-generation-acceptance-first-run.json",
        "evals/results/2026-10-22-generation-acceptance-after-egress-fix.json",
    ]
    return {
        "protocol": "day3-new-question-check-v1",
        "frozen_question_path": str(question_path.relative_to(ROOT)),
        "frozen_at": dataset.get("frozen_at"),
        "question_set_canonical_sha256": canonical_sha256(dataset),
        "question_file_sha256": _sha256(question_path),
        "corpus_identity": dataset["corpus_identity"],
        "runtime": {
            "retrieval_backend": "bm25",
            "geological_top_k": settings.geological_top_k,
            "geological_context_chunks": settings.geological_context_chunks,
            "geological_context_chars": settings.geological_context_chars,
            "model": settings.deepseek_model,
            "temperature": 0.0,
            "llm_max_retries": settings.llm_max_retries,
            "llm_retry_semantics": "max_attempts=1",
            "repair_policy": "production JSON validation may issue at most one repair call",
            "database_url": "sqlite+aiosqlite:///:memory:",
            "redis_url": "disabled",
        },
        "pre_run": {
            "recorded_at": datetime.now(UTC).isoformat(),
            "head": _git("rev-parse", "HEAD").strip(),
            "git_status_short": _git("status", "--short").splitlines(),
            "git_diff_check": _git("diff", "--check").splitlines(),
            "tracked_diff_sha256": hashlib.sha256(_git("diff").encode()).hexdigest(),
        },
        "historic_artifact_sha256": {item: _sha256(ROOT / item) for item in historic},
    }


async def _build(dataset: dict[str, Any]) -> tuple[Any, CapturingRetriever, Any]:
    settings = _runtime_settings()
    container = await build_container(settings)
    identity = container.retriever.corpus_identity
    if identity is None or identity.model_dump(mode="json") != dataset["corpus_identity"]:
        await container.aclose()
        raise RuntimeError("runtime corpus identity does not match frozen questions")
    return container, CapturingRetriever(container.retriever, settings.geological_context_chunks), settings


async def retrieval(dataset: dict[str, Any], output_dir: Path) -> None:
    container, retriever, settings = await _build(dataset)
    try:
        rows: list[dict[str, Any]] = []
        for question in dataset["questions"]:
            retriever.begin_question()
            await retriever.retrieve(question["question"], top_k=settings.geological_top_k, filters=question_filters(question))
            rows.append({
                "question_id": question["question_id"],
                "question": question["question"],
                "expected_status": question["expected_status"],
                "filters": question["filters"],
                "retrieval": _retrieval_audit(question, retriever),
            })
        (output_dir / "retrieval-results.json").write_text(json.dumps({
            "protocol": "day3-new-question-check-v1",
            "phase": "retrieval_preflight",
            "question_set_canonical_sha256": canonical_sha256(dataset),
            "corpus_identity": dataset["corpus_identity"],
            "rows": rows,
        }, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    finally:
        await container.aclose()


async def generation(dataset: dict[str, Any], output_dir: Path) -> None:
    retrieval_path = output_dir / "retrieval-results.json"
    if not retrieval_path.exists():
        raise RuntimeError("run retrieval first")
    if json.loads(retrieval_path.read_text(encoding="utf-8")).get("question_set_canonical_sha256") != canonical_sha256(dataset):
        raise RuntimeError("retrieval result does not match frozen question set")
    container, retriever, settings = await _build(dataset)
    if not settings.llm_configured:
        await container.aclose()
        raise RuntimeError("DeepSeek is not configured")
    try:
        llm = InstrumentedLLM(container.llm, max_retries=settings.llm_max_retries)
        service = ChatService(
            settings=settings, llm=llm, retriever=retriever,
            session_factory=container.session_factory,
            rate_limiter=container.chat_service._rate_limiter,
            registry=container.chat_service.registry,
        )
        rows: list[dict[str, Any]] = []
        systemic_failure = False
        for question in dataset["questions"]:
            if systemic_failure:
                rows.append({"question_id": question["question_id"], "execution": "not_executed_after_systemic_error"})
                continue
            llm.begin_question()
            retriever.begin_question()
            trace_id = new_trace_id()
            response = await service.chat(ChatRequest(
                message=question["question"], user_id="day3_new_question_check",
                filters=question_filters(question),
            ), trace_id=trace_id)
            events = list(llm.events)
            rows.append({
                "question_id": question["question_id"], "question": question["question"],
                "expected_status": question["expected_status"], "filters": question["filters"],
                "trace_id": trace_id, "response": _response_payload(response),
                "llm_call_events": events, "usage_state": _usage_state(events),
                "retrieval": _retrieval_audit(question, retriever),
            })
            systemic_failure = response.status == "execution_failed" and any(event.get("status") == "error" for event in events)
        (output_dir / "generation-results.json").write_text(json.dumps({
            "protocol": "day3-new-question-check-v1", "phase": "generation",
            "run_started_at": datetime.now(UTC).isoformat(),
            "question_set_canonical_sha256": canonical_sha256(dataset),
            "corpus_identity": dataset["corpus_identity"],
            "runtime": {"model": settings.deepseek_model, "temperature": 0.0, "llm_max_retries": settings.llm_max_retries},
            "rows": rows,
        }, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    finally:
        await container.aclose()


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("retrieval", "generation"), required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output_dir = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    question_path = output_dir / "questions.json"
    dataset = load_question_set(question_path, expected_split="dev")
    settings = _runtime_settings()
    if args.phase == "retrieval":
        if (output_dir / "run-manifest.json").exists() or (output_dir / "retrieval-results.json").exists():
            raise RuntimeError("refusing to overwrite existing retrieval artifacts")
        (output_dir / "run-manifest.json").write_text(json.dumps(
            _manifest(dataset, question_path, settings), indent=2, ensure_ascii=True
        ) + "\n", encoding="utf-8")
        await retrieval(dataset, output_dir)
    elif (output_dir / "generation-results.json").exists():
        raise RuntimeError("refusing to overwrite generation results")
    else:
        await generation(dataset, output_dir)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(f"Day 3 evaluator failed: {exc}", file=sys.stderr)
        raise
