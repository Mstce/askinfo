from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from asset_mapping_agent.assets import MergedAssetRecord, NormalizedAssetRecord
from asset_mapping_agent.query import QueryIntent
from asset_mapping_agent.reporting import AssetWorkbookExportResult


class AgentStage(str, Enum):
    PLANNING_STARTED = "planning_started"
    PLANNING_COMPLETED = "planning_completed"
    PLATFORM_RETRY = "platform_retry"
    PLATFORM_DEGRADED = "platform_degraded"
    PRIMARY_QUERY_STARTED = "primary_query_started"
    PRIMARY_QUERY_COMPLETED = "primary_query_completed"
    DOMAIN_ENRICHMENT_STARTED = "domain_enrichment_started"
    DOMAIN_ENRICHMENT_COMPLETED = "domain_enrichment_completed"
    BUDGET_LIMIT_REACHED = "budget_limit_reached"
    ASSET_PROCESSING_STARTED = "asset_processing_started"
    MERGE_COMPLETED = "merge_completed"
    CLASSIFICATION_COMPLETED = "classification_completed"
    VERIFICATION_STARTED = "verification_started"
    VERIFICATION_COMPLETED = "verification_completed"
    ASSET_PROCESSING_COMPLETED = "asset_processing_completed"
    EXPORT_STARTED = "export_started"
    EXPORT_COMPLETED = "export_completed"
    RUN_FAILED = "run_failed"


@dataclass(slots=True)
class AgentLogEvent:
    stage: AgentStage
    message: str
    timestamp: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgentPlan:
    source_text: str
    subject_name: str
    known_domains: list[str]
    province: str
    focus: list[str]
    primary_platforms: list[str]
    enrichment_platforms: list[str]
    special_output_format: str
    follow_domain_enrichment: bool
    verify_http: bool
    verify_tcp: bool
    max_results_per_platform: int
    max_primary_platforms: int
    max_enrichment_rounds: int
    max_enrichment_domains_total: int
    max_platform_calls: int
    primary_intent: QueryIntent
    notes: list[str] = field(default_factory=list)
    raw_plan: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgentRunResult:
    plan: AgentPlan
    output_path: Path
    normalized_assets: list[NormalizedAssetRecord]
    merged_assets: list[MergedAssetRecord]
    export_result: AssetWorkbookExportResult
    events: list[AgentLogEvent] = field(default_factory=list)
