"""Fixed geological question-answering graph.

This path retrieves evidence from geological PDFs and generates cited answers
within the configured document filters. It is the auditable chain used for the
GeoExplore geological PDF question-answering prototype.
"""

from __future__ import annotations

import logging
import re
import time
from functools import partial
from pathlib import PurePosixPath
from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agents.nodes.guardrail import guardrail_node
from app.agents.state import AgentState
from app.config.settings import Settings
from app.core.exceptions import LLMOutputError, LLMProviderError
from app.observability.logging import request_id_var, trace_id_var
from app.providers.base import LLMProvider, LLMResponse
from app.providers.fake import OfflineLLMProvider
from app.providers.json_parser import parse_model
from app.retrieval.base import Retriever
from app.retrieval.filters import effective_filters, matches_retrieval_filters
from app.schemas.common import LatencyBreakdown, TokenUsage
from app.schemas.retrieval import Citation, RetrievedChunk

logger = logging.getLogger(__name__)


class GeologicalAnswerPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["answered", "insufficient_evidence"]
    answer: str = ""
    citation_chunk_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_status_fields(self) -> GeologicalAnswerPayload:
        if self.status == "answered":
            if not self.answer.strip():
                raise ValueError("answered output requires a non-empty answer")
            if not self.citation_chunk_ids:
                raise ValueError("answered output requires at least one citation")
        else:
            if self.answer.strip():
                raise ValueError("insufficient_evidence output must not contain an answer")
            if self.citation_chunk_ids:
                raise ValueError("insufficient_evidence output must not contain citations")
        return self


def _backend_name(provider: object) -> str:
    if isinstance(provider, OfflineLLMProvider):
        return "offline"
    return str(getattr(provider, "backend", provider.__class__.__name__.lower()))


def _source_file(chunk: RetrievedChunk) -> str:
    source = chunk.metadata.get("source_file") or chunk.metadata.get("source", "")
    return PurePosixPath(source.replace("\\", "/")).name if source else f"{chunk.title}.pdf"


def _page_number(chunk: RetrievedChunk) -> int | None:
    raw = chunk.metadata.get("page_number", "")
    try:
        return int(raw) if raw else None
    except ValueError:
        return None


def citation_for_chunk(chunk: RetrievedChunk, *, excerpt: str | None = None) -> Citation:
    """Build a citation from retrieval metadata, never from model text."""
    return Citation(
        document_id=chunk.document_id,
        title=chunk.title,
        chunk_id=chunk.chunk_id,
        section=chunk.section,
        source_file=_source_file(chunk),
        page_number=_page_number(chunk),
        excerpt=excerpt if excerpt is not None else chunk.content,
        data_type=chunk.metadata.get("data_type", ""),
        document_type=chunk.metadata.get("document_type", ""),
        language=chunk.metadata.get("language", ""),
        document_sha256=chunk.metadata.get("sha256", ""),
        corpus_fingerprint=chunk.metadata.get("corpus_fingerprint", ""),
    )


def _bounded_chunks(state: AgentState, settings: Settings) -> list[RetrievedChunk]:
    chunks = list((state.get("retrieved_chunks") or [])[: settings.geological_context_chunks])
    filters = state.get("retrieval_filters")
    if any(not matches_retrieval_filters(chunk, filters) for chunk in chunks):
        raise ValueError("retrieved chunk violates retrieval filters")
    document_order: dict[str, int] = {}
    for chunk in chunks:
        document_order.setdefault(chunk.document_id, len(document_order))
    chunks.sort(key=lambda chunk: (document_order[chunk.document_id], chunk.chunk_index))
    return chunks


def _evidence_text(chunks: list[RetrievedChunk], settings: Settings) -> str:
    pieces: list[str] = []
    for chunk in chunks:
        page = _page_number(chunk)
        page_label = f"p. {page}" if page is not None else "page unavailable"
        excerpt = chunk.content[: settings.geological_context_chars]
        pieces.append(
            f"[{chunk.chunk_id}] {chunk.title} | {_source_file(chunk)} | {page_label}\n{excerpt}"
        )
    return "\n\n".join(pieces) or "(no supporting evidence)"


def _insufficient_evidence_answer(filters_applied: bool) -> str:
    if filters_applied:
        return "指定资料范围内没有足够证据。"
    return "现有地质文献证据不足以支持这个问题，未给出推断性结论。"


