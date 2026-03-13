from __future__ import annotations

import html
import re
import socket
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from asset_mapping_agent.assets.models import MergedAssetRecord, VerificationResult


@dataclass(slots=True)
class HttpFetchResponse:
    url: str
    final_url: str
    status_code: int | None
    ok: bool
    body: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    error: str = ""


@dataclass(slots=True)
class TcpConnectResponse:
    host: str
    port: int
    ok: bool
    error: str = ""


class HttpFetcher(Protocol):
    def fetch(self, url: str, timeout: int, headers: dict[str, str]) -> HttpFetchResponse:
        ...


class TcpConnector(Protocol):
    def connect(self, host: str, port: int, timeout: int) -> TcpConnectResponse:
        ...


@dataclass(slots=True)
class UrllibHttpFetcher:
    user_agent: str = "askinfo/0.1"
    max_read_bytes: int = 65536

    def fetch(self, url: str, timeout: int, headers: dict[str, str]) -> HttpFetchResponse:
        merged_headers = {"User-Agent": self.user_agent}
        merged_headers.update(headers)
        request = Request(url=url, headers=merged_headers, method="GET")

        try:
            with urlopen(request, timeout=timeout) as response:
                body = response.read(self.max_read_bytes).decode("utf-8", errors="ignore")
                return HttpFetchResponse(
                    url=url,
                    final_url=response.geturl(),
                    status_code=getattr(response, "status", 200),
                    ok=True,
                    body=body,
                    headers=dict(response.headers.items()),
                )
        except HTTPError as exc:
            body = exc.read(self.max_read_bytes).decode("utf-8", errors="ignore")
            return HttpFetchResponse(
                url=url,
                final_url=exc.geturl(),
                status_code=exc.code,
                ok=False,
                body=body,
                headers=dict(exc.headers.items()),
                error=f"HTTPError: {exc.code}",
            )
        except URLError as exc:
            return HttpFetchResponse(
                url=url,
                final_url=url,
                status_code=None,
                ok=False,
                error=f"URLError: {exc.reason}",
            )
        except Exception as exc:
            return HttpFetchResponse(
                url=url,
                final_url=url,
                status_code=None,
                ok=False,
                error=f"UnexpectedError: {exc}",
            )


@dataclass(slots=True)
class SocketTcpConnector:
    def connect(self, host: str, port: int, timeout: int) -> TcpConnectResponse:
        try:
            connection = socket.create_connection((host, port), timeout=timeout)
            connection.close()
            return TcpConnectResponse(host=host, port=port, ok=True)
        except ConnectionRefusedError:
            return TcpConnectResponse(host=host, port=port, ok=False, error="ConnectionRefused")
        except TimeoutError:
            return TcpConnectResponse(host=host, port=port, ok=False, error="Timeout")
        except socket.timeout:
            return TcpConnectResponse(host=host, port=port, ok=False, error="Timeout")
        except OSError as exc:
            return TcpConnectResponse(host=host, port=port, ok=False, error=f"OSError: {exc}")
        except Exception as exc:
            return TcpConnectResponse(host=host, port=port, ok=False, error=f"UnexpectedError: {exc}")


@dataclass(slots=True)
class HttpVerificationService:
    timeout: int = 15
    headers: dict[str, str] = field(default_factory=dict)

    def verify_asset(
        self,
        asset: MergedAssetRecord,
        fetcher: HttpFetcher | None = None,
    ) -> VerificationResult:
        target_url = self._resolve_target_url(asset)
        verified_at = _now()
        if not target_url:
            return VerificationResult(
                asset_id=asset.asset_id,
                method="http_request",
                status="skipped",
                detail="Asset is not an HTTP/HTTPS candidate.",
                verified_at=verified_at,
            )

        client = fetcher or UrllibHttpFetcher()
        response = client.fetch(target_url, timeout=self.timeout, headers=self.headers)
        title = self._extract_title(response.body)
        status = self._map_status(response)
        detail = response.error
        if not detail and not response.ok and response.status_code is not None:
            detail = f"HTTP status {response.status_code}"

        return VerificationResult(
            asset_id=asset.asset_id,
            method="http_request",
            status=status,
            status_code=response.status_code,
            title=title,
            detail=detail,
            verified_at=verified_at,
            url=target_url,
            final_url=response.final_url,
        )

    def verify_assets(
        self,
        assets: list[MergedAssetRecord],
        fetcher: HttpFetcher | None = None,
    ) -> list[MergedAssetRecord]:
        verified_assets: list[MergedAssetRecord] = []
        for asset in assets:
            result = self.verify_asset(asset, fetcher=fetcher)
            verification_results = list(asset.verification_results)
            verification_results.append(result)
            verified_assets.append(replace(asset, verification_results=verification_results))
        return verified_assets

    def _resolve_target_url(self, asset: MergedAssetRecord) -> str:
        if asset.url.startswith(("http://", "https://")):
            return asset.url

        scheme = asset.scheme.lower() if asset.scheme else ""
        target = asset.host or asset.domain or asset.ip
        if scheme in {"http", "https"} and target:
            if asset.port and not self._is_default_port(scheme, asset.port):
                return f"{scheme}://{target}:{asset.port}"
            return f"{scheme}://{target}"

        if asset.port == 443 and target:
            return f"https://{target}"
        if asset.port == 80 and target:
            return f"http://{target}"
        return ""

    def _map_status(self, response: HttpFetchResponse) -> str:
        if response.ok:
            return "success"
        if response.status_code is not None:
            return "http_error"
        return "network_error"

    def _extract_title(self, body: str) -> str:
        if not body:
            return ""
        match = re.search(r"<title[^>]*>(.*?)</title>", body, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            return ""
        title = html.unescape(match.group(1))
        title = re.sub(r"\s+", " ", title).strip()
        return title

    def _is_default_port(self, scheme: str, port: int) -> bool:
        return (scheme == "http" and port == 80) or (scheme == "https" and port == 443)


@dataclass(slots=True)
class TcpVerificationService:
    timeout: int = 10

    def verify_asset(
        self,
        asset: MergedAssetRecord,
        connector: TcpConnector | None = None,
    ) -> VerificationResult:
        verified_at = _now()
        target = asset.host or asset.domain or asset.ip
        if not target or asset.port is None:
            return VerificationResult(
                asset_id=asset.asset_id,
                method="tcp_connect",
                status="skipped",
                detail="Asset is missing host/ip or port for TCP verification.",
                verified_at=verified_at,
            )

        client = connector or SocketTcpConnector()
        response = client.connect(target, asset.port, timeout=self.timeout)
        status = self._map_status(response)
        detail = response.error
        target_url = f"tcp://{target}:{asset.port}"

        return VerificationResult(
            asset_id=asset.asset_id,
            method="tcp_connect",
            status=status,
            detail=detail,
            verified_at=verified_at,
            url=target_url,
            final_url=target_url,
        )

    def verify_assets(
        self,
        assets: list[MergedAssetRecord],
        connector: TcpConnector | None = None,
    ) -> list[MergedAssetRecord]:
        verified_assets: list[MergedAssetRecord] = []
        for asset in assets:
            result = self.verify_asset(asset, connector=connector)
            verification_results = list(asset.verification_results)
            verification_results.append(result)
            verified_assets.append(replace(asset, verification_results=verification_results))
        return verified_assets

    def _map_status(self, response: TcpConnectResponse) -> str:
        if response.ok:
            return "success"
        if response.error == "ConnectionRefused":
            return "refused"
        if response.error == "Timeout":
            return "timeout"
        return "network_error"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
