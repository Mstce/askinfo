from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from asset_mapping_agent.assets import MergedAssetRecord


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class TaskStage(str, Enum):
    QUEUED = "queued"
    WORKFLOW_EXECUTION = "workflow_execution"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(slots=True)
class TaskDefinition:
    source_text: str
    platforms: list[str]
    output_path: str
    platform_options: dict[str, dict[str, object]] = field(default_factory=dict)
    baseline_keys: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TaskAuditEntry:
    timestamp: str
    event: str
    detail: str = ""


@dataclass(slots=True)
class TaskQueryRecord:
    platform: str
    compiled_query: str
    filters_used: list[str] = field(default_factory=list)
    post_filters: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    request: dict[str, Any] = field(default_factory=dict)
    response: dict[str, Any] = field(default_factory=dict)
    record_count: int = 0


@dataclass(slots=True)
class TaskReportRecord:
    output_path: str
    total_assets: int
    key_assets: int
    new_assets: int
    invalid_assets: int


@dataclass(slots=True)
class TaskRecord:
    task_id: str
    definition: TaskDefinition
    status: TaskStatus
    current_stage: TaskStage
    created_at: str
    updated_at: str
    parse_warnings: list[str] = field(default_factory=list)
    dsl_json: dict[str, Any] = field(default_factory=dict)
    queries: list[TaskQueryRecord] = field(default_factory=list)
    assets: list[MergedAssetRecord] = field(default_factory=list)
    report: TaskReportRecord | None = None
    error_message: str = ""
    audit_log: list[TaskAuditEntry] = field(default_factory=list)
