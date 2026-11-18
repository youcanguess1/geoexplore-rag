import pytest

from app.agents.geological import (
    geological_answer_node,
    geological_retrieval_node,
)
from app.config.settings import Settings
from app.core.exceptions import LLMProviderError
from app.observability.logging import request_id_var
from app.providers.base import LLMResponse
from app.providers.fake import OfflineLLMProvider
from app.schemas.common import TokenUsage
from app.schemas.retrieval import RetrievalFilters, RetrievedChunk


class SequenceLLMProvider:
    """Return scripted generation outputs so primary and repair calls can differ."""

    backend = "test-llm"

    def __init__(self, outputs: list[str | Exception]) -> None:
        self._outputs = list(outputs)
        self.calls: list[list[dict[str, str]]] = []

    async def ping(self) -> bool:
        return True

    async def generate(self, messages: list[dict[str, str]], **kwargs) -> LLMResponse:
        self.calls.append(messages)
        output = self._outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return LLMResponse(
            content=output,
            usage=TokenUsage(prompt_tokens=3, completion_tokens=4, total_tokens=7),
            model="test-llm",
        )


def _chunk(chunk_id: str = "geo-1996-21_10") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id="geo-1996-21",
        title="1996-21",
        content="The BLIMP procedure lists numbered steps for band-limited impedance inversion.",
        score=1.0,
        metadata={
            "source": r"C:\runtime\1996-21.pdf",
            "page_number": "3",
            "parser": "pypdf",
            "data_type": "02_Academic",
            "document_type": "paper",
            "language": "en",
        },
    )


