from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from asset_mapping_agent.adapters.base import BasePlatformAdapter
from asset_mapping_agent.adapters.models import AdapterRequest, AdapterResponse, SearchExecutionResult
from asset_mapping_agent.query.models import CompiledQuery


@dataclass(slots=True)
class WhoisXmlCredentials:
    api_key: str


class WhoisXmlAdapter(BasePlatformAdapter):
    platform = "whoisxml"
    whois_url = "https://www.whoisxmlapi.com/whoisserver/WhoisService"
    subdomains_url = "https://subdomains.whoisxmlapi.com/api/v1"

    def __init__(self, credentials: WhoisXmlCredentials) -> None:
        self.credentials = credentials

    def build_search_request(self, compiled: CompiledQuery, **kwargs: object) -> AdapterRequest:
        hostname = self._normalize_hostname(compiled.query)
        mode = str(kwargs.get("mode") or compiled.metadata.get("lookup_mode") or "whois").strip().lower()
        if mode not in {"whois", "subdomains"}:
            mode = "whois"

        if not hostname:
            return AdapterRequest(
                platform=self.platform,
                method="GET",
                url=self.whois_url,
                params={
                    "apiKey": self.credentials.api_key,
                    "outputFormat": "JSON",
                },
                metadata={
                    "compiled_query": compiled.query,
                    "hostname": "",
                    "mode": "invalid",
                },
            )

        if mode == "subdomains":
            url = self.subdomains_url
            params = {
                "apiKey": self.credentials.api_key,
                "domainName": hostname,
                "outputFormat": "JSON",
            }
        else:
            url = self.whois_url
            params = {
                "apiKey": self.credentials.api_key,
                "domainName": hostname,
                "outputFormat": "JSON",
            }

        return AdapterRequest(
            platform=self.platform,
            method="GET",
            url=url,
            params=params,
            metadata={
                "compiled_query": compiled.query,
                "hostname": hostname,
                "mode": mode,
            },
        )

    def parse_search_response(self, response: AdapterResponse) -> SearchExecutionResult:
        warnings: list[str] = []
        payload = response.payload if isinstance(response.payload, dict) else {}
        mode = str(response.request.metadata.get("mode") or "whois")
        hostname = self._text(response.request.metadata.get("hostname"))

        if not response.ok:
            warnings.append(response.error or "WhoisXML API request failed.")

        if not isinstance(response.payload, dict):
            warnings.append("WhoisXML API response payload is not a JSON object.")
            return SearchExecutionResult(
                platform=self.platform,
                request=response.request,
                response=response,
                records=[],
                warnings=warnings,
                pagination=self._extract_pagination(payload, response.request, 0),
            )

        if mode == "invalid":
            warnings.append("WhoisXML API query is empty; a domain or hostname is required.")
            records: list[dict[str, Any]] = []
        elif mode == "subdomains":
            records = self._parse_subdomain_records(payload, hostname)
        else:
            records = self._parse_whois_records(payload, hostname)

        message = self._text(payload.get("ErrorMessage") or payload.get("error") or payload.get("message"))
        if message and (not response.ok or not records):
            warnings.append(message)

        return SearchExecutionResult(
            platform=self.platform,
            request=response.request,
            response=response,
            records=records,
            warnings=self._deduplicate(warnings),
            pagination=self._extract_pagination(payload, response.request, len(records)),
        )

    def _parse_whois_records(self, payload: dict[str, Any], fallback_hostname: str) -> list[dict[str, Any]]:
        record = payload.get("WhoisRecord") if isinstance(payload.get("WhoisRecord"), dict) else payload
        hostname = self._text(record.get("domainName") or fallback_hostname).lower()
        registry_data = record.get("registryData") if isinstance(record.get("registryData"), dict) else {}
        registrant = self._select_contact(record, registry_data, "registrant")
        admin = self._select_contact(record, registry_data, "administrativeContact")
        technical = self._select_contact(record, registry_data, "technicalContact")

        org = self._extract_org(registrant, admin, technical)
        country = self._extract_geo_value(registrant, admin, technical, "country")
        province = self._extract_geo_value(registrant, admin, technical, "state")
        city = self._extract_geo_value(registrant, admin, technical, "city")
        registrar = self._text(record.get("registrarName") or registry_data.get("registrarName"))
        name_servers = self._extract_name_servers(record, registry_data)
        ips = self._normalize_list(record.get("ips") or registry_data.get("ips"))
        statuses = self._normalize_list(record.get("status") or registry_data.get("status"))
        emails = self._extract_emails(record, registry_data, registrant, admin, technical)
        created_at = self._text(
            record.get("createdDateNormalized") or registry_data.get("createdDateNormalized") or record.get("createdDate")
        )
        updated_at = self._text(
            record.get("updatedDateNormalized") or registry_data.get("updatedDateNormalized") or record.get("updatedDate")
        )
        expires_at = self._text(
            record.get("expiresDateNormalized") or registry_data.get("expiresDateNormalized") or record.get("expiresDate")
        )

        records: list[dict[str, Any]] = []
        for ip in ips:
            records.append(
                {
                    "host": hostname,
                    "domain": hostname,
                    "ip": ip,
                    "service": "whois",
                    "service_name": "whois",
                    "org": org,
                    "country": country,
                    "province": province,
                    "city": city,
                    "registrar": registrar,
                    "name_servers": name_servers,
                    "contact_emails": emails,
                    "status": statuses,
                    "created_at": created_at,
                    "updated_at": updated_at,
                    "expires_at": expires_at,
                    "lookup_source": "whois",
                    "audit": record.get("audit"),
                }
            )

        if records:
            return records

        return [
            {
                "host": hostname,
                "domain": hostname,
                "service": "whois",
                "service_name": "whois",
                "org": org,
                "country": country,
                "province": province,
                "city": city,
                "registrar": registrar,
                "name_servers": name_servers,
                "contact_emails": emails,
                "status": statuses,
                "created_at": created_at,
                "updated_at": updated_at,
                "expires_at": expires_at,
                "lookup_source": "whois",
                "audit": record.get("audit"),
            }
        ]

    def _parse_subdomain_records(self, payload: dict[str, Any], fallback_hostname: str) -> list[dict[str, Any]]:
        search = self._text(payload.get("search") or fallback_hostname).lower()
        result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
        raw_records = result.get("records") if isinstance(result, dict) else []
        if isinstance(raw_records, dict):
            raw_records = [raw_records]

        records: list[dict[str, Any]] = []
        for item in raw_records or []:
            if not isinstance(item, dict):
                continue
            host = self._text(item.get("domain") or item.get("subdomain")).lower()
            if not host:
                continue
            records.append(
                {
                    "host": host,
                    "domain": search,
                    "service": "dns",
                    "service_name": "dns",
                    "record_type": "SUBDOMAIN",
                    "first_seen": self._text(item.get("firstSeen")),
                    "last_seen": self._text(item.get("lastSeen")),
                    "lookup_source": "subdomains_lookup",
                }
            )
        return records

    def _extract_pagination(self, payload: dict[str, Any], request: AdapterRequest, count: int) -> dict[str, Any]:
        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        return {
            "mode": request.metadata.get("mode"),
            "hostname": request.metadata.get("hostname"),
            "count": count,
            "total": result.get("total") or result.get("count") or count,
        }

    def _select_contact(self, record: dict[str, Any], registry_data: dict[str, Any], key: str) -> dict[str, Any]:
        candidate = record.get(key)
        if isinstance(candidate, dict) and candidate:
            return candidate
        candidate = registry_data.get(key)
        if isinstance(candidate, dict):
            return candidate
        return {}

    def _extract_org(self, *contacts: dict[str, Any]) -> str:
        for contact in contacts:
            for key in ("organization", "org", "name"):
                value = self._text(contact.get(key))
                if value:
                    return value
        return ""

    def _extract_geo_value(self, *contacts_and_key: Any) -> str:
        *contacts, key = contacts_and_key
        for contact in contacts:
            if not isinstance(contact, dict):
                continue
            value = self._text(contact.get(key))
            if value:
                return value
        return ""

    def _extract_name_servers(self, record: dict[str, Any], registry_data: dict[str, Any]) -> list[str]:
        sources = [record.get("nameServers"), registry_data.get("nameServers")]
        for source in sources:
            if isinstance(source, dict):
                hosts = source.get("hostNames") or source.get("ips") or source.get("rawText")
                values = self._normalize_list(hosts)
                if values:
                    return values
            values = self._normalize_list(source)
            if values:
                return values
        return []

    def _extract_emails(
        self,
        record: dict[str, Any],
        registry_data: dict[str, Any],
        registrant: dict[str, Any],
        admin: dict[str, Any],
        technical: dict[str, Any],
    ) -> list[str]:
        values: list[str] = []
        for candidate in (
            record.get("contactEmail"),
            registry_data.get("contactEmail"),
            registrant.get("email"),
            admin.get("email"),
            technical.get("email"),
        ):
            for item in self._normalize_list(candidate):
                if item and item not in values:
                    values.append(item)
        return values

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
            result: list[str] = []
            for item in value.values():
                text = self._text(item)
                if text and text not in result:
                    result.append(text)
            return result
        text = self._text(value)
        return [text] if text else []

    def _normalize_hostname(self, value: object) -> str:
        text = self._text(value).lower()
        if not text:
            return ""
        if "://" in text:
            parsed = urlparse(text)
            return (parsed.hostname or "").strip().lower()
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
