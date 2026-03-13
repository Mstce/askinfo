from __future__ import annotations

from ..capabilities import PLATFORM_CAPABILITIES
from ..compiler_base import BaseQueryCompiler
from ..models import ComparisonOperator, Predicate


class ShodanCompiler(BaseQueryCompiler):
    def __init__(self) -> None:
        super().__init__(PLATFORM_CAPABILITIES["shodan"])

    def _render_joiner(self, operator):
        if operator.value == "and":
            return " "
        return " OR "

    def render_predicate(self, predicate: Predicate) -> str:
        field = self.capability.field_mapping[predicate.field]
        operator = predicate.operator

        if field == "_keyword":
            if operator in {ComparisonOperator.EQ, ComparisonOperator.CONTAINS}:
                return self._quote(predicate.value)
            if operator is ComparisonOperator.IN:
                values = predicate.value if isinstance(predicate.value, (list, tuple, set)) else [predicate.value]
                return " OR ".join(self._quote(value) for value in values)

        if operator in {ComparisonOperator.EQ, ComparisonOperator.CONTAINS}:
            return f"{field}:{self._format_value(field, predicate.value)}"
        if operator is ComparisonOperator.IN:
            values = predicate.value if isinstance(predicate.value, (list, tuple, set)) else [predicate.value]
            return "(" + " OR ".join(f"{field}:{self._format_value(field, value)}" for value in values) + ")"
        raise ValueError(f"Unsupported operator for Shodan compiler: {operator.value}")

    def _format_value(self, field: str, value: object) -> str:
        text = str(value).strip()
        if field == "port" and text.isdigit():
            return text
        if field == "asn" and (text.isdigit() or text.upper().startswith("AS")):
            return text.upper()
        return self._quote(value)
