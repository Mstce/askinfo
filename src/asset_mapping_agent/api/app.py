from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

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
from asset_mapping_agent.api.pages import (
    render_task_history_page,
    render_task_results_page,
    render_task_status_page,
)
from asset_mapping_agent.config import RuntimeSettings
from asset_mapping_agent.execution import QueryExecutionService
from asset_mapping_agent.query import CompilerRegistry
from asset_mapping_agent.tasking import InMemoryTaskService, TaskNotFoundError
from asset_mapping_agent.workflows import AssetReportWorkflowService


class CreateTaskRequest(BaseModel):
    source_text: str = Field(default="")
    platforms: list[str] = Field(default_factory=list)
    output_path: str | None = None
    platform_options: dict[str, dict[str, Any]] = Field(default_factory=dict)
    baseline_keys: list[str] = Field(default_factory=list)
    run_async: bool = False


def _build_default_task_service() -> InMemoryTaskService:
    settings = RuntimeSettings.from_env_file(Path(".env"))
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

    query_execution_service = QueryExecutionService(CompilerRegistry.default(), registry)
    workflow_service = AssetReportWorkflowService(query_execution_service)
    return InMemoryTaskService(workflow_service, reports_dir=Path("task_reports"))


def create_app(task_service: InMemoryTaskService | None = None) -> FastAPI:
    app = FastAPI(title="askinfo Task API", version="0.1.0")
    service = task_service or _build_default_task_service()

    @app.post("/tasks")
    def create_task(request: CreateTaskRequest, background_tasks: BackgroundTasks):
        source_text = request.source_text.strip()
        platforms = [platform.strip() for platform in request.platforms if platform.strip()]
        if not source_text:
            raise HTTPException(status_code=400, detail="source_text is required")
        if not platforms:
            raise HTTPException(status_code=400, detail="platforms is required")

        task = service.create_task(
            source_text=source_text,
            platforms=platforms,
            output_path=request.output_path,
            platform_options=request.platform_options,
            baseline_keys=request.baseline_keys,
        )
        if request.run_async:
            background_tasks.add_task(service.run_task, task.task_id)
            return JSONResponse(service.serialize_task(task.task_id), status_code=202)
        service.run_task(task.task_id)
        return JSONResponse(service.serialize_task(task.task_id), status_code=201)

    @app.get("/tasks")
    def get_tasks():
        return {"tasks": service.list_tasks()}

    @app.get("/tasks/history-page", response_class=HTMLResponse)
    def get_task_history_page():
        return HTMLResponse(render_task_history_page(service.list_tasks()))

    @app.get("/tasks/{task_id}")
    def get_task(task_id: str):
        try:
            return service.serialize_task(task_id)
        except TaskNotFoundError:
            raise HTTPException(status_code=404, detail="task not found")

    @app.get("/tasks/{task_id}/audit-log")
    def get_task_audit_log(task_id: str):
        try:
            return {
                "task_id": task_id,
                "audit_log": service.list_task_audit_log(task_id),
            }
        except TaskNotFoundError:
            raise HTTPException(status_code=404, detail="task not found")

    @app.get("/tasks/{task_id}/status-page", response_class=HTMLResponse)
    def get_task_status_page(task_id: str):
        try:
            task = service.serialize_task(task_id)
            queries = service.list_task_queries(task_id)
        except TaskNotFoundError:
            raise HTTPException(status_code=404, detail="task not found")
        return HTMLResponse(render_task_status_page(task, queries))

    @app.get("/tasks/{task_id}/results-page", response_class=HTMLResponse)
    def get_task_results_page(task_id: str):
        try:
            task = service.serialize_task(task_id)
            assets = service.list_task_assets(task_id)
        except TaskNotFoundError:
            raise HTTPException(status_code=404, detail="task not found")
        return HTMLResponse(render_task_results_page(task, assets))

    @app.get("/tasks/{task_id}/queries")
    def get_task_queries(task_id: str):
        try:
            return {
                "task_id": task_id,
                "queries": service.list_task_queries(task_id),
            }
        except TaskNotFoundError:
            raise HTTPException(status_code=404, detail="task not found")

    @app.get("/tasks/{task_id}/assets")
    def get_task_assets(task_id: str):
        try:
            assets = service.list_task_assets(task_id)
            return {
                "task_id": task_id,
                "count": len(assets),
                "assets": assets,
            }
        except TaskNotFoundError:
            raise HTTPException(status_code=404, detail="task not found")

    @app.get("/tasks/{task_id}/report")
    def get_task_report(task_id: str):
        try:
            report_path = service.get_report_path(task_id)
        except TaskNotFoundError:
            raise HTTPException(status_code=404, detail="task not found")

        if report_path is None:
            raise HTTPException(status_code=409, detail="report is not ready")
        if not report_path.exists():
            raise HTTPException(status_code=404, detail="report file not found")

        return FileResponse(
            report_path,
            filename=report_path.name,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    return app


app = create_app()
