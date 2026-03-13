from __future__ import annotations

from dataclasses import dataclass, field

from asset_mapping_agent.adapters import AdapterRegistry, HttpClient
from asset_mapping_agent.adapters.base import BasePlatformAdapter
from asset_mapping_agent.adapters.models import AdapterRequest, AdapterResponse, SearchExecutionResult
from asset_mapping_agent.parsing import NaturalLanguageQueryParser
from asset_mapping_agent.query import CompilerRegistry
from asset_mapping_agent.query.models import CompiledQuery, QueryIntent


PLATFORM_ALIASES = {
    "360_quake": "quake",
    "360-quake": "quake",
}
DEFAULT_RETRY_ATTEMPTS = 2
RETRYABLE_STATUS_CODES = {0, 408, 409, 429, 500, 502, 503, 504}


@dataclass(slots=True)
class PlatformExecution:
    platform: str
    compiled_query: CompiledQuery
    search_result: SearchExecutionResult
    attempts: int = 1
    degraded: bool = False
    error: str = ""


@dataclass(slots=True)
class ExecutionBatchResult:
    intent: QueryIntent
    source_text: str = ""
    parse_warnings: list[str] = field(default_factory=list)
    executions: dict[str, PlatformExecution] = field(default_factory=dict)


class QueryExecutionService:
    def __init__(self, compiler_registry: CompilerRegistry, adapter_registry: AdapterRegistry) -> None:
        self.compiler_registry = compiler_registry
        self.adapter_registry = adapter_registry

    def execute_intent(
        self,
        intent: QueryIntent,
        platforms: list[str],
        http_clients: dict[str, HttpClient] | None = None,
        platform_options: dict[str, dict[str, object]] | None = None,
    ) -> ExecutionBatchResult:
        executions: dict[str, PlatformExecution] = {}
        http_clients = http_clients or {}
        platform_options = platform_options or {}

        for platform in platforms:
            normalized_platform = self._normalize_platform(platform)
            compiled = self.compiler_registry.compile_for_platform(normalized_platform, intent)
            platform_key = self._normalize_platform(compiled.platform)
            http_client = http_clients.get(platform_key) or http_clients.get(normalized_platform)
            options = dict(platform_options.get(platform_key) or platform_options.get(normalized_platform, {}))
            retry_attempts = self._normalize_retry_attempts(options.pop("retry_attempts", DEFAULT_RETRY_ATTEMPTS))
            degrade_on_failure = self._normalize_degrade_on_failure(options.pop("degrade_on_failure", True))
            adapter = self.adapter_registry.get(compiled.platform)
            result, attempts, degraded, error = self._execute_platform_with_retry(
                adapter=adapter,
                compiled=compiled,
                http_client=http_client,
                options=options,
                retry_attempts=retry_attempts,
                degrade_on_failure=degrade_on_failure,
            )
            executions[platform_key] = PlatformExecution(
                platform=platform_key,
                compiled_query=compiled,
                search_result=result,
                attempts=attempts,
                degraded=degraded,
                error=error,
            )

        return ExecutionBatchResult(intent=intent, source_text=intent.source_text, executions=executions)

    def execute_text(
        self,
        text: str,
        platforms: list[str],
        parser: NaturalLanguageQueryParser | None = None,
        http_clients: dict[str, HttpClient] | None = None,
        platform_options: dict[str, dict[str, object]] | None = None,
    ) -> ExecutionBatchResult:
        parser = parser or NaturalLanguageQueryParser()
        parsed = parser.parse(text)
        batch = self.execute_intent(
            parsed.intent,
            platforms,
            http_clients=http_clients,
            platform_options=platform_options,
        )
        batch.source_text = text
        batch.parse_warnings = parsed.warnings
        return batch

    def _execute_platform_with_retry(
        self,
        *,
        adapter: BasePlatformAdapter,
        compiled: CompiledQuery,
        http_client: HttpClient | None,
        options: dict[str, object],
        retry_attempts: int,
        degrade_on_failure: bool,
    ) -> tuple[SearchExecutionResult, int, bool, str]:
        last_result: SearchExecutionResult | None = None
        last_exception: Exception | None = None

        for attempt in range(1, retry_attempts + 1):
            try:
                result = adapter.search(compiled, http_client=http_client, **options)
            except Exception as exc:
                last_exception = exc
                if attempt < retry_attempts:
                    continue
                if degrade_on_failure:
                    degraded = self._build_degraded_result_from_exception(
                        adapter=adapter,
                        compiled=compiled,
                        options=options,
                        error_message=str(exc),
                        attempts=attempt,
                    )
                    return degraded, attempt, True, str(exc)
                raise

            last_result = result
            if result.response.ok:
                if attempt > 1:
                    result = self._append_execution_warning(
                        result,
                        f"platform query succeeded after {attempt} attempts",
                        attempt=attempt,
                    )
                return result, attempt, False, ""

            error_message = result.response.error or f"http status {result.response.status_code}"
            if attempt < retry_attempts and self._is_retryable_failure(result.response):
                continue
            if degrade_on_failure:
                degraded = self._build_degraded_result_from_result(
                    result,
                    error_message=error_message,
                    attempts=attempt,
                )
                return degraded, attempt, True, error_message
            raise RuntimeError(f"platform query failed: {compiled.platform}: {error_message}")

        if last_result is not None:
            return last_result, retry_attempts, False, ""
        if last_exception is not None:
            raise last_exception
        raise RuntimeError(f"platform query failed without response: {compiled.platform}")

    def _is_retryable_failure(self, response: AdapterResponse) -> bool:
        if response.status_code in RETRYABLE_STATUS_CODES:
            return True
        return bool(response.error) and not response.ok and not response.raw_text

    def _build_degraded_result_from_result(
        self,
        result: SearchExecutionResult,
        *,
        error_message: str,
        attempts: int,
    ) -> SearchExecutionResult:
        warnings = list(result.warnings)
        warnings.append(f"platform query degraded after {attempts} attempts: {error_message}")
        pagination = dict(result.pagination)
        pagination["attempts"] = attempts
        pagination["degraded"] = True
        return SearchExecutionResult(
            platform=result.platform,
            request=result.request,
            response=result.response,
            records=[],
            warnings=warnings,
            pagination=pagination,
        )

    def _build_degraded_result_from_exception(
        self,
        *,
        adapter: BasePlatformAdapter,
        compiled: CompiledQuery,
        options: dict[str, object],
        error_message: str,
        attempts: int,
    ) -> SearchExecutionResult:
        request = self._build_fallback_request(adapter, compiled, options)
        response = AdapterResponse(
            platform=request.platform,
            request=request,
            status_code=0,
            ok=False,
            error=error_message,
        )
        return SearchExecutionResult(
            platform=request.platform,
            request=request,
            response=response,
            records=[],
            warnings=[f"platform query degraded after {attempts} attempts: {error_message}"],
            pagination={"attempts": attempts, "degraded": True},
        )

    def _build_fallback_request(
        self,
        adapter: BasePlatformAdapter,
        compiled: CompiledQuery,
        options: dict[str, object],
    ) -> AdapterRequest:
        try:
            return adapter.build_search_request(compiled, **options)
        except Exception:
            return AdapterRequest(
                platform=self._normalize_platform(compiled.platform),
                method="GET",
                url="",
                metadata={"compiled_query": compiled.query},
            )

    def _append_execution_warning(
        self,
        result: SearchExecutionResult,
        message: str,
        *,
        attempt: int,
    ) -> SearchExecutionResult:
        warnings = list(result.warnings)
        warnings.append(message)
        pagination = dict(result.pagination)
        pagination["attempts"] = attempt
        return SearchExecutionResult(
            platform=result.platform,
            request=result.request,
            response=result.response,
            records=list(result.records),
            warnings=warnings,
            pagination=pagination,
        )

    def _normalize_retry_attempts(self, value: object) -> int:
        try:
            candidate = int(value)
        except (TypeError, ValueError):
            return DEFAULT_RETRY_ATTEMPTS
        return min(max(candidate, 1), 5)

    def _normalize_degrade_on_failure(self, value: object) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return True
        if isinstance(value, (int, float)):
            return bool(value)
        return str(value).strip().lower() not in {"0", "false", "no", "off"}

    def _normalize_platform(self, platform: str) -> str:
        key = platform.strip().lower().replace("-", "_").replace(" ", "_")
        return PLATFORM_ALIASES.get(key, key)
