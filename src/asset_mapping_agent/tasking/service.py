from __future__ import annotations

from dataclasses import fields, is_dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from asset_mapping_agent.assets import MergedAssetRecord
from asset_mapping_agent.tasking.models import (
    TaskAuditEntry,
    TaskDefinition,
    TaskQueryRecord,
    TaskRecord,
    TaskReportRecord,
    TaskStage,
    TaskStatus,
)
from asset_mapping_agent.workflows import AssetReportWorkflowService


SENSITIVE_KEYS = {"key", "api-key", "api_key", "apikey", "authorization", "x-quaketoken"}


class TaskNotFoundError(KeyError):
    pass


class InMemoryTaskService:
    def __init__(
        self,
        workflow_service: AssetReportWorkflowService,
        *,
        reports_dir: str | Path = "task_reports",
        http_clients: dict[str, object] | None = None,
        http_fetcher: object | None = None,
        tcp_connector: object | None = None,
    ) -> None:
        self.workflow_service = workflow_service
        self.reports_dir = Path(reports_dir)
        self.http_clients = http_clients or {}
        self.http_fetcher = http_fetcher
        self.tcp_connector = tcp_connector
        self._tasks: dict[str, TaskRecord] = {}
        self._lock = Lock()

    def create_task(
        self,
        *,
        source_text: str,
        platforms: list[str],
        output_path: str | None = None,
        platform_options: dict[str, dict[str, object]] | None = None,
        baseline_keys: list[str] | None = None,
    ) -> TaskRecord:
        task_id = uuid4().hex
        normalized_output_path = str(self._normalize_output_path(task_id, output_path))
        now = self._now()
        definition = TaskDefinition(
            source_text=source_text,
            platforms=list(platforms),
            output_path=normalized_output_path,
            platform_options=dict(platform_options or {}),
            baseline_keys=list(baseline_keys or []),
        )
        task = TaskRecord(
            task_id=task_id,
            definition=definition,
            status=TaskStatus.PENDING,
            current_stage=TaskStage.QUEUED,
            created_at=now,
            updated_at=now,
            audit_log=[TaskAuditEntry(timestamp=now, event="task_created", detail="任务已创建")],
        )
        with self._lock:
            self._tasks[task_id] = task
        return task

    def run_task(self, task_id: str) -> TaskRecord:
        task = self.get_task(task_id)
        if task.status is TaskStatus.RUNNING:
            return task
        if task.status is TaskStatus.SUCCEEDED:
            return task

        self._transition(task_id, status=TaskStatus.RUNNING, stage=TaskStage.WORKFLOW_EXECUTION)
        self._append_audit(task_id, "task_running", "开始执行工作流")
        task = self.get_task(task_id)

        try:
            result = self.workflow_service.execute_text_to_xlsx(
                task.definition.source_text,
                task.definition.platforms,
                task.definition.output_path,
                http_clients=self.http_clients,
                platform_options=task.definition.platform_options,
                baseline_keys=task.definition.baseline_keys,
                http_fetcher=self.http_fetcher,
                tcp_connector=self.tcp_connector,
            )
            queries = self._build_query_records(result.batch.executions)
            report = TaskReportRecord(
                output_path=str(result.export_result.output_path),
                total_assets=result.export_result.total_assets,
                key_assets=result.export_result.key_assets,
                new_assets=result.export_result.new_assets,
                invalid_assets=result.export_result.invalid_assets,
            )
            with self._lock:
                current = self._require_task(task_id)
                updated = replace(
                    current,
                    status=TaskStatus.SUCCEEDED,
                    current_stage=TaskStage.COMPLETED,
                    updated_at=self._now(),
                    parse_warnings=list(result.batch.parse_warnings),
                    dsl_json=self._serialize_value(result.batch.intent),
                    queries=queries,
                    assets=list(result.merged_assets),
                    report=report,
                    error_message="",
                )
                self._tasks[task_id] = updated
            self._append_audit(task_id, "task_succeeded", f"任务完成，输出 {report.total_assets} 条资产")
        except Exception as exc:
            with self._lock:
                current = self._require_task(task_id)
                updated = replace(
                    current,
                    status=TaskStatus.FAILED,
                    current_stage=TaskStage.FAILED,
                    updated_at=self._now(),
                    error_message=str(exc),
                )
                self._tasks[task_id] = updated
            self._append_audit(task_id, "task_failed", str(exc))

        return self.get_task(task_id)

    def get_task(self, task_id: str) -> TaskRecord:
        with self._lock:
            return self._require_task(task_id)

    def list_task_queries(self, task_id: str) -> list[dict[str, Any]]:
        task = self.get_task(task_id)
        return [self._serialize_value(query) for query in task.queries]

    def list_task_assets(self, task_id: str) -> list[dict[str, Any]]:
        task = self.get_task(task_id)
        return [self._serialize_asset(asset) for asset in task.assets]

    def list_task_audit_log(self, task_id: str) -> list[dict[str, Any]]:
        task = self.get_task(task_id)
        return [self._serialize_value(entry) for entry in task.audit_log]

    def list_tasks(self) -> list[dict[str, Any]]:
        with self._lock:
            task_ids = [
                task.task_id
                for task in sorted(self._tasks.values(), key=lambda item: item.updated_at, reverse=True)
            ]
        return [self.serialize_task(task_id) for task_id in task_ids]

    def get_report_path(self, task_id: str) -> Path | None:
        task = self.get_task(task_id)
        if task.report is None:
            return None
        return Path(task.report.output_path)

    def serialize_task(self, task_id: str) -> dict[str, Any]:
        task = self.get_task(task_id)
        payload = {
            "task_id": task.task_id,
            "source_text": task.definition.source_text,
            "platforms": list(task.definition.platforms),
            "output_path": task.definition.output_path,
            "status": task.status.value,
            "current_stage": task.current_stage.value,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
            "parse_warnings": list(task.parse_warnings),
            "dsl_json": task.dsl_json,
            "query_count": len(task.queries),
            "asset_count": len(task.assets),
            "error_message": task.error_message,
            "audit_log": [self._serialize_value(entry) for entry in task.audit_log],
            "report": self._serialize_value(task.report) if task.report else None,
        }
        return payload

    def _build_query_records(self, executions: dict[str, Any]) -> list[TaskQueryRecord]:
        records: list[TaskQueryRecord] = []
        for platform, execution in executions.items():
            search_result = execution.search_result
            request_summary = self._sanitize_request(search_result.request)
            response_summary = {
                "status_code": search_result.response.status_code,
                "ok": search_result.response.ok,
                "error": search_result.response.error,
                "attempts": execution.attempts,
                "degraded": execution.degraded,
                "execution_error": execution.error,
                "pagination": self._serialize_value(search_result.pagination),
            }
            records.append(
                TaskQueryRecord(
                    platform=platform,
                    compiled_query=execution.compiled_query.query,
                    filters_used=list(execution.compiled_query.filters_used),
                    post_filters=list(execution.compiled_query.post_filters),
                    warnings=list(execution.compiled_query.warnings) + list(search_result.warnings),
                    request=request_summary,
                    response=response_summary,
                    record_count=len(search_result.records),
                )
            )
        return records

    def _sanitize_request(self, request: Any) -> dict[str, Any]:
        params = {
            key: self._mask_sensitive_value(key, value)
            for key, value in getattr(request, "params", {}).items()
        }
        headers = {
            key: self._mask_sensitive_value(key, value)
            for key, value in getattr(request, "headers", {}).items()
        }
        return {
            "method": getattr(request, "method", ""),
            "url": getattr(request, "url", ""),
            "params": self._serialize_value(params),
            "headers": self._serialize_value(headers),
            "metadata": self._serialize_value(getattr(request, "metadata", {})),
        }

    def _mask_sensitive_value(self, key: str, value: Any) -> Any:
        normalized_key = key.strip().lower()
        if normalized_key in SENSITIVE_KEYS:
            return "***"
        return value

    def _serialize_asset(self, asset: MergedAssetRecord) -> dict[str, Any]:
        return {
            "asset_id": asset.asset_id,
            "normalized_key": asset.normalized_key,
            "host": asset.host,
            "domain": asset.domain,
            "ip": asset.ip,
            "port": asset.port,
            "scheme": asset.scheme,
            "url": asset.url,
            "title": asset.title,
            "service": asset.service,
            "product": asset.product,
            "org": asset.org,
            "icp": asset.icp,
            "geo": self._serialize_value(asset.geo),
            "hostnames": list(asset.hostnames),
            "tags": list(asset.tags),
            "source_platforms": list(asset.source_platforms),
            "source_queries": list(asset.source_queries),
            "conflict_fields": self._serialize_value(asset.conflict_fields),
            "raw_record_count": len(asset.raw_records),
            "verification_results": [self._serialize_value(item) for item in asset.verification_results],
        }

    def _transition(self, task_id: str, *, status: TaskStatus, stage: TaskStage) -> None:
        with self._lock:
            current = self._require_task(task_id)
            self._tasks[task_id] = replace(
                current,
                status=status,
                current_stage=stage,
                updated_at=self._now(),
            )

    def _append_audit(self, task_id: str, event: str, detail: str = "") -> None:
        with self._lock:
            current = self._require_task(task_id)
            audit_log = list(current.audit_log)
            audit_log.append(TaskAuditEntry(timestamp=self._now(), event=event, detail=detail))
            self._tasks[task_id] = replace(current, audit_log=audit_log, updated_at=self._now())

    def _normalize_output_path(self, task_id: str, output_path: str | None) -> Path:
        if output_path:
            return Path(output_path)
        return self.reports_dir / f"task_{task_id}.xlsx"

    def _require_task(self, task_id: str) -> TaskRecord:
        if task_id not in self._tasks:
            raise TaskNotFoundError(task_id)
        return self._tasks[task_id]

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _serialize_value(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, Path):
            return str(value)
        if is_dataclass(value):
            return {field.name: self._serialize_value(getattr(value, field.name)) for field in fields(value)}
        if isinstance(value, dict):
            return {str(key): self._serialize_value(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._serialize_value(item) for item in value]
        return value

