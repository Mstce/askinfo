from __future__ import annotations

from base64 import urlsafe_b64encode
from dataclasses import dataclass, field
from typing import Any, Iterable
from urllib.parse import urlparse

from asset_mapping_agent.adapters.base import BasePlatformAdapter
from asset_mapping_agent.adapters.http import HttpClient, UrllibHttpClient
from asset_mapping_agent.adapters.models import AdapterRequest, AdapterResponse, SearchExecutionResult
from asset_mapping_agent.query.models import CompiledQuery


@dataclass(slots=True)
class HunterCredentials:
    api_key: str


@dataclass(slots=True)
class HunterBatchSubmitResult:
    platform: str
    request: AdapterRequest
    response: AdapterResponse
    task_id: int | None = None
    filename: str = ""
    warnings: list[str] = field(default_factory=list)
    quota: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class HunterBatchStatusResult:
    platform: str
    request: AdapterRequest
    response: AdapterResponse
    task_id: int | None = None
    status: str = ""
    progress: str = ""
    rest_time: str = ""
    warnings: list[str] = field(default_factory=list)
    raw_data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class HunterBatchDownloadResult:
    platform: str
    request: AdapterRequest
    response: AdapterResponse
    task_id: int | None = None
    content: str = ""
    filename: str = ""
    warnings: list[str] = field(default_factory=list)


