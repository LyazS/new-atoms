from __future__ import annotations

import asyncio
import random
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

import httpcore
import httpx
from loguru import logger
from openai import APIConnectionError, APIError, APIStatusError, APITimeoutError, AsyncOpenAI
from openai.types.chat import (
    ChatCompletionChunk,
    ChatCompletionMessageParam,
    ChatCompletionToolChoiceOptionParam,
    ChatCompletionToolParam,
)

from app.config.settings import settings


@dataclass(slots=True)
class OpenAIRetryContext:
    attempt: int
    max_attempts: int
    delay_seconds: float
    exception: Exception
    stream_started: bool
    elapsed_ms: int
    status_code: int | None = None


class OpenAIStreamRetryExhaustedError(RuntimeError):
    def __init__(self, message: str, *, attempts: int, last_exception: Exception) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.last_exception = last_exception


class OpenAIClient:
    def __init__(self, client: AsyncOpenAI) -> None:
        self._client = client
        self._settings = settings

    async def create_chat_completion_stream(
        self,
        *,
        model: str,
        messages: list[ChatCompletionMessageParam],
        tools: list[ChatCompletionToolParam],
        tool_choice: ChatCompletionToolChoiceOptionParam | Literal["auto", "required", "none"],
        parallel_tool_calls: bool,
        on_retry: Callable[[OpenAIRetryContext], Awaitable[None] | None] | None = None,
    ) -> AsyncIterator[ChatCompletionChunk]:
        max_attempts = self._settings.openai_max_retries + 1
        last_exception: Exception | None = None
        attempts_made = 0

        for attempt in range(1, max_attempts + 1):
            attempts_made = attempt
            attempt_started_at = time.perf_counter()
            stream_started = False

            try:
                logger.info("openai stream attempt start attempt={} max_attempts={}", attempt, max_attempts)
                stream = await self._client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=tools,
                    tool_choice=tool_choice,
                    parallel_tool_calls=parallel_tool_calls,
                    stream=True,
                )

                async for chunk in stream:
                    stream_started = True
                    yield chunk

                elapsed_ms = int((time.perf_counter() - attempt_started_at) * 1000)
                logger.info(
                    "openai stream attempt succeeded attempt={} max_attempts={} elapsed_ms={}",
                    attempt,
                    max_attempts,
                    elapsed_ms,
                )
                return
            except Exception as exc:
                last_exception = exc
                elapsed_ms = int((time.perf_counter() - attempt_started_at) * 1000)
                status_code = self._extract_status_code(exc)
                retryable = self._is_retryable_error(exc, status_code)
                has_remaining_attempts = attempt < max_attempts

                logger.warning(
                    "openai stream attempt failed attempt={} max_attempts={} elapsed_ms={} stream_started={} "
                    "retryable={} status_code={} error_type={} error={}",
                    attempt,
                    max_attempts,
                    elapsed_ms,
                    stream_started,
                    retryable,
                    status_code,
                    type(exc).__name__,
                    exc,
                )

                if not retryable or not has_remaining_attempts:
                    break

                delay_seconds = self._compute_retry_delay_seconds(attempt)
                if on_retry is not None:
                    retry_context = OpenAIRetryContext(
                        attempt=attempt,
                        max_attempts=max_attempts,
                        delay_seconds=delay_seconds,
                        exception=exc,
                        stream_started=stream_started,
                        elapsed_ms=elapsed_ms,
                        status_code=status_code,
                    )
                    maybe_awaitable = on_retry(retry_context)
                    if maybe_awaitable is not None:
                        await maybe_awaitable

                await asyncio.sleep(delay_seconds)

        final_status_code = self._extract_status_code(last_exception) if last_exception is not None else None
        logger.error(
            "openai stream failed after retries attempts={} status_code={} error_type={} error={}",
            attempts_made,
            final_status_code,
            type(last_exception).__name__ if last_exception is not None else None,
            last_exception,
        )
        raise OpenAIStreamRetryExhaustedError(
            "OpenAI request failed.",
            attempts=attempts_made,
            last_exception=last_exception or RuntimeError("unknown OpenAI stream failure"),
        ) from last_exception

    def _extract_status_code(self, exc: Exception | None) -> int | None:
        if isinstance(exc, APIStatusError):
            return exc.status_code
        status_code = getattr(exc, "status_code", None)
        if isinstance(status_code, int):
            return status_code
        return None

    def _is_retryable_error(self, exc: Exception, status_code: int | None) -> bool:
        if isinstance(
            exc,
            (
                APITimeoutError,
                APIConnectionError,
                asyncio.TimeoutError,
                OSError,
                httpx.TimeoutException,
                httpx.NetworkError,
                httpx.ProtocolError,
                httpx.ReadError,
                httpx.RemoteProtocolError,
                httpcore.TimeoutException,
                httpcore.NetworkError,
                httpcore.ProtocolError,
                httpcore.ReadError,
                httpcore.RemoteProtocolError,
            ),
        ):
            return True
        if isinstance(exc, APIStatusError):
            if status_code in {408, 409, 429}:
                return True
            return bool(status_code and status_code >= 500)
        if isinstance(exc, APIError) and status_code is None:
            return True
        return False

    def _compute_retry_delay_seconds(self, attempt: int) -> float:
        base_seconds = self._settings.openai_retry_base_delay_ms / 1000
        max_seconds = self._settings.openai_retry_max_delay_ms / 1000
        jitter_ratio = max(self._settings.openai_retry_jitter_ratio, 0)
        raw_delay = min(max_seconds, base_seconds * (2 ** max(attempt - 1, 0)))
        jitter_multiplier = 1 + random.uniform(-jitter_ratio, jitter_ratio)
        return max(0.0, raw_delay * jitter_multiplier)


def create_openai_client() -> OpenAIClient:
    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        timeout=settings.openai_timeout,
    )
    return OpenAIClient(client)


openai_client = create_openai_client()
