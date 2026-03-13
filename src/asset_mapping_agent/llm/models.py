from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class LlmMessage:
    role: str
    content: str


@dataclass(slots=True)
class LlmResponse:
    content: str
    model: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    raw_payload: dict[str, Any] = field(default_factory=dict)
