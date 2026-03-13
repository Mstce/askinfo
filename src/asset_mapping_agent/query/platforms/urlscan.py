from __future__ import annotations

import re

from ..capabilities import PLATFORM_CAPABILITIES
from ..compiler_base import BaseQueryCompiler
from ..models import ComparisonOperator, Predicate


class UrlscanCompiler(BaseQueryCompiler):
    _TOKEN_RE = re.compile(r"^[A-Za-z0-9._:/-]+$")

    def __init__(self) -> None:
        super().__init__(PLATFORM_CAPABILITIES["urlscan"])

    @property
    def platform_key(self) -> str:
        return "urlscan"

    def render_predicate(self, predicate: Predicate) -> str:
        field = self.capability.field_mapping[predicate.field]
        operator = predicate.operator

        if field == "_keyword":
            if operator in {ComparisonOperator.EQ, ComparisonOperator.CONTAINS}:
                return self._format_value(predicate.value)
            if operator is ComparisonOperator.IN:
                values = predicate.value if isinstance(predicate.value, (list, tuple, set)) else [predicate.value]
                return " OR ".join(self._format_value(value) for value in values)

        if operator in {ComparisonOperator.EQ, ComparisonOperator.CONTAINS}:
            return f"{field}:{self._format_value(predicate.value)}"
        if operator is ComparisonOperator.IN:
            values = predicate.value if isinstance(predicate.value, (list, tuple, set)) else [predicate.value]
            return "(" + " OR ".join(f"{field}:{self._format_value(value)}" for value in values) + ")"
        raise ValueError(f"Unsupported operator for urlscan compiler: {operator.value}")

    def _format_value(self, value: object) -> str:
        text = str(value).strip()
        if self._TOKEN_RE.match(text):
            return text
        return self._quote(value)
