from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable
import re

from asset_mapping_agent.adapters.base import BasePlatformAdapter
from asset_mapping_agent.adapters.models import AdapterRequest, AdapterResponse, SearchExecutionResult
from asset_mapping_agent.query.models import CompiledQuery


@dataclass(slots=True)
class ShodanCredentials:
    api_key: str


class ShodanAdapter(BasePlatformAdapter):
    platform = "shodan"
    search_url = "https://api.shodan.io/shodan/host/search"

    def __init__(self, credentials: ShodanCredentials) -> None:
        self.credentials = credentials

    def build_search_request(self, compiled: CompiledQuery, **kwargs: object) -> AdapterRequest:
        page = int(kwargs.get("page", self._offset_to_page(compiled.metadata.get("offset", 0))))
        params: dict[str, object] = {
            "key": self.credentials.api_key,
            "query": compiled.query or "",
            "page": page,
            "minify": self._normalize_bool_text(kwargs.get("minify", True)),
        }

        fields = self._normalize_csv(kwargs.get("fields"))
        if fields:
            params["fields"] = fields

        facets = self._normalize_csv(kwargs.get("facets"))
        if facets:
            params["facets"] = facets

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
        pagination = self._extract_pagination(payload, response.request, records)

        if not response.ok:
            warnings.append(response.error or "Shodan request failed.")

        if not isinstance(response.payload, dict):
            warnings.append("Shodan response payload is not a JSON object.")
            return SearchExecutionResult(
                platform=self.platform,
                request=response.request,
                response=response,
                records=[],
                warnings=warnings,
                pagination=pagination,
            )

        if payload.get("error"):
            warnings.append(str(payload.get("error")))

        return SearchExecutionResult(
            platform=self.platform,
            request=response.request,
            response=response,
            records=records,
            warnings=warnings,
            pagination=pagination,
        )

    def _parse_records(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        raw_results = payload.get("matches", []) if isinstance(payload, dict) else []
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
        http = row.get("http") if isinstance(row.get("http"), dict) else {}
        location = row.get("location") if isinstance(row.get("location"), dict) else {}
        shodan_meta = row.get("_shodan") if isinstance(row.get("_shodan"), dict) else {}
        hostnames = self._normalize_string_list(row.get("hostnames"))
        domains = self._normalize_string_list(row.get("domains"))
        ip = self._text(row.get("ip_str") or row.get("ip"))
        host = self._text(http.get("host")) or (hostnames[0] if hostnames else "") or (domains[0] if domains else "") or ip
        product = self._text(row.get("product")) or self._extract_http_component(http.get("components"))
        module = self._text(shodan_meta.get("module"))

        record.update(
            {
                "host": host,
                "domain": (domains[0] if domains else (hostnames[0] if hostnames else "")),
                "ip": ip,
                "port": row.get("port"),
                "protocol": self._infer_protocol(row, http),
                "title": self._text(http.get("title")),
                "service_name": product or module,
                "service": module or self._text(row.get("transport")),
                "server": self._text(http.get("server")),
                "status_code": self._extract_status_code(row, http),
                "body": self._text(http.get("html")) or self._text(row.get("data")),
                "response": self._text(row.get("data")),
                "product": product,
                "org": self._text(row.get("org")),
                "country": self._text(location.get("country_name")) or self._text(location.get("country_code")),
                "province": self._text(location.get("region_code")),
                "city": self._text(location.get("city")),
                "isp": self._text(row.get("isp")),
                "asn": self._text(row.get("asn")),
                "hostnames": hostnames,
                "domains": domains,
                "transport": self._text(row.get("transport")),
                "timestamp": self._text(row.get("timestamp")),
                "os": self._text(row.get("os")),
                "module": module,
            }
        )
        return record

    def _extract_pagination(
        self,
        payload: dict[str, Any],
        request: AdapterRequest,
        records: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "page": request.params.get("page", 1),
            "size": len(records),
            "total": payload.get("total") if isinstance(payload, dict) else None,
            "facets": payload.get("facets") if isinstance(payload, dict) else None,
        }

    def _offset_to_page(self, offset: object) -> int:
        try:
            offset_value = int(offset or 0)
        except (TypeError, ValueError):
            offset_value = 0
        return max(1, (offset_value // 100) + 1)

    def _normalize_bool_text(self, value: object) -> str:
        if isinstance(value, bool):
            return str(value).lower()
        if value in (None, ""):
            return "true"
        return "true" if str(value).strip().lower() == "true" else "false"

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

    def _normalize_string_list(self, value: Any) -> list[str]:
        if isinstance(value, list):
            values: list[str] = []
            for item in value:
                text = self._text(item)
                if text:
                    values.append(text)
            return values
        text = self._text(value)
        return [text] if text else []

    def _extract_http_component(self, components: Any) -> str:
        if isinstance(components, dict):
            for name in components.keys():
                text = self._text(name)
                if text:
                    return text
        return ""

    def _extract_status_code(self, row: dict[str, Any], http: dict[str, Any]) -> int | str:
        status = http.get("status")
        if status not in (None, ""):
            return status
        data = self._text(row.get("data"))
        match = re.search(r"HTTP/\d(?:\.\d)?\s+(\d{3})", data)
        if match:
            return int(match.group(1))
        return ""

    def _infer_protocol(self, row: dict[str, Any], http: dict[str, Any]) -> str:
        port = str(row.get("port") or "").strip()
        if http:
            if port == "443":
                return "https"
            return "http"
        if port == "443":
            return "https"
        if port == "80":
            return "http"
        return ""

    def _text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()
