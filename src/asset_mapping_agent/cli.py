from __future__ import annotations

import argparse
import json
import os
import sys
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any

from asset_mapping_agent.adapters import (
    AdapterRegistry,
    FofaAdapter,
    FofaCredentials,
    HunterAdapter,
    HunterCredentials,
    QuakeAdapter,
    QuakeCredentials,
    SecurityTrailsAdapter,
    SecurityTrailsCredentials,
    ShodanAdapter,
    ShodanCredentials,
    UrlscanAdapter,
    UrlscanCredentials,
    WhoisXmlAdapter,
    WhoisXmlCredentials,
)
from asset_mapping_agent.agent import AgentLogEvent, AgentPlan, AgentStage, TerminalAgentOrchestrator, TerminalAgentPlanner
from asset_mapping_agent.config import RuntimeSettings
from asset_mapping_agent.execution import QueryExecutionService
from asset_mapping_agent.llm import OpenAICompatibleLlmClient
from asset_mapping_agent.query import CompilerRegistry
from asset_mapping_agent.reporting import (
    AgentWorkbookLogEntry,
    AgentWorkbookSummary,
    SpecialReportExporter,
)
from asset_mapping_agent.workflows import AssetReportWorkflowService


PLATFORM_DISPLAY_NAMES = {
    "fofa": "FOFA",
    "quake": "360 Quake",
    "360_quake": "360 Quake",
    "hunter": "Hunter",
    "shodan": "Shodan",
    "urlscan": "urlscan",
    "securitytrails": "SecurityTrails",
    "whoisxml": "WhoisXML",
}


def build_adapter_registry(settings: RuntimeSettings) -> AdapterRegistry:
    registry = AdapterRegistry()
    if settings.fofa_email and settings.fofa_api_key:
        registry.register(FofaAdapter(FofaCredentials(email=settings.fofa_email, api_key=settings.fofa_api_key)))
    if settings.quake_api_key:
        registry.register(QuakeAdapter(QuakeCredentials(api_key=settings.quake_api_key)), "360_quake", "360-quake")
    if settings.hunter_api_key:
        registry.register(HunterAdapter(HunterCredentials(api_key=settings.hunter_api_key)))
    if settings.shodan_api_key:
        registry.register(ShodanAdapter(ShodanCredentials(api_key=settings.shodan_api_key)))
    if settings.urlscan_api_key:
        registry.register(UrlscanAdapter(UrlscanCredentials(api_key=settings.urlscan_api_key)))
    if settings.securitytrails_api_key:
        registry.register(SecurityTrailsAdapter(SecurityTrailsCredentials(api_key=settings.securitytrails_api_key)))
    if settings.whoisxml_api_key:
        registry.register(WhoisXmlAdapter(WhoisXmlCredentials(api_key=settings.whoisxml_api_key)))
    return registry


def build_output_paths(text: str, output: str | None, plan: AgentPlan) -> tuple[Path, Path]:
    if output:
        final_output = Path(output)
    else:
        safe_name = _build_default_output_name(plan, fallback_text=text)
        extension = _special_format_to_suffix(plan.special_output_format)
        final_output = Path(".\\tmp") / f"{safe_name}{extension}"

    if not plan.special_output_format:
        return final_output.with_suffix(".xlsx"), final_output.with_suffix(".xlsx")

    xlsx_output = final_output.with_suffix(".xlsx")
    return xlsx_output, final_output


def print_event(event: AgentLogEvent) -> None:
    for line in format_event_lines(event):
        print(line, flush=True)


def print_status(message: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)


def prompt_open_asset_workbook(output_path: Path) -> bool:
    if output_path.suffix.lower() != ".xlsx":
        return False
    if not output_path.exists():
        return False
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return False

    try:
        choice = _read_open_workbook_choice()
    except EOFError:
        return False
    except KeyboardInterrupt:
        print()
        return False

    if choice != "1":
        return False

    try:
        if hasattr(os, "startfile"):
            os.startfile(str(output_path.resolve()))  # type: ignore[attr-defined]
        else:
            webbrowser.open(output_path.resolve().as_uri())
        print_status(f"已打开资产表：{output_path}")
        return True
    except Exception as exc:
        print_status(f"打开资产表失败：{exc}")
        return False


def _read_open_workbook_choice() -> str:
    if os.name == "nt":
        import msvcrt

        print("按 1 打开资产表，其他任意键退出：", end="", flush=True)
        first = msvcrt.getwch()
        if first in {"\x00", "\xe0"}:
            msvcrt.getwch()
            first = ""
        print()
        return first.strip()

    return input("按 1 打开资产表，其他任意键退出：").strip()


