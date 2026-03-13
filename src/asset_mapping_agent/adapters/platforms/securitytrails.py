from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from asset_mapping_agent.adapters.base import BasePlatformAdapter
from asset_mapping_agent.adapters.models import AdapterRequest, AdapterResponse, SearchExecutionResult
from asset_mapping_agent.query.models import CompiledQuery


@dataclass(slots=True)
class SecurityTrailsCredentials:
    api_key: str


class SecurityTrailsAdapter(BasePlatformAdapter):
    platform = "securitytrails"
    base_url = "https://api.securitytrails.com/v1"

    def __init__(self, credentials: SecurityTrailsCredentials) -> None:
        self.credentials = credentials

    def build_search_request(self, compiled: CompiledQuery, **kwargs: object) -> AdapterRequest:
        hostname = self._normalize_hostname(compiled.query)
        mode = str(kwargs.get("mode") or compiled.metadata.get("lookup_mode") or "domain").strip().lower()
        if mode not in {"domain", "subdomains"}:
            mode = "domain"

        headers = {
            "APIKEY": self.credentials.api_key,
            "Accept": "application/json",
        }

        if not hostname:
            return AdapterRequest(
                platform=self.platform,
                method="GET",
                url=f"{self.base_url}/ping",
                headers=headers,
                metadata={
                    "compiled_query": compiled.query,
                    "hostname": "",
                    "mode": "invalid",
                },
            )

        path = f"/domain/{quote(hostname, safe='')}"
        if mode == "subdomains":
            path += "/subdomains"

        return AdapterRequest(
            platform=self.platform,
            method="GET",
            url=f"{self.base_url}{path}",
            headers=headers,
            metadata={
                "compiled_query": compiled.query,
                "hostname": hostname,
                "mode": mode,
            },
        )

    def parse_search_response(self, response: AdapterResponse) -> SearchExecutionResult:
        warnings: list[str] = []
        payload = response.payload if isinstance(response.payload, dict) else {}
        mode = str(response.request.metadata.get("mode") or "domain")
        hostname = self._text(response.request.metadata.get("hostname"))

        if not response.ok:
            warnings.append(response.error or "SecurityTrails request failed.")

        if not isinstance(response.payload, dict):
            warnings.append("SecurityTrails response payload is not a JSON object.")
            return SearchExecutionResult(
                platform=self.platform,
                request=response.request,
                response=response,
                records=[],
                warnings=warnings,
                pagination=self._extract_pagination(payload, response.request, 0),
            )

        if mode == "invalid":
            warnings.append("SecurityTrails query is empty; a domain or hostname is required.")
            records: list[dict[str, Any]] = []
        elif mode == "subdomains":
            records = self._parse_subdomain_records(payload, hostname)
        else:
            records = self._parse_domain_records(payload, hostname)

        message = payload.get("message") or payload.get("error")
        if isinstance(message, str) and message.strip() and not response.ok:
            warnings.append(message.strip())

        return SearchExecutionResult(
            platform=self.platform,
            request=response.request,
            response=response,
            records=records,
            warnings=self._deduplicate(warnings),
            pagination=self._extract_pagination(payload, response.request, len(records)),
        )

    def _parse_domain_records(self, payload: dict[str, Any], fallback_hostname: str) -> list[dict[str, Any]]:
        hostname = self._text(payload.get("hostname") or payload.get("domain") or fallback_hostname).lower()
        apex_domain = self._text(payload.get("apex_domain") or payload.get("root_domain") or hostname).lower()
        current_dns = payload.get("current_dns") if isinstance(payload.get("current_dns"), dict) else {}
        org = self._extract_org(payload)
        registrar = self._extract_registrar(payload)
        provider = self._extract_provider(payload)
        tags = self._normalize_list(payload.get("tags"))

        records: list[dict[str, Any]] = []
        for record_type, keys in (("a", ("ip", "value", "address")), ("aaaa", ("ipv6", "ip", "value", "address"))):
            for ip_value, raw_item in self._extract_dns_values(current_dns, record_type, keys):
                records.append(
                    {
                        "host": hostname,
                        "domain": apex_domain,
                        "ip": ip_value,
                        "service": "dns",
                        "service_name": "dns",
                        "product": provider,
                        "org": org,
                        "registrar": registrar,
                        "record_type": record_type.upper(),
                        "record_stats": raw_item,
                        "created_at": self._text(payload.get("created")),
                        "updated_at": self._text(payload.get("updated")),
                        "subdomains_count": payload.get("subdomains_count") or payload.get("subdomain_count"),
                        "tags": tags,
                        "current_dns": current_dns,
                    }
                )

        if records:
            return records

        return [
            {
                "host": hostname,
                "domain": apex_domain,
                "service": "dns",
                "service_name": "dns",
                "product": provider,
                "org": org,
                "registrar": registrar,
                "created_at": self._text(payload.get("created")),
                "updated_at": self._text(payload.get("updated")),
                "subdomains_count": payload.get("subdomains_count") or payload.get("subdomain_count"),
                "tags": tags,
                "current_dns": current_dns,
            }
        ]

    def _parse_subdomain_records(self, payload: dict[str, Any], fallback_hostname: str) -> list[dict[str, Any]]:
        apex_domain = self._text(payload.get("hostname") or payload.get("apex_domain") or fallback_hostname).lower()
        org = self._extract_org(payload)
        provider = self._extract_provider(payload)

        raw_values = payload.get("subdomains") or payload.get("records") or []
        if isinstance(raw_values, dict):
            raw_values = [raw_values]

        records: list[dict[str, Any]] = []
        for item in raw_values:
            subdomain = self._extract_subdomain(item)
            if not subdomain:
                continue
            host = subdomain if subdomain.endswith(apex_domain) else f"{subdomain}.{apex_domain}"
            records.append(
                {
                    "host": host.lower(),
                    "domain": apex_domain,
                    "service": "dns",
                    "service_name": "dns",
                    "product": provider,
                    "org": org,
                    "record_type": "SUBDOMAIN",
                    "subdomain": subdomain,
                }
            )
        return records

    def _extract_pagination(self, payload: dict[str, Any], request: AdapterRequest, count: int) -> dict[str, Any]:
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        return {
            "mode": request.metadata.get("mode"),
            "hostname": request.metadata.get("hostname"),
            "count": count,
            "total": meta.get("total") or meta.get("count") or count,
        }

    def _extract_dns_values(
        self,
        current_dns: dict[str, Any],
        record_type: str,
        keys: tuple[str, ...],
    ) -> list[tuple[str, dict[str, Any]]]:
        raw_section = current_dns.get(record_type)
        if isinstance(raw_section, dict):
            raw_values = raw_section.get("values", [])
        else:
            raw_values = raw_section or []

        if isinstance(raw_values, dict):
            raw_values = [raw_values]
        if not isinstance(raw_values, list):
            raw_values = [raw_values]

        extracted: list[tuple[str, dict[str, Any]]] = []
        for item in raw_values:
            if isinstance(item, dict):
                for key in keys:
                    value = self._text(item.get(key))
                    if value:
                        extracted.append((value, dict(item)))
                        break
            else:
                value = self._text(item)
                if value:
                    extracted.append((value, {"value": value}))
        return extracted

    def _extract_org(self, payload: dict[str, Any]) -> str:
        paths = [
            ("current_whois", "registrant", "organization"),
            ("current_whois", "registrant", "organization_name"),
            ("whois", "registrant", "organization"),
            ("registrant", "organization"),
            ("organization",),
        ]
        for path in paths:
            value = self._dig(payload, *path)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _extract_registrar(self, payload: dict[str, Any]) -> str:
        paths = [
            ("current_whois", "registrar", "name"),
            ("whois", "registrar", "name"),
            ("registrar",),
        ]
        for path in paths:
            value = self._dig(payload, *path)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _extract_provider(self, payload: dict[str, Any]) -> str:
        providers = self._normalize_list(payload.get("providers") or payload.get("provider"))
        return providers[0] if providers else ""

    def _extract_subdomain(self, item: Any) -> str:
        if isinstance(item, str):
            return item.strip().lower()
        if isinstance(item, dict):
            for key in ("subdomain", "hostname", "value"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip().lower()
        return ""

    def _normalize_list(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            text = value.strip()
            return [text] if text else []
        if isinstance(value, list):
            result: list[str] = []
            for item in value:
                text = self._text(item)
                if text and text not in result:
                    result.append(text)
            return result
        if isinstance(value, dict):
            result = []
            for item in value.values():
                text = self._text(item)
                if text and text not in result:
                    result.append(text)
            return result
        text = self._text(value)
        return [text] if text else []

    def _dig(self, payload: dict[str, Any], *path: str) -> Any:
        current: Any = payload
        for key in path:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    def _normalize_hostname(self, value: object) -> str:
        text = self._text(value).lower()
        if not text:
            return ""
        return text.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]

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
