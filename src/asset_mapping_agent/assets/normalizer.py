from __future__ import annotations

import hashlib
import ipaddress
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from asset_mapping_agent.assets.models import AssetGeo, AssetRawRecord, NormalizedAssetRecord
from asset_mapping_agent.execution.service import ExecutionBatchResult, PlatformExecution


@dataclass(slots=True)
class AssetNormalizationService:
    def normalize_batch(self, batch: ExecutionBatchResult) -> list[NormalizedAssetRecord]:
        assets: list[NormalizedAssetRecord] = []
        for execution in batch.executions.values():
            assets.extend(self.normalize_platform_execution(execution))
        return assets

    def normalize_platform_execution(self, execution: PlatformExecution) -> list[NormalizedAssetRecord]:
        normalized: list[NormalizedAssetRecord] = []
        source_query = execution.compiled_query.query
        warnings = execution.search_result.warnings

        for record in execution.search_result.records:
            normalized_record = self.normalize_record(
                execution.platform,
                record,
                source_query=source_query,
                warnings=warnings,
            )
            normalized.append(normalized_record)
        return normalized

    def normalize_record(
        self,
        platform: str,
        record: dict[str, Any],
        *,
        source_query: str = "",
        warnings: list[str] | None = None,
    ) -> NormalizedAssetRecord:
        normalized_platform = self._normalize_platform(platform)
        host = self._extract_host(record)
        ip = self._extract_ip(record, host)
        hostnames = self._extract_hostnames(record, host, ip)
        domain = self._extract_domain(record, host, hostnames, ip)
        port = self._extract_port(record)
        scheme = self._extract_scheme(record, port)
        url = self._extract_url(record, host, domain, ip, scheme, port)
        title = self._clean_text(record.get("title"))
        service = self._extract_service(record)
        product = self._extract_product(record)
        org = self._clean_text(record.get("org") or record.get("organization"))
        icp = self._clean_text(record.get("icp") or record.get("icp_org"))
        geo = AssetGeo(
            country=self._clean_text(record.get("country")),
            province=self._clean_text(record.get("province")),
            city=self._clean_text(record.get("city")),
        )

        normalized_key = self._build_normalized_key(scheme, host or domain or ip, port)
        asset_id = self._build_asset_id(normalized_key)
        raw_record = AssetRawRecord(
            platform=normalized_platform,
            raw_payload=dict(record),
            normalized_key=normalized_key,
            source_query=source_query,
            warnings=list(warnings or []),
        )

        return NormalizedAssetRecord(
            asset_id=asset_id,
            normalized_key=normalized_key,
            platform=normalized_platform,
            host=host,
            domain=domain,
            ip=ip,
            port=port,
            scheme=scheme,
            url=url,
            title=title,
            service=service,
            product=product,
            org=org,
            icp=icp,
            geo=geo,
            hostnames=hostnames,
            source_query=source_query,
            raw_record=raw_record,
        )

    def _extract_host(self, record: dict[str, Any]) -> str:
        host_value = record.get("host") or record.get("url")
        if isinstance(host_value, str):
            parsed = urlparse(host_value)
            if parsed.hostname:
                return parsed.hostname.lower()
            cleaned = host_value.strip().lower().strip("/")
            if cleaned and "://" not in cleaned and "/" not in cleaned:
                return cleaned
        for key in ("hostnames", "names"):
            value = record.get(key)
            if isinstance(value, list) and value:
                candidate = str(value[0]).strip().lower()
                if candidate:
                    return candidate
        return ""

    def _extract_ip(self, record: dict[str, Any], host: str) -> str:
        raw_ip = record.get("ip") or record.get("address") or record.get("host_ip")
        if isinstance(raw_ip, str) and self._is_ip(raw_ip):
            return raw_ip
        if host and self._is_ip(host):
            return host
        return ""

    def _extract_hostnames(self, record: dict[str, Any], host: str, ip: str) -> list[str]:
        values: list[str] = []
        for key in ("hostnames", "names"):
            raw = record.get(key)
            if isinstance(raw, list):
                for item in raw:
                    candidate = str(item).strip().lower()
                    if candidate and candidate not in values and candidate != ip:
                        values.append(candidate)
        if host and host != ip and host not in values:
            values.insert(0, host)
        return values

    def _extract_domain(self, record: dict[str, Any], host: str, hostnames: list[str], ip: str) -> str:
        raw_domain = record.get("domain")
        if isinstance(raw_domain, str) and raw_domain.strip():
            return raw_domain.strip().lower()
        for candidate in [host, *hostnames]:
            if candidate and candidate != ip and not self._is_ip(candidate):
                return candidate
        return ""

    def _extract_port(self, record: dict[str, Any]) -> int | None:
        raw_port = record.get("port")
        if raw_port in (None, ""):
            return None
        try:
            value = int(str(raw_port).strip())
        except (TypeError, ValueError):
            return None
        return value if 1 <= value <= 65535 else None

    def _extract_scheme(self, record: dict[str, Any], port: int | None) -> str:
        for key in ("protocol", "scheme"):
            value = record.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip().lower()

        if port == 443:
            return "https"
        if port == 80:
            return "http"

        service_name = self._clean_text(record.get("service_name") or record.get("service"))
        if service_name.lower() in {"https", "http"}:
            return service_name.lower()
        return ""

    def _extract_url(self, record: dict[str, Any], host: str, domain: str, ip: str, scheme: str, port: int | None) -> str:
        for key in ("url",):
            value = record.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        raw_host = record.get("host")
        if isinstance(raw_host, str) and raw_host.startswith(("http://", "https://")):
            return raw_host.strip()

        target = host or domain or ip
        if not target:
            return ""
        if not scheme:
            return target
        if port and self._is_default_port(scheme, port):
            return f"{scheme}://{target}"
        if port:
            return f"{scheme}://{target}:{port}"
        return f"{scheme}://{target}"

    def _extract_service(self, record: dict[str, Any]) -> str:
        for key in ("service_name", "service", "server"):
            value = record.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _extract_product(self, record: dict[str, Any]) -> str:
        value = record.get("product")
        if isinstance(value, str) and value.strip():
            return value.strip()

        services = record.get("services")
        if isinstance(services, list):
            for service in services:
                if isinstance(service, dict):
                    candidate = service.get("product") or service.get("software")
                    if isinstance(candidate, str) and candidate.strip():
                        return candidate.strip()
                    if isinstance(candidate, dict):
                        name = candidate.get("product")
                        if isinstance(name, str) and name.strip():
                            return name.strip()
        return ""

    def _build_normalized_key(self, scheme: str, target: str, port: int | None) -> str:
        normalized_target = (target or "").strip().lower()
        normalized_scheme = scheme.strip().lower() if scheme else ""
        if normalized_scheme and port:
            return f"{normalized_scheme}://{normalized_target}:{port}"
        if port:
            return f"{normalized_target}:{port}"
        return normalized_target

    def _build_asset_id(self, normalized_key: str) -> str:
        return hashlib.sha1(normalized_key.encode("utf-8")).hexdigest()[:16]

    def _normalize_platform(self, platform: str) -> str:
        return platform.strip().lower().replace("-", "_").replace(" ", "_")

    def _clean_text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()

    def _is_ip(self, value: str) -> bool:
        try:
            ipaddress.ip_address(value)
            return True
        except ValueError:
            return False

    def _is_default_port(self, scheme: str, port: int) -> bool:
        return (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
