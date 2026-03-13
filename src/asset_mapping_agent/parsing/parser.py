from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from asset_mapping_agent.query.models import (
    ComparisonOperator,
    Group,
    LogicOperator,
    Predicate,
    QueryIntent,
    QueryOptions,
)


PROVINCE_ALIASES = {
    "北京": "北京市",
    "天津": "天津市",
    "上海": "上海市",
    "重庆": "重庆市",
    "四川": "四川省",
    "广东": "广东省",
    "江苏": "江苏省",
    "浙江": "浙江省",
    "湖北": "湖北省",
    "湖南": "湖南省",
    "河南": "河南省",
    "河北": "河北省",
    "山东": "山东省",
    "福建": "福建省",
    "安徽": "安徽省",
    "江西": "江西省",
    "陕西": "陕西省",
    "山西": "山西省",
    "辽宁": "辽宁省",
    "吉林": "吉林省",
    "黑龙江": "黑龙江省",
    "云南": "云南省",
    "贵州": "贵州省",
    "广西": "广西壮族自治区",
    "内蒙古": "内蒙古自治区",
    "新疆": "新疆维吾尔自治区",
    "西藏": "西藏自治区",
    "宁夏": "宁夏回族自治区",
    "海南": "海南省",
    "甘肃": "甘肃省",
    "青海": "青海省",
    "台湾": "台湾省",
    "香港": "香港特别行政区",
    "澳门": "澳门特别行政区",
}

COMPANY_SUFFIXES = (
    "有限公司",
    "集团",
    "公司",
    "研究院",
    "医院",
    "学校",
    "大学",
    "中心",
    "委员会",
    "银行",
    "学院",
    "局",
    "院",
)

MIDDLEWARE_HINTS = [
    "Jenkins",
    "Nexus",
    "MinIO",
    "GitLab",
    "Grafana",
    "Kibana",
    "Harbor",
    "SonarQube",
    "Nacos",
]

TITLE_KEYWORDS = {
    "登录页": "登录",
    "登录": "登录",
    "后台": "后台",
    "管理后台": "后台",
    "管理系统": "管理",
    "控制台": "控制台",
    "OA": "OA",
}

DOMAIN_RE = re.compile(r"(?<!@)(?:https?://)?(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,63}", re.IGNORECASE)


@dataclass(slots=True)
class ParseResult:
    intent: QueryIntent
    warnings: list[str] = field(default_factory=list)
    extracted_entities: list[str] = field(default_factory=list)
    extracted_locations: list[str] = field(default_factory=list)


