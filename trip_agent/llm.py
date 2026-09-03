from __future__ import annotations

import asyncio
import json
import os
from types import SimpleNamespace
from typing import Any

import httpx


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

    async def _stream_response(
        self,
        endpoint: str,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> str:
        text_parts: list[str] = []
        completed_text = ""
        event_name = ""
        received_event = False
        try:
            async with self.client.stream(
                "POST", endpoint, headers=headers, json=payload
            ) as response:
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
                    event_type = str(event.get("type") or event_name)
                    if event_type == "response.output_text.delta":
                        delta = event.get("delta")
                        if isinstance(delta, str):
                            text_parts.append(delta)
                    elif event_type == "response.output_text.done":
                        text = event.get("text")
                        if isinstance(text, str):
                            completed_text = text
                    elif event_type == "response.completed" and not text_parts:
                        completed = event.get("response")
                        if isinstance(completed, dict):
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
        return content

    async def ainvoke(self, messages: list[dict[str, Any]]) -> Any:
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
        headers = {
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }

        for attempt in range(3):
            try:
                if self.wire_api == "responses":
                    content = await self._stream_response(endpoint, headers, payload)
                else:
                    response = await self.client.post(
                        endpoint,
                        headers=headers,
                        json=payload,
                    )
                    response.raise_for_status()
                    content = self._response_content(response.json())
                return SimpleNamespace(content=content)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in retryable_statuses:
                    raise
                last_error = exc
            except httpx.ReadTimeout:
                raise
            except httpx.TransportError as exc:
                last_error = exc

            if attempt < 2:
                await asyncio.sleep(0.5 * (2**attempt))

        raise RuntimeError(
            f"LLM request failed after retries: {last_error}"
        ) from last_error