def format_event_lines(event: AgentLogEvent) -> list[str]:
    timestamp = _format_event_time(event.timestamp)
    prefix = f"[{timestamp}]"
    details = event.details
    lines: list[str] = []
    indent = " " * (len(prefix) + 1)

    if event.stage.value == "planning_started":
        return [f"{prefix} 开始规划：正在用 AI 解析任务意图"]

    if event.stage.value == "planning_completed":
        lines.append(f"{prefix} 规划完成")
        lines.append(f"{indent}目标: {details.get('subject_name') or '未识别'}")
        primary_platforms = _format_platform_list(details.get("primary_platforms"))
        if primary_platforms:
            lines.append(f"{indent}主平台: {primary_platforms}")
        enrichment_platforms = _format_platform_list(details.get("enrichment_platforms"))
        if enrichment_platforms:
            lines.append(f"{indent}补查平台: {enrichment_platforms}")
        budget = details.get("budget") if isinstance(details.get("budget"), dict) else {}
        if budget:
            budget_text = (
                f"主查询最多 {budget.get('max_primary_platforms', '-') } 个平台，"
                f"补查 {budget.get('max_enrichment_rounds', '-') } 轮，"
                f"最多 {budget.get('max_platform_calls', '-') } 次平台调用"
            )
            lines.append(f"{indent}预算: {budget_text}")
        return lines

    if event.stage.value == "primary_query_started":
        platforms = _format_platform_list(details.get("platforms")) or "未指定"
        remaining = details.get("remaining_platform_calls", "-")
        return [f"{prefix} 开始主查询：{platforms}，剩余平台调用预算 {remaining}"]

    if event.stage.value == "primary_query_completed":
        normalized_assets = details.get("normalized_assets", 0)
        lines.append(f"{prefix} 主查询完成：当前标准化资产 {normalized_assets} 条")
        platform_records = details.get("platform_records")
        platform_text = _format_platform_records(platform_records)
        if platform_text:
            lines.append(f"{indent}平台结果: {platform_text}")
        platform_calls_used = details.get("platform_calls_used")
        if platform_calls_used not in (None, ""):
            lines.append(f"{indent}已消耗平台调用: {platform_calls_used}")
        return lines

    if event.stage.value == "domain_enrichment_started":
        round_index = details.get("round", "-")
        domains = _format_domain_list(details.get("domains"))
        platforms = _format_platform_list(details.get("platforms"))
        return [
            f"{prefix} 开始域名补查：第 {round_index} 轮",
            f"{indent}域名: {domains or '无'}",
            f"{indent}平台: {platforms or '无'}",
        ]

    if event.stage.value == "domain_enrichment_completed":
        lines.append(
            f"{prefix} 域名补查完成：第 {details.get('round', '-')} 轮，新增 {details.get('added_assets', 0)} 条资产"
        )
        next_domains = _format_domain_list(details.get("next_domains"))
        if next_domains:
            lines.append(f"{indent}下一轮待查: {next_domains}")
        return lines

    if event.stage.value == "budget_limit_reached":
        message = _translate_budget_message(event.message, details)
        lines.append(f"{prefix} 预算限制：{message}")
        return lines

    if event.stage.value == "platform_retry":
        platform = _format_platform_name(details.get("platform"))
        attempts = details.get("attempts", "-")
        phase = _format_phase(details.get("phase"))
        return [f"{prefix} 平台重试：{platform} 第 {attempts} 次，阶段={phase}"]

    if event.stage.value == "platform_degraded":
        platform = _format_platform_name(details.get("platform"))
        attempts = details.get("attempts", "-")
        phase = _format_phase(details.get("phase"))
        error = str(details.get("error") or "").strip()
        line = f"{prefix} 平台降级：{platform} 连续失败后已跳过，阶段={phase}，重试 {attempts} 次"
        if error:
            line = f"{line}，原因={error}"
        return [line]

    if event.stage.value == "asset_processing_started":
        count = details.get("normalized_assets", 0)
        return [f"{prefix} 开始资产处理：待处理 {count} 条标准化资产"]

    if event.stage.value == "merge_completed":
        return [f"{prefix} 归并完成：当前合并后 {details.get('merged_assets', 0)} 条资产"]

    if event.stage.value == "classification_completed":
        lines.append(f"{prefix} 分类完成：已完成标签识别")
        tag_summary = details.get("tag_summary")
        if isinstance(tag_summary, dict) and tag_summary:
            lines.append(f"{indent}重点标签: {_format_tag_summary(tag_summary)}")
        return lines

    if event.stage.value == "verification_started":
        http_count = details.get("http_candidates", 0)
        tcp_count = details.get("tcp_candidates", 0)
        return [f"{prefix} 开始有效性验证：HTTP {http_count} 条，TCP {tcp_count} 条"]

    if event.stage.value == "verification_completed":
        verified_assets = details.get("verified_assets", 0)
        return [f"{prefix} 有效性验证完成：已处理 {verified_assets} 条资产"]

    if event.stage.value == "asset_processing_completed":
        return [f"{prefix} 资产处理完成：合并后 {details.get('merged_assets', 0)} 条资产"]

    if event.stage.value == "export_started":
        return [f"{prefix} 开始导出报告：{details.get('output_path') or ''}".rstrip()]

    if event.stage.value == "export_completed":
        return [f"{prefix} 导出完成：{details.get('output_path') or ''}，共 {details.get('total_assets', 0)} 条资产"]

    if event.stage.value == "run_failed":
        return [f"{prefix} 执行失败：{details.get('error') or event.message}"]

    detail_text = _format_key_value_details(details)
    if detail_text:
        return [f"{prefix} {event.message}：{detail_text}"]
    return [f"{prefix} {event.message}"]


