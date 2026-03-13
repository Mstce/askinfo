from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from asset_mapping_agent.assets import MergedAssetRecord, NormalizedAssetRecord
from asset_mapping_agent.execution import ExecutionBatchResult, QueryExecutionService
from asset_mapping_agent.reporting import AgentWorkbookLogEntry, AgentWorkbookSummary, AssetWorkbookContext
from asset_mapping_agent.workflows import AssetReportWorkflowService

from .models import AgentLogEvent, AgentPlan, AgentRunResult, AgentStage
from .planner import TerminalAgentPlanner


MAX_ENRICHMENT_DOMAINS_PER_ROUND = 5
DOMAIN_MODE_BY_PLATFORM = {
    "securitytrails": "domain",
    "whoisxml": "whois",
}
SUBDOMAIN_MODE_BY_PLATFORM = {
    "securitytrails": "subdomains",
    "whoisxml": "subdomains",
}


@dataclass(slots=True)
class PlatformBudgetState:
    max_platform_calls: int
    max_enrichment_rounds: int
    max_enrichment_domains_total: int
    platform_calls_used: int = 0
    enrichment_rounds_used: int = 0
    enrichment_domains_used: int = 0

    @property
    def remaining_platform_calls(self) -> int:
        return max(self.max_platform_calls - self.platform_calls_used, 0)

    @property
    def remaining_enrichment_domains(self) -> int:
        return max(self.max_enrichment_domains_total - self.enrichment_domains_used, 0)


