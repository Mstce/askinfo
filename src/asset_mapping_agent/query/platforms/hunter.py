from __future__ import annotations

from ..capabilities import PLATFORM_CAPABILITIES
from ..compiler_base import BaseQueryCompiler
from ..models import ComparisonOperator, LogicOperator, Predicate


class HunterCompiler(BaseQueryCompiler):
    def __init__(self) -> None:
        super().__init__(PLATFORM_CAPABILITIES["hunter"])

    def render_predicate(self, predicate: Predicate) -> str:
        field = self.capability.field_mapping[predicate.field]
        operator = predicate.operator

        if predicate.field == "keyword":
            return self._render_keyword(predicate)

        if operator in {ComparisonOperator.EQ, ComparisonOperator.CONTAINS}:
            return f"{field}={self._quote(predicate.value)}"
        if operator is ComparisonOperator.IN:
            values = predicate.value if isinstance(predicate.value, (list, tuple, set)) else [predicate.value]
            joiner = self._render_joiner(LogicOperator.OR)
            return "(" + joiner.join(f"{field}={self._quote(value)}" for value in values) + ")"
        if operator is ComparisonOperator.EXISTS:
            return f'{field}!=""'
        raise ValueError(f"Unsupported operator for Hunter compiler: {operator.value}")

    def _render_joiner(self, operator: LogicOperator) -> str:
        mapping = {
            LogicOperator.AND: " && ",
            LogicOperator.OR: " || ",
        }
        return mapping[operator]

    def _render_keyword(self, predicate: Predicate) -> str:
        operator = predicate.operator
        if operator in {ComparisonOperator.EQ, ComparisonOperator.CONTAINS}:
            return self._quote(predicate.value)
        if operator is ComparisonOperator.IN:
            values = predicate.value if isinstance(predicate.value, (list, tuple, set)) else [predicate.value]
            return "(" + self._render_joiner(LogicOperator.OR).join(self._quote(value) for value in values) + ")"
        if operator is ComparisonOperator.EXISTS:
            return '""!=""'
        raise ValueError(f"Unsupported keyword operator for Hunter compiler: {operator.value}")
