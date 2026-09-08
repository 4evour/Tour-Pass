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
    requires_decision_wrapper = True
    supports_tool_calls = True

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
            "TRIP_AGENT_REASONING_EFFORT", "low"
        ).strip()
        self.final_reasoning_effort = os.environ.get(
            "TRIP_AGENT_FINAL_REASONING_EFFORT", "low"
        ).strip()
        self.max_output_tokens = max(
            1024,
            min(
                int(os.environ.get("TRIP_AGENT_MAX_OUTPUT_TOKENS", "4096")),
                4096,
            ),
        )
        self.hedge_delay_seconds = max(
            0.0,
            min(
                float(os.environ.get("TRIP_AGENT_LLM_HEDGE_DELAY_SECONDS", "1.5")),
                10.0,
            ),
        )
        self.timeout_seconds = max(
            15.0,
            min(
                float(os.environ.get("TRIP_AGENT_LLM_TIMEOUT_SECONDS", "60")),
                120.0,
            ),
        )
        self.client: httpx.AsyncClient | None = None

    @property
    def available(self) -> bool:
        return bool(self.key)

    async def close(self) -> None:
        if self.client and not self.client.is_closed:
            await self.client.aclose()

    def _request(
        self,
        messages: list[dict[str, Any]],
        *,
        output_format: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        prompt_cache_key: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
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
            if output_format is not None:
                payload["text"] = {"format": output_format}
            if tools:
                payload["tools"] = tools
                payload["tool_choice"] = tool_choice or "auto"
            if prompt_cache_key:
                payload["prompt_cache_key"] = prompt_cache_key
            return f"{base_url}/responses", payload
        response_format = (
            {
                "type": "json_schema",
                "json_schema": {
                    key: value for key, value in output_format.items() if key != "type"
                },
            }
            if output_format is not None
            else {"type": "json_object"}
        )
        payload = {
            "model": self.model,
            "max_tokens": self.max_output_tokens,
            "temperature": 0.2,
            "messages": self._chat_messages(messages),
            "response_format": response_format,
        }
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool["description"],
                        "parameters": tool["parameters"],
                        "strict": tool.get("strict", True),
                    },
                }
                for tool in tools
            ]
            payload["tool_choice"] = tool_choice or "auto"
        return f"{base_url}/chat/completions", payload

    def _response_content(self, body: dict[str, Any]) -> str:
        if self.wire_api == "chat_completions":
            choices = body.get("choices") or []
            if not choices or not isinstance(choices[0].get("message"), dict):
                raise RuntimeError("LLM response has no message")
            content = choices[0]["message"].get("content")
            return content if isinstance(content, str) else ""

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
        return "".join(text_parts)

    @staticmethod
    def _response_tool_calls(
        body: dict[str, Any], wire_api: str
    ) -> list[dict[str, Any]]:
        if wire_api == "chat_completions":
            choices = body.get("choices") or []
            message = choices[0].get("message") if choices else {}
            raw_calls = message.get("tool_calls") if isinstance(message, dict) else []
            calls = []
            for item in raw_calls or []:
                function = item.get("function") if isinstance(item, dict) else {}
                if not isinstance(function, dict):
                    continue
                calls.append(
                    {
                        "call_id": str(item.get("id") or uuid.uuid4().hex),
                        "name": str(function.get("name") or ""),
                        "arguments": str(function.get("arguments") or "{}"),
                    }
                )
            return calls
        return [
            {
                "call_id": str(
                    item.get("call_id") or item.get("id") or uuid.uuid4().hex
                ),
                "name": str(item.get("name") or ""),
                "arguments": str(item.get("arguments") or "{}"),
            }
            for item in body.get("output") or []
            if isinstance(item, dict) and item.get("type") == "function_call"
        ]

    @staticmethod
    def _chat_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        converted: list[dict[str, Any]] = []
        for message in messages:
            if message.get("type") == "function_call":
                converted.append(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": message["call_id"],
                                "type": "function",
                                "function": {
                                    "name": message["name"],
                                    "arguments": message["arguments"],
                                },
                            }
                        ],
                    }
                )
            elif message.get("type") == "function_call_output":
                converted.append(
                    {
                        "role": "tool",
                        "tool_call_id": message["call_id"],
                        "content": message["output"],
                    }
                )
            else:
                converted.append(message)
        return converted

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
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
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
        tool_calls: list[dict[str, Any]] = []

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
                    elif event_type == "response.output_item.done":
                        item = event.get("item")
                        if (
                            isinstance(item, dict)
                            and item.get("type") == "function_call"
                        ):
                            tool_calls = self._response_tool_calls(
                                {"output": [item]}, "responses"
                            )
                    elif event_type == "response.completed":
                        completed = event.get("response")
                        if isinstance(completed, dict):
                            raw_usage = completed.get("usage")
                            if isinstance(raw_usage, dict):
                                usage = self._usage_summary(raw_usage)
                            if not text_parts:
                                completed_text = self._response_content(completed)
                            completed_calls = self._response_tool_calls(
                                completed, "responses"
                            )
                            if completed_calls:
                                tool_calls = completed_calls
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
        if not content and not tool_calls:
            raise RuntimeError("LLM stream has neither output text nor tool calls")
        return (
            content,
            tool_calls,
            {
                "connected_ms": connected_ms,
                "first_event_ms": first_event_ms,
                "first_text_ms": first_text_ms,
                "total_ms": elapsed_ms(),
                "sse_event_count": event_count,
                "output_chars": len(content),
                "tool_call_count": len(tool_calls),
                "usage": usage,
            },
        )

    async def _stream_response_hedged(
        self,
        endpoint: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        on_progress: Callable[[dict[str, Any]], None] | None,
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
        primary = asyncio.create_task(
            self._stream_response(
                endpoint,
                headers,
                payload,
                on_progress=on_progress,
            )
        )
        try:
            result = await asyncio.wait_for(
                asyncio.shield(primary), timeout=self.hedge_delay_seconds
            )
            result[2]["provider_request_count"] = 1
            return result
        except TimeoutError:
            pass

        hedge = asyncio.create_task(
            self._stream_response(
                endpoint,
                headers,
                payload,
                on_progress=None,
            )
        )
        pending: set[asyncio.Task[Any]] = {primary, hedge}
        first_error: BaseException | None = None
        try:
            while pending:
                done, pending = await asyncio.wait(
                    pending, return_when=asyncio.FIRST_COMPLETED
                )
                for completed in done:
                    try:
                        result = completed.result()
                    except BaseException as exc:
                        first_error = first_error or exc
                        continue
                    result[2]["provider_request_count"] = 2
                    result[2]["hedged"] = completed is hedge
                    return result
            if first_error is not None:
                raise first_error
            raise RuntimeError("LLM hedge completed without a result")
        finally:
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

    async def ainvoke(
        self,
        messages: list[dict[str, Any]],
        *,
        trace: dict[str, Any] | None = None,
        on_progress: Callable[[dict[str, Any]], None] | None = None,
        reasoning_effort: str | None = None,
        output_format: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        prompt_cache_key: str | None = None,
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
        endpoint, payload = self._request(
            messages,
            output_format=output_format,
            tools=tools,
            tool_choice=tool_choice,
            prompt_cache_key=prompt_cache_key,
        )
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
        tool_schema_chars = len(
            json.dumps(tools or [], ensure_ascii=False, separators=(",", ":"))
        )
        output_schema_chars = len(
            json.dumps(output_format or {}, ensure_ascii=False, separators=(",", ":"))
        )
        request_chars = len(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
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
            tool_schema_chars=tool_schema_chars,
            output_schema_chars=output_schema_chars,
            request_chars=request_chars,
            max_output_tokens=self.max_output_tokens,
            prompt_cache_enabled=bool(prompt_cache_key),
            **trace_fields,
        )

        for attempt in range(2):
            try:
                if self.wire_api == "responses":
                    async with asyncio.timeout(self.timeout_seconds):
                        if output_format and self.hedge_delay_seconds > 0:
                            (
                                content,
                                tool_calls,
                                metrics,
                            ) = await self._stream_response_hedged(
                                endpoint,
                                headers,
                                payload,
                                on_progress,
                            )
                        else:
                            content, tool_calls, metrics = await self._stream_response(
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
                    body = response.json()
                    content = self._response_content(body)
                    tool_calls = self._response_tool_calls(body, self.wire_api)
                    if not content and not tool_calls:
                        raise RuntimeError(
                            "LLM response has neither text nor tool calls"
                        )
                    metrics = {
                        "total_ms": round(
                            (time.perf_counter() - request_started) * 1000
                        ),
                        "output_chars": len(content),
                        "tool_call_count": len(tool_calls),
                    }
                log_event(
                    "llm_request_finished",
                    call_id=call_id,
                    attempt=attempt + 1,
                    **metrics,
                    **trace_fields,
                )
                return SimpleNamespace(
                    content=content, tool_calls=tool_calls, metrics=metrics
                )
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
            except RuntimeError as exc:
                if not any(
                    marker in str(exc)
                    for marker in (
                        "stream_read_error",
                        "stream interrupted after response started",
                    )
                ):
                    log_event(
                        "llm_request_failed",
                        call_id=call_id,
                        attempt=attempt + 1,
                        error_type=type(exc).__name__,
                        total_ms=round((time.perf_counter() - request_started) * 1000),
                        **trace_fields,
                    )
                    raise
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
            if attempt < 1:
                await asyncio.sleep(0.5)

        error = RuntimeError(f"LLM request failed after retries: {last_error}")
        log_event(
            "llm_request_failed",
            call_id=call_id,
            attempt=2,
            error_type=type(last_error).__name__,
            total_ms=round((time.perf_counter() - request_started) * 1000),
            **trace_fields,
        )
        raise error from last_error
