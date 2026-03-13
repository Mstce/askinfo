from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol
from urllib.parse import urlparse

from asset_mapping_agent.adapters import AdapterRequest, UrllibHttpClient

from .models import LlmMessage, LlmResponse


class StructuredLlmClient(Protocol):
    def complete_json(
        self,
        messages: list[LlmMessage],
        *,
        temperature: float = 0.2,
        response_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...


@dataclass(slots=True)
class OpenAICompatibleLlmClient:
    api_key: str
    model: str
    base_url: str = "https://api.openai.com/v1"
    timeout: int = 60
    max_attempts: int = 3
    retry_delay_seconds: float = 0.5
    heartbeat_interval_seconds: float = 5.0
    progress_logger: Callable[[str], None] | None = None
    http_client: UrllibHttpClient | None = None

    def complete(self, messages: list[LlmMessage], *, temperature: float = 0.2) -> LlmResponse:
        client = self.http_client or UrllibHttpClient(user_agent="askinfo-llm/0.1")
        response = None
        attempts = max(1, int(self.max_attempts or 1))
        for attempt_index in range(attempts):
            attempt_text = f"第 {attempt_index + 1}/{attempts} 次"
            if self._prefer_responses_api():
                request_label = f"Responses API，模型={self.model}，{attempt_text}"
                self._log_progress(f"AI 请求：使用 {request_label}")
                self._log_progress(f"AI 请求已发出，等待网关响应，超时 {self.timeout} 秒")
                response = self._execute_with_heartbeat(client, self._build_responses_request(messages), request_label)
            else:
                request_label = f"Chat Completions，模型={self.model}，{attempt_text}"
                self._log_progress(f"AI 请求：使用 {request_label}")
                self._log_progress(f"AI 请求已发出，等待网关响应，超时 {self.timeout} 秒")
                response = self._execute_with_heartbeat(
                    client,
                    self._build_chat_completions_request(messages, temperature=temperature),
                    request_label,
                )
                if self._should_fallback_to_responses(response):
                    fallback_label = f"Responses API，模型={self.model}，兼容回退"
                    self._log_progress("AI 网关不支持 chat/completions，自动切换到 Responses API")
                    self._log_progress(f"AI 请求：使用 {fallback_label}")
                    self._log_progress(f"AI 请求已发出，等待网关响应，超时 {self.timeout} 秒")
                    response = self._execute_with_heartbeat(
                        client,
                        self._build_responses_request(messages),
                        fallback_label,
                    )

            if response.ok and isinstance(response.payload, dict):
                self._log_progress("AI 响应已返回，正在解析结果")
                break
            if attempt_index + 1 >= attempts or not self._should_retry(response):
                break
            self._log_progress(f"AI 请求失败，准备重试：{self._build_error_message(response)}")
            time.sleep(self.retry_delay_seconds)

        if response is None:
            raise RuntimeError("LLM request failed")
        if not response.ok or not isinstance(response.payload, dict):
            raise RuntimeError(self._build_error_message(response))

        content = self._extract_response_text(response.payload)
        if not content:
            raise RuntimeError("LLM response does not contain message content")

        return LlmResponse(
            content=content,
            model=str(response.payload.get("model") or self.model),
            usage=response.payload.get("usage") or {},
            raw_payload=response.payload,
        )

    def _execute_with_heartbeat(
        self,
        client: UrllibHttpClient,
        request: AdapterRequest,
        request_label: str,
    ):
        interval = max(float(self.heartbeat_interval_seconds or 0), 0.0)
        stop_event = threading.Event()
        heartbeat_thread: threading.Thread | None = None

        if self.progress_logger and interval > 0:
            started_at = time.monotonic()

            def _heartbeat() -> None:
                while not stop_event.wait(interval):
                    elapsed = int(time.monotonic() - started_at)
                    self._log_progress(f"AI 等待中：{request_label}，已等待 {elapsed} 秒")

            heartbeat_thread = threading.Thread(
                target=_heartbeat,
                name="askinfo-llm-heartbeat",
                daemon=True,
            )
            heartbeat_thread.start()

        try:
            return client.execute(request)
        finally:
            stop_event.set()
            if heartbeat_thread:
                heartbeat_thread.join(timeout=0.2)

    def _chat_completions_url(self) -> str:
        normalized_base = self._normalize_base_url(self.base_url)
        return f"{normalized_base.rstrip('/')}/chat/completions"

    def _responses_url(self) -> str:
        normalized_base = self._normalize_base_url(self.base_url)
        return f"{normalized_base.rstrip('/')}/responses"

    def _normalize_base_url(self, base_url: str) -> str:
        cleaned = (base_url or "").strip().rstrip("/")
        if not cleaned:
            return "https://api.openai.com/v1"
        parsed = urlparse(cleaned)
        if parsed.path in {"", "/"}:
            return f"{cleaned}/v1"
        return cleaned

    def _build_chat_completions_request(
        self,
        messages: list[LlmMessage],
        *,
        temperature: float,
    ) -> AdapterRequest:
        return AdapterRequest(
            platform="llm",
            method="POST",
            url=self._chat_completions_url(),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json_body={
                "model": self.model,
                "temperature": temperature,
                "messages": [{"role": item.role, "content": item.content} for item in messages],
            },
            timeout=self.timeout,
        )

    def _build_responses_request(self, messages: list[LlmMessage]) -> AdapterRequest:
        input_items = [
            {
                "role": item.role,
                "content": [
                    {
                        "type": "input_text",
                        "text": item.content,
                    }
                ],
            }
            for item in messages
        ]
        return AdapterRequest(
            platform="llm",
            method="POST",
            url=self._responses_url(),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json_body={
                "model": self.model,
                "stream": False,
                "input": input_items,
            },
            timeout=self.timeout,
        )

    def _prefer_responses_api(self) -> bool:
        normalized_base = self._normalize_base_url(self.base_url)
        parsed = urlparse(normalized_base)
        hostname = (parsed.hostname or "").lower()
        return hostname not in {"api.openai.com"}

    def _should_retry(self, response) -> bool:  # type: ignore[no-untyped-def]
        if getattr(response, "status_code", 0) in {0, 502, 503, 504}:
            return True
        error_text = str(getattr(response, "error", "") or "").lower()
        return any(
            item in error_text
            for item in [
                "timed out",
                "connection reset",
                "forcibly closed",
                "bad gateway",
                "temporarily unavailable",
            ]
        )

    def _should_fallback_to_responses(self, response) -> bool:  # type: ignore[no-untyped-def]
        if response.ok or not isinstance(response.payload, dict):
            return False
        error = response.payload.get("error")
        if not isinstance(error, dict):
            return False
        message = str(error.get("message") or "")
        lowered = message.lower()
        return "unsupported legacy protocol" in lowered and "/v1/responses" in lowered

    def _extract_response_text(self, payload: dict[str, Any]) -> str:
        output_text = str(payload.get("output_text") or "").strip()
        if output_text:
            return output_text

        choice = ((payload.get("choices") or [{}])[0] or {}).get("message") or {}
        content = str(choice.get("content") or "").strip()
        if content:
            return content

        texts: list[str] = []
        for item in payload.get("output") or []:
            if not isinstance(item, dict):
                continue
            for content_item in item.get("content") or []:
                if not isinstance(content_item, dict):
                    continue
                if str(content_item.get("type") or "").strip() != "output_text":
                    continue
                text = str(content_item.get("text") or "").strip()
                if text:
                    texts.append(text)
        return "\n".join(texts).strip()

    def _build_error_message(self, response) -> str:  # type: ignore[no-untyped-def]
        if isinstance(response.payload, dict):
            error = response.payload.get("error")
            if isinstance(error, dict):
                message = str(error.get("message") or "").strip()
                if message:
                    return message
        return response.error or "LLM request failed"

    def _log_progress(self, message: str) -> None:
        if self.progress_logger:
            self.progress_logger(message)

    def complete_json(
        self,
        messages: list[LlmMessage],
        *,
        temperature: float = 0.2,
        response_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        schema_text = ""
        if response_schema:
            schema_text = (
                "\n\nOutput JSON must conform to this schema summary:\n"
                + json.dumps(response_schema, ensure_ascii=False, indent=2)
            )
            messages = [
                *messages[:-1],
                LlmMessage(
                    role=messages[-1].role,
                    content=f"{messages[-1].content}{schema_text}",
                ),
            ]

        response = self.complete(messages, temperature=temperature)
        content = self._strip_code_fence(response.content)
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"LLM did not return valid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("LLM JSON output must be an object")
        return payload

    def _strip_code_fence(self, content: str) -> str:
        cleaned = content.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            return "\n".join(lines).strip()
        return cleaned
