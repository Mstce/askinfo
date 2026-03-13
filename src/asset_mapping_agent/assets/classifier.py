from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any

from asset_mapping_agent.assets.models import MergedAssetRecord


LOGIN_KEYWORDS = [
    "登录",
    "login",
    "signin",
    "sign in",
    "sso",
    "统一身份认证",
    "单点登录",
    "认证中心",
]

ADMIN_KEYWORDS = [
    "后台",
    "管理后台",
    "控制台",
    "管理系统",
    "运维平台",
    "dashboard",
    "console",
    "backend",
]

ADMIN_PATTERNS = [
    r"(^|[._/\-\s])admin($|[._/\-\s])",
    r"(^|[._/\-\s])(manage|management|manager)($|[._/\-\s])",
    r"(^|[._/\-\s])(console|dashboard|backend)($|[._/\-\s])",
    r"/admin($|[/?#])",
    r"/manage($|[/?#])",
    r"/console($|[/?#])",
]

MIDDLEWARE_PRODUCTS = {
    "jenkins": ["jenkins"],
    "nexus": ["nexus", "nexus repository"],
    "gitlab": ["gitlab"],
    "harbor": ["harbor"],
    "sonarqube": ["sonarqube"],
    "minio": ["minio"],
    "nacos": ["nacos"],
    "grafana": ["grafana"],
    "kibana": ["kibana"],
    "prometheus": ["prometheus"],
    "rabbitmq": ["rabbitmq"],
    "rocketmq": ["rocketmq"],
    "kafka": ["kafka"],
    "emqx": ["emqx"],
    "consul": ["consul"],
    "zookeeper": ["zookeeper"],
    "redis": ["redis"],
}

ENVIRONMENT_RULES = [
    ("test", [r"(^|[._/\-\s])(test|testing|qa)($|[._/\-\s])"], ["测试"]),
    ("dev", [r"(^|[._/\-\s])dev($|[._/\-\s])"], ["开发"]),
    ("uat", [r"(^|[._/\-\s])uat($|[._/\-\s])"], []),
    ("sit", [r"(^|[._/\-\s])sit($|[._/\-\s])"], []),
    (
        "staging",
        [r"(^|[._/\-\s])(stage|staging|pre|preprod|pre-prod)($|[._/\-\s])"],
        ["预发", "预生产", "灰度"],
    ),
    ("demo", [r"(^|[._/\-\s])demo($|[._/\-\s])"], ["演示"]),
    ("prod", [r"(^|[._/\-\s])(prod|prd|production)($|[._/\-\s])"], ["生产环境"]),
]


@dataclass(slots=True)
class AssetTaggingService:
    def classify_assets(self, assets: list[MergedAssetRecord]) -> list[MergedAssetRecord]:
        return [self.classify_asset(asset) for asset in assets]

    def classify_asset(self, asset: MergedAssetRecord) -> MergedAssetRecord:
        texts = self._collect_texts(asset)
        lowered = [text.lower() for text in texts if text]
        combined = "\n".join(lowered)
        tags = list(asset.tags)

        if self._has_login_signal(combined):
            self._add_tag(tags, "login_page")

        if self._has_admin_signal(texts, lowered, combined):
            self._add_tag(tags, "admin_panel")

        middleware_hits = self._detect_middleware(combined)
        if middleware_hits:
            self._add_tag(tags, "middleware_console")
            for middleware in middleware_hits:
                self._add_tag(tags, f"middleware:{middleware}")

        environment = self._detect_environment(texts, lowered)
        if environment:
            self._add_tag(tags, f"env:{environment}")

        return replace(asset, tags=tags)

    def _has_login_signal(self, combined: str) -> bool:
        return any(keyword in combined for keyword in LOGIN_KEYWORDS)

    def _has_admin_signal(self, texts: list[str], lowered: list[str], combined: str) -> bool:
        if any(keyword in combined for keyword in ADMIN_KEYWORDS):
            return True
        return any(re.search(pattern, text) for text in lowered for pattern in ADMIN_PATTERNS)

    def _detect_middleware(self, combined: str) -> list[str]:
        hits: list[str] = []
        for middleware, keywords in MIDDLEWARE_PRODUCTS.items():
            if any(keyword in combined for keyword in keywords):
                hits.append(middleware)
        return hits

    def _detect_environment(self, texts: list[str], lowered: list[str]) -> str:
        original_combined = "\n".join(texts)
        for name, patterns, chinese_keywords in ENVIRONMENT_RULES:
            if any(re.search(pattern, text) for text in lowered for pattern in patterns):
                return name
            if any(keyword in original_combined for keyword in chinese_keywords):
                return name
        return ""

    def _collect_texts(self, asset: MergedAssetRecord) -> list[str]:
        values: list[str] = []
        for candidate in [
            asset.host,
            asset.domain,
            asset.url,
            asset.title,
            asset.service,
            asset.product,
            asset.org,
            asset.icp,
            *asset.hostnames,
        ]:
            self._append_text(values, candidate)

        for raw_record in asset.raw_records:
            self._extend_from_payload(values, raw_record.raw_payload)
        return values

    def _extend_from_payload(self, values: list[str], payload: Any) -> None:
        if isinstance(payload, str):
            self._append_text(values, payload)
            return
        if isinstance(payload, dict):
            for item in payload.values():
                self._extend_from_payload(values, item)
            return
        if isinstance(payload, (list, tuple, set)):
            for item in payload:
                self._extend_from_payload(values, item)

    def _append_text(self, values: list[str], candidate: Any) -> None:
        if not isinstance(candidate, str):
            return
        text = candidate.strip()
        if text and text not in values:
            values.append(text)

    def _add_tag(self, tags: list[str], tag: str) -> None:
        if tag not in tags:
            tags.append(tag)
