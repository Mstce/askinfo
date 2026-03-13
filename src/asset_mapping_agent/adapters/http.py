from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from asset_mapping_agent.adapters.models import AdapterRequest, AdapterResponse


class HttpClient(Protocol):
    def execute(self, request: AdapterRequest) -> AdapterResponse:
        ...


@dataclass(slots=True)
class UrllibHttpClient:
    user_agent: str = "askinfo/0.1"

    def execute(self, request: AdapterRequest) -> AdapterResponse:
        url = request.url
        if request.method.upper() == "GET" and request.params:
            query_string = urlencode(request.params, doseq=True)
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}{query_string}"

        headers = {"User-Agent": self.user_agent}
        headers.update(request.headers)

        data = None
        if request.json_body is not None:
            data = json.dumps(request.json_body).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")

        req = Request(url=url, data=data, headers=headers, method=request.method.upper())
        try:
            with urlopen(req, timeout=request.timeout) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
                payload = self._parse_payload(raw)
                return AdapterResponse(
                    platform=request.platform,
                    request=request,
                    status_code=getattr(resp, "status", 200),
                    ok=True,
                    payload=payload,
                    raw_text=raw,
                )
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="ignore")
            payload = self._parse_payload(raw)
            return AdapterResponse(
                platform=request.platform,
                request=request,
                status_code=exc.code,
                ok=False,
                payload=payload,
                error=f"HTTPError: {exc.code}",
                raw_text=raw,
            )
        except URLError as exc:
            return AdapterResponse(
                platform=request.platform,
                request=request,
                status_code=0,
                ok=False,
                payload=None,
                error=f"URLError: {exc.reason}",
            )
        except Exception as exc:
            return AdapterResponse(
                platform=request.platform,
                request=request,
                status_code=0,
                ok=False,
                payload=None,
                error=f"UnexpectedError: {exc}",
            )

    def _parse_payload(self, raw: str):
        try:
            return json.loads(raw)
        except Exception:
            return raw
