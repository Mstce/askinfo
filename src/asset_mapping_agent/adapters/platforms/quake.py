from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from asset_mapping_agent.adapters.base import BasePlatformAdapter
from asset_mapping_agent.adapters.models import AdapterRequest, AdapterResponse, SearchExecutionResult
from asset_mapping_agent.query.models import CompiledQuery


@dataclass(slots=True)
class QuakeCredentials:
    api_key: str


class QuakeAdapter(BasePlatformAdapter):
    platform = "quake"
    search_url = "https://quake.360.net/api/v3/search/quake_service"
    default_include = [
        "ip",
        "port",
        "hostname",
        "transport",
        "asn",
        "org",
        "service.name",
        "location.country_cn",
        "location.province_cn",
        "location.city_cn",
        "service.http.host",
        "service.http.title",
        "service.http.server",
    ]

    def __init__(self, credentials: QuakeCredentials) -> None:
        self.credentials = credentials

    def build_search_request(self, compiled: CompiledQuery, **kwargs: object) -> AdapterRequest:
        start = int(kwargs.get("start", compiled.metadata.get("offset", 0) or 0))
        size = int(kwargs.get("size", compiled.metadata.get("limit", 100) or 100))
        include = self._normalize_string_list(kwargs.get("include"))
        exclude = self._normalize_string_list(kwargs.get("exclude"))
        shortcuts = self._normalize_string_list(kwargs.get("shortcuts"))
        ip_list = self._normalize_string_list(kwargs.get("ip_list"))

        json_body: dict[str, object] = {
            "query": compiled.query or "*",
            "start": start,
            "size": size,
            "ignore_cache": bool(kwargs.get("ignore_cache", False)),
            "latest": bool(kwargs.get("latest", True)),
        }
        if kwargs.get("use_default_include", True) and not include:
            json_body["include"] = list(self.default_include)
        elif include:
            json_body["include"] = include
        if exclude:
            json_body["exclude"] = exclude
        if shortcuts:
            json_body["shortcuts"] = shortcuts
        if ip_list:
            json_body["ip_list"] = ip_list
        if kwargs.get("rule"):
            json_body["rule"] = str(kwargs["rule"])
        if kwargs.get("start_time"):
            json_body["start_time"] = str(kwargs["start_time"])
        if kwargs.get("end_time"):
            json_body["end_time"] = str(kwargs["end_time"])

        return AdapterRequest(
            platform=self.platform,
            method="POST",
            url=self.search_url,
            headers={
                "X-QuakeToken": self.credentials.api_key,
                "Content-Type": "application/json",
            },
            json_body=json_body,
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
            warnings.append(response.error or "Quake request failed.")

        if not isinstance(response.payload, dict):
            warnings.append("Quake response payload is not a JSON object.")
            return SearchExecutionResult(
                platform=self.platform,
                request=response.request,
                response=response,
                records=[],
                warnings=warnings,
                pagination=pagination,
            )

        code = payload.get("code")
        if code not in (None, 0):
            message = payload.get("message") or f"Quake API returned code {code}."
            warnings.append(str(message))

        return SearchExecutionResult(
            platform=self.platform,
            request=response.request,
            response=response,
            records=records,
            warnings=warnings,
            pagination=pagination,
        )

    def _parse_records(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        raw_results = payload.get("data", []) if isinstance(payload, dict) else []
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
        service_name = self._pick_first(row, "service.name", "service")
        host_value = self._pick_first(row, "service.http.host", "hostname", "domain", "ip")
        domain_value = self._pick_domain(row)
        title_value = self._pick_first(row, "service.http.title", "title")
        product_value = self._extract_product(row)
        country_value = self._pick_first(row, "location.country_cn", "location.country_en", "country")
        province_value = self._pick_first(row, "location.province_cn", "location.province_en", "province")
        city_value = self._pick_first(row, "location.city_cn", "location.city_en", "city")
        protocol_value = self._infer_protocol(row, service_name)

        record.update(
            {
                "host": host_value,
                "domain": domain_value,
                "ip": self._pick_first(row, "ip"),
                "port": self._pick_first(row, "port"),
                "protocol": protocol_value,
                "title": title_value,
                "service_name": service_name,
                "service": service_name or self._pick_first(row, "transport"),
                "server": self._pick_first(row, "service.http.server", "server"),
                "status_code": self._pick_first(row, "service.http.status_code", "status_code"),
                "body": self._pick_first(row, "service.http.body", "body"),
                "response": self._pick_first(row, "service.response", "response"),
                "cert": self._pick_first(row, "service.cert", "cert"),
                "product": product_value,
                "org": self._pick_first(row, "org"),
                "country": country_value,
                "province": province_value,
                "city": city_value,
                "district": self._pick_first(row, "location.district_cn", "location.district_en", "district"),
                "isp": self._pick_first(row, "location.isp", "isp"),
                "transport": self._pick_first(row, "transport"),
            }
        )
        return record

    def _extract_pagination(self, payload: dict[str, Any], request: AdapterRequest) -> dict[str, Any]:
        meta = payload.get("meta") if isinstance(payload, dict) else {}
        pagination = meta.get("pagination") if isinstance(meta, dict) else {}
        start = 0
        size = 0
        if isinstance(request.json_body, dict):
            start = int(request.json_body.get("start", 0) or 0)
            size = int(request.json_body.get("size", 0) or 0)

        page_index = pagination.get("page_index")
        if page_index is None and size:
            page_index = (start // size) + 1

        return {
            "page": page_index,
            "size": pagination.get("page_size", size),
            "count": pagination.get("count"),
            "total": pagination.get("total"),
        }

    def _pick_domain(self, row: dict[str, Any]) -> str:
        domain_value = self._pick_first(row, "domain")
        if domain_value:
            return domain_value
        host_value = self._pick_first(row, "hostname")
        return host_value

    def _extract_product(self, row: dict[str, Any]) -> str:
        product = self._pick_first(
            row,
            "components.product_name_cn",
            "components.product_name_en",
            "components.product",
            "app",
            "product",
        )
        if product:
            return product

        components = row.get("components")
        if isinstance(components, list):
            for component in components:
                if not isinstance(component, dict):
                    continue
                product = self._pick_first(
                    component,
                    "product_name_cn",
                    "product_name_en",
                    "product",
                    "name",
                )
                if product:
                    return product
        return ""

    def _infer_protocol(self, row: dict[str, Any], service_name: str) -> str:
        protocol = self._pick_first(row, "protocol")
        if protocol:
            return protocol
        if service_name.lower() in {"http", "https"}:
            return service_name.lower()
        port = self._pick_first(row, "port")
        if str(port) == "443":
            return "https"
        if str(port) == "80":
            return "http"
        return ""

    def _pick_first(self, data: Any, *paths: str) -> Any:
        for path in paths:
            value = self._resolve_path(data, path)
            normalized = self._normalize_value(value)
            if normalized not in (None, ""):
                return normalized
        return ""

    def _resolve_path(self, data: Any, path: str) -> Any:
        if isinstance(data, dict) and path in data:
            return data[path]

        current = data
        for part in path.split("."):
            if isinstance(current, dict):
                if part not in current:
                    return None
                current = current[part]
                continue
            return None
        return current

    def _normalize_value(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, list):
            for item in value:
                normalized = self._normalize_value(item)
                if normalized not in (None, ""):
                    return normalized
            return ""
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            return value.strip()
        return value

    def _normalize_string_list(self, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, Iterable):
            values: list[str] = []
            for item in value:
                text = str(item).strip()
                if text:
                    values.append(text)
            return values
        text = str(value).strip()
        return [text] if text else []
