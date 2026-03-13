from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class RuntimeSettings:
    fofa_email: str = ""
    fofa_api_key: str = ""
    quake_api_key: str = ""
    hunter_api_key: str = ""
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4.1-mini"
    openai_timeout: int = 60
    shodan_api_key: str = ""
    urlscan_api_key: str = ""
    securitytrails_api_key: str = ""
    whoisxml_api_key: str = ""
    request_timeout: int = 20
    http_proxy: str = ""
    https_proxy: str = ""

    @classmethod
    def from_env(cls) -> "RuntimeSettings":
        return cls(
            fofa_email=os.getenv("FOFA_EMAIL", "").strip(),
            fofa_api_key=os.getenv("FOFA_API_KEY", "").strip(),
            quake_api_key=os.getenv("QUAKE_API_KEY", "").strip(),
            hunter_api_key=os.getenv("HUNTER_API_KEY", "").strip(),
            openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip(),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip(),
            openai_timeout=int(os.getenv("OPENAI_TIMEOUT", "60") or "60"),
            shodan_api_key=os.getenv("SHODAN_API_KEY", "").strip(),
            urlscan_api_key=os.getenv("URLSCAN_API_KEY", "").strip(),
            securitytrails_api_key=os.getenv("SECURITYTRAILS_API_KEY", "").strip(),
            whoisxml_api_key=os.getenv("WHOISXML_API_KEY", "").strip(),
            request_timeout=int(os.getenv("REQUEST_TIMEOUT", "20") or "20"),
            http_proxy=os.getenv("HTTP_PROXY", "").strip(),
            https_proxy=os.getenv("HTTPS_PROXY", "").strip(),
        )

    @classmethod
    def from_env_file(cls, path: str | Path = ".env") -> "RuntimeSettings":
        file_path = Path(path)
        if not file_path.exists():
            return cls.from_env()

        parsed = dict(os.environ)
        for raw_line in file_path.read_text(encoding="utf-8-sig").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            parsed[key.strip()] = value.strip().strip('"').strip("'")

        return cls(
            fofa_email=parsed.get("FOFA_EMAIL", "").strip(),
            fofa_api_key=parsed.get("FOFA_API_KEY", "").strip(),
            quake_api_key=parsed.get("QUAKE_API_KEY", "").strip(),
            hunter_api_key=parsed.get("HUNTER_API_KEY", "").strip(),
            openai_api_key=parsed.get("OPENAI_API_KEY", "").strip(),
            openai_base_url=parsed.get("OPENAI_BASE_URL", "https://api.openai.com/v1").strip(),
            openai_model=parsed.get("OPENAI_MODEL", "gpt-4.1-mini").strip(),
            openai_timeout=int(parsed.get("OPENAI_TIMEOUT", "60") or "60"),
            shodan_api_key=parsed.get("SHODAN_API_KEY", "").strip(),
            urlscan_api_key=parsed.get("URLSCAN_API_KEY", "").strip(),
            securitytrails_api_key=parsed.get("SECURITYTRAILS_API_KEY", "").strip(),
            whoisxml_api_key=parsed.get("WHOISXML_API_KEY", "").strip(),
            request_timeout=int(parsed.get("REQUEST_TIMEOUT", "20") or "20"),
            http_proxy=parsed.get("HTTP_PROXY", "").strip(),
            https_proxy=parsed.get("HTTPS_PROXY", "").strip(),
        )
