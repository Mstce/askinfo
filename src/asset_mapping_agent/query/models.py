from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class LogicOperator(str, Enum):
    AND = "and"
    OR = "or"
    NOT = "not"


class ComparisonOperator(str, Enum):
    EQ = "eq"
    NEQ = "neq"
    CONTAINS = "contains"
    IN = "in"
    RANGE = "range"
    EXISTS = "exists"
    STARTSWITH = "startswith"
    ENDSWITH = "endswith"


@dataclass(slots=True)
class Predicate:
    field: str
    operator: ComparisonOperator
    value: Any = None


@dataclass(slots=True)
class Group:
    operator: LogicOperator
    items: list[Predicate | Group] = field(default_factory=list)


@dataclass(slots=True)
class QueryOptions:
    limit: int = 100
    offset: int = 0
    aggregate: bool = False
    prefer_active: bool = True
    include_non_standard_ports: bool = False
    native_flags: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class QueryIntent:
    targets: list[str] = field(default_factory=list)
    group: Group | None = None
    options: QueryOptions = field(default_factory=QueryOptions)
    output_fields: list[str] = field(default_factory=list)
    source_text: str = ""


@dataclass(slots=True)
class CompiledQuery:
    platform: str
    query: str
    filters_used: list[str] = field(default_factory=list)
    post_filters: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
