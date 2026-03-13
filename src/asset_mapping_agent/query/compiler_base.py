from __future__ import annotations

from abc import ABC, abstractmethod

from .capabilities import PlatformCapability
from .models import CompiledQuery, ComparisonOperator, Group, LogicOperator, Predicate, QueryIntent


class BaseQueryCompiler(ABC):
    platform: str

    def __init__(self, capability: PlatformCapability) -> None:
        self.capability = capability
        self.platform = capability.name.lower().replace(" ", "-")

    def compile(self, intent: QueryIntent) -> CompiledQuery:
        filters_used: list[str] = []
        post_filters: list[str] = []
        warnings: list[str] = list(self.capability.notes)
        root = self._merge_targets(intent)
        query = self._compile_group(root, filters_used, post_filters, warnings)
        if self.capability.requires_account_validation:
            warnings.append(
                f"{self.capability.name} compiler output is a draft and must be validated with a real account."
            )
        return CompiledQuery(
            platform=self.platform_key,
            query=query or "",
            filters_used=filters_used,
            post_filters=post_filters,
            warnings=self._deduplicate(warnings),
            metadata={
                "limit": intent.options.limit,
                "offset": intent.options.offset,
                "aggregate": intent.options.aggregate,
            },
        )

    @property
    def platform_key(self) -> str:
        return self.capability.name.lower().replace(" ", "_")

    def _build_default_group(self, intent: QueryIntent) -> Group:
        items = [
            Predicate(field="keyword", operator=ComparisonOperator.CONTAINS, value=target)
            for target in intent.targets
        ]
        return Group(operator=LogicOperator.OR, items=items)

    def _merge_targets(self, intent: QueryIntent) -> Group:
        target_group = self._build_default_group(intent)
        if intent.group is None:
            return target_group
        if not target_group.items:
            return intent.group
        return Group(
            operator=LogicOperator.AND,
            items=[target_group, intent.group],
        )

    def _compile_group(
        self,
        group: Group,
        filters_used: list[str],
        post_filters: list[str],
        warnings: list[str],
    ) -> str | None:
        if group.operator is LogicOperator.OR and not self.capability.supports_or:
            warning = f"{self.capability.name} does not support OR in the current compiler profile."
            warnings.append(warning)
            post_filters.append(self._describe_group(group))
            return None
        if group.operator is LogicOperator.NOT and not self.capability.supports_not:
            warning = f"{self.capability.name} does not support NOT in the current compiler profile."
            warnings.append(warning)
            post_filters.append(self._describe_group(group))
            return None

        parts: list[str] = []
        for item in group.items:
            if isinstance(item, Predicate):
                rendered = self._compile_predicate(item, filters_used, post_filters, warnings)
            else:
                rendered = self._compile_group(item, filters_used, post_filters, warnings)
            if rendered:
                parts.append(rendered)

        if not parts:
            return None
        if group.operator is LogicOperator.NOT:
            return self._render_not(parts[0])
        joiner = self._render_joiner(group.operator)
        if len(parts) == 1:
            return parts[0]
        return f"({joiner.join(parts)})"

    def _compile_predicate(
        self,
        predicate: Predicate,
        filters_used: list[str],
        post_filters: list[str],
        warnings: list[str],
    ) -> str | None:
        if predicate.field not in self.capability.supported_fields:
            warnings.append(
                f"Field '{predicate.field}' is not supported by {self.capability.name}; moved to post-filter."
            )
            post_filters.append(self._describe_predicate(predicate))
            return None
        if predicate.operator not in self.capability.supported_operators:
            warnings.append(
                f"Operator '{predicate.operator.value}' is not supported by {self.capability.name}; moved to post-filter."
            )
            post_filters.append(self._describe_predicate(predicate))
            return None
        expression = self.render_predicate(predicate)
        filters_used.append(self._describe_predicate(predicate))
        return expression

    def _describe_group(self, group: Group) -> str:
        inner = ", ".join(
            self._describe_predicate(item) if isinstance(item, Predicate) else self._describe_group(item)
            for item in group.items
        )
        return f"{group.operator.value}({inner})"

    def _describe_predicate(self, predicate: Predicate) -> str:
        return f"{predicate.field} {predicate.operator.value} {predicate.value}"

    def _render_joiner(self, operator: LogicOperator) -> str:
        mapping = {
            LogicOperator.AND: " AND ",
            LogicOperator.OR: " OR ",
        }
        return mapping[operator]

    def _render_not(self, expression: str) -> str:
        return f"NOT ({expression})"

    def _quote(self, value: object) -> str:
        if value is None:
            return '""'
        text = str(value).replace('"', r'\"')
        return f'"{text}"'

    def _deduplicate(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        deduplicated: list[str] = []
        for value in values:
            if value not in seen:
                seen.add(value)
                deduplicated.append(value)
        return deduplicated

    @abstractmethod
    def render_predicate(self, predicate: Predicate) -> str:
        raise NotImplementedError
