from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from asset_mapping_agent.adapters.base import BasePlatformAdapter
from asset_mapping_agent.adapters.models import AdapterRequest, AdapterResponse, SearchExecutionResult
from asset_mapping_agent.query.models import CompiledQuery


@dataclass(slots=True)
class UrlscanCredentials:
    api_key: str


class UrlscanAdapter(BasePlatformAdapter):
    platform = "urlscan"
    search_url = "https://urlscan.io/api/v1/search/"

    def __init__(self, credentials: UrlscanCredentials) -> None:
        self.credentials = credentials

    def build_search_request(self, compiled: CompiledQuery, **kwargs: object) -> AdapterRequest:
        size = self._coerce_int(kwargs.get("size", compiled.metadata.get("limit", 100)), default=100)
        offset = self._coerce_int(kwargs.get("offset", compiled.metadata.get("offset", 0)), default=0)

        params: dict[str, object] = {
            "q": compiled.query or "",
            "size": size,
        }
        if offset > 0:
            params["offset"] = offset

        search_after = kwargs.get("search_after") or compiled.metadata.get("search_after")
        if search_after not in (None, ""):
            params["search_after"] = search_after

        return AdapterRequest(
            platform=self.platform,
            method="GET",
            url=self.search_url,
            headers={
                "API-Key": self.credentials.api_key,
                "Accept": "application/json",
            },
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
            warnings.append(response.error or "urlscan.io request failed.")

        if not isinstance(response.payload, dict):
            warnings.append("urlscan.io response payload is not a JSON object.")
            return SearchExecutionResult(
                platform=self.platform,
                request=response.request,
                response=response,
                records=[],
                warnings=warnings,
                pagination=pagination,
            )

        if payload.get("message"):
            warnings.append(str(payload.get("message")))
        if payload.get("error"):
            warnings.append(str(payload.get("error")))

        return SearchExecutionResult(
            platform=self.platform,
            request=response.request,
            response=response,
            records=records,
            warnings=self._deduplicate(warnings),
            pagination=pagination,
        )

    def _parse_records(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        raw_results = payload.get("results", []) if isinstance(payload, dict) else []
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
        task = row.get("task") if isinstance(row.get("task"), dict) else {}
        page = row.get("page") if isinstance(row.get("page"), dict) else {}
        stats = row.get("stats") if isinstance(row.get("stats"), dict) else {}
        verdicts = row.get("verdicts") if isinstance(row.get("verdicts"), dict) else {}
        parsed_url = urlparse(self._text(page.get("url") or task.get("url")))
        host = self._text(parsed_url.hostname) or self._text(page.get("domain") or task.get("domain"))
        scheme = self._text(parsed_url.scheme)
        port = parsed_url.port or page.get("port") or task.get("port")
        status_code = page.get("status") or page.get("status_code") or task.get("status")

        record = dict(row)
        record.update(
            {
                "host": host,
                "domain": self._text(page.get("domain") or task.get("domain")),
                "ip": self._text(page.get("ip")),
                "url": self._text(page.get("url") or task.get("url")),
                "port": port,
                "protocol": scheme,
                "title": self._text(page.get("title")),
                "server": self._text(page.get("server")),
                "status_code": status_code,
                "country": self._text(page.get("country")),
                "asn": self._text(page.get("asn")),
                "asn_name": self._text(page.get("asnname")),
                "org": self._text(page.get("asnname")),
                "task_time": self._text(task.get("time")),
                "task_url": self._text(task.get("url")),
                "task_method": self._text(task.get("method")),
                "task_source": self._text(task.get("source")),
                "uuid": self._text(task.get("uuid") or row.get("_id")),
                "result_url": self._text(row.get("result")),
                "screenshot_url": self._text(row.get("screenshot")),
                "uniq_ips": stats.get("uniqIPs"),
                "uniq_countries": stats.get("uniqCountries"),
                "malicious": self._dig(verdicts, "overall", "malicious"),
                "brands": row.get("brands") or [],
            }
        )
        return record

    def _extract_pagination(
        self,
        payload: dict[str, Any],
        request: AdapterRequest,
        records: list[dict[str, Any]],
    ) -> dict[str, Any]:
        next_search_after = None
        if records:
            last = records[-1]
            sort_value = last.get("sort")
            if sort_value not in (None, ""):
                next_search_after = sort_value

        return {
            "size": request.params.get("size"),
            "offset": request.params.get("offset", 0),
            "returned": len(records),
            "total": payload.get("total") if isinstance(payload, dict) else None,
            "has_more": payload.get("has_more") if isinstance(payload, dict) else None,
            "search_after": next_search_after,
        }

    def _coerce_int(self, value: object, default: int) -> int:
        try:
            return int(value or default)
        except (TypeError, ValueError):
            return default

    def _dig(self, payload: dict[str, Any], *path: str) -> Any:
        current: Any = payload
        for key in path:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    def _deduplicate(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        deduplicated: list[str] = []
        for value in values:
            if value not in seen:
                seen.add(value)
                deduplicated.append(value)
        return deduplicated

    def _text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()
