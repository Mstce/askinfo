from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from asset_mapping_agent.llm import LlmMessage, StructuredLlmClient
from asset_mapping_agent.parsing.parser import COMPANY_SUFFIXES, DOMAIN_RE, PROVINCE_ALIASES
from asset_mapping_agent.query import (
    ComparisonOperator,
    Group,
    LogicOperator,
    Predicate,
    QueryIntent,
    QueryOptions,
)

from .models import AgentPlan


DEFAULT_PRIMARY_PLATFORMS = ["fofa", "360_quake", "hunter"]
DEFAULT_ENRICHMENT_PLATFORMS = ["securitytrails", "whoisxml"]
DEFAULT_MAX_RESULTS_PER_PLATFORM = 100
DEFAULT_MAX_PRIMARY_PLATFORMS = 3
DEFAULT_MAX_ENRICHMENT_ROUNDS = 2
DEFAULT_MAX_ENRICHMENT_DOMAINS_TOTAL = 10
DEFAULT_MAX_PLATFORM_CALLS = 20
SUPPORTED_SPECIAL_OUTPUTS = {"markdown", "md", "json", "csv", "txt", "text"}
BOOL_TRUE_VALUES = {"1", "true", "yes", "y", "on", "是", "需要", "开启", "启用"}
BOOL_FALSE_VALUES = {"0", "false", "no", "n", "off", "否", "不需要", "关闭", "禁用"}
TASK_PREFIX_RE = re.compile(r"^(?:帮我|请|麻烦|需要|我要|我想|想要)?(?:收集|梳理|盘点|查询|查找|搜集|整理|分析|测绘)?")
GENERIC_SUBJECT_PATTERNS = [
    r"互联网资产",
    r"外网资产",
    r"资产测绘",
    r"资产",
    r"后台",
    r"登录页",
    r"测试环境",
    r"中间件",
    r"控制台",
]
FOCUS_ALIASES = {
    "login": "login_page",
    "login_page": "login_page",
    "登录页": "login_page",
    "登录": "login_page",
    "admin": "admin_panel",
    "admin_panel": "admin_panel",
    "后台": "admin_panel",
    "管理后台": "admin_panel",
    "管理系统": "admin_panel",
    "middleware": "middleware_console",
    "middleware_console": "middleware_console",
    "中间件": "middleware_console",
    "中间件控制台": "middleware_console",
    "控制台": "middleware_console",
    "test": "test_environment",
    "test_environment": "test_environment",
    "测试环境": "test_environment",
    "测试": "test_environment",
    "portal": "portal",
    "门户": "portal",
    "门户页面": "portal",
}
FOCUS_TEXT_HINTS = {
    "login_page": ["登录页", "登录", "signin", "login"],
    "admin_panel": ["后台", "管理后台", "管理系统", "admin"],
    "middleware_console": ["中间件", "控制台", "运维平台", "jenkins", "gitlab", "nacos", "grafana"],
    "test_environment": ["测试环境", "测试", "预发", "uat", "sit", "staging", "demo", "dev"],
    "portal": ["门户", "门户页面", "portal"],
}
MIDDLEWARE_HINTS = ["Jenkins", "Nexus", "MinIO", "GitLab", "Grafana", "Kibana", "Harbor", "SonarQube", "Nacos"]
ENV_HINTS = ["test", "dev", "uat", "sit", "stage", "staging", "demo"]
PLAN_SCHEMA = {
    "subject_name": "string",
    "known_domains": ["string"],
    "province": "string",
    "platforms": ["fofa|360_quake|hunter"],
    "domain_enrichment_platforms": ["securitytrails|whoisxml"],
    "focus": ["login_page|admin_panel|middleware_console|test_environment|portal"],
    "follow_domain_enrichment": "boolean",
    "verify_http": "boolean",
    "verify_tcp": "boolean",
    "max_results_per_platform": "integer",
    "max_primary_platforms": "integer",
    "max_enrichment_rounds": "integer",
    "max_enrichment_domains_total": "integer",
    "max_platform_calls": "integer",
    "special_output_format": "string",
    "notes": ["string"],
}