class HunterAdapter(BasePlatformAdapter):
    platform = "hunter"
    search_url = "https://hunter.qianxin.com/openApi/search"
    batch_search_url = "https://hunter.qianxin.com/openApi/search/batch"
    batch_download_url_template = "https://hunter.qianxin.com/openApi/search/download/{task_id}"

    def __init__(self, credentials: HunterCredentials) -> None:
        self.credentials = credentials

    def build_search_request(self, compiled: CompiledQuery, **kwargs: object) -> AdapterRequest:
        page_size = int(kwargs.get("page_size", compiled.metadata.get("limit", 100) or 100))
        page = int(kwargs.get("page", self._offset_to_page(compiled.metadata.get("offset", 0), page_size)))
        params: dict[str, object] = {
            "api-key": self.credentials.api_key,
            "search": self._encode_search(compiled.query or ""),
            "page": page,
            "page_size": page_size,
        }
        params.update(self._build_optional_params(kwargs))

        return AdapterRequest(
            platform=self.platform,
            method="GET",
            url=self.search_url,
            params=params,
            metadata={
                "compiled_query": compiled.query,
            },
        )

    def parse_search_response(self, response: AdapterResponse) -> SearchExecutionResult:
        warnings: list[str] = []
        payload = response.payload if isinstance(response.payload, dict) else {}
        records = self._parse_records(payload)
        pagination = self._extract_pagination(payload, response.request)

        if not response.ok:
            warnings.append(response.error or "Hunter request failed.")

        if not isinstance(response.payload, dict):
            warnings.append("Hunter response payload is not a JSON object.")
            return SearchExecutionResult(
                platform=self.platform,
                request=response.request,
                response=response,
                records=[],
                warnings=warnings,
                pagination=pagination,
            )

        code = payload.get("code")
        if code not in (None, 200):
            message = payload.get("message") or f"Hunter API returned code {code}."
            warnings.append(str(message))

        return SearchExecutionResult(
            platform=self.platform,
            request=response.request,
            response=response,
            records=records,
            warnings=warnings,
            pagination=pagination,
        )

    def build_batch_search_request(self, compiled: CompiledQuery, **kwargs: object) -> AdapterRequest:
        params: dict[str, object] = {
            "api-key": self.credentials.api_key,
            "search": self._encode_search(compiled.query or ""),
        }
        params.update(self._build_optional_params(kwargs, include_fields=True, include_search_type=True))
        return AdapterRequest(
            platform=self.platform,
            method="POST",
            url=self.batch_search_url,
            params=params,
            metadata={
                "compiled_query": compiled.query,
                "mode": "batch_submit",
            },
        )

    def parse_batch_submit_response(self, response: AdapterResponse) -> HunterBatchSubmitResult:
        warnings: list[str] = []
        payload = response.payload if isinstance(response.payload, dict) else {}
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}

        if not response.ok:
            warnings.append(response.error or "Hunter batch submit request failed.")
        if not isinstance(response.payload, dict):
            warnings.append("Hunter batch submit response payload is not a JSON object.")
            return HunterBatchSubmitResult(
                platform=self.platform,
                request=response.request,
                response=response,
                warnings=warnings,
            )

        code = payload.get("code")
        if code not in (None, 200):
            warnings.append(str(payload.get("message") or f"Hunter batch submit returned code {code}."))

        return HunterBatchSubmitResult(
            platform=self.platform,
            request=response.request,
            response=response,
            task_id=self._to_int(data.get("task_id")),
            filename=self._text(data.get("filename")),
            warnings=self._deduplicate(warnings),
            quota={
                "consume_quota": data.get("consume_quota"),
                "rest_quota": data.get("rest_quota"),
            },
        )

    def submit_batch_search(
        self,
        compiled: CompiledQuery,
        http_client: HttpClient | None = None,
        **kwargs: object,
    ) -> HunterBatchSubmitResult:
        client = http_client or UrllibHttpClient()
        request = self.build_batch_search_request(compiled, **kwargs)
        response = client.execute(request)
        return self.parse_batch_submit_response(response)

    def build_batch_status_request(self, task_id: int | str) -> AdapterRequest:
        normalized_task_id = self._normalize_task_id(task_id)
        return AdapterRequest(
            platform=self.platform,
            method="GET",
            url=f"{self.batch_search_url}/{normalized_task_id}",
            params={
                "api-key": self.credentials.api_key,
            },
            metadata={
                "task_id": normalized_task_id,
                "mode": "batch_status",
            },
        )

    def parse_batch_status_response(self, response: AdapterResponse) -> HunterBatchStatusResult:
        warnings: list[str] = []
        payload = response.payload if isinstance(response.payload, dict) else {}
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}

        if not response.ok:
            warnings.append(response.error or "Hunter batch status request failed.")
        if not isinstance(response.payload, dict):
            warnings.append("Hunter batch status response payload is not a JSON object.")
            return HunterBatchStatusResult(
                platform=self.platform,
                request=response.request,
                response=response,
                task_id=self._to_int(response.request.metadata.get("task_id")),
                warnings=warnings,
            )

        code = payload.get("code")
        if code not in (None, 200):
            warnings.append(str(payload.get("message") or f"Hunter batch status returned code {code}."))

        return HunterBatchStatusResult(
            platform=self.platform,
            request=response.request,
            response=response,
            task_id=self._to_int(response.request.metadata.get("task_id")),
            status=self._text(data.get("status")),
            progress=self._text(data.get("progress")),
            rest_time=self._text(data.get("rest_time")),
            warnings=self._deduplicate(warnings),
            raw_data=dict(data),
        )

    def get_batch_status(
        self,
        task_id: int | str,
        http_client: HttpClient | None = None,
    ) -> HunterBatchStatusResult:
        client = http_client or UrllibHttpClient()
        request = self.build_batch_status_request(task_id)
        response = client.execute(request)
        return self.parse_batch_status_response(response)

    def build_batch_download_request(self, task_id: int | str) -> AdapterRequest:
        normalized_task_id = self._normalize_task_id(task_id)
        return AdapterRequest(
            platform=self.platform,
            method="GET",
            url=self.batch_download_url_template.format(task_id=normalized_task_id),
            params={
                "api-key": self.credentials.api_key,
            },
            metadata={
                "task_id": normalized_task_id,
                "mode": "batch_download",
            },
        )

    def parse_batch_download_response(self, response: AdapterResponse) -> HunterBatchDownloadResult:
        warnings: list[str] = []
        if not response.ok:
            warnings.append(response.error or "Hunter batch download request failed.")

        content = response.raw_text
        if not content and isinstance(response.payload, str):
            content = response.payload
        if not content and isinstance(response.payload, dict):
            message = self._text(response.payload.get("message") or response.payload.get("error"))
            if message:
                warnings.append(message)

        return HunterBatchDownloadResult(
            platform=self.platform,
            request=response.request,
            response=response,
            task_id=self._to_int(response.request.metadata.get("task_id")),
            content=content,
            filename=f"hunter_batch_{response.request.metadata.get('task_id')}.csv",
            warnings=self._deduplicate(warnings),
        )

    def download_batch_result(
        self,
        task_id: int | str,
        http_client: HttpClient | None = None,
    ) -> HunterBatchDownloadResult:
        client = http_client or UrllibHttpClient()
        request = self.build_batch_download_request(task_id)
        response = client.execute(request)
        return self.parse_batch_download_response(response)

    def _parse_records(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        raw_results = data.get("arr", []) if isinstance(data, dict) else []
        if isinstance(raw_results, dict):
            raw_results = [raw_results]

        records: list[dict[str, Any]] = []
        for row in raw_results:
            if isinstance(row, dict):
                records.append(self._flatten_record(row))
            else:
                records.append({"value": row})
        return records

    def _flatten_record(self, row: dict[str, Any]) -> dict[str, Any]:
        record = dict(row)
        url = self._text(row.get("url"))
        domain = self._text(row.get("domain"))
        ip = self._text(row.get("ip"))
        protocol = self._text(row.get("protocol"))
        company = self._text(row.get("company"))
        as_org = self._text(row.get("as_org"))
        host = self._extract_host(url, domain, ip)

        record.update(
            {
                "host": host,
                "domain": domain,
                "ip": ip,
                "port": row.get("port"),
                "protocol": protocol,
                "service_name": protocol,
                "service": protocol or self._text(row.get("base_protocol")),
                "title": self._text(row.get("web_title")),
                "product": self._extract_product(row.get("component")),
                "org": company or as_org,
                "icp_org": company,
                "icp": self._text(row.get("number")),
                "country": self._text(row.get("country")),
                "province": self._text(row.get("province")),
                "city": self._text(row.get("city")),
                "status_code": row.get("status_code"),
                "url": url,
                "os": self._text(row.get("os")),
                "updated_at": self._text(row.get("updated_at")),
                "banner": self._text(row.get("banner")),
                "header": self._text(row.get("header")),
                "is_web": self._text(row.get("is_web")),
                "as_org": as_org,
                "isp": self._text(row.get("isp")),
                "component": row.get("component"),
                "base_protocol": self._text(row.get("base_protocol")),
            }
        )
        return record

    def _extract_pagination(self, payload: dict[str, Any], request: AdapterRequest) -> dict[str, Any]:
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        total = data.get("total") if isinstance(data, dict) else None
        duration = data.get("time") if isinstance(data, dict) else None
        return {
            "page": request.params.get("page", 1),
            "size": request.params.get("page_size", 100),
            "total": total,
            "time": duration,
            "consume_quota": data.get("consume_quota") if isinstance(data, dict) else None,
            "rest_quota": data.get("rest_quota") if isinstance(data, dict) else None,
        }

    def _build_optional_params(
        self,
        kwargs: dict[str, object],
        *,
        include_fields: bool = False,
        include_search_type: bool = False,
    ) -> dict[str, object]:
        params: dict[str, object] = {}

        is_web = self._normalize_is_web(kwargs.get("is_web"))
        if is_web is not None:
            params["is_web"] = is_web

        if kwargs.get("start_time"):
            params["start_time"] = str(kwargs["start_time"])
        if kwargs.get("end_time"):
            params["end_time"] = str(kwargs["end_time"])

        status_code = self._normalize_csv(kwargs.get("status_code"))
        if status_code:
            params["status_code"] = status_code

        port_filter = self._normalize_bool_text(kwargs.get("port_filter"))
        if port_filter is not None:
            params["port_filter"] = port_filter

        if include_fields:
            fields = self._normalize_csv(kwargs.get("fields"))
            if fields:
                params["fields"] = fields

        if include_search_type:
            search_type = self._normalize_search_type(kwargs.get("search_type"))
            if search_type:
                params["search_type"] = search_type

        return params

    def _encode_search(self, query: str) -> str:
        return urlsafe_b64encode(query.encode("utf-8")).decode("ascii")

    def _extract_host(self, url: str, domain: str, ip: str) -> str:
        if url:
            parsed = urlparse(url)
            if parsed.hostname:
                return parsed.hostname.lower()
        if domain:
            return domain.lower()
        return ip

    def _extract_product(self, components: Any) -> str:
        if isinstance(components, list):
            for component in components:
                if not isinstance(component, dict):
                    continue
                name = self._text(component.get("name"))
                if name:
                    return name
        return ""

    def _offset_to_page(self, offset: object, page_size: int) -> int:
        try:
            offset_value = int(offset or 0)
        except (TypeError, ValueError):
            offset_value = 0
        if page_size <= 0:
            return 1
        return max(1, (offset_value // page_size) + 1)

    def _normalize_is_web(self, value: object) -> int | None:
        if value in (None, ""):
            return None
        if isinstance(value, bool):
            return 1 if value else 2
        if isinstance(value, int):
            return value if value in {1, 2, 3} else None
        text = str(value).strip().lower()
        mapping = {
            "1": 1,
            "web": 1,
            "site": 1,
            "true": 1,
            "2": 2,
            "non_web": 2,
            "non-web": 2,
            "false": 2,
            "3": 3,
            "all": 3,
        }
        return mapping.get(text)

    def _normalize_csv(self, value: object) -> str:
        if value in (None, ""):
            return ""
        if isinstance(value, str):
            return ",".join(part.strip() for part in value.split(",") if part.strip())
        if isinstance(value, Iterable):
            values: list[str] = []
            for item in value:
                text = str(item).strip()
                if text:
                    values.append(text)
            return ",".join(values)
        return str(value).strip()

    def _normalize_bool_text(self, value: object) -> str | None:
        if value in (None, ""):
            return None
        if isinstance(value, bool):
            return str(value).lower()
        text = str(value).strip().lower()
        if text in {"true", "false"}:
            return text
        return None

    def _normalize_search_type(self, value: object) -> str:
        if value in (None, ""):
            return ""
        text = str(value).strip().lower()
        return text if text in {"all", "ip", "domain", "company"} else ""

    def _normalize_task_id(self, task_id: int | str) -> int:
        normalized = self._to_int(task_id)
        if normalized is None or normalized <= 0:
            raise ValueError("task_id must be a positive integer")
        return normalized

    def _to_int(self, value: object) -> int | None:
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return None

    def _text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()

    def _deduplicate(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        deduplicated: list[str] = []
        for value in values:
            if value not in seen:
                seen.add(value)
                deduplicated.append(value)
        return deduplicated