def _format_event_time(timestamp: str) -> str:
    try:
        return datetime.fromisoformat(timestamp).astimezone().strftime("%H:%M:%S")
    except Exception:
        return timestamp


def _format_platform_name(platform: object) -> str:
    value = str(platform or "").strip().lower().replace("-", "_")
    return PLATFORM_DISPLAY_NAMES.get(value, str(platform or "").strip() or "未知平台")


def _format_platform_list(platforms: object) -> str:
    if not isinstance(platforms, list):
        return ""
    values = [_format_platform_name(item) for item in platforms if str(item or "").strip()]
    return " / ".join(values)


def _format_platform_records(records: object) -> str:
    if not isinstance(records, dict):
        return ""
    parts: list[str] = []
    for platform, count in records.items():
        parts.append(f"{_format_platform_name(platform)} {count} 条")
    return "，".join(parts)


def _format_domain_list(domains: object) -> str:
    if not isinstance(domains, list):
        return ""
    values = [str(item).strip() for item in domains if str(item).strip()]
    if not values:
        return ""
    if len(values) > 4:
        return "，".join(values[:4]) + f" 等 {len(values)} 个"
    return "，".join(values)


def _format_phase(phase: object) -> str:
    value = str(phase or "").strip().lower()
    mapping = {
        "primary_query": "主查询",
        "domain_enrichment_domain": "域名详情补查",
        "domain_enrichment_subdomains": "子域补查",
    }
    return mapping.get(value, value or "未知阶段")


def _translate_budget_message(message: str, details: dict[str, Any]) -> str:
    if "max_primary_platforms" in details and "selected" in details:
        return (
            f"主查询平台已裁剪为 {_format_platform_list(details.get('selected'))}，"
            f"上限 {details.get('max_primary_platforms')}"
        )
    if "remaining_platform_calls" in details and "required_calls_per_domain" in details:
        return (
            f"剩余平台调用不足以继续域名补查，剩余 {details.get('remaining_platform_calls')} 次，"
            f"每个域名至少需要 {details.get('required_calls_per_domain')} 次"
        )
    if "max_enrichment_rounds" in details:
        return f"域名补查达到轮次上限 {details.get('max_enrichment_rounds')}"
    if "max_enrichment_domains_total" in details:
        return f"域名补查达到域名数量上限 {details.get('max_enrichment_domains_total')}"
    if "max_platform_calls" in details:
        return f"平台调用达到预算上限 {details.get('max_platform_calls')}"
    return message


def _format_key_value_details(details: dict[str, Any]) -> str:
    parts: list[str] = []
    for key, value in details.items():
        if isinstance(value, list):
            parts.append(f"{key}={','.join(str(item) for item in value)}")
        elif isinstance(value, dict):
            parts.append(f"{key}={json.dumps(value, ensure_ascii=False)}")
        else:
            parts.append(f"{key}={value}")
    return "；".join(parts)


def _format_tag_summary(summary: dict[str, int]) -> str:
    label_map = {
        "login_page": "登录页",
        "admin_panel": "后台",
        "middleware_console": "中间件控制台",
        "test_environment": "测试环境",
        "portal": "门户",
    }
    parts: list[str] = []
    for key, count in summary.items():
        parts.append(f"{label_map.get(key, key)} {count} 条")
    return "，".join(parts)


