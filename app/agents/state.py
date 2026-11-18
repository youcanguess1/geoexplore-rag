"""Shared agent state passed between graph nodes."""

from typing import Any, TypedDict

from app.core.enums import QueryComplexity, RetrievalStrategy
from app.schemas.agent import AgentPlan, ComplexityResult, IntentResult, ToolResult
from app.schemas.chat import ActionProposal, ChatMessage, ChatStatus
from app.schemas.common import LatencyBreakdown, TokenUsage
from app.schemas.retrieval import Citation, RetrievalFilters, RetrievedChunk


class AgentState(TypedDict, total=False):
    """LangGraph state. Partial updates replace listed keys; no infinite append reducer.

    Nodes return partial state updates. Conversation persistence is handled by
    ChatService; retrieval context is bounded by the geological graph.
    """

    trace_id: str
    session_id: str
    user_id: str
    user_query: str
    retrieval_filters: RetrievalFilters | None
    messages: list[ChatMessage]
    summary: str
    intent: IntentResult | None
    complexity: ComplexityResult | None
    strategy: RetrievalStrategy | None
    query_complexity: QueryComplexity | None
    rewritten_queries: list[str]
    retrieved_chunks: list[RetrievedChunk]
    plan: AgentPlan | None
    tool_results: list[ToolResult]
    pending_action: ActionProposal | None
    confirmed_action: ActionProposal | None
    confirm_action_id: str | None
    idempotency_key: str | None
    final_answer: str | None
    status: ChatStatus
    generation_backend: str
    retrieval_backend: str
    citations: list[Citation]
    refused: bool
    error: str | None
    step_count: int
    token_usage: TokenUsage
    latency: LatencyBreakdown
    extra: dict[str, Any]
