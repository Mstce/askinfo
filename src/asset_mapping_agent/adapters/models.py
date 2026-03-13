from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AdapterRequest:
    platform: str
    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    params: dict[str, object] = field(default_factory=dict)
    json_body: dict[str, object] | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    timeout: int = 20


@dataclass(slots=True)
class AdapterResponse:
    platform: str
    request: AdapterRequest
    status_code: int
    ok: bool
    payload: Any = None
    error: str = ""
    raw_text: str = ""


@dataclass(slots=True)
class SearchExecutionResult:
    platform: str
    request: AdapterRequest
    response: AdapterResponse
    records: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    pagination: dict[str, Any] = field(default_factory=dict)
