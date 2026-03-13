from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from asset_mapping_agent.assets import MergedAssetRecord
from asset_mapping_agent.reporting.xlsx_exporter import AgentWorkbookLogEntry, AgentWorkbookSummary, AssetWorkbookExportResult


SPECIAL_FORMAT_ALIASES = {
    "md": "markdown",
    "markdown": "markdown",
    "json": "json",
    "csv": "csv",
    "txt": "txt",
    "text": "txt",
}


@dataclass(slots=True)
class SpecialReportExporter:
    def export(
        self,
        format_name: str,
        output_path: str | Path,
        *,
        report_result: AssetWorkbookExportResult,
        agent_summary: AgentWorkbookSummary,
        execution_logs: list[AgentWorkbookLogEntry],
        assets: list[MergedAssetRecord],
    ) -> Path:
        normalized_format = self._normalize_format(format_name)
        path = self._normalize_output_path(output_path, normalized_format)
        path.parent.mkdir(parents=True, exist_ok=True)

        if normalized_format == "json":
            path.write_text(
                json.dumps(
                    self._build_json_payload(report_result, agent_summary, execution_logs, assets),
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            return path
        if normalized_format == "csv":
            self._write_csv(path, assets)
            return path
        if normalized_format == "markdown":
            path.write_text(
                self._build_markdown(report_result, agent_summary, execution_logs, assets),
                encoding="utf-8",
            )
            return path
        if normalized_format == "txt":
            path.write_text(
                self._build_text(report_result, agent_summary, execution_logs, assets),
                encoding="utf-8",
            )
            return path
        raise ValueError(f"Unsupported special output format: {format_name}")

    def normalize_requested_format(self, format_name: str) -> str:
        return self._normalize_format(format_name)

    def _normalize_format(self, format_name: str) -> str:
        key = str(format_name or "").strip().lower()
        if key not in SPECIAL_FORMAT_ALIASES:
            raise ValueError(f"Unsupported special output format: {format_name}")
        return SPECIAL_FORMAT_ALIASES[key]

    def _normalize_output_path(self, output_path: str | Path, format_name: str) -> Path:
        path = Path(output_path)
        suffix = {
            "json": ".json",
            "csv": ".csv",
            "markdown": ".md",
            "txt": ".txt",
        }[format_name]
        if not path.suffix:
            return path.with_suffix(suffix)
        return path.with_suffix(suffix)

    def _build_json_payload(
        self,
        report_result: AssetWorkbookExportResult,
        agent_summary: AgentWorkbookSummary,
        execution_logs: list[AgentWorkbookLogEntry],
        assets: list[MergedAssetRecord],
    ) -> dict[str, object]:
        return {
            "report": {
                "total_assets": report_result.total_assets,
                "key_assets": report_result.key_assets,
                "new_assets": report_result.new_assets,
                "invalid_assets": report_result.invalid_assets,
            },
            "agent_summary": {
                "source_text": agent_summary.source_text,
                "subject_name": agent_summary.subject_name,
                "known_domains": list(agent_summary.known_domains),
                "province": agent_summary.province,
                "focus": list(agent_summary.focus),
                "primary_platforms": list(agent_summary.primary_platforms),
                "enrichment_platforms": list(agent_summary.enrichment_platforms),
                "follow_domain_enrichment": agent_summary.follow_domain_enrichment,
                "verify_http": agent_summary.verify_http,
                "verify_tcp": agent_summary.verify_tcp,
                "max_results_per_platform": agent_summary.max_results_per_platform,
                "max_primary_platforms": agent_summary.max_primary_platforms,
                "max_enrichment_rounds": agent_summary.max_enrichment_rounds,
                "max_enrichment_domains_total": agent_summary.max_enrichment_domains_total,
                "max_platform_calls": agent_summary.max_platform_calls,
                "special_output_format": agent_summary.special_output_format,
                "notes": list(agent_summary.notes),
            },
            "execution_logs": [
                {
                    "timestamp": item.timestamp,
                    "stage": item.stage,
                    "message": item.message,
                    "details": dict(item.details),
                }
                for item in execution_logs
            ],
            "assets": [self._build_asset_dict(asset) for asset in assets],
        }

    def _write_csv(self, path: Path, assets: list[MergedAssetRecord]) -> None:
        headers = [
            "asset_id",
            "normalized_key",
            "host",
            "domain",
            "ip",
            "port",
            "scheme",
            "url",
            "title",
            "service",
            "product",
            "org",
            "icp",
            "country",
            "province",
            "city",
            "tags",
            "source_platforms",
        ]
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            for asset in assets:
                writer.writerow(
                    {
                        "asset_id": asset.asset_id,
                        "normalized_key": asset.normalized_key,
                        "host": asset.host,
                        "domain": asset.domain,
                        "ip": asset.ip,
                        "port": asset.port or "",
                        "scheme": asset.scheme,
                        "url": asset.url,
                        "title": asset.title,
                        "service": asset.service,
                        "product": asset.product,
                        "org": asset.org,
                        "icp": asset.icp,
                        "country": asset.geo.country,
                        "province": asset.geo.province,
                        "city": asset.geo.city,
                        "tags": " | ".join(asset.tags),
                        "source_platforms": " | ".join(asset.source_platforms),
                    }
                )

    def _build_markdown(
        self,
        report_result: AssetWorkbookExportResult,
        agent_summary: AgentWorkbookSummary,
        execution_logs: list[AgentWorkbookLogEntry],
        assets: list[MergedAssetRecord],
    ) -> str:
        lines = [
            "# 资产测绘结果",
            "",
            "## 概览",
            f"- 目标主体: {agent_summary.subject_name}",
            f"- 总资产数: {report_result.total_assets}",
            f"- 重点资产数: {report_result.key_assets}",
            f"- 新增资产数: {report_result.new_assets}",
            f"- 无效资产数: {report_result.invalid_assets}",
            "",
            "## Agent 摘要",
            f"- 原始任务: {agent_summary.source_text}",
            f"- 已知域名: {' | '.join(agent_summary.known_domains)}",
            f"- 关注重点: {' | '.join(agent_summary.focus)}",
            f"- 主查询平台: {' | '.join(agent_summary.primary_platforms)}",
            "",
            "## 重点资产",
            "",
            "| 主机 | 标题 | 标签 | 来源平台 |",
            "| --- | --- | --- | --- |",
        ]
        key_assets = [asset for asset in assets if any(tag in {"login_page", "admin_panel"} or tag.startswith("middleware:") for tag in asset.tags)]
        for asset in key_assets[:20]:
            lines.append(
                f"| {asset.host or asset.domain or asset.ip} | {asset.title} | {' | '.join(asset.tags)} | {' | '.join(asset.source_platforms)} |"
            )
        if not key_assets:
            lines.append("| - | - | - | - |")
        lines.extend(
            [
                "",
                "## 执行日志摘要",
                f"- 日志总数: {len(execution_logs)}",
                f"- 重试事件数: {sum(1 for item in execution_logs if item.stage == 'platform_retry')}",
                f"- 降级事件数: {sum(1 for item in execution_logs if item.stage == 'platform_degraded')}",
            ]
        )
        return "\n".join(lines) + "\n"

    def _build_text(
        self,
        report_result: AssetWorkbookExportResult,
        agent_summary: AgentWorkbookSummary,
        execution_logs: list[AgentWorkbookLogEntry],
        assets: list[MergedAssetRecord],
    ) -> str:
        lines = [
            "资产测绘结果",
            f"目标主体: {agent_summary.subject_name}",
            f"原始任务: {agent_summary.source_text}",
            f"总资产数: {report_result.total_assets}",
            f"重点资产数: {report_result.key_assets}",
            f"新增资产数: {report_result.new_assets}",
            f"无效资产数: {report_result.invalid_assets}",
            f"主查询平台: {' | '.join(agent_summary.primary_platforms)}",
            f"执行日志总数: {len(execution_logs)}",
            "",
            "重点资产:",
        ]
        key_assets = [asset for asset in assets if any(tag in {"login_page", "admin_panel"} or tag.startswith("middleware:") for tag in asset.tags)]
        for asset in key_assets[:20]:
            lines.append(
                f"- {asset.host or asset.domain or asset.ip} | {asset.title} | {' | '.join(asset.tags)} | {' | '.join(asset.source_platforms)}"
            )
        if not key_assets:
            lines.append("- 无")
        return "\n".join(lines) + "\n"

    def _build_asset_dict(self, asset: MergedAssetRecord) -> dict[str, object]:
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
            "country": asset.geo.country,
            "province": asset.geo.province,
            "city": asset.geo.city,
            "hostnames": list(asset.hostnames),
            "tags": list(asset.tags),
            "source_platforms": list(asset.source_platforms),
            "source_queries": list(asset.source_queries),
        }