def _build_default_output_name(plan: AgentPlan, fallback_text: str = "") -> str:
    for candidate in [plan.subject_name, *(plan.known_domains or []), fallback_text]:
        cleaned = _sanitize_filename_component(str(candidate or ""))
        if cleaned:
            return f"{cleaned}_资产清单"
    return "asset_inventory"


def _sanitize_filename_component(value: str) -> str:
    text = value.strip()
    if not text:
        return ""
    cleaned = "".join(char if char.isalnum() or char in "-_." else "_" for char in text).strip("_.")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned[:64].strip("_.")


def diagnose_runtime(settings: RuntimeSettings) -> tuple[dict[str, str], list[str], list[str], list[str]]:
    statuses = {
        "OPENAI_API_KEY": "configured" if settings.openai_api_key else "missing",
        "FOFA": "configured" if settings.fofa_email and settings.fofa_api_key else "missing",
        "360_Quake": "configured" if settings.quake_api_key else "missing",
        "Hunter": "configured" if settings.hunter_api_key else "missing",
        "Shodan": "configured" if settings.shodan_api_key else "missing",
        "urlscan": "configured" if settings.urlscan_api_key else "missing",
        "SecurityTrails": "configured" if settings.securitytrails_api_key else "missing",
        "WhoisXML": "configured" if settings.whoisxml_api_key else "missing",
    }
    primary_platforms = [
        platform
        for platform, status in (
            ("fofa", statuses["FOFA"]),
            ("quake", statuses["360_Quake"]),
            ("hunter", statuses["Hunter"]),
            ("shodan", statuses["Shodan"]),
            ("urlscan", statuses["urlscan"]),
        )
        if status == "configured"
    ]
    enrichment_platforms = [
        platform
        for platform, status in (
            ("securitytrails", statuses["SecurityTrails"]),
            ("whoisxml", statuses["WhoisXML"]),
        )
        if status == "configured"
    ]
    blockers: list[str] = []
    if statuses["OPENAI_API_KEY"] != "configured":
        blockers.append("missing OPENAI_API_KEY")
    if not primary_platforms:
        blockers.append("no primary platform credentials configured")
    return statuses, primary_platforms, enrichment_platforms, blockers


def run_doctor(settings: RuntimeSettings) -> int:
    statuses, primary_platforms, enrichment_platforms, blockers = diagnose_runtime(settings)
    print("Terminal Agent Doctor")
    for key, value in statuses.items():
        print(f"- {key}: {value}")
    print(f"- primary_platforms: {', '.join(primary_platforms) if primary_platforms else 'none'}")
    print(f"- enrichment_platforms: {', '.join(enrichment_platforms) if enrichment_platforms else 'none'}")
    if blockers:
        print(f"- status: blocked ({'; '.join(blockers)})")
        return 2
    print("- status: ready")
    return 0


def serialize_plan(plan: AgentPlan) -> dict[str, Any]:
    return {
        "source_text": plan.source_text,
        "subject_name": plan.subject_name,
        "known_domains": list(plan.known_domains),
        "province": plan.province,
        "focus": list(plan.focus),
        "primary_platforms": list(plan.primary_platforms),
        "enrichment_platforms": list(plan.enrichment_platforms),
        "special_output_format": plan.special_output_format,
        "follow_domain_enrichment": plan.follow_domain_enrichment,
        "verify_http": plan.verify_http,
        "verify_tcp": plan.verify_tcp,
        "max_results_per_platform": plan.max_results_per_platform,
        "max_primary_platforms": plan.max_primary_platforms,
        "max_enrichment_rounds": plan.max_enrichment_rounds,
        "max_enrichment_domains_total": plan.max_enrichment_domains_total,
        "max_platform_calls": plan.max_platform_calls,
        "notes": list(plan.notes),
        "raw_plan": dict(plan.raw_plan),
    }


def load_plan_from_file(path: str | Path, planner: TerminalAgentPlanner, fallback_text: str = "") -> AgentPlan:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("plan file must contain a JSON object")

    raw_plan = payload.get("raw_plan")
    if isinstance(raw_plan, dict):
        normalized_payload = dict(raw_plan)
    else:
        normalized_payload = dict(payload)

    if "platforms" not in normalized_payload and isinstance(payload.get("primary_platforms"), list):
        normalized_payload["platforms"] = payload.get("primary_platforms")
    if "domain_enrichment_platforms" not in normalized_payload and isinstance(payload.get("enrichment_platforms"), list):
        normalized_payload["domain_enrichment_platforms"] = payload.get("enrichment_platforms")

    source_text = str(payload.get("source_text") or fallback_text or normalized_payload.get("subject_name") or "").strip()
    return planner.plan_from_payload(normalized_payload, source_text=source_text)


