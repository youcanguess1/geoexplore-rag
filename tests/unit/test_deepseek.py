from __future__ import annotations

import httpx
import pytest

from app.config.settings import Settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import LLMProviderError
from app.providers.deepseek import DeepSeekProvider


@pytest.mark.asyncio
async def test_missing_usage_is_explicitly_unknown() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/chat/completions"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "{}"}}]},
        )

    settings = Settings(
        deepseek_api_key="test-key",
        deepseek_base_url="https://deepseek.test",
        llm_max_retries=1,
    )
    client = httpx.AsyncClient(
        base_url=settings.deepseek_base_url,
        transport=httpx.MockTransport(handler),
    )
    provider = DeepSeekProvider(settings, client=client)
    try:
        response = await provider.generate([{"role": "user", "content": "test"}])
    finally:
        await client.aclose()

    assert response.usage.prompt_tokens == 0
    assert response.usage.completion_tokens == 0
    assert response.usage.total_tokens == 0
    assert response.usage.usage_known is False


@pytest.mark.asyncio
async def test_transport_diagnostics_preserve_errno_without_exception_text() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        error = OSError(10061, "credential-like-proxy-value-must-not-leak")
        raise httpx.ConnectError("https://secret.example.invalid", request=request) from error

    settings = Settings(
        deepseek_api_key="test-key",
        deepseek_base_url="https://deepseek.test",
        llm_max_retries=1,
    )
    client = httpx.AsyncClient(
        base_url=settings.deepseek_base_url,
        transport=httpx.MockTransport(handler),
    )
    provider = DeepSeekProvider(settings, client=client)
    try:
        with pytest.raises(LLMProviderError) as raised:
            await provider.generate([{"role": "user", "content": "test"}])
    finally:
        await client.aclose()

    error = raised.value
    assert error.message == "DeepSeek transport error"
    assert error.error_code is ErrorCode.LLM_PROVIDER_UNAVAILABLE
    assert error.diagnostics == {
        "failure_stage": "connect",
        "exception_types": ["ConnectError", "ConnectionRefusedError"],
        "target_host": "deepseek.test",
        "errno": 10061,
    }
    assert "secret" not in str(error.diagnostics)


@pytest.mark.asyncio
async def test_read_timeout_is_classified_without_request_details() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("sensitive request detail", request=request)

    settings = Settings(
        deepseek_api_key="test-key",
        deepseek_base_url="https://deepseek.test",
        llm_max_retries=1,
    )
    client = httpx.AsyncClient(
        base_url=settings.deepseek_base_url,
        transport=httpx.MockTransport(handler),
    )
    provider = DeepSeekProvider(settings, client=client)
    try:
        with pytest.raises(LLMProviderError) as raised:
            await provider.generate([{"role": "user", "content": "test"}])
    finally:
        await client.aclose()

    error = raised.value
    assert error.error_code is ErrorCode.LLM_TIMEOUT
    assert error.diagnostics["failure_stage"] == "read"
    assert error.diagnostics["exception_types"] == ["ReadTimeout"]
    assert "sensitive" not in str(error.diagnostics)


@pytest.mark.asyncio
async def test_http_error_records_status_without_response_body() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "secret body"}})

    settings = Settings(
        deepseek_api_key="test-key",
        deepseek_base_url="https://deepseek.test",
        llm_max_retries=1,
    )
    client = httpx.AsyncClient(
        base_url=settings.deepseek_base_url,
        transport=httpx.MockTransport(handler),
    )
    provider = DeepSeekProvider(settings, client=client)
    try:
        with pytest.raises(LLMProviderError) as raised:
            await provider.generate([{"role": "user", "content": "test"}])
    finally:
        await client.aclose()

    error = raised.value
    assert error.error_code is ErrorCode.LLM_RATE_LIMITED
    assert error.diagnostics == {
        "failure_stage": "http_response",
        "exception_types": ["HTTPResponse"],
        "target_host": "deepseek.test",
        "http_status": 429,
    }
    assert "secret" not in str(error.diagnostics)


@pytest.mark.asyncio
async def test_list_models_parses_configured_model_without_generation() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/models"
        return httpx.Response(200, json={"data": [{"id": "deepseek-flash"}]})

    settings = Settings(
        deepseek_api_key="test-key",
        deepseek_base_url="https://deepseek.test",
        deepseek_model="deepseek-flash",
    )
    client = httpx.AsyncClient(
        base_url=settings.deepseek_base_url,
        transport=httpx.MockTransport(handler),
    )
    provider = DeepSeekProvider(settings, client=client)
    try:
        assert await provider.list_models() == ["deepseek-flash"]
        assert provider.last_http_status == 200
    finally:
        await client.aclose()