def _generation_messages(*, question: str, context: str) -> list[dict[str, str]]:
    system = (
        "Use only the supplied Evidence. Do not use model memory or make professional "
        "conclusions beyond the Evidence. Do not merge similar chunks that have different "
        "conditions, entities, parameters, or applicability. If the Evidence does not directly "
        "support the answer, return insufficient_evidence. Every substantive answered claim must "
        "be supported by the selected citation IDs, copied exactly from Evidence labels. Do not "
        "output page numbers, file names, or citation IDs not present in Evidence. Return JSON only. "
        "Schema: status answered|insufficient_evidence, answer, citation_chunk_ids. answered "
        "requires a non-empty answer and at least one citation; insufficient_evidence requires "
        "an empty answer and no citations."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Question: {question}\n\nEvidence:\n{context}"},
    ]


def _repair_messages(
    *, raw_output: str, validation_error: str, allowed_chunk_ids: list[str]
) -> list[dict[str, str]]:
    system = "Repair the output into exactly one valid JSON object. Do not add claims or IDs."
    user = f"Original output:\n{raw_output}\n\nValidation error:\n{validation_error}\n\n"
    user += f"Allowed chunk IDs: {allowed_chunk_ids}\n\nSchema: {GeologicalAnswerPayload.model_json_schema()}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _validated_citation_ids(
    payload: GeologicalAnswerPayload,
    *,
    chunks_by_id: dict[str, RetrievedChunk],
    filters,
) -> list[str]:
    if payload.status == "insufficient_evidence":
        return []
    result: list[str] = []
    for chunk_id in payload.citation_chunk_ids:
        chunk = chunks_by_id.get(chunk_id)
        if chunk is None:
            raise LLMOutputError(f"citation chunk ID is outside bounded context: {chunk_id}")
        if not matches_retrieval_filters(chunk, filters):
            raise LLMOutputError(f"citation chunk ID violates retrieval filters: {chunk_id}")
        if chunk_id not in result:
            result.append(chunk_id)
    return result


def _merged_usage(previous: TokenUsage, responses: list[LLMResponse]) -> TokenUsage:
    return TokenUsage(
        prompt_tokens=previous.prompt_tokens
        + sum(response.usage.prompt_tokens for response in responses),
        completion_tokens=previous.completion_tokens
        + sum(response.usage.completion_tokens for response in responses),
        total_tokens=previous.total_tokens
        + sum(response.usage.total_tokens for response in responses),
        usage_known=previous.usage_known
        and all(response.usage.usage_known for response in responses),
    )