def export_special_output(plan: AgentPlan, result, output_path: Path) -> Path:  # type: ignore[no-untyped-def]
    exporter = SpecialReportExporter()
    return exporter.export(
        plan.special_output_format,
        output_path,
        report_result=result.export_result,
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
            for event in result.events
        ],
        assets=result.merged_assets,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the terminal AI agent.")
    parser.add_argument("text", nargs="?", help="Natural language task text.")
    parser.add_argument("--env-file", default=".env", help="Path to local env file.")
    parser.add_argument("--output", help="Output report path.")
    parser.add_argument("--doctor", action="store_true", help="Check runtime prerequisites and exit.")
    args = parser.parse_args()
    args.plan_only = False
    args.plan_file = None

    settings = RuntimeSettings.from_env_file(args.env_file)
    if args.doctor:
        return run_doctor(settings)
    if not args.text:
        parser.error("text is required unless --doctor is used")

    llm_client = None
    if settings.openai_api_key:
        llm_client = OpenAICompatibleLlmClient(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            base_url=settings.openai_base_url,
            timeout=settings.openai_timeout,
            progress_logger=print_status,
        )
    if not llm_client and not args.plan_file:
        raise SystemExit("OPENAI_API_KEY is required for terminal AI agent.")

    planner = TerminalAgentPlanner(
        llm_client or OpenAICompatibleLlmClient(api_key="offline", model="offline"),
    )
    if args.plan_file:
        print_status(f"读取计划文件：{args.plan_file}")
        plan = load_plan_from_file(args.plan_file, planner, fallback_text=args.text or "")
        print_status(f"计划文件已加载：目标 {plan.subject_name or '未识别'}")
    else:
        print_status("开始规划：正在用 AI 解析任务意图")
        print_status(f"任务原文：{args.text}")
        print_status("AI 输出要求：主体识别、平台选择、补查策略、预算控制")
        print_status(f"AI 模型：{settings.openai_model}")
        print_status(f"AI 网关：{settings.openai_base_url}")
        plan = planner.plan(args.text)
        print_status("AI 原始规划返回如下：")
        print(json.dumps(plan.raw_plan, ensure_ascii=False, indent=2), flush=True)
        planning_event = AgentLogEvent(
            stage=AgentStage.PLANNING_COMPLETED,
            message="Planning completed",
            timestamp=datetime.now().astimezone().isoformat(),
            details={
                "subject_name": plan.subject_name,
                "primary_platforms": plan.primary_platforms,
                "enrichment_platforms": plan.enrichment_platforms,
                "budget": {
                    "max_primary_platforms": plan.max_primary_platforms,
                    "max_enrichment_rounds": plan.max_enrichment_rounds,
                    "max_enrichment_domains_total": plan.max_enrichment_domains_total,
                    "max_platform_calls": plan.max_platform_calls,
                },
            },
        )
        print_event(planning_event)

    if args.plan_only:
        print(json.dumps(serialize_plan(plan), ensure_ascii=False, indent=2))
        return 0

    registry = build_adapter_registry(settings)
    query_execution_service = QueryExecutionService(CompilerRegistry.default(), registry)
    workflow_service = AssetReportWorkflowService(query_execution_service)
    orchestrator = TerminalAgentOrchestrator(planner, workflow_service)

    xlsx_output_path, final_output_path = build_output_paths(args.text, args.output, plan)
    print_status(f"输出文件：{xlsx_output_path}")
    result = orchestrator.run(
        args.text or plan.source_text,
        xlsx_output_path,
        plan=plan,
        emit_planning_events=False,
        emit=print_event,
    )

    output_path = result.output_path
    if plan.special_output_format:
        output_path = export_special_output(plan, result, final_output_path)
        print(f"Special format: {plan.special_output_format}")

    print(f"Output: {output_path}")
    print(f"Merged assets: {len(result.merged_assets)}")
    print(f"Key assets: {result.export_result.key_assets}")
    prompt_open_asset_workbook(Path(output_path))
    return 0


def _special_format_to_suffix(format_name: str) -> str:
    normalized = str(format_name or "").strip().lower()
    if normalized in {"", "xlsx"}:
        return ".xlsx"
    if normalized == "json":
        return ".json"
    if normalized == "csv":
        return ".csv"
    if normalized in {"markdown", "md"}:
        return ".md"
    if normalized in {"txt", "text"}:
        return ".txt"
    return ".out"


if __name__ == "__main__":
    raise SystemExit(main())