class TerminalAgentOrchestrator:
    def __init__(
        self,
        planner: TerminalAgentPlanner,
        workflow_service: AssetReportWorkflowService,
    ) -> None:
        self.planner = planner
        self.workflow_service = workflow_service
        self.query_execution_service: QueryExecutionService = workflow_service.query_execution_service

    def run(
        self,
        text: str,
        output_path: str | Path,
        *,
        plan: AgentPlan | None = None,
        include_trace_in_report: bool = False,
        emit_planning_events: bool = True,
        emit: Callable[[AgentLogEvent], None] | None = None,
        baseline_keys: list[str] | None = None,
        http_clients: dict[str, object] | None = None,
        platform_options: dict[str, dict[str, object]] | None = None,
    ) -> AgentRunResult:
        events: list[AgentLogEvent] = []

        def log(stage: AgentStage, message: str, **details: object) -> None:
            event = AgentLogEvent(
                stage=stage,
                message=message,
                timestamp=datetime.now(timezone.utc).isoformat(),
                details={key: value for key, value in details.items() if value not in (None, "", [], {})},
            )
            events.append(event)
            if emit:
                emit(event)

        try:
            if emit_planning_events:
                log(AgentStage.PLANNING_STARTED, "Start planning task with LLM")
            active_plan = plan or self.planner.plan(text)
            budget = PlatformBudgetState(
                max_platform_calls=active_plan.max_platform_calls,
                max_enrichment_rounds=active_plan.max_enrichment_rounds,
                max_enrichment_domains_total=active_plan.max_enrichment_domains_total,
            )
            if emit_planning_events:
                log(
                    AgentStage.PLANNING_COMPLETED,
                    "Planning completed",
                    subject_name=active_plan.subject_name,
                    primary_platforms=active_plan.primary_platforms,
                    enrichment_platforms=active_plan.enrichment_platforms,
                    budget={
                        "max_primary_platforms": active_plan.max_primary_platforms,
                        "max_enrichment_rounds": active_plan.max_enrichment_rounds,
                        "max_enrichment_domains_total": active_plan.max_enrichment_domains_total,
                        "max_platform_calls": active_plan.max_platform_calls,
                    },
                )

            primary_platforms = self._select_primary_platforms(active_plan, budget, events_log=log)
            normalized_assets: list[NormalizedAssetRecord] = []
            platform_records: dict[str, int] = {}

            if primary_platforms:
                log(
                    AgentStage.PRIMARY_QUERY_STARTED,
                    "Start primary asset query",
                    platforms=primary_platforms,
                    remaining_platform_calls=budget.remaining_platform_calls,
                )
                primary_batch = self.query_execution_service.execute_intent(
                    active_plan.primary_intent,
                    primary_platforms,
                    http_clients=http_clients,
                    platform_options=platform_options,
                )
                budget.platform_calls_used += len(primary_batch.executions)
                normalized_assets = list(self.workflow_service.normalizer.normalize_batch(primary_batch))
                self._log_batch_execution_events(primary_batch, events_log=log, phase="primary_query")
                platform_records = {
                    platform: len(execution.search_result.records)
                    for platform, execution in primary_batch.executions.items()
                }
                active_plan, normalized_assets, platform_records = self._retry_primary_query_with_ai_replan(
                    active_plan,
                    normalized_assets,
                    platform_records,
                    budget=budget,
                    events_log=log,
                    http_clients=http_clients,
                    platform_options=platform_options,
                )
            else:
                log(
                    AgentStage.BUDGET_LIMIT_REACHED,
                    "Skip primary query because no platform budget remains",
                    max_platform_calls=active_plan.max_platform_calls,
                )

            log(
                AgentStage.PRIMARY_QUERY_COMPLETED,
                "Primary asset query completed",
                platform_records=platform_records,
                normalized_assets=len(normalized_assets),
                platform_calls_used=budget.platform_calls_used,
            )

            available_enrichment_platforms = [
                platform for platform in active_plan.enrichment_platforms if self._supports_platform(platform)
            ]
            if active_plan.follow_domain_enrichment and available_enrichment_platforms:
                normalized_assets = self._run_domain_enrichment(
                    active_plan,
                    normalized_assets,
                    available_enrichment_platforms,
                    budget=budget,
                    events_log=log,
                    http_clients=http_clients,
                    platform_options=platform_options,
                )

            log(
                AgentStage.ASSET_PROCESSING_STARTED,
                "Start merge, classify and verify",
                normalized_assets=len(normalized_assets),
            )
            merged_assets = self.workflow_service.merger.merge_assets(normalized_assets) if normalized_assets else []
            log(
                AgentStage.MERGE_COMPLETED,
                "Merge completed",
                merged_assets=len(merged_assets),
            )
            tagged_assets = self.workflow_service.tagger.classify_assets(merged_assets)
            log(
                AgentStage.CLASSIFICATION_COMPLETED,
                "Classification completed",
                merged_assets=len(tagged_assets),
                tag_summary=self._build_tag_summary(tagged_assets),
            )
            http_candidates, tcp_candidates = self._count_verification_candidates(tagged_assets, active_plan)
            log(
                AgentStage.VERIFICATION_STARTED,
                "Verification started",
                http_candidates=http_candidates,
                tcp_candidates=tcp_candidates,
            )
            verified_assets = self._verify_assets(tagged_assets, active_plan)
            log(
                AgentStage.VERIFICATION_COMPLETED,
                "Verification completed",
                verified_assets=len(verified_assets),
                http_candidates=http_candidates,
                tcp_candidates=tcp_candidates,
            )
            log(
                AgentStage.ASSET_PROCESSING_COMPLETED,
                "Asset processing completed",
                merged_assets=len(verified_assets),
            )

            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            log(AgentStage.EXPORT_STARTED, "Start exporting xlsx", output_path=str(output_file))
            export_result = self.workflow_service.exporter.export(
                verified_assets,
                output_path=output_file,
                baseline_keys=baseline_keys,
                context=self._build_export_context(active_plan, events) if include_trace_in_report else None,
            )
            log(
                AgentStage.EXPORT_COMPLETED,
                "xlsx export completed",
                output_path=str(export_result.output_path),
                total_assets=export_result.total_assets,
            )

            return AgentRunResult(
                plan=active_plan,
                output_path=export_result.output_path,
                normalized_assets=normalized_assets,
                merged_assets=verified_assets,
                export_result=export_result,
                events=events,
            )
        except Exception as exc:
            log(AgentStage.RUN_FAILED, "Task execution failed", error=str(exc))
            raise

    def _run_domain_enrichment(
        self,
        plan: AgentPlan,
        normalized_assets: list[NormalizedAssetRecord],
        available_platforms: list[str],
        *,
        budget: PlatformBudgetState,
        events_log: Callable[..., None],
        http_clients: dict[str, object] | None,
        platform_options: dict[str, dict[str, object]] | None,
    ) -> list[NormalizedAssetRecord]:
        processed_domains: set[str] = set()
        pending_domains = self._extract_enrichment_domains(plan, normalized_assets)
        subdomain_platforms = [platform for platform in available_platforms if platform in SUBDOMAIN_MODE_BY_PLATFORM]
        calls_per_domain = len(available_platforms) + len(subdomain_platforms)
        round_index = 0

        if budget.max_enrichment_rounds <= 0:
            events_log(
                AgentStage.BUDGET_LIMIT_REACHED,
                "Skip domain enrichment because max_enrichment_rounds is 0",
                max_enrichment_rounds=budget.max_enrichment_rounds,
            )
            return normalized_assets

        if budget.remaining_enrichment_domains <= 0:
            events_log(
                AgentStage.BUDGET_LIMIT_REACHED,
                "Skip domain enrichment because enrichment domain budget is exhausted",
                max_enrichment_domains_total=budget.max_enrichment_domains_total,
            )
            return normalized_assets

        while pending_domains and round_index < budget.max_enrichment_rounds:
            if calls_per_domain > 0 and budget.remaining_platform_calls < calls_per_domain:
                events_log(
                    AgentStage.BUDGET_LIMIT_REACHED,
                    "Stop domain enrichment because remaining platform calls are insufficient",
                    remaining_platform_calls=budget.remaining_platform_calls,
                    required_calls_per_domain=calls_per_domain,
                )
                break

            round_index += 1
            round_limit = min(
                MAX_ENRICHMENT_DOMAINS_PER_ROUND,
                budget.remaining_enrichment_domains,
            )
            affordable_domains = (
                budget.remaining_platform_calls // calls_per_domain if calls_per_domain else round_limit
            )
            if affordable_domains <= 0:
                events_log(
                    AgentStage.BUDGET_LIMIT_REACHED,
                    "Stop domain enrichment because current round budget is exhausted",
                    round=round_index,
                    remaining_platform_calls=budget.remaining_platform_calls,
                    remaining_enrichment_domains=budget.remaining_enrichment_domains,
                )
                break

            current_round: list[str] = []
            for domain in pending_domains:
                if domain not in processed_domains:
                    current_round.append(domain)
                if len(current_round) >= min(round_limit, affordable_domains):
                    break

            if not current_round:
                break

            events_log(
                AgentStage.DOMAIN_ENRICHMENT_STARTED,
                "Start domain enrichment round",
                round=round_index,
                domains=current_round,
                platforms=available_platforms,
                remaining_platform_calls=budget.remaining_platform_calls,
            )

            round_assets: list[NormalizedAssetRecord] = []
            for domain in current_round:
                processed_domains.add(domain)

                domain_assets, domain_calls = self._run_domain_lookup_mode(
                    domain,
                    plan,
                    available_platforms,
                    mode_mapping=DOMAIN_MODE_BY_PLATFORM,
                    http_clients=http_clients,
                    platform_options=platform_options,
                    events_log=events_log,
                    phase="domain_enrichment_domain",
                )
                budget.platform_calls_used += domain_calls
                round_assets.extend(domain_assets)

                subdomain_assets, subdomain_calls = self._run_domain_lookup_mode(
                    domain,
                    plan,
                    subdomain_platforms,
                    mode_mapping=SUBDOMAIN_MODE_BY_PLATFORM,
                    http_clients=http_clients,
                    platform_options=platform_options,
                    events_log=events_log,
                    phase="domain_enrichment_subdomains",
                )
                budget.platform_calls_used += subdomain_calls
                round_assets.extend(subdomain_assets)

            budget.enrichment_rounds_used += 1
            budget.enrichment_domains_used += len(current_round)

            normalized_assets.extend(round_assets)
            discovered_domains = self._extract_domains_from_assets(round_assets)
            pending_domains = [domain for domain in discovered_domains if domain not in processed_domains]

            events_log(
                AgentStage.DOMAIN_ENRICHMENT_COMPLETED,
                "Domain enrichment round completed",
                round=round_index,
                added_assets=len(round_assets),
                next_domains=pending_domains,
                platform_calls_used=budget.platform_calls_used,
                enrichment_domains_used=budget.enrichment_domains_used,
            )

            if pending_domains and budget.enrichment_domains_used >= budget.max_enrichment_domains_total:
                events_log(
                    AgentStage.BUDGET_LIMIT_REACHED,
                    "Stop domain enrichment because max_enrichment_domains_total was reached",
                    max_enrichment_domains_total=budget.max_enrichment_domains_total,
                    processed_domains=budget.enrichment_domains_used,
                    next_domains=pending_domains,
                )
                break

        if pending_domains and budget.enrichment_rounds_used >= budget.max_enrichment_rounds:
            events_log(
                AgentStage.BUDGET_LIMIT_REACHED,
                "Stop domain enrichment because max_enrichment_rounds was reached",
                max_enrichment_rounds=budget.max_enrichment_rounds,
                next_domains=pending_domains,
            )

        return normalized_assets

    def _run_domain_lookup_mode(
        self,
        domain: str,
        plan: AgentPlan,
        platforms: list[str],
        *,
        mode_mapping: dict[str, str],
        http_clients: dict[str, object] | None,
        platform_options: dict[str, dict[str, object]] | None,
        events_log: Callable[..., None] | None = None,
        phase: str = "",
    ) -> tuple[list[NormalizedAssetRecord], int]:
        if not platforms:
            return [], 0
        intent = self.planner.build_domain_intent(domain, plan.max_results_per_platform)
        merged_platform_options = self._merge_platform_options(platform_options, mode_mapping)
        batch = self.query_execution_service.execute_intent(
            intent,
            platforms,
            http_clients=http_clients,
            platform_options=merged_platform_options,
        )
        if events_log:
            self._log_batch_execution_events(batch, events_log=events_log, phase=phase, domain=domain)
        return self.workflow_service.normalizer.normalize_batch(batch), len(batch.executions)

    def _select_primary_platforms(
        self,
        plan: AgentPlan,
        budget: PlatformBudgetState,
        *,
        events_log: Callable[..., None],
    ) -> list[str]:
        trimmed_by_plan = plan.primary_platforms[: plan.max_primary_platforms]
        if len(trimmed_by_plan) < len(plan.primary_platforms):
            events_log(
                AgentStage.BUDGET_LIMIT_REACHED,
                "Primary platforms were limited by max_primary_platforms",
                requested=plan.primary_platforms,
                selected=trimmed_by_plan,
                max_primary_platforms=plan.max_primary_platforms,
            )

        selected = trimmed_by_plan[: budget.remaining_platform_calls]
        if len(selected) < len(trimmed_by_plan):
            events_log(
                AgentStage.BUDGET_LIMIT_REACHED,
                "Primary platforms were limited by remaining platform call budget",
                selected=selected,
                remaining_platform_calls=budget.remaining_platform_calls,
                max_platform_calls=budget.max_platform_calls,
            )
        return selected

    def _retry_primary_query_with_ai_replan(
        self,
        plan: AgentPlan,
        normalized_assets: list[NormalizedAssetRecord],
        platform_records: dict[str, int],
        *,
        budget: PlatformBudgetState,
        events_log: Callable[..., None],
        http_clients: dict[str, object] | None,
        platform_options: dict[str, dict[str, object]] | None,
    ) -> tuple[AgentPlan, list[NormalizedAssetRecord], dict[str, int]]:
        if normalized_assets:
            return plan, normalized_assets, platform_records
        if not plan.primary_platforms:
            return plan, normalized_assets, platform_records
        if budget.remaining_platform_calls <= 0:
            return plan, normalized_assets, platform_records

        replanned = self.planner.replan_for_zero_results(plan.source_text, plan, platform_records)
        if replanned is None:
            return plan, normalized_assets, platform_records

        retry_platforms = self._select_primary_platforms(replanned, budget, events_log=events_log)
        if not retry_platforms:
            return plan, normalized_assets, platform_records

        events_log(
            AgentStage.QUERY_STRATEGY_ADJUSTED,
            "AI revised the primary query strategy after zero results",
            reason="zero_results",
            previous_subject_name=plan.subject_name,
            previous_province=plan.province,
            previous_focus=list(plan.focus),
            new_subject_name=replanned.subject_name,
            new_province=replanned.province,
            new_focus=list(replanned.focus),
            previous_platform_records=platform_records,
        )
        events_log(
            AgentStage.PRIMARY_QUERY_STARTED,
            "Retry primary asset query with AI-adjusted strategy",
            platforms=retry_platforms,
            remaining_platform_calls=budget.remaining_platform_calls,
        )
        retry_batch = self.query_execution_service.execute_intent(
            replanned.primary_intent,
            retry_platforms,
            http_clients=http_clients,
            platform_options=platform_options,
        )
        budget.platform_calls_used += len(retry_batch.executions)
        retry_assets = list(self.workflow_service.normalizer.normalize_batch(retry_batch))
        self._log_batch_execution_events(retry_batch, events_log=events_log, phase="primary_query_replanned")
        retry_records = {
            platform: len(execution.search_result.records)
            for platform, execution in retry_batch.executions.items()
        }
        return replanned, retry_assets, retry_records

    def _log_batch_execution_events(
        self,
        batch: ExecutionBatchResult,
        *,
        events_log: Callable[..., None],
        phase: str,
        domain: str = "",
    ) -> None:
        for execution in batch.executions.values():
            if execution.attempts > 1:
                events_log(
                    AgentStage.PLATFORM_RETRY,
                    "Platform query retried",
                    platform=execution.platform,
                    attempts=execution.attempts,
                    phase=phase,
                    domain=domain,
                )
            if execution.degraded:
                events_log(
                    AgentStage.PLATFORM_DEGRADED,
                    "Platform query degraded after retries",
                    platform=execution.platform,
                    attempts=execution.attempts,
                    error=execution.error,
                    phase=phase,
                    domain=domain,
                )

    def _merge_platform_options(
        self,
        base_options: dict[str, dict[str, object]] | None,
        mode_mapping: dict[str, str],
    ) -> dict[str, dict[str, object]]:
        merged = {key: dict(value) for key, value in (base_options or {}).items()}
        for platform, mode in mode_mapping.items():
            merged.setdefault(platform, {})
            merged[platform]["mode"] = mode
        return merged

    def _extract_enrichment_domains(
        self,
        plan: AgentPlan,
        normalized_assets: list[NormalizedAssetRecord],
    ) -> list[str]:
        values: list[str] = []
        for item in plan.known_domains:
            normalized = self._normalize_domain_candidate(item)
            if normalized and normalized not in values:
                values.append(normalized)
        for candidate in self._extract_domains_from_assets(normalized_assets):
            if candidate not in values:
                values.append(candidate)
        return values[: min(MAX_ENRICHMENT_DOMAINS_PER_ROUND, plan.max_enrichment_domains_total)]

    def _extract_domains_from_assets(self, assets: list[NormalizedAssetRecord]) -> list[str]:
        values: list[str] = []
        for asset in assets:
            for candidate in (asset.domain, asset.host, *asset.hostnames):
                normalized = self._normalize_domain_candidate(candidate)
                if normalized and normalized not in values:
                    values.append(normalized)
        return values

    def _normalize_domain_candidate(self, candidate: object) -> str:
        value = str(candidate or "").strip().lower()
        if not value:
            return ""
        if value.startswith("http://"):
            value = value[7:]
        if value.startswith("https://"):
            value = value[8:]
        value = value.split("/", 1)[0]
        if not value or value.replace(".", "").isdigit():
            return ""
        return value

    def _build_export_context(self, plan: AgentPlan, events: list[AgentLogEvent]) -> AssetWorkbookContext:
        return AssetWorkbookContext(
            agent_summary=AgentWorkbookSummary(
                source_text=plan.source_text,
                subject_name=plan.subject_name,
                known_domains=list(plan.known_domains),
                province=plan.province,
                focus=list(plan.focus),
                primary_platforms=list(plan.primary_platforms),
                enrichment_platforms=list(plan.enrichment_platforms),
                follow_domain_enrichment=plan.follow_domain_enrichment,
                verify_http=plan.verify_http,
                verify_tcp=plan.verify_tcp,
                max_results_per_platform=plan.max_results_per_platform,
                max_primary_platforms=plan.max_primary_platforms,
                max_enrichment_rounds=plan.max_enrichment_rounds,
                max_enrichment_domains_total=plan.max_enrichment_domains_total,
                max_platform_calls=plan.max_platform_calls,
                special_output_format=plan.special_output_format,
                notes=list(plan.notes),
            ),
            execution_logs=[
                AgentWorkbookLogEntry(
                    timestamp=event.timestamp,
                    stage=event.stage.value,
                    message=event.message,
                    details=dict(event.details),
                )
                for event in events
            ],
        )

    def _verify_assets(self, assets: list[MergedAssetRecord], plan: AgentPlan) -> list[MergedAssetRecord]:
        verified_assets: list[MergedAssetRecord] = []
        for asset in assets:
            updated = asset
            if plan.verify_http and self._is_http_candidate(asset):
                updated = replace(
                    updated,
                    verification_results=[
                        *updated.verification_results,
                        self.workflow_service.http_verifier.verify_asset(asset),
                    ],
                )
            elif plan.verify_tcp and self._is_tcp_candidate(asset):
                updated = replace(
                    updated,
                    verification_results=[
                        *updated.verification_results,
                        self.workflow_service.tcp_verifier.verify_asset(asset),
                    ],
                )
            verified_assets.append(updated)
        return verified_assets

    def _count_verification_candidates(self, assets: list[MergedAssetRecord], plan: AgentPlan) -> tuple[int, int]:
        http_candidates = 0
        tcp_candidates = 0
        for asset in assets:
            if plan.verify_http and self._is_http_candidate(asset):
                http_candidates += 1
            elif plan.verify_tcp and self._is_tcp_candidate(asset):
                tcp_candidates += 1
        return http_candidates, tcp_candidates

    def _build_tag_summary(self, assets: list[MergedAssetRecord]) -> dict[str, int]:
        interesting_tags = [
            "login_page",
            "admin_panel",
            "middleware_console",
            "test_environment",
            "portal",
        ]
        summary: dict[str, int] = {}
        for tag in interesting_tags:
            count = sum(1 for asset in assets if tag in asset.tags)
            if count:
                summary[tag] = count
        return summary

    def _is_http_candidate(self, asset: MergedAssetRecord) -> bool:
        return (
            asset.url.startswith(("http://", "https://"))
            or asset.scheme.lower() in {"http", "https"}
            or asset.port in {80, 443}
        )

    def _is_tcp_candidate(self, asset: MergedAssetRecord) -> bool:
        target = asset.host or asset.domain or asset.ip
        return bool(target and asset.port is not None)

    def _supports_platform(self, platform: str) -> bool:
        try:
            self.query_execution_service.adapter_registry.get(platform)
        except KeyError:
            return False
        return True