class TerminalAgentPlanner:
    def __init__(self, llm_client: StructuredLlmClient, prompt_path: str | Path | None = None) -> None:
        self.llm_client = llm_client
        self.prompt_path = Path(prompt_path) if prompt_path else self._default_prompt_path()

    def plan(self, text: str) -> AgentPlan:
        source_text = text.strip()
        prompt = self._load_prompt()
        payload = self.llm_client.complete_json(
            [
                LlmMessage(role="system", content=prompt),
                LlmMessage(role="user", content=self._build_user_prompt(source_text)),
            ],
            response_schema=PLAN_SCHEMA,
        )
        return self.plan_from_payload(payload, source_text=source_text)

    def replan_for_zero_results(self, text: str, previous_plan: AgentPlan, platform_records: dict[str, int]) -> AgentPlan | None:
        source_text = text.strip()
        prompt = self._load_prompt()
        payload = self.llm_client.complete_json(
            [
                LlmMessage(role="system", content=prompt),
                LlmMessage(
                    role="user",
                    content=self._build_zero_result_replan_prompt(
                        source_text=source_text,
                        previous_plan=previous_plan,
                        platform_records=platform_records,
                    ),
                ),
            ],
            response_schema=PLAN_SCHEMA,
        )
        replanned = self.plan_from_payload(payload, source_text=source_text)
        if self._plan_signature(replanned) == self._plan_signature(previous_plan):
            return None
        return replanned

    def plan_from_payload(self, payload: dict[str, Any], *, source_text: str) -> AgentPlan:
        source_text = source_text.strip()
        notes = self._normalize_notes(payload.get("notes"))

        known_domains = self._merge_domains(payload.get("known_domains"), source_text)
        subject_name = self._normalize_subject_name(payload.get("subject_name"), source_text, known_domains, notes)
        province = self._normalize_province_value(payload.get("province"), source_text, notes)
        max_primary_platforms = self._normalize_budget_int(
            payload.get("max_primary_platforms"),
            default=DEFAULT_MAX_PRIMARY_PLATFORMS,
            minimum=1,
            maximum=len(DEFAULT_PRIMARY_PLATFORMS),
            field_name="max_primary_platforms",
            notes=notes,
        )
        max_enrichment_rounds = self._normalize_budget_int(
            payload.get("max_enrichment_rounds"),
            default=DEFAULT_MAX_ENRICHMENT_ROUNDS,
            minimum=0,
            maximum=5,
            field_name="max_enrichment_rounds",
            notes=notes,
        )
        max_enrichment_domains_total = self._normalize_budget_int(
            payload.get("max_enrichment_domains_total"),
            default=DEFAULT_MAX_ENRICHMENT_DOMAINS_TOTAL,
            minimum=0,
            maximum=20,
            field_name="max_enrichment_domains_total",
            notes=notes,
        )
        max_platform_calls = self._normalize_budget_int(
            payload.get("max_platform_calls"),
            default=DEFAULT_MAX_PLATFORM_CALLS,
            minimum=1,
            maximum=50,
            field_name="max_platform_calls",
            notes=notes,
        )
        primary_platforms = self._normalize_primary_platforms(payload.get("platforms"), max_primary_platforms, notes)
        enrichment_platforms = self._normalize_enrichment_platforms(payload.get("domain_enrichment_platforms"), notes)
        focus = self._normalize_focus(payload.get("focus"), source_text, notes)
        special_output_format = self._normalize_special_output_format(payload.get("special_output_format"), source_text, notes)
        follow_domain_enrichment = self._normalize_follow_domain_enrichment(
            payload.get("follow_domain_enrichment"),
            source_text,
            known_domains,
        )
        verify_http = self._normalize_bool(payload.get("verify_http"), default=True)
        verify_tcp = self._normalize_bool(payload.get("verify_tcp"), default=True)
        max_results = self._normalize_max_results(payload.get("max_results_per_platform"), notes)

        primary_intent = self._build_primary_intent(
            subject_name=subject_name,
            known_domains=known_domains,
            province=province,
            focus=focus,
            max_results=max_results,
            source_text=source_text,
        )
        return AgentPlan(
            source_text=source_text,
            subject_name=subject_name,
            known_domains=known_domains,
            province=province,
            focus=focus,
            primary_platforms=primary_platforms,
            enrichment_platforms=enrichment_platforms,
            special_output_format=special_output_format,
            follow_domain_enrichment=follow_domain_enrichment,
            verify_http=verify_http,
            verify_tcp=verify_tcp,
            max_results_per_platform=max_results,
            max_primary_platforms=max_primary_platforms,
            max_enrichment_rounds=max_enrichment_rounds,
            max_enrichment_domains_total=max_enrichment_domains_total,
            max_platform_calls=max_platform_calls,
            primary_intent=primary_intent,
            notes=notes,
            raw_plan=payload,
        )

    def build_domain_intent(self, domain: str, max_results: int) -> QueryIntent:
        return QueryIntent(
            targets=[domain],
            options=QueryOptions(limit=max_results, prefer_active=True),
            source_text=f"domain enrichment: {domain}",
        )

    def _build_user_prompt(self, text: str) -> str:
        return (
            "Task text:\n"
            f"{text}\n\n"
            "Return only a JSON object. If the user does not explicitly request a special format, "
            'special_output_format must be "".'
        )

    def _build_zero_result_replan_prompt(
        self,
        *,
        source_text: str,
        previous_plan: AgentPlan,
        platform_records: dict[str, int],
    ) -> str:
        return (
            "The previous search strategy returned zero results across all primary platforms.\n"
            "Revise the plan to broaden recall while keeping the user's intent.\n"
            "Prefer these adjustments when appropriate:\n"
            "1. Relax title/focus constraints before changing the target subject.\n"
            "2. Remove or broaden province constraints if they may be over-restrictive.\n"
            "3. Keep the same output format and budget unless there is a clear reason to change.\n"
            "4. Do not invent domains unless strongly implied.\n\n"
            f"Original task text:\n{source_text}\n\n"
            "Previous normalized plan:\n"
            f"{self._serialize_plan_snapshot(previous_plan)}\n\n"
            f"Platform record counts: {platform_records}\n\n"
            "Return only a revised JSON object."
        )

    def _load_prompt(self) -> str:
        if self.prompt_path.exists():
            return self.prompt_path.read_text(encoding="utf-8")
        return "You are an asset mapping planning assistant. Return valid JSON only."

    def _serialize_plan_snapshot(self, plan: AgentPlan) -> str:
        snapshot = {
            "subject_name": plan.subject_name,
            "known_domains": list(plan.known_domains),
            "province": plan.province,
            "platforms": list(plan.primary_platforms),
            "domain_enrichment_platforms": list(plan.enrichment_platforms),
            "focus": list(plan.focus),
            "follow_domain_enrichment": plan.follow_domain_enrichment,
            "verify_http": plan.verify_http,
            "verify_tcp": plan.verify_tcp,
            "max_results_per_platform": plan.max_results_per_platform,
            "max_primary_platforms": plan.max_primary_platforms,
            "max_enrichment_rounds": plan.max_enrichment_rounds,
            "max_enrichment_domains_total": plan.max_enrichment_domains_total,
            "max_platform_calls": plan.max_platform_calls,
            "special_output_format": plan.special_output_format,
            "notes": list(plan.notes),
        }
        return str(snapshot)

    def _plan_signature(self, plan: AgentPlan) -> tuple[object, ...]:
        return (
            plan.subject_name,
            tuple(plan.known_domains),
            plan.province,
            tuple(plan.focus),
            tuple(plan.primary_platforms),
            tuple(plan.enrichment_platforms),
            plan.max_results_per_platform,
            plan.max_primary_platforms,
            plan.max_enrichment_rounds,
            plan.max_enrichment_domains_total,
            plan.max_platform_calls,
            plan.special_output_format,
        )

    def _build_primary_intent(
        self,
        *,
        subject_name: str,
        known_domains: list[str],
        province: str,
        focus: list[str],
        max_results: int,
        source_text: str,
    ) -> QueryIntent:
        root_items: list[Predicate | Group] = []
        target_items: list[Predicate] = []
        if subject_name:
            target_items.extend(
                [
                    Predicate(field="keyword", operator=ComparisonOperator.CONTAINS, value=subject_name),
                    Predicate(field="org", operator=ComparisonOperator.CONTAINS, value=subject_name),
                    Predicate(field="icp_org", operator=ComparisonOperator.EQ, value=subject_name),
                ]
            )
        for domain in known_domains:
            target_items.append(Predicate(field="domain", operator=ComparisonOperator.CONTAINS, value=domain))
            target_items.append(Predicate(field="host", operator=ComparisonOperator.CONTAINS, value=domain))
        if target_items:
            root_items.append(Group(operator=LogicOperator.OR, items=target_items))

        if province:
            root_items.append(Predicate(field="province", operator=ComparisonOperator.EQ, value=province))

        root_items.extend(self._build_focus_groups(focus))

        return QueryIntent(
            targets=[],
            group=Group(operator=LogicOperator.AND, items=root_items) if root_items else None,
            options=QueryOptions(limit=max_results, prefer_active=True, include_non_standard_ports=True),
            source_text=source_text,
        )

    def _build_focus_groups(self, focus: list[str]) -> list[Group]:
        groups: list[Group] = []
        if "login_page" in focus:
            groups.append(
                Group(
                    operator=LogicOperator.OR,
                    items=[Predicate(field="title", operator=ComparisonOperator.CONTAINS, value="登录")],
                )
            )
        if "admin_panel" in focus:
            groups.append(
                Group(
                    operator=LogicOperator.OR,
                    items=[
                        Predicate(field="title", operator=ComparisonOperator.CONTAINS, value="后台"),
                        Predicate(field="title", operator=ComparisonOperator.CONTAINS, value="管理"),
                    ],
                )
            )
        if "middleware_console" in focus:
            groups.append(
                Group(
                    operator=LogicOperator.OR,
                    items=[
                        Predicate(field="title", operator=ComparisonOperator.CONTAINS, value="控制台"),
                        *[
                            Predicate(field="product", operator=ComparisonOperator.CONTAINS, value=item)
                            for item in MIDDLEWARE_HINTS
                        ],
                    ],
                )
            )
        if "portal" in focus:
            groups.append(
                Group(
                    operator=LogicOperator.OR,
                    items=[
                        Predicate(field="title", operator=ComparisonOperator.CONTAINS, value="门户"),
                        Predicate(field="title", operator=ComparisonOperator.CONTAINS, value="平台"),
                    ],
                )
            )
        if "test_environment" in focus:
            groups.append(
                Group(
                    operator=LogicOperator.OR,
                    items=[
                        *[
                            Predicate(field="host", operator=ComparisonOperator.CONTAINS, value=item)
                            for item in ENV_HINTS
                        ],
                        Predicate(field="title", operator=ComparisonOperator.CONTAINS, value="测试"),
                    ],
                )
            )
        return groups

    def _normalize_subject_name(
        self,
        raw_value: Any,
        text: str,
        known_domains: list[str],
        notes: list[str],
    ) -> str:
        candidate = self._clean_text(raw_value)
        if self._is_valid_subject_name(candidate):
            return candidate

        fallback = self._extract_subject_from_text(text)
        if fallback:
            notes.append("subject_name was backfilled from task text")
            return fallback

        if known_domains:
            notes.append("subject_name was backfilled from known domain")
            return known_domains[0]

        notes.append("subject_name fell back to source text")
        return text

    def _normalize_primary_platforms(
        self,
        raw_value: Any,
        max_primary_platforms: int,
        notes: list[str],
    ) -> list[str]:
        normalized = self._normalize_platform_values(raw_value)
        values = [item for item in normalized if item in {"fofa", "360_quake", "hunter"}]
        if not values:
            notes.append("primary platforms fell back to defaults")
            values = list(DEFAULT_PRIMARY_PLATFORMS)
        if len(values) > max_primary_platforms:
            notes.append("primary platforms were trimmed by max_primary_platforms")
        return values[:max_primary_platforms]

    def _normalize_enrichment_platforms(self, raw_value: Any, notes: list[str]) -> list[str]:
        normalized = self._normalize_platform_values(raw_value)
        values = [item for item in normalized if item in {"securitytrails", "whoisxml"}]
        if values:
            return values
        return list(DEFAULT_ENRICHMENT_PLATFORMS)

    def _normalize_platform_values(self, raw_value: Any) -> list[str]:
        values: list[str] = []
        for item in raw_value if isinstance(raw_value, list) else []:
            candidate = self._clean_text(item).lower().replace("-", "_")
            if candidate == "quake":
                candidate = "360_quake"
            if candidate and candidate not in values:
                values.append(candidate)
        return values

    def _normalize_focus(self, raw_value: Any, text: str, notes: list[str]) -> list[str]:
        values: list[str] = []
        for item in raw_value if isinstance(raw_value, list) else []:
            candidate = self._map_focus_alias(item)
            if candidate and candidate not in values:
                values.append(candidate)
        for candidate in self._infer_focus_from_text(text):
            if candidate not in values:
                values.append(candidate)
        if not values:
            notes.append("focus fell back to an empty set")
        return values

    def _merge_domains(self, raw_value: Any, text: str) -> list[str]:
        values = self._normalize_domains(raw_value)
        for candidate in self._extract_domains_from_text(text):
            if candidate not in values:
                values.append(candidate)
        return values

    def _normalize_domains(self, raw_value: Any) -> list[str]:
        values: list[str] = []
        for item in raw_value if isinstance(raw_value, list) else []:
            candidate = self._clean_text(item).lower().strip("/")
            if candidate.startswith("http://"):
                candidate = candidate[7:]
            if candidate.startswith("https://"):
                candidate = candidate[8:]
            candidate = candidate.split("/", 1)[0]
            if candidate and candidate not in values:
                values.append(candidate)
        return values

    def _normalize_notes(self, raw_value: Any) -> list[str]:
        values: list[str] = []
        for item in raw_value if isinstance(raw_value, list) else []:
            candidate = self._clean_text(item)
            if candidate and candidate not in values:
                values.append(candidate)
        return values

    def _normalize_province_value(self, raw_value: Any, text: str, notes: list[str]) -> str:
        candidate = self._clean_text(raw_value)
        if candidate in PROVINCE_ALIASES:
            return PROVINCE_ALIASES[candidate]
        if candidate in PROVINCE_ALIASES.values():
            return candidate
        inferred = self._infer_province_from_text(text)
        if inferred:
            if not candidate:
                notes.append("province was backfilled from task text")
            return inferred
        return candidate

    def _normalize_follow_domain_enrichment(self, raw_value: Any, text: str, domains: list[str]) -> bool:
        normalized = self._normalize_bool(raw_value, default=False)
        if normalized:
            return True
        if domains:
            return True
        return any(keyword in text.lower() for keyword in ["域名", "子域", "备案", "whois", "证书"])

    def _normalize_special_output_format(self, raw_value: Any, text: str, notes: list[str]) -> str:
        explicit = self._detect_special_output_format(text)
        if explicit:
            return explicit

        candidate = self._clean_text(raw_value).lower()
        if candidate in SUPPORTED_SPECIAL_OUTPUTS:
            notes.append("special_output_format from LLM was ignored because task text did not explicitly request it")
        return ""

    def _normalize_max_results(self, value: Any, notes: list[str]) -> int:
        try:
            candidate = int(value)
        except (TypeError, ValueError):
            notes.append(f"max_results_per_platform fell back to default {DEFAULT_MAX_RESULTS_PER_PLATFORM}")
            return DEFAULT_MAX_RESULTS_PER_PLATFORM
        normalized = min(max(candidate, 1), 500)
        if normalized != candidate:
            notes.append("max_results_per_platform was clamped into [1, 500]")
        return normalized

    def _normalize_budget_int(
        self,
        value: Any,
        *,
        default: int,
        minimum: int,
        maximum: int,
        field_name: str,
        notes: list[str],
    ) -> int:
        try:
            candidate = int(value)
        except (TypeError, ValueError):
            notes.append(f"{field_name} fell back to default {default}")
            return default
        normalized = min(max(candidate, minimum), maximum)
        if normalized != candidate:
            notes.append(f"{field_name} was clamped into [{minimum}, {maximum}]")
        return normalized

    def _normalize_bool(self, value: Any, *, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return bool(value)
        text = self._clean_text(value).lower()
        if text in BOOL_TRUE_VALUES:
            return True
        if text in BOOL_FALSE_VALUES:
            return False
        return default

    def _extract_subject_from_text(self, text: str) -> str:
        for suffix in COMPANY_SUFFIXES:
            pattern = rf"[\u4e00-\u9fa5A-Za-z0-9（）()\-]{{2,40}}{suffix}"
            matches = re.findall(pattern, text)
            if matches:
                return TASK_PREFIX_RE.sub("", matches[0]).strip("，。；、:： ")

        candidate = TASK_PREFIX_RE.sub("", text).strip("，。；、:： ")
        candidate = re.split(r"(?:在|的|并|，|。|；|重点|关注|输出|导出)", candidate, maxsplit=1)[0]
        candidate = candidate.strip("，。；、:： ")
        for pattern in GENERIC_SUBJECT_PATTERNS:
            candidate = re.sub(pattern, "", candidate)
        candidate = candidate.strip()
        return candidate

    def _extract_domains_from_text(self, text: str) -> list[str]:
        values: list[str] = []
        for match in DOMAIN_RE.findall(text):
            candidate = match.lower().strip().strip("/")
            if candidate.startswith("http://"):
                candidate = candidate[7:]
            if candidate.startswith("https://"):
                candidate = candidate[8:]
            if candidate and candidate not in values:
                values.append(candidate)
        return values

    def _infer_province_from_text(self, text: str) -> str:
        for alias, normalized in PROVINCE_ALIASES.items():
            if alias in text:
                return normalized
        return ""

    def _infer_focus_from_text(self, text: str) -> list[str]:
        lowered = text.lower()
        values: list[str] = []
        for focus, hints in FOCUS_TEXT_HINTS.items():
            if any(hint.lower() in lowered for hint in hints):
                values.append(focus)
        return values

    def _detect_special_output_format(self, text: str) -> str:
        lowered = text.lower()
        if re.search(r"\bmarkdown\b", lowered) or re.search(r"\bmd\b", lowered) or "markdown格式" in text:
            return "markdown"
        if re.search(r"\bjson\b", lowered):
            return "json"
        if re.search(r"\bcsv\b", lowered):
            return "csv"
        if re.search(r"\btxt\b", lowered) or "纯文本" in text or "文本格式" in text:
            return "txt"
        return ""

    def _map_focus_alias(self, value: Any) -> str:
        cleaned = self._clean_text(value)
        lowered = cleaned.lower()
        return FOCUS_ALIASES.get(cleaned, FOCUS_ALIASES.get(lowered, ""))

    def _is_valid_subject_name(self, value: str) -> bool:
        candidate = value.strip()
        if not candidate:
            return False
        if len(candidate) <= 1:
            return False
        if " " in candidate and len(candidate.split()) > 8:
            return False
        if candidate.endswith(("资产", "系统", "平台")) and len(candidate) <= 6:
            return False
        return True

    def _clean_text(self, value: Any) -> str:
        return str(value or "").strip()

    def _default_prompt_path(self) -> Path:
        return Path(__file__).resolve().parents[3] / "prompts" / "intent_and_plan.md"
