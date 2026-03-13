from __future__ import annotations

from base64 import b64encode
from dataclasses import dataclass
from typing import Any

from asset_mapping_agent.adapters.base import BasePlatformAdapter
from asset_mapping_agent.adapters.models import AdapterRequest, AdapterResponse, SearchExecutionResult
from asset_mapping_agent.query.models import CompiledQuery


@dataclass(slots=True)
class FofaCredentials:
    email: str
    api_key: str


class FofaAdapter(BasePlatformAdapter):
    platform = "fofa"
    search_url = "https://en.fofa.info/api/v1/search/all"
    default_fields = [
        "host",
        "ip",
        "port",
        "protocol",
        "title",
        "domain",
        "server",
        "country",
        "province",
        "city",
    ]

    def __init__(self, credentials: FofaCredentials) -> None:
        self.credentials = credentials

    def build_search_request(self, compiled: CompiledQuery, **kwargs: object) -> AdapterRequest:
        page = int(kwargs.get("page", 1))
        fields = kwargs.get("fields", ",".join(self.default_fields))
        qbase64 = b64encode(compiled.query.encode("utf-8")).decode("ascii")
        return AdapterRequest(
            platform=self.platform,
            method="GET",
            url=self.search_url,
            params={
                "email": self.credentials.email,
                "key": self.credentials.api_key,
                "qbase64": qbase64,
                "fields": fields,
                "size": compiled.metadata.get("limit", 100),
                "page": page,
            },
            metadata={
                "compiled_query": compiled.query,
            },
        )

    def parse_search_response(self, response: AdapterResponse) -> SearchExecutionResult:
        warnings: list[str] = []
        payload = response.payload if isinstance(response.payload, dict) else {}
        records = self._parse_records(response.request, payload)
        pagination = {
            "page": payload.get("page", response.request.params.get("page", 1)),
            "size": payload.get("size", len(records)),
            "total": payload.get("total"),
            "mode": payload.get("mode"),
        }

        if not response.ok:
            warnings.append(response.error or "FOFA request failed.")
            return SearchExecutionResult(
                platform=self.platform,
                request=response.request,
                response=response,
                records=records,
                warnings=warnings,
                pagination=pagination,
            )

        if not isinstance(response.payload, dict):
            warnings.append("FOFA response payload is not a JSON object.")
            return SearchExecutionResult(
                platform=self.platform,
                request=response.request,
                response=response,
                records=[],
                warnings=warnings,
                pagination=pagination,
            )

        if payload.get("error"):
            message = payload.get("errmsg") or payload.get("message") or "FOFA API returned an error."
            warnings.append(str(message))

        return SearchExecutionResult(
            platform=self.platform,
            request=response.request,
            response=response,
            records=records,
            warnings=warnings,
            pagination=pagination,
        )

    def _parse_records(self, request: AdapterRequest, payload: dict[str, Any]) -> list[dict[str, Any]]:
        fields = self._resolve_fields(request)
        raw_results = payload.get("results", []) if isinstance(payload, dict) else []
        records: list[dict[str, Any]] = []

        for row in raw_results:
            if isinstance(row, dict):
                records.append(row)
                continue
            if isinstance(row, (list, tuple)):
                record = {
                    field: row[index] if index < len(row) else None
                    for index, field in enumerate(fields)
                }
                if len(row) > len(fields):
                    record["_extra"] = list(row[len(fields) :])
                records.append(record)
                continue
            records.append({"value": row})

        return records

    def _resolve_fields(self, request: AdapterRequest) -> list[str]:
        raw_fields = request.params.get("fields", ",".join(self.default_fields))
        if isinstance(raw_fields, str):
            return [field.strip() for field in raw_fields.split(",") if field.strip()]
        if isinstance(raw_fields, (list, tuple)):
            return [str(field).strip() for field in raw_fields if str(field).strip()]
        return list(self.default_fields)
