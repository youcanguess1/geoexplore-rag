"""Run the frozen GeoExplore generation evaluation against the production BM25 path."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config.settings import Settings
from app.core.exceptions import LLMProviderError
from app.core.ids import new_id, new_trace_id
from app.providers.base import LLMProvider, LLMResponse
from app.retrieval.base import Retriever
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.retrieval import RetrievalFilters, RetrievedChunk
from app.services.chat_service import ChatService
from app.services.container import build_container
from eval.geological_generation import (
    automatic_review,
    canonical_sha256,
    load_question_set,
    question_filters,
    summarize_rows,
    validate_split_independence,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "evals" / "results" / "2026-10-21-generation-dev.json"
QUESTION_PATHS = {
    "dev": ROOT / "evals" / "generation_dev_questions.json",
    "acceptance": ROOT / "evals" / "generation_acceptance_questions.json",
}


class InstrumentedLLM:
    """Capture call-level audit data without retaining prompts or credentials."""

    def __init__(self, provider: LLMProvider, *, max_retries: int) -> None:
        self._provider = provider
        self.backend = getattr(provider, "backend", provider.__class__.__name__.lower())
        self._max_retries = max_retries
        self.events: list[dict[str, Any]] = []

    def begin_question(self) -> None:
        self.events = []

    async def ping(self) -> bool:
        return await self._provider.ping()

    async def generate(self, messages: list[dict[str, str]], **kwargs: Any) -> LLMResponse:
        event_index = len(self.events) + 1
        phase = "primary" if event_index == 1 else "repair"
        attempt_id = new_id("llm_")
        started = time.perf_counter()
        event: dict[str, Any] = {
            "attempt_id": attempt_id,
            "phase": phase,
            "model": getattr(getattr(self._provider, "_settings", None), "deepseek_model", ""),
            "provider_retry_limit": self._max_retries,
            "provider_retry_attempts_observed": 0,
        }
        try:
            response = await self._provider.generate(messages, **kwargs)
        except LLMProviderError as exc:
            event.update(
                {
                    "status": "error",
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                    "error_category": exc.error_code.value,
                    "error_diagnostics": exc.diagnostics,
                    "usage_state": "unknown",
                }
            )
            self.events.append(event)
            raise
        event.update(
            {
                "status": "success",
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                "model": response.model,
                "usage_state": "known" if response.usage.usage_known else "unknown",
                "usage": response.usage.model_dump(mode="json"),
            }
        )
        self.events.append(event)
        return response


class InstrumentedRetriever:
    """Record the exact bounded-context candidates passed into the graph."""

    def __init__(self, retriever: Retriever, *, context_chunks: int) -> None:
        self._retriever = retriever
        self.backend = getattr(retriever, "backend", "unknown")
        self.corpus_identity = getattr(retriever, "corpus_identity", None)
        self._context_chunks = context_chunks
        self.returned_chunks: list[RetrievedChunk] = []

    def begin_question(self) -> None:
        self.returned_chunks = []

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int,
        filters: RetrievalFilters | None = None,
    ) -> list[RetrievedChunk]:
        chunks = await self._retriever.retrieve(query, top_k=top_k, filters=filters)
        self.returned_chunks = list(chunks)
        return chunks

    def bounded_context(self) -> list[dict[str, Any]]:
        chunks = list(self.returned_chunks[: self._context_chunks])
        document_order: dict[str, int] = {}
        for chunk in chunks:
            document_order.setdefault(chunk.document_id, len(document_order))
        chunks.sort(key=lambda chunk: (document_order[chunk.document_id], chunk.chunk_index))
        return [
            {
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "physical_page": _physical_page(chunk),
                "document_type": chunk.metadata.get("document_type", ""),
                "language": chunk.metadata.get("language", ""),
                "corpus_fingerprint": chunk.metadata.get("corpus_fingerprint", ""),
            }
            for chunk in chunks
        ]


def _physical_page(chunk: RetrievedChunk) -> int | None:
    value = chunk.metadata.get("page_number")
    try:
        return int(value) if value else None
    except ValueError:
        return None


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _runtime_settings() -> Settings:
    settings = Settings()
    return settings.model_copy(
        update={
            "app_env": "development",
            "database_url": "sqlite+aiosqlite:///:memory:",
            "redis_url": "",
            "llm_max_retries": 1,
        }
    )


def _response_payload(response: ChatResponse) -> dict[str, Any]:
    return {
        "status": response.status,
        "answer": response.answer,
        "citations": [citation.model_dump(mode="json") for citation in response.citations],
        "error_code": response.error_code,
        "generation_backend": response.generation_backend,
        "retrieval_backend": response.retrieval_backend,
        "token_usage": response.token_usage.model_dump(mode="json"),
        "latency": response.latency.model_dump(mode="json"),
    }


def _usage_state(events: list[dict[str, Any]]) -> str:
    if not events:
        return "not_applicable"
    return "known" if all(event["usage_state"] == "known" for event in events) else "unknown"


def _select_questions(dataset: dict[str, Any], question_id: str | None) -> list[dict[str, Any]]:
    questions = list(dataset["questions"])
    if question_id is None:
        return questions
    selected = [question for question in questions if question["question_id"] == question_id]
    if not selected:
        raise ValueError(f"question is not in the selected split: {question_id}")
    return selected


async def run(
    *,
    split: str,
    output: Path,
    allow_acceptance: bool = False,
    question_id: str | None = None,
) -> dict[str, Any]:
    if split == "acceptance" and not allow_acceptance:
        raise ValueError("acceptance execution requires --allow-acceptance")
    if split not in QUESTION_PATHS:
        raise ValueError(f"unknown split: {split}")

    dev = load_question_set(QUESTION_PATHS["dev"], expected_split="dev")
    acceptance = load_question_set(QUESTION_PATHS["acceptance"], expected_split="acceptance")
    validate_split_independence(dev, acceptance)
    dataset = dev if split == "dev" else acceptance
    questions = _select_questions(dataset, question_id)
    settings = _runtime_settings()
    if not settings.llm_configured:
        raise RuntimeError("DeepSeek must be configured for real generation evaluation")

    container = await build_container(settings)
    try:
        identity = getattr(container.retriever, "corpus_identity", None)
        expected_identity = dataset["corpus_identity"]
        if identity is None or identity.model_dump(mode="json") != expected_identity:
            raise RuntimeError("runtime corpus identity does not match frozen generation set")

        llm = InstrumentedLLM(container.llm, max_retries=settings.llm_max_retries)
        retriever = InstrumentedRetriever(
            container.retriever,
            context_chunks=settings.geological_context_chunks,
        )
        service = ChatService(
            settings=settings,
            llm=llm,  # type: ignore[arg-type]
            retriever=retriever,  # type: ignore[arg-type]
            session_factory=container.session_factory,
            rate_limiter=container.chat_service._rate_limiter,
            registry=container.chat_service.registry,
        )
        rows: list[dict[str, Any]] = []
        for question in questions:
            llm.begin_question()
            retriever.begin_question()
            trace_id = new_trace_id()
            response = await service.chat(
                ChatRequest(
                    message=question["question"],
                    user_id=f"generation_eval_{split}",
                    filters=question_filters(question),
                ),
                trace_id=trace_id,
            )
            response_payload = _response_payload(response)
            context = retriever.bounded_context()
            row = {
                "question_id": question["question_id"],
                "question_type": question["question_type"],
                "expected_status": question["expected_status"],
                "filters": question["filters"],
                "trace_id": trace_id,
                "bounded_context": context,
                "llm_call_events": llm.events,
                "usage_state": _usage_state(llm.events),
                "response": response_payload,
            }
            row["automatic_review"] = automatic_review(
                question=question,
                response=response_payload,
                bounded_context=context,
                corpus_identity=identity,
            )
            rows.append(row)
    finally:
        await container.aclose()

    payload = {
        "protocol": "geoexplore-generation-v1",
        "run_started_at": datetime.now(UTC).isoformat(),
        "split": split,
        "evaluation_code_commit": _git_commit(),
        "dataset_path": str(QUESTION_PATHS[split].relative_to(ROOT)),
        "dataset_sha256": canonical_sha256(dataset),
        "corpus_identity": dataset["corpus_identity"],
        "runtime": {
            "retrieval_backend": "bm25",
            "generation_backend": "deepseek",
            "model": settings.deepseek_model,
            "llm_max_retries": settings.llm_max_retries,
            "geological_top_k": settings.geological_top_k,
            "geological_context_chunks": settings.geological_context_chunks,
            "geological_context_chars": settings.geological_context_chars,
        },
        "manual_gold_annotation": "frozen in the question set; never modified by this runner",
        "manual_response_review": "pending PDF-based human review",
        "executed_question_ids": [question["question_id"] for question in questions],
        "rows": rows,
        "summary": summarize_rows(rows),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("dev", "acceptance"), default="dev")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--allow-acceptance", action="store_true")
    parser.add_argument("--question-id")
    return parser.parse_args()


async def _main() -> None:
    args = _parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    payload = await run(
        split=args.split,
        output=output,
        allow_acceptance=args.allow_acceptance,
        question_id=args.question_id,
    )
    print(json.dumps(payload["summary"], indent=2, ensure_ascii=True))
    print(f"wrote {output.relative_to(ROOT)}")


if __name__ == "__main__":
    asyncio.run(_main())