class NaturalLanguageQueryParser:
    def parse(self, text: str) -> ParseResult:
        normalized = self._normalize(text)
        warnings: list[str] = []
        targets = self._extract_targets(normalized)
        provinces = self._extract_provinces(normalized)
        port_values = self._extract_ports(normalized)

        predicates: list[Predicate | Group] = []

        if provinces:
            for province in provinces:
                predicates.append(
                    Predicate(
                        field="province",
                        operator=ComparisonOperator.EQ,
                        value=province,
                    )
                )

        title_group = self._build_title_group(normalized)
        if title_group is not None:
            predicates.append(title_group)

        middleware_group = self._build_middleware_group(normalized)
        if middleware_group is not None:
            predicates.append(middleware_group)

        if port_values:
            predicates.append(
                Predicate(
                    field="port",
                    operator=ComparisonOperator.IN,
                    value=port_values,
                )
            )

        options = QueryOptions(
            prefer_active=self._contains_any(normalized, ["有效", "存活", "活跃", "暴露"]),
            include_non_standard_ports=self._contains_any(
                normalized,
                ["非常规端口", "非标准端口", "高位端口", "异常端口"],
            ),
        )

        if not targets:
            warnings.append("No explicit target entity was extracted; later parsing may require manual confirmation.")

        if not predicates:
            warnings.append("No structured filters were extracted; query will rely on target keywords only.")

        intent = QueryIntent(
            targets=targets,
            group=Group(operator=LogicOperator.AND, items=predicates) if predicates else None,
            options=options,
            source_text=text.strip(),
        )
        return ParseResult(
            intent=intent,
            warnings=warnings,
            extracted_entities=targets,
            extracted_locations=provinces,
        )

    def _normalize(self, text: str) -> str:
        return re.sub(r"\s+", "", text.strip())

    def _extract_targets(self, text: str) -> list[str]:
        candidates: list[str] = []

        for domain in self._extract_domains(text):
            self._append_candidate(candidates, domain)

        for suffix in COMPANY_SUFFIXES:
            pattern = rf"[\u4e00-\u9fa5A-Za-z0-9（）()\-]{{2,40}}{suffix}"
            for match in re.findall(pattern, text):
                self._append_candidate(candidates, match)

        leading = re.search(
            r"(?:梳理|查询|查找|查|找|盘点|收集|搜集|测绘)(.+?)(?:在|的|所有|互联网|外网|暴露|资产|系统|域名|网站)",
            text,
        )
        if leading:
            candidate = leading.group(1).strip("，。；、 ")
            if 2 <= len(candidate) <= 60:
                self._append_candidate(candidates, candidate)

        before_location = re.search(r"(.+?)在(?:北京|天津|上海|重庆|四川|广东|江苏|浙江|湖北|湖南|河南|河北)", text)
        if before_location:
            candidate = before_location.group(1)
            candidate = re.sub(r"^(梳理|查询|查找|查|找|盘点|收集|搜集|测绘)", "", candidate)
            candidate = candidate.strip("，。；、 ")
            if 2 <= len(candidate) <= 60:
                self._append_candidate(candidates, candidate)

        return candidates

    def _extract_domains(self, text: str) -> list[str]:
        domains: list[str] = []
        for match in DOMAIN_RE.findall(text):
            cleaned = match.strip().strip("，。；、 ")
            if "://" in cleaned:
                parsed = urlparse(cleaned)
                cleaned = parsed.hostname or ""
            cleaned = cleaned.lower().strip("/")
            if cleaned and cleaned not in domains:
                domains.append(cleaned)
        return domains

    def _append_candidate(self, candidates: list[str], value: str) -> None:
        cleaned = value.strip("，。；、 ")
        if cleaned and cleaned not in candidates:
            candidates.append(cleaned)

    def _extract_provinces(self, text: str) -> list[str]:
        provinces: list[str] = []
        for alias, normalized in PROVINCE_ALIASES.items():
            if alias in text and normalized not in provinces:
                provinces.append(normalized)
        return provinces

    def _extract_ports(self, text: str) -> list[int]:
        ports: list[int] = []
        for match in re.findall(r"(?<!\d)(\d{2,5})(?!\d)", text):
            value = int(match)
            if 1 <= value <= 65535 and value not in ports:
                ports.append(value)
        return ports

    def _build_title_group(self, text: str) -> Group | None:
        title_predicates: list[Predicate] = []
        for hint, keyword in TITLE_KEYWORDS.items():
            if hint in text:
                predicate = Predicate(
                    field="title",
                    operator=ComparisonOperator.CONTAINS,
                    value=keyword,
                )
                if predicate.value not in [item.value for item in title_predicates]:
                    title_predicates.append(predicate)
        if not title_predicates:
            return None
        return Group(operator=LogicOperator.OR, items=title_predicates)

    def _build_middleware_group(self, text: str) -> Group | None:
        if not self._contains_any(text, ["中间件", "控制台", "中间件控制台", "运维平台"]):
            return None
        return Group(
            operator=LogicOperator.OR,
            items=[
                Predicate(
                    field="product",
                    operator=ComparisonOperator.CONTAINS,
                    value=product,
                )
                for product in MIDDLEWARE_HINTS
            ],
        )

    def _contains_any(self, text: str, values: list[str]) -> bool:
        return any(value in text for value in values)
