"""DeepSeek chat-completion provider."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from urllib.parse import urlparse

import httpx

from app.config.settings import Settings
from app.core.exceptions import LLMProviderError
from app.core.retry import is_retryable_status, with_exponential_backoff
from app.providers.base import LLMResponse
from app.schemas.common import TokenUsage

logger = logging.getLogger(__name__)


def _failure_stage(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.ProxyError):
        return "proxy"
    if isinstance(exc, httpx.ConnectTimeout | httpx.ConnectError):
        return "connect"
    if isinstance(exc, httpx.ReadTimeout):
        return "read"
    if isinstance(exc, httpx.WriteTimeout):
        return "write"
    if isinstance(exc, httpx.PoolTimeout):
        return "pool"
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    return "transport"


def _exception_diagnostics(
    exc: BaseException, *, target_host: str, failure_stage: str
) -> dict[str, object]:
    types: list[str] = []
    errno: int | None = None
    winerror: int | None = None
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen and len(types) < 8:
        seen.add(id(current))
        types.append(type(current).__name__)
        value = getattr(current, "errno", None)
        if errno is None and isinstance(value, int):
            errno = value
        value = getattr(current, "winerror", None)
        if winerror is None and isinstance(value, int):
            winerror = value
        cause = current.__cause__
        current = cause if isinstance(cause, BaseException) else current.__context__
    diagnostics: dict[str, object] = {
        "failure_stage": failure_stage,
        "exception_types": types,
        "target_host": target_host,
    }
    if errno is not None:
        diagnostics["errno"] = errno
    if winerror is not None:
        diagnostics["winerror"] = winerror
    return diagnostics


def _http_status_diagnostics(*, target_host: str, status: int) -> dict[str, object]:
    return {
        "failure_stage": "http_response",
        "exception_types": ["HTTPResponse"],
        "target_host": target_host,
        "http_status": status,
    }


class DeepSeekProvider:
    """OpenAI-compatible DeepSeek chat completions client.

    Timeouts are split so a hung connect does not block a worker forever.
    400/401/403 are not retried.
    """

    backend = "deepseek"

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._owns_client = client is None
        self._last_http_status: int | None = None
        self._client = client or httpx.AsyncClient(
            base_url=settings.deepseek_base_url.rstrip("/"),
            timeout=httpx.Timeout(
                connect=3.0,
                read=settings.llm_timeout_seconds,
                write=10.0,
                pool=5.0,
            ),
        )

    @property
    def target_host(self) -> str:
        return urlparse(self._settings.deepseek_base_url).hostname or ""

    @property
    def last_http_status(self) -> int | None:
        """Status from the most recent response, never inferred from transport failures."""
        return self._last_http_status

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def ping(self) -> bool:
        """Do not call chat completions here — readiness must stay cheap."""
        return bool(self._settings.deepseek_api_key.get_secret_value())

    def _transport_error(self, message: str, exc: httpx.HTTPError) -> LLMProviderError:
        diagnostics = _exception_diagnostics(
            exc,
            target_host=self.target_host,
            failure_stage=_failure_stage(exc),
        )
        return LLMProviderError(
            message,
            timeout=isinstance(exc, httpx.TimeoutException),
            diagnostics=diagnostics,
        )

    def _raise_for_http_status(self, response: httpx.Response) -> None:
        status = response.status_code
        self._last_http_status = status
        if status < 400:
            return
        diagnostics = _http_status_diagnostics(target_host=self.target_host, status=status)
        if status in {400, 401, 403, 404, 422}:
            raise LLMProviderError(
                f"DeepSeek HTTP {status}", retryable=False, diagnostics=diagnostics
            )
        if status == 429:
            raise LLMProviderError(
                "DeepSeek rate limited", rate_limited=True, diagnostics=diagnostics
            )
        raise LLMProviderError(
            f"DeepSeek HTTP {status}",
            retryable=is_retryable_status(status),
            diagnostics=diagnostics,
        )

    async def list_models(self) -> list[str]:
        """List account models without sending a generation request."""
        api_key = self._settings.deepseek_api_key.get_secret_value()
        if not api_key:
            raise LLMProviderError("DeepSeek API key is not configured")
        try:
            response = await self._client.get(
                "/models", headers={"Authorization": f"Bearer {api_key}"}
            )
        except httpx.HTTPError as exc:
            raise self._transport_error("DeepSeek models transport error", exc) from exc
        self._raise_for_http_status(response)
        try:
            records = response.json()["data"]
            model_ids = [str(record["id"]) for record in records if isinstance(record, dict)]
        except (KeyError, TypeError, ValueError) as exc:
            raise LLMProviderError("DeepSeek models response missing data") from exc
        return sorted(set(model_ids))

    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        response_format: dict[str, str] | None = None,
    ) -> LLMResponse:
        api_key = self._settings.deepseek_api_key.get_secret_value()
        if not api_key:
            raise LLMProviderError("DeepSeek API key is not configured")

        payload: dict[str, object] = {
            "model": self._settings.deepseek_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format is not None:
            payload["response_format"] = response_format

        async def _call() -> LLMResponse:
            try:
                response = await self._client.post(
                    "/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=payload,
                )
            except httpx.HTTPError as exc:
                message = (
                    "DeepSeek request timed out"
                    if isinstance(exc, httpx.TimeoutException)
                    else "DeepSeek transport error"
                )
                raise self._transport_error(message, exc) from exc

            self._raise_for_http_status(response)

            body = response.json()
            try:
                content = body["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as exc:
                raise LLMProviderError("DeepSeek response missing choices") from exc
            usage_raw = body.get("usage") or {}
            usage_fields = ("prompt_tokens", "completion_tokens", "total_tokens")
            usage_known = all(
                field in usage_raw and usage_raw[field] is not None for field in usage_fields
            )
            usage = TokenUsage(
                prompt_tokens=int(usage_raw.get("prompt_tokens") or 0),
                completion_tokens=int(usage_raw.get("completion_tokens") or 0),
                total_tokens=int(usage_raw.get("total_tokens") or 0),
                usage_known=usage_known,
            )
            return LLMResponse(
                content=content or "", usage=usage, model=self._settings.deepseek_model
            )

        return await with_exponential_backoff(
            _call,
            max_attempts=self._settings.llm_max_retries,
            operation_name="deepseek.generate",
        )

    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        response_format: dict[str, str] | None = None,
    ) -> AsyncIterator[str]:
        api_key = self._settings.deepseek_api_key.get_secret_value()
        if not api_key:
            raise LLMProviderError("DeepSeek API key is not configured")

        payload: dict[str, object] = {
            "model": self._settings.deepseek_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if response_format is not None:
            payload["response_format"] = response_format

        try:
            async with self._client.stream(
                "POST",
                "/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            ) as response:
                self._raise_for_http_status(response)
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:].strip()
                    if not data or data == "[DONE]":
                        continue
                    try:
                        chunk = json.loads(data)
                        delta = chunk["choices"][0].get("delta", {}).get("content") or ""
                    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                        continue
                    if delta:
                        yield delta
        except httpx.HTTPError as exc:
            message = (
                "DeepSeek stream timed out"
                if isinstance(exc, httpx.TimeoutException)
                else "DeepSeek stream transport error"
            )
            raise self._transport_error(message, exc) from exc
