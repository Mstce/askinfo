from __future__ import annotations

from dataclasses import dataclass

from asset_mapping_agent.assets.models import AssetGeo, AssetRawRecord, MergedAssetRecord, NormalizedAssetRecord


@dataclass(slots=True)
class AssetMergeService:
    def merge_assets(self, assets: list[NormalizedAssetRecord]) -> list[MergedAssetRecord]:
        grouped: dict[str, list[NormalizedAssetRecord]] = {}
        for asset in assets:
            grouped.setdefault(asset.normalized_key, []).append(asset)
        return [self.merge_group(group) for group in grouped.values()]

    def merge_group(self, assets: list[NormalizedAssetRecord]) -> MergedAssetRecord:
        if not assets:
            raise ValueError("merge_group requires at least one asset")

        first = assets[0]
        merged = MergedAssetRecord(
            asset_id=first.asset_id,
            normalized_key=first.normalized_key,
            host=self._pick_scalar(assets, "host"),
            domain=self._pick_scalar(assets, "domain"),
            ip=self._pick_scalar(assets, "ip"),
            port=self._pick_port(assets),
            scheme=self._pick_scalar(assets, "scheme"),
            url=self._pick_scalar(assets, "url"),
            title=self._pick_scalar(assets, "title"),
            service=self._pick_scalar(assets, "service"),
            product=self._pick_scalar(assets, "product"),
            org=self._pick_scalar(assets, "org"),
            icp=self._pick_scalar(assets, "icp"),
            geo=AssetGeo(
                country=self._pick_geo(assets, "country"),
                province=self._pick_geo(assets, "province"),
                city=self._pick_geo(assets, "city"),
            ),
            hostnames=self._merge_list_fields(assets, "hostnames"),
            tags=self._merge_list_fields(assets, "tags"),
            source_platforms=self._merge_source_platforms(assets),
            source_queries=self._merge_source_queries(assets),
            raw_records=self._merge_raw_records(assets),
            conflict_fields=self._collect_conflicts(assets),
        )
        return merged

    def _pick_scalar(self, assets: list[NormalizedAssetRecord], field_name: str) -> str:
        for asset in assets:
            value = getattr(asset, field_name)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _pick_port(self, assets: list[NormalizedAssetRecord]) -> int | None:
        for asset in assets:
            if asset.port is not None:
                return asset.port
        return None

    def _pick_geo(self, assets: list[NormalizedAssetRecord], field_name: str) -> str:
        for asset in assets:
            value = getattr(asset.geo, field_name)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _merge_list_fields(self, assets: list[NormalizedAssetRecord], field_name: str) -> list[str]:
        values: list[str] = []
        for asset in assets:
            for item in getattr(asset, field_name):
                candidate = str(item).strip()
                if candidate and candidate not in values:
                    values.append(candidate)
        return values

    def _merge_source_platforms(self, assets: list[NormalizedAssetRecord]) -> list[str]:
        values: list[str] = []
        for asset in assets:
            if asset.platform and asset.platform not in values:
                values.append(asset.platform)
        return values

    def _merge_source_queries(self, assets: list[NormalizedAssetRecord]) -> list[str]:
        values: list[str] = []
        for asset in assets:
            if asset.source_query and asset.source_query not in values:
                values.append(asset.source_query)
        return values

    def _merge_raw_records(self, assets: list[NormalizedAssetRecord]) -> list[AssetRawRecord]:
        values: list[AssetRawRecord] = []
        for asset in assets:
            if asset.raw_record is not None:
                values.append(asset.raw_record)
        return values

    def _collect_conflicts(self, assets: list[NormalizedAssetRecord]) -> dict[str, list[str]]:
        conflicts: dict[str, list[str]] = {}
        for field_name in ("host", "domain", "ip", "scheme", "url", "title", "service", "product", "org", "icp"):
            values = self._collect_distinct_strings([getattr(asset, field_name) for asset in assets])
            if len(values) > 1:
                conflicts[field_name] = values

        for geo_field in ("country", "province", "city"):
            values = self._collect_distinct_strings([getattr(asset.geo, geo_field) for asset in assets])
            if len(values) > 1:
                conflicts[f"geo.{geo_field}"] = values

        port_values = self._collect_distinct_strings([
            str(asset.port) if asset.port is not None else "" for asset in assets
        ])
        if len(port_values) > 1:
            conflicts["port"] = port_values
        return conflicts

    def _collect_distinct_strings(self, raw_values: list[str]) -> list[str]:
        values: list[str] = []
        for raw_value in raw_values:
            candidate = str(raw_value).strip()
            if candidate and candidate not in values:
                values.append(candidate)
        return values
