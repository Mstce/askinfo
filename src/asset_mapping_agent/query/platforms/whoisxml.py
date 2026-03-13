from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

from ..capabilities import PLATFORM_CAPABILITIES
from ..compiler_base import BaseQueryCompiler
from ..models import CompiledQuery, ComparisonOperator, Group, LogicOperator, Predicate, QueryIntent


class WhoisXmlCompiler(BaseQueryCompiler):
    _DOMAIN_RE = re.compile(
        r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$",
        re.IGNORECASE,
    )

    def __init__(self) -> None:
        super().__init__(PLATFORM_CAPABILITIES["whoisxml"])

    @property
    def platform_key(self) -> str:
        return "whoisxml"

    def compile(self, intent: QueryIntent) -> CompiledQuery:
        filters_used: list[str] = []
        post_filters: list[str] = []
        warnings: list[str] = list(self.capability.notes)

        candidates: list[str] = []
        for target in intent.targets:
            normalized = self._normalize_hostname_candidate(target)
            if normalized:
                candidates.append(normalized)
            elif target:
                post_filters.append(f"keyword contains {target}")

        if intent.group is not None:
            self._collect_group_candidates(intent.group, candidates, post_filters)

        unique_candidates = self._deduplicate(candidates)
        hostname = unique_candidates[0] if unique_candidates else ""
        if hostname:
            filters_used.append(f"domainName eq {hostname}")
        else:
            warnings.append("WhoisXML API current compiler requires a domain or hostname target.")

        if len(unique_candidates) > 1:
            warnings.append(
                "WhoisXML API current adapter executes a single domain lookup; extra hostname candidates were moved to post-filter."
            )
            post_filters.extend(f"domainName eq {candidate}" for candidate in unique_candidates[1:])

        if intent.options.aggregate:
            warnings.append("WhoisXML API current adapter ignores aggregate mode.")

        return CompiledQuery(
            platform=self.platform_key,
            query=hostname,
            filters_used=filters_used,
            post_filters=self._deduplicate(post_filters),
            warnings=self._deduplicate(warnings),
            metadata={
                "limit": intent.options.limit,
                "offset": intent.options.offset,
                "aggregate": intent.options.aggregate,
                "lookup_mode": intent.options.native_flags.get("whoisxml_mode", "whois"),
            },
        )

    def render_predicate(self, predicate: Predicate) -> str:
        raise NotImplementedError("WhoisXML compiler uses custom domain extraction instead of predicate rendering.")

    def _collect_group_candidates(
        self,
        group: Group,
        candidates: list[str],
        post_filters: list[str],
    ) -> None:
        if group.operator is LogicOperator.NOT:
            post_filters.append(self._describe_group(group))
            return

        for item in group.items:
            if isinstance(item, Group):
                self._collect_group_candidates(item, candidates, post_filters)
                continue
            self._collect_predicate_candidate(item, candidates, post_filters)

    def _collect_predicate_candidate(
        self,
        predicate: Predicate,
        candidates: list[str],
        post_filters: list[str],
    ) -> None:
        if predicate.field not in {"keyword", "domain", "host"}:
            post_filters.append(self._describe_predicate(predicate))
            return
        if predicate.operator not in {
            ComparisonOperator.EQ,
            ComparisonOperator.CONTAINS,
            ComparisonOperator.IN,
        }:
            post_filters.append(self._describe_predicate(predicate))
            return

        values = predicate.value if isinstance(predicate.value, (list, tuple, set)) else [predicate.value]
        matched = False
        for value in values:
            normalized = self._normalize_hostname_candidate(value)
            if normalized:
                candidates.append(normalized)
                matched = True
        if not matched:
            post_filters.append(self._describe_predicate(predicate))

    def _normalize_hostname_candidate(self, value: object) -> str:
        if value is None:
            return ""
        text = str(value).strip().lower()
        if not text:
            return ""

        if "://" in text:
            parsed = urlparse(text)
            text = (parsed.hostname or "").strip().lower()
        else:
            text = text.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
            if ":" in text and text.count(":") == 1:
                host_part, port_part = text.rsplit(":", 1)
                if port_part.isdigit():
                    text = host_part

        if text.startswith("*."):
            text = text[2:]

        if not text or self._is_ip(text):
            return ""
        if not self._DOMAIN_RE.match(text):
            return ""
        return text

    def _is_ip(self, value: str) -> bool:
        try:
            ipaddress.ip_address(value)
            return True
        except ValueError:
            return False
