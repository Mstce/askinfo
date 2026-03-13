from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AssetGeo:
    country: str = ""
    province: str = ""
    city: str = ""


@dataclass(slots=True)
class AssetRawRecord:
    platform: str
    raw_payload: dict[str, Any]
    normalized_key: str
    source_query: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class VerificationResult:
    asset_id: str
    method: str
    status: str
    status_code: int | None = None
    title: str = ""
    detail: str = ""
    verified_at: str = ""
    url: str = ""
    final_url: str = ""


@dataclass(slots=True)
class NormalizedAssetRecord:
    asset_id: str
    normalized_key: str
    platform: str
    host: str = ""
    domain: str = ""
    ip: str = ""
    port: int | None = None
    scheme: str = ""
    url: str = ""
    title: str = ""
    service: str = ""
    product: str = ""
    org: str = ""
    icp: str = ""
    geo: AssetGeo = field(default_factory=AssetGeo)
    hostnames: list[str] = field(default_factory=list)
    source_query: str = ""
    raw_record: AssetRawRecord | None = None
    tags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class MergedAssetRecord:
    asset_id: str
    normalized_key: str
    host: str = ""
    domain: str = ""
    ip: str = ""
    port: int | None = None
    scheme: str = ""
    url: str = ""
    title: str = ""
    service: str = ""
    product: str = ""
    org: str = ""
    icp: str = ""
    geo: AssetGeo = field(default_factory=AssetGeo)
    hostnames: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    source_platforms: list[str] = field(default_factory=list)
    source_queries: list[str] = field(default_factory=list)
    raw_records: list[AssetRawRecord] = field(default_factory=list)
    conflict_fields: dict[str, list[str]] = field(default_factory=dict)
    verification_results: list[VerificationResult] = field(default_factory=list)
