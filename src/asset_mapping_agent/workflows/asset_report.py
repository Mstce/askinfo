from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

from asset_mapping_agent.assets import (
    AssetMergeService,
    AssetNormalizationService,
    AssetTaggingService,
    HttpFetcher,
    HttpVerificationService,
    MergedAssetRecord,
    NormalizedAssetRecord,
    TcpConnector,
    TcpVerificationService,
)
from asset_mapping_agent.execution import ExecutionBatchResult, QueryExecutionService
from asset_mapping_agent.parsing import NaturalLanguageQueryParser
from asset_mapping_agent.query import QueryIntent
from asset_mapping_agent.reporting import AssetWorkbookExportResult, AssetWorkbookExporter


@dataclass(slots=True)
class PreparedAssetBatch:
    normalized_assets: list[NormalizedAssetRecord]
    merged_assets: list[MergedAssetRecord]


@dataclass(slots=True)
class AssetReportWorkflowResult:
    batch: ExecutionBatchResult
    normalized_assets: list[NormalizedAssetRecord]
    merged_assets: list[MergedAssetRecord]
    export_result: AssetWorkbookExportResult


class AssetReportWorkflowService:
    def __init__(
        self,
        query_execution_service: QueryExecutionService,
        normalizer: AssetNormalizationService | None = None,
        merger: AssetMergeService | None = None,
        tagger: AssetTaggingService | None = None,
        http_verifier: HttpVerificationService | None = None,
        tcp_verifier: TcpVerificationService | None = None,
        exporter: AssetWorkbookExporter | None = None,
    ) -> None:
        self.query_execution_service = query_execution_service
        self.normalizer = normalizer or AssetNormalizationService()
        self.merger = merger or AssetMergeService()
        self.tagger = tagger or AssetTaggingService()
        self.http_verifier = http_verifier or HttpVerificationService()
        self.tcp_verifier = tcp_verifier or TcpVerificationService()
        self.exporter = exporter or AssetWorkbookExporter()

    def prepare_assets(
        self,
        batch: ExecutionBatchResult,
        http_fetcher: HttpFetcher | None = None,
        tcp_connector: TcpConnector | None = None,
    ) -> PreparedAssetBatch:
        normalized_assets = self.normalizer.normalize_batch(batch)
        merged_assets = self.merger.merge_assets(normalized_assets)
        tagged_assets = self.tagger.classify_assets(merged_assets)
        verified_assets = self._verify_assets(
            tagged_assets,
            http_fetcher=http_fetcher,
            tcp_connector=tcp_connector,
        )
        return PreparedAssetBatch(
            normalized_assets=normalized_assets,
            merged_assets=verified_assets,
        )

    def export_batch_to_xlsx(
        self,
        batch: ExecutionBatchResult,
        output_path: str | Path,
        baseline_keys: Iterable[str] | None = None,
        http_fetcher: HttpFetcher | None = None,
        tcp_connector: TcpConnector | None = None,
    ) -> AssetReportWorkflowResult:
        prepared = self.prepare_assets(
            batch,
            http_fetcher=http_fetcher,
            tcp_connector=tcp_connector,
        )
        export_result = self.exporter.export(
            prepared.merged_assets,
            output_path=output_path,
            baseline_keys=baseline_keys,
        )
        return AssetReportWorkflowResult(
            batch=batch,
            normalized_assets=prepared.normalized_assets,
            merged_assets=prepared.merged_assets,
            export_result=export_result,
        )

    def execute_text_to_xlsx(
        self,
        text: str,
        platforms: list[str],
        output_path: str | Path,
        *,
        parser: NaturalLanguageQueryParser | None = None,
        http_clients: dict[str, object] | None = None,
        platform_options: dict[str, dict[str, object]] | None = None,
        baseline_keys: Iterable[str] | None = None,
        http_fetcher: HttpFetcher | None = None,
        tcp_connector: TcpConnector | None = None,
    ) -> AssetReportWorkflowResult:
        batch = self.query_execution_service.execute_text(
            text,
            platforms,
            parser=parser,
            http_clients=http_clients,
            platform_options=platform_options,
        )
        return self.export_batch_to_xlsx(
            batch,
            output_path=output_path,
            baseline_keys=baseline_keys,
            http_fetcher=http_fetcher,
            tcp_connector=tcp_connector,
        )

    def execute_intent_to_xlsx(
        self,
        intent: QueryIntent,
        platforms: list[str],
        output_path: str | Path,
        *,
        http_clients: dict[str, object] | None = None,
        platform_options: dict[str, dict[str, object]] | None = None,
        baseline_keys: Iterable[str] | None = None,
        http_fetcher: HttpFetcher | None = None,
        tcp_connector: TcpConnector | None = None,
    ) -> AssetReportWorkflowResult:
        batch = self.query_execution_service.execute_intent(
            intent,
            platforms,
            http_clients=http_clients,
            platform_options=platform_options,
        )
        return self.export_batch_to_xlsx(
            batch,
            output_path=output_path,
            baseline_keys=baseline_keys,
            http_fetcher=http_fetcher,
            tcp_connector=tcp_connector,
        )

    def _verify_assets(
        self,
        assets: list[MergedAssetRecord],
        *,
        http_fetcher: HttpFetcher | None,
        tcp_connector: TcpConnector | None,
    ) -> list[MergedAssetRecord]:
        verified_assets: list[MergedAssetRecord] = []
        for asset in assets:
            if self._is_http_candidate(asset):
                result = self.http_verifier.verify_asset(asset, fetcher=http_fetcher)
                verified_assets.append(self._append_verification_result(asset, result))
                continue
            if self._is_tcp_candidate(asset):
                result = self.tcp_verifier.verify_asset(asset, connector=tcp_connector)
                verified_assets.append(self._append_verification_result(asset, result))
                continue
            verified_assets.append(asset)
        return verified_assets

    def _append_verification_result(self, asset: MergedAssetRecord, result) -> MergedAssetRecord:
        verification_results = list(asset.verification_results)
        verification_results.append(result)
        return replace(asset, verification_results=verification_results)

    def _is_http_candidate(self, asset: MergedAssetRecord) -> bool:
        if asset.url.startswith(("http://", "https://")):
            return True
        if asset.scheme.lower() in {"http", "https"}:
            return True
        return asset.port in {80, 443}

    def _is_tcp_candidate(self, asset: MergedAssetRecord) -> bool:
        target = asset.host or asset.domain or asset.ip
        return bool(target and asset.port is not None)