def _settings() -> Settings:
    return Settings(
        app_env="testing",
        geological_context_chunks=2,
        geological_context_chars=120,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("metadata_key", ["source", "source_file"])
@pytest.mark.parametrize(
    "source_path",
    [
        r"C:\runtime\1996-21.pdf",
        r"\\server\share\1996-21.pdf",
        "/runtime/1996-21.pdf",
        "C:/runtime/1996-21.pdf",
        "1996-21.pdf",
    ],
)
async def test_offline_mode_is_evidence_only_with_physical_page_and_excerpt(
    metadata_key: str, source_path: str
) -> None:
    chunk = _chunk()
    chunk.metadata.pop("source")
    chunk.metadata[metadata_key] = source_path
    result = await geological_answer_node(
        {"user_query": "What is the BLIMP procedure?", "retrieved_chunks": [chunk]},
        llm=OfflineLLMProvider(),
        settings=_settings(),
    )
    assert result["status"] == "evidence_only"
    citation = result["citations"][0]
    assert citation.source_file == "1996-21.pdf"
    assert citation.page_number == 3
    assert citation.excerpt in _chunk().content
    assert "not a synthesized" not in result["final_answer"]


@pytest.mark.asyncio
async def test_valid_answer_uses_only_context_citations_and_deduplicates_ids() -> None:
    llm = SequenceLLMProvider(
        [
            (
                '{"status":"answered","answer":"BLIMP has numbered steps.",'
                '"citation_chunk_ids":["geo-1996-21_10","geo-1996-21_10"]}'
            )
        ]
    )
    result = await geological_answer_node(
        {"user_query": "What is the BLIMP procedure?", "retrieved_chunks": [_chunk()]},
        llm=llm,  # type: ignore[arg-type]
        settings=_settings(),
    )
    assert result["status"] == "answered"
    assert result["final_answer"] == "BLIMP has numbered steps."
    assert [citation.chunk_id for citation in result["citations"]] == ["geo-1996-21_10"]
    assert result["token_usage"].total_tokens == 7
    assert len(llm.calls) == 1


@pytest.mark.asyncio
async def test_generation_context_restores_source_order_within_each_document() -> None:
    later = _chunk("geo-1996-21_11").model_copy(
        update={"chunk_index": 11, "content": "Steps five through nine."}
    )
    earlier = _chunk("geo-1996-21_10").model_copy(
        update={"chunk_index": 10, "content": "Steps one through five."}
    )
    llm = SequenceLLMProvider(
        [
            (
                '{"status":"answered","answer":"The evidence lists nine steps.",'
                '"citation_chunk_ids":["geo-1996-21_10","geo-1996-21_11"]}'
            )
        ]
    )

    result = await geological_answer_node(
        {
            "user_query": "What are the numbered BLIMP steps?",
            "retrieved_chunks": [later, earlier],
        },
        llm=llm,  # type: ignore[arg-type]
        settings=_settings(),
    )

    evidence_prompt = llm.calls[0][-1]["content"]
    assert evidence_prompt.index("[geo-1996-21_10]") < evidence_prompt.index("[geo-1996-21_11]")
    assert result["status"] == "answered"


@pytest.mark.asyncio
async def test_model_can_report_insufficient_evidence_despite_nonempty_context() -> None:
    llm = SequenceLLMProvider(
        ['{"status":"insufficient_evidence","answer":"","citation_chunk_ids":[]}']
    )
    result = await geological_answer_node(
        {"user_query": "What drilling mud density is recommended?", "retrieved_chunks": [_chunk()]},
        llm=llm,  # type: ignore[arg-type]
        settings=_settings(),
    )
    assert result["status"] == "insufficient_evidence"
    assert result["citations"] == []
    assert "证据不足" in result["final_answer"]
    assert len(llm.calls) == 1


@pytest.mark.asyncio
async def test_answered_without_citations_repairs_once_then_fails_closed() -> None:
    invalid = '{"status":"answered","answer":"unsupported","citation_chunk_ids":[]}'
    llm = SequenceLLMProvider([invalid, invalid])
    result = await geological_answer_node(
        {"user_query": "What is the BLIMP procedure?", "retrieved_chunks": [_chunk()]},
        llm=llm,  # type: ignore[arg-type]
        settings=_settings(),
    )
    assert result["status"] == "execution_failed"
    assert result["error"] == "invalid_generation_output"
    assert result["citations"] == []
    assert len(llm.calls) == 2


@pytest.mark.asyncio
async def test_insufficient_evidence_with_citations_repairs_once_then_fails_closed() -> None:
    invalid = (
        '{"status":"insufficient_evidence","answer":"","citation_chunk_ids":["geo-1996-21_10"]}'
    )
    llm = SequenceLLMProvider([invalid, invalid])
    result = await geological_answer_node(
        {"user_query": "What is the BLIMP procedure?", "retrieved_chunks": [_chunk()]},
        llm=llm,  # type: ignore[arg-type]
        settings=_settings(),
    )
    assert result["status"] == "execution_failed"
    assert result["error"] == "invalid_generation_output"
    assert len(llm.calls) == 2


@pytest.mark.asyncio
async def test_unknown_model_citation_is_repaired_once_and_never_silently_dropped() -> None:
    invalid = (
        '{"status":"answered","answer":"supported","citation_chunk_ids":'
        '["unknown","geo-1996-21_10"]}'
    )
    llm = SequenceLLMProvider([invalid, invalid])
    result = await geological_answer_node(
        {"user_query": "What is the BLIMP procedure?", "retrieved_chunks": [_chunk()]},
        llm=llm,  # type: ignore[arg-type]
        settings=_settings(),
    )
    assert result["status"] == "execution_failed"
    assert result["error"] == "invalid_generation_output"
    assert result["citations"] == []
    assert len(llm.calls) == 2
    assert "Allowed chunk IDs: ['geo-1996-21_10']" in llm.calls[1][-1]["content"]


@pytest.mark.asyncio
async def test_malformed_primary_output_can_be_repaired_with_usage_accumulated() -> None:
    llm = SequenceLLMProvider(
        [
            "not json",
            (
                '{"status":"answered","answer":"BLIMP has numbered steps.",'
                '"citation_chunk_ids":["geo-1996-21_10"]}'
            ),
        ]
    )
    result = await geological_answer_node(
        {"user_query": "What is the BLIMP procedure?", "retrieved_chunks": [_chunk()]},
        llm=llm,  # type: ignore[arg-type]
        settings=_settings(),
    )
    assert result["status"] == "answered"
    assert len(llm.calls) == 2
    assert result["token_usage"] == TokenUsage(
        prompt_tokens=6, completion_tokens=8, total_tokens=14
    )


@pytest.mark.asyncio
async def test_extra_payload_field_is_repaired_to_a_strictly_valid_answer() -> None:
    llm = SequenceLLMProvider(
        [
            (
                '{"status":"answered","answer":"BLIMP has numbered steps.",'
                '"citation_chunk_ids":["geo-1996-21_10"],"page_number":3}'
            ),
            (
                '{"status":"answered","answer":"BLIMP has numbered steps.",'
                '"citation_chunk_ids":["geo-1996-21_10"]}'
            ),
        ]
    )
    result = await geological_answer_node(
        {"user_query": "What is the BLIMP procedure?", "retrieved_chunks": [_chunk()]},
        llm=llm,  # type: ignore[arg-type]
        settings=_settings(),
    )
    assert result["status"] == "answered"
    assert [citation.chunk_id for citation in result["citations"]] == ["geo-1996-21_10"]
    assert len(llm.calls) == 2


@pytest.mark.asyncio
async def test_extra_payload_field_in_primary_and_repair_fails_closed() -> None:
    invalid = (
        '{"status":"answered","answer":"BLIMP has numbered steps.",'
        '"citation_chunk_ids":["geo-1996-21_10"],"unsupported_reasoning":"extra"}'
    )
    llm = SequenceLLMProvider([invalid, invalid])
    result = await geological_answer_node(
        {"user_query": "What is the BLIMP procedure?", "retrieved_chunks": [_chunk()]},
        llm=llm,  # type: ignore[arg-type]
        settings=_settings(),
    )
    assert result["status"] == "execution_failed"
    assert result["error"] == "invalid_generation_output"
    assert result["citations"] == []
    assert len(llm.calls) == 2


@pytest.mark.asyncio
async def test_invalid_repair_output_returns_execution_failed() -> None:
    llm = SequenceLLMProvider(["not json", "still not json"])
    result = await geological_answer_node(
        {"user_query": "What is the BLIMP procedure?", "retrieved_chunks": [_chunk()]},
        llm=llm,  # type: ignore[arg-type]
        settings=_settings(),
    )
    assert result["status"] == "execution_failed"
    assert result["error"] == "invalid_generation_output"
    assert len(llm.calls) == 2


@pytest.mark.asyncio
async def test_provider_error_returns_execution_failed_without_repair() -> None:
    llm = SequenceLLMProvider([LLMProviderError("timed out", timeout=True)])
    result = await geological_answer_node(
        {"user_query": "What is the BLIMP procedure?", "retrieved_chunks": [_chunk()]},
        llm=llm,  # type: ignore[arg-type]
        settings=_settings(),
    )
    assert result["status"] == "execution_failed"
    assert result["error"] == "generation_failed"
    assert result["token_usage"].usage_known is False
    assert len(llm.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("outputs", "expected_phase"),
    [
        (
            [
                LLMProviderError(
                    "sensitive raw exception text",
                    diagnostics={
                        "failure_stage": "connect",
                        "exception_types": ["ConnectError", "credential=secret"],
                        "target_host": "deepseek.test",
                        "errno": 10061,
                        "winerror": 10061,
                        "http_status": 999,
                        "proxy_url": "http://user:password@proxy.local",
                    },
                )
            ],
            "primary",
        ),
        (
            [
                "not valid json",
                LLMProviderError(
                    "sensitive repair exception text",
                    diagnostics={"failure_stage": "read", "exception_types": ["ReadTimeout"]},
                ),
            ],
            "repair",
        ),
    ],
)
async def test_provider_failure_logs_safe_diagnostics_and_call_phase(
    outputs: list[str | Exception], expected_phase: str, caplog: pytest.LogCaptureFixture
) -> None:
    llm = SequenceLLMProvider(outputs)
    token = request_id_var.set("req-test-123")
    try:
        with caplog.at_level("ERROR", logger="app.agents.geological"):
            result = await geological_answer_node(
                {
                    "trace_id": "tr-test-456",
                    "user_query": "What is supported by the evidence?",
                    "retrieved_chunks": [_chunk()],
                },
                llm=llm,  # type: ignore[arg-type]
                settings=_settings(),
            )
    finally:
        request_id_var.reset(token)

    assert result["status"] == "execution_failed"
    assert result["error"] == "generation_failed"
    records = [
        record
        for record in caplog.records
        if record.getMessage() == "geological_generation_provider_failed"
    ]
    assert len(records) == 1
    record = records[0]
    assert record.trace_id == "tr-test-456"
    assert record.request_id == "req-test-123"
    assert record.generation_phase == expected_phase
    assert (
        record.target_host == "deepseek.test"
        if expected_phase == "primary"
        else not hasattr(record, "target_host")
    )
    assert "sensitive" not in caplog.text
    assert "credential" not in caplog.text
    assert "password" not in caplog.text
    if expected_phase == "primary":
        assert record.failure_stage == "connect"
        assert record.exception_types == ["ConnectError"]
        assert record.errno == 10061
        assert record.winerror == 10061
        assert not hasattr(record, "http_status")
        assert not hasattr(record, "proxy_url")
    else:
        assert record.failure_stage == "read"
        assert record.exception_types == ["ReadTimeout"]


@pytest.mark.asyncio
async def test_no_chunks_returns_insufficient_evidence_without_llm_call() -> None:
    llm = SequenceLLMProvider(
        ['{"status":"answered","answer":"must not be called","citation_chunk_ids":["x"]}']
    )
    result = await geological_answer_node(
        {"user_query": "What is the BLIMP procedure?", "retrieved_chunks": []},
        llm=llm,  # type: ignore[arg-type]
        settings=_settings(),
    )
    assert result["status"] == "insufficient_evidence"
    assert result["citations"] == []
    assert llm.calls == []


@pytest.mark.asyncio
async def test_citation_outside_filtered_context_requires_valid_repair() -> None:
    invalid = '{"status":"answered","answer":"unsupported","citation_chunk_ids":["report-1"]}'
    llm = SequenceLLMProvider([invalid, invalid])
    result = await geological_answer_node(
        {
            "user_query": "What is the BLIMP procedure?",
            "retrieved_chunks": [_chunk()],
            "retrieval_filters": RetrievalFilters(document_types=["paper"], languages=["en"]),
        },
        llm=llm,  # type: ignore[arg-type]
        settings=_settings(),
    )
    assert result["status"] == "execution_failed"
    assert result["error"] == "invalid_generation_output"
    assert result["citations"] == []


@pytest.mark.asyncio
async def test_retrieval_result_outside_filter_fails_before_context() -> None:
    class LeakyRetriever:
        backend = "hybrid-bm25+test"

        async def retrieve(self, query: str, *, top_k: int, filters=None) -> list[RetrievedChunk]:
            return [_chunk().model_copy(update={"metadata": {"document_type": "report"}})]

    result = await geological_retrieval_node(
        {
            "user_query": "What is BLIMP?",
            "retrieval_filters": RetrievalFilters(document_types=["paper"]),
        },
        retriever=LeakyRetriever(),  # type: ignore[arg-type]
        settings=_settings(),
    )
    assert result["status"] == "execution_failed"
    assert result["error"] == "invalid_retrieval_filters"


@pytest.mark.asyncio
async def test_retrieval_exception_returns_execution_failed() -> None:
    class BrokenRetriever:
        backend = "hybrid-bm25+hash"

        async def retrieve(self, query: str, *, top_k: int) -> list[RetrievedChunk]:
            raise RuntimeError("backend down")

    result = await geological_retrieval_node(
        {"user_query": "What is BLIMP?"},
        retriever=BrokenRetriever(),  # type: ignore[arg-type]
        settings=_settings(),
    )
    assert result["status"] == "execution_failed"
    assert result["error"] == "retrieval_failed"