_SAFE_FAILURE_STAGES = {
    "connect",
    "proxy",
    "read",
    "write",
    "pool",
    "timeout",
    "transport",
    "http_response",
}
_SAFE_HOST_PATTERN = re.compile(
    r"^(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)
_SAFE_EXCEPTION_TYPE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")


def _log_provider_failure(exc: LLMProviderError, *, phase: str, state: AgentState) -> None:
    """Log only approved, typed provider diagnostics; never the exception text."""
    raw = exc.diagnostics
    diagnostics: dict[str, object] = {}
    failure_stage = raw.get("failure_stage")
    if isinstance(failure_stage, str) and failure_stage in _SAFE_FAILURE_STAGES:
        diagnostics["failure_stage"] = failure_stage
    exception_types = raw.get("exception_types")
    if isinstance(exception_types, list):
        safe_types = [
            value
            for value in exception_types[:8]
            if isinstance(value, str) and _SAFE_EXCEPTION_TYPE_PATTERN.fullmatch(value)
        ]
        if safe_types:
            diagnostics["exception_types"] = safe_types
    target_host = raw.get("target_host")
    if (
        isinstance(target_host, str)
        and len(target_host) <= 253
        and _SAFE_HOST_PATTERN.fullmatch(target_host)
    ):
        diagnostics["target_host"] = target_host
    for field in ("http_status", "errno", "winerror"):
        value = raw.get(field)
        if isinstance(value, int) and not isinstance(value, bool):
            if field != "http_status" or 100 <= value <= 599:
                diagnostics[field] = value
    # HTTP middleware normally binds this context. Direct graph invocations do
    # not, so use the state value only when the ambient trace is unavailable.
    trace_token = None
    state_trace_id = state.get("trace_id")
    if trace_id_var.get() == "-" and isinstance(state_trace_id, str) and state_trace_id:
        trace_token = trace_id_var.set(state_trace_id)
    try:
        logger.error(
            "geological_generation_provider_failed",
            extra={
                "trace_id": trace_id_var.get(),
                "request_id": request_id_var.get(),
                "generation_phase": phase,
                "error_code": exc.error_code.value,
                **diagnostics,
            },
        )
    finally:
        if trace_token is not None:
            trace_id_var.reset(trace_token)


def _generation_failure(
    *,
    state: AgentState,
    started: float,
    generation_backend: str,
    error: str,
    responses: list[LLMResponse],
    usage_unknown: bool,
    message: str,
) -> dict:
    latency = state.get("latency") or LatencyBreakdown()
    latency.llm_ms = (time.perf_counter() - started) * 1000
    usage = _merged_usage(state.get("token_usage") or TokenUsage(), responses)
    if usage_unknown:
        usage = usage.model_copy(update={"usage_known": False})
    return {
        "status": "execution_failed",
        "generation_backend": generation_backend,
        "error": error,
        "final_answer": message,
        "citations": [],
        "token_usage": usage,
        "latency": latency,
    }


async def geological_retrieval_node(
    state: AgentState,
    *,
    retriever: Retriever,
    settings: Settings,
) -> dict:
    started = time.perf_counter()
    backend = getattr(retriever, "backend", "hybrid")
    filters = effective_filters(state.get("retrieval_filters"))
    try:
        if filters is None:
            chunks = await retriever.retrieve(state["user_query"], top_k=settings.geological_top_k)
        else:
            chunks = await retriever.retrieve(
                state["user_query"], top_k=settings.geological_top_k, filters=filters
            )
    except Exception as exc:
        latency = state.get("latency") or LatencyBreakdown()
        latency.retrieval_ms = (time.perf_counter() - started) * 1000
        return {
            "retrieved_chunks": [],
            "retrieval_backend": backend,
            "status": "execution_failed",
            "error": "retrieval_failed",
            "final_answer": f"检索执行失败，未能读取地质文献证据：{exc}",
            "citations": [],
            "latency": latency,
        }
    if any(not matches_retrieval_filters(chunk, filters) for chunk in chunks):
        latency = state.get("latency") or LatencyBreakdown()
        latency.retrieval_ms = (time.perf_counter() - started) * 1000
        return {
            "retrieved_chunks": [],
            "retrieval_backend": backend,
            "status": "execution_failed",
            "error": "invalid_retrieval_filters",
            "final_answer": "检索结果超出指定资料范围，未返回该结果。",
            "citations": [],
            "latency": latency,
        }
    latency = state.get("latency") or LatencyBreakdown()
    latency.retrieval_ms = (time.perf_counter() - started) * 1000
    return {
        "retrieved_chunks": chunks,
        "retrieval_backend": backend,
        "latency": latency,
    }


async def geological_answer_node(
    state: AgentState, *, llm: LLMProvider, settings: Settings
) -> dict:
    started = time.perf_counter()
    generation_backend = _backend_name(llm)
    if state.get("status") == "execution_failed":
        return {"generation_backend": generation_backend}
    try:
        chunks = _bounded_chunks(state, settings)
    except ValueError as exc:
        latency = state.get("latency") or LatencyBreakdown()
        latency.llm_ms = (time.perf_counter() - started) * 1000
        return {
            "status": "execution_failed",
            "generation_backend": generation_backend,
            "error": "invalid_retrieval_filters",
            "final_answer": f"检索结果超出指定资料范围，未返回该结果：{exc}",
            "citations": [],
            "latency": latency,
        }
    filters = effective_filters(state.get("retrieval_filters"))
    if not chunks:
        return {
            "status": "insufficient_evidence",
            "generation_backend": generation_backend,
            "final_answer": _insufficient_evidence_answer(filters is not None),
            "citations": [],
        }

    if isinstance(llm, OfflineLLMProvider):
        lines = [
            "当前未配置生成模型，以下仅展示检索到的原文证据，不作综合结论：",
        ]
        citations = []
        for chunk in chunks:
            excerpt = chunk.content[: settings.geological_context_chars]
            page = _page_number(chunk)
            page_label = f"物理页 {page}" if page is not None else "物理页未知"
            lines.append(
                f"\n[{chunk.chunk_id}] {chunk.title}，{_source_file(chunk)}，{page_label}\n> {excerpt}"
            )
            citations.append(citation_for_chunk(chunk, excerpt=excerpt))
        return {
            "status": "evidence_only",
            "generation_backend": generation_backend,
            "final_answer": "\n".join(lines),
            "citations": citations,
        }

    context = _evidence_text(chunks, settings)
    by_id = {chunk.chunk_id: chunk for chunk in chunks}
    responses: list[LLMResponse] = []
    try:
        primary = await llm.generate(
            _generation_messages(question=state["user_query"], context=context),
            temperature=0.0,
            max_tokens=700,
            response_format={"type": "json_object"},
        )
        responses.append(primary)
    except LLMProviderError as exc:
        _log_provider_failure(exc, phase="primary", state=state)
        return _generation_failure(
            state=state,
            started=started,
            generation_backend=generation_backend,
            error="generation_failed",
            responses=responses,
            usage_unknown=True,
            message=f"生成执行失败，未能可靠整理地质证据：{exc}",
        )

    try:
        payload = parse_model(primary.content, GeologicalAnswerPayload)
        citation_ids = _validated_citation_ids(payload, chunks_by_id=by_id, filters=filters)
    except LLMOutputError as first_error:
        try:
            repair = await llm.generate(
                _repair_messages(
                    raw_output=primary.content,
                    validation_error=str(first_error),
                    allowed_chunk_ids=list(by_id),
                ),
                temperature=0.0,
                max_tokens=700,
                response_format={"type": "json_object"},
            )
            responses.append(repair)
        except LLMProviderError as exc:
            _log_provider_failure(exc, phase="repair", state=state)
            return _generation_failure(
                state=state,
                started=started,
                generation_backend=generation_backend,
                error="generation_failed",
                responses=responses,
                usage_unknown=True,
                message=f"生成执行失败，未能可靠整理地质证据：{exc}",
            )
        try:
            payload = parse_model(repair.content, GeologicalAnswerPayload)
            citation_ids = _validated_citation_ids(payload, chunks_by_id=by_id, filters=filters)
        except LLMOutputError:
            return _generation_failure(
                state=state,
                started=started,
                generation_backend=generation_backend,
                error="invalid_generation_output",
                responses=responses,
                usage_unknown=False,
                message="生成结果不符合受限证据与引用契约，未返回该结论。",
            )

    latency = state.get("latency") or LatencyBreakdown()
    latency.llm_ms = (time.perf_counter() - started) * 1000
    usage = _merged_usage(state.get("token_usage") or TokenUsage(), responses)
    if payload.status == "insufficient_evidence":
        return {
            "status": "insufficient_evidence",
            "generation_backend": generation_backend,
            "final_answer": _insufficient_evidence_answer(filters is not None),
            "citations": [],
            "token_usage": usage,
            "latency": latency,
        }
    return {
        "status": "answered",
        "generation_backend": generation_backend,
        "final_answer": payload.answer,
        "citations": [citation_for_chunk(by_id[chunk_id]) for chunk_id in citation_ids],
        "token_usage": usage,
        "latency": latency,
    }


async def geological_refuse_node(
    state: AgentState, *, llm: LLMProvider, retriever: Retriever
) -> dict:
    return {
        "status": "execution_failed",
        "generation_backend": _backend_name(llm),
        "retrieval_backend": getattr(retriever, "backend", "hybrid"),
        "final_answer": "请求被安全策略拦截。",
        "refused": True,
        "citations": [],
        "error": state.get("error") or "query_rejected",
    }


def build_geological_graph(
    *, llm: LLMProvider, settings: Settings, retriever: Retriever
) -> CompiledStateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("apply_guardrail", guardrail_node)
    graph.add_node(
        "retrieve_geological_evidence",
        partial(geological_retrieval_node, retriever=retriever, settings=settings),
    )
    graph.add_node(
        "answer_geological_question",
        partial(geological_answer_node, llm=llm, settings=settings),
    )
    graph.add_node(
        "refuse_geological_question",
        partial(geological_refuse_node, llm=llm, retriever=retriever),
    )

    def after_guardrail(state: AgentState) -> str:
        return (
            "refuse_geological_question" if state.get("refused") else "retrieve_geological_evidence"
        )

    graph.add_edge(START, "apply_guardrail")
    graph.add_conditional_edges(
        "apply_guardrail",
        after_guardrail,
        {
            "retrieve_geological_evidence": "retrieve_geological_evidence",
            "refuse_geological_question": "refuse_geological_question",
        },
    )
    graph.add_edge("retrieve_geological_evidence", "answer_geological_question")
    graph.add_edge("answer_geological_question", END)
    graph.add_edge("refuse_geological_question", END)
    return graph.compile()
