from __future__ import annotations

from ..capabilities import PLATFORM_CAPABILITIES
from ..compiler_base import BaseQueryCompiler
from ..models import ComparisonOperator, Predicate


class QuakeCompiler(BaseQueryCompiler):
    def __init__(self) -> None:
        super().__init__(PLATFORM_CAPABILITIES["quake"])

    def render_predicate(self, predicate: Predicate) -> str:
        if predicate.field == "keyword":
            return self._quote(predicate.value)

        field = self.capability.field_mapping[predicate.field]
        operator = predicate.operator
        if operator in {ComparisonOperator.EQ, ComparisonOperator.CONTAINS}:
            return f"{field}:{self._quote(predicate.value)}"
        if operator is ComparisonOperator.IN:
            values = predicate.value if isinstance(predicate.value, (list, tuple, set)) else [predicate.value]
            return "(" + " OR ".join(f"{field}:{self._quote(value)}" for value in values) + ")"
        if operator is ComparisonOperator.EXISTS:
            return f"{field}:*"
        raise ValueError(f"Unsupported operator for Quake compiler: {operator.value}")
