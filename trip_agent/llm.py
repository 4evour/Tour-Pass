from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from types import SimpleNamespace
from collections.abc import Callable
from typing import Any

import httpx

from .observability import log_event


class OpenAICompatibleLLM:
    def __init__(self) -> None:
        self.key = (
            os.environ.get("TRIP_AGENT_LLM_KEY")
            or os.environ.get("DEEPSEEK_API_KEY")
            or os.environ.get("OPENAI_API_KEY", "")
        )
        self.base_url = os.environ.get("TRIP_AGENT_BASE_URL") or os.environ.get(
            "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
        )
        self.model = os.environ.get("TRIP_AGENT_MODEL") or os.environ.get(
            "DEEPSEEK_MODEL", "deepseek-chat"
        )
        wire_api = (
            os.environ.get("TRIP_AGENT_WIRE_API", "chat_completions")
            .strip()
            .lower()
            .replace("-", "_")
        )
        if wire_api in {"response", "responses"}:
            self.wire_api = "responses"
        elif wire_api in {"chat", "chat_completion", "chat_completions"}:
            self.wire_api = "chat_completions"
        else:
            raise ValueError(f"Unsupported TRIP_AGENT_WIRE_API: {wire_api}")
        self.reasoning_effort = os.environ.get(
            "TRIP_AGENT_REASONING_EFFORT", "high"
        ).strip()
        self.final_reasoning_effort = os.environ.get(
            "TRIP_AGENT_FINAL_REASONING_EFFORT", "medium"
        ).strip()
        self.max_output_tokens = max(
            2048,
            min(
                int(os.environ.get("TRIP_AGENT_MAX_OUTPUT_TOKENS", "8192")),
                8192,
            ),
        )
        self.timeout_seconds = max(
            30.0,
            min(
                float(os.environ.get("TRIP_AGENT_LLM_TIMEOUT_SECONDS", "480")),
                540.0,
            ),
        )
        self.client: httpx.AsyncClient | None = None

    @property
    def available(self) -> bool:
        return bool(self.key)

    async def close(self) -> None:
        if self.client and not self.client.is_closed:
            await self.client.aclose()

    def _request(self, messages: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
        base_url = self.base_url.rstrip("/")
        if self.wire_api == "responses":
            payload: dict[str, Any] = {
                "model": self.model,
                "input": messages,
                "max_output_tokens": self.max_output_tokens,
                "stream": True,
                "store": False,
            }
            if self.reasoning_effort:
                payload["reasoning"] = {"effort": self.reasoning_effort}
            return f"{base_url}/responses", payload
        return (
            f"{base_url}/chat/completions",
            {
                "model": self.model,
                "max_tokens": self.max_output_tokens,
                "temperature": 0.2,
                "messages": messages,
                "response_format": {"type": "json_object"},
            },
        )

    def _response_content(self, body: dict[str, Any]) -> str:
        if self.wire_api == "chat_completions":
            choices = body.get("choices") or []
            if not choices or not isinstance(choices[0].get("message"), dict):
                raise RuntimeError("LLM response has no message")
            return str(choices[0]["message"].get("content", ""))

        output_text = body.get("output_text")
        if isinstance(output_text, str) and output_text:
            return output_text
        text_parts: list[str] = []
        for item in body.get("output") or []:
            if not isinstance(item, dict):
                continue
            for content in item.get("content") or []:
                if not isinstance(content, dict):
                    continue
                text = content.get("text")
                if isinstance(text, str) and text:
                    text_parts.append(text)
        if not text_parts:
            raise RuntimeError("LLM response has no output text")
        return "".join(text_parts)

    @staticmethod
    def _usage_summary(usage: dict[str, Any]) -> dict[str, int]:
        summary: dict[str, int] = {}
        for key in ("input_tokens", "output_tokens", "total_tokens"):
            value = usage.get(key)
            if isinstance(value, int):
                summary[key] = value
        for detail_name in ("input_tokens_details", "output_tokens_details"):
            details = usage.get(detail_name)
            if not isinstance(details, dict):
                continue
            for key, value in details.items():
                if isinstance(value, int):
                    summary[f"{detail_name}.{key}"] = value
        return summary

    async def _stream_response(
        self,
        endpoint: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        *,
        on_progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        started_at = time.perf_counter()
        text_parts: list[str] = []
        completed_text = ""
        event_name = ""
        received_event = False
        event_count = 0
        first_event_ms: int | None = None
        first_text_ms: int | None = None
        connected_ms: int | None = None
        usage: dict[str, Any] = {}

        def elapsed_ms() -> int:
            return round((time.perf_counter() - started_at) * 1000)

        def publish(milestone: str, **fields: Any) -> None:
            if on_progress is not None:
                on_progress(
                    {
                        "type": "model_stream",
                        "milestone": milestone,
                        "model_elapsed_ms": elapsed_ms(),
                        **fields,
                    }
                )

        try:
            async with self.client.stream(
                "POST", endpoint, headers=headers, json=payload
            ) as response:
                connected_ms = elapsed_ms()
                publish("connected", http_status=response.status_code)
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("event:"):
                        event_name = line.removeprefix("event:").strip()
                        continue
                    if not line.startswith("data:"):
                        continue
                    raw_event = line.removeprefix("data:").strip()
                    if not raw_event or raw_event == "[DONE]":
                        continue
                    event = json.loads(raw_event)
                    received_event = True
                    event_count += 1
                    event_type = str(event.get("type") or event_name)
                    if first_event_ms is None:
                        first_event_ms = elapsed_ms()
                        publish("first_event", event_type=event_type)
                    if event_type == "response.output_text.delta":
                        delta = event.get("delta")
                        if isinstance(delta, str):
                            if first_text_ms is None:
                                first_text_ms = elapsed_ms()
                                publish("first_text")
                            text_parts.append(delta)
                    elif event_type == "response.output_text.done":
                        text = event.get("text")
                        if isinstance(text, str):
                            completed_text = text
                    elif event_type == "response.completed":
                        completed = event.get("response")
                        if isinstance(completed, dict):
                            raw_usage = completed.get("usage")
                            if isinstance(raw_usage, dict):
                                usage = self._usage_summary(raw_usage)
                            if not text_parts:
                                completed_text = self._response_content(completed)
                    elif event_type in {
                        "error",
                        "response.failed",
                        "response.incomplete",
                    }:
                        error = event.get("error")
                        if not isinstance(error, dict):
                            response_body = event.get("response")
                            error = (
                                response_body.get("error")
                                if isinstance(response_body, dict)
                                else {}
                            )
                        message = (
                            error.get("message") if isinstance(error, dict) else None
                        )
                        raise RuntimeError(
                            f"LLM stream failed: {message or event_type}"
                        )
        except httpx.TransportError as exc:
            if received_event:
                raise RuntimeError(
                    "LLM stream interrupted after response started"
                ) from exc
            raise

        content = "".join(text_parts) or completed_text
        if not content:
            raise RuntimeError("LLM stream has no output text")
        return content, {
            "connected_ms": connected_ms,
            "first_event_ms": first_event_ms,
            "first_text_ms": first_text_ms,
            "total_ms": elapsed_ms(),
            "sse_event_count": event_count,
            "output_chars": len(content),
            "usage": usage,
        }

    async def ainvoke(
        self,
        messages: list[dict[str, Any]],
        *,
        trace: dict[str, Any] | None = None,
        on_progress: Callable[[dict[str, Any]], None] | None = None,
        reasoning_effort: str | None = None,
    ) -> Any:
        if not self.available:
            raise RuntimeError("TRIP_AGENT_LLM_KEY is not configured")
        self.client = self.client or httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=15.0,
                read=self.timeout_seconds,
                write=30.0,
                pool=30.0,
            )
        )
        retryable_statuses = {429, 500, 502, 503, 504}
        last_error: Exception | None = None
        endpoint, payload = self._request(messages)
        if self.wire_api == "responses" and reasoning_effort is not None:
            if reasoning_effort:
                payload["reasoning"] = {"effort": reasoning_effort}
            else:
                payload.pop("reasoning", None)
        headers = {
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }
        trace_fields = trace or {}
        call_id = uuid.uuid4().hex[:12]
        request_started = time.perf_counter()
        input_chars = sum(
            len(json.dumps(message, ensure_ascii=False, separators=(",", ":")))
            for message in messages
        )
        log_event(
            "llm_request_started",
            call_id=call_id,
            model=self.model,
            wire_api=self.wire_api,
            reasoning_effort=(
                reasoning_effort
                if reasoning_effort is not None
                else self.reasoning_effort
            ),
            message_count=len(messages),
            input_chars=input_chars,
            max_output_tokens=self.max_output_tokens,
            **trace_fields,
        )

        for attempt in range(3):
            try:
                if self.wire_api == "responses":
                    content, metrics = await self._stream_response(
                        endpoint,
                        headers,
                        payload,
                        on_progress=on_progress,
                    )
                else:
                    response = await self.client.post(
                        endpoint,
                        headers=headers,
                        json=payload,
                    )
                    response.raise_for_status()
                    content = self._response_content(response.json())
                    metrics = {
                        "total_ms": round(
                            (time.perf_counter() - request_started) * 1000
                        ),
                        "output_chars": len(content),
                    }
                log_event(
                    "llm_request_finished",
                    call_id=call_id,
                    attempt=attempt + 1,
                    **metrics,
                    **trace_fields,
                )
                return SimpleNamespace(content=content, metrics=metrics)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in retryable_statuses:
                    log_event(
                        "llm_request_failed",
                        call_id=call_id,
                        attempt=attempt + 1,
                        error_type=type(exc).__name__,
                        http_status=exc.response.status_code,
                        total_ms=round((time.perf_counter() - request_started) * 1000),
                        **trace_fields,
                    )
                    raise
                last_error = exc
            except httpx.ReadTimeout as exc:
                log_event(
                    "llm_request_failed",
                    call_id=call_id,
                    attempt=attempt + 1,
                    error_type=type(exc).__name__,
                    total_ms=round((time.perf_counter() - request_started) * 1000),
                    **trace_fields,
                )
                raise
            except httpx.TransportError as exc:
                last_error = exc
            except Exception as exc:
                log_event(
                    "llm_request_failed",
                    call_id=call_id,
                    attempt=attempt + 1,
                    error_type=type(exc).__name__,
                    total_ms=round((time.perf_counter() - request_started) * 1000),
                    **trace_fields,
                )
                raise

            log_event(
                "llm_request_retry",
                call_id=call_id,
                attempt=attempt + 1,
                error_type=type(last_error).__name__,
                **trace_fields,
            )
            if attempt < 2:
                await asyncio.sleep(0.5 * (2**attempt))

        error = RuntimeError(f"LLM request failed after retries: {last_error}")
        log_event(
            "llm_request_failed",
            call_id=call_id,
            attempt=3,
            error_type=type(last_error).__name__,
            total_ms=round((time.perf_counter() - request_started) * 1000),
            **trace_fields,
        )
        raise error from last_error
