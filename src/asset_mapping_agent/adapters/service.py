from __future__ import annotations

from dataclasses import dataclass, field

from asset_mapping_agent.adapters.base import BasePlatformAdapter
from asset_mapping_agent.adapters.http import HttpClient
from asset_mapping_agent.adapters.models import SearchExecutionResult
from asset_mapping_agent.query.models import CompiledQuery


PLATFORM_ALIASES = {
    "360_quake": "quake",
    "360-quake": "quake",
}


@dataclass(slots=True)
class AdapterRegistry:
    adapters: dict[str, BasePlatformAdapter] = field(default_factory=dict)

    def register(self, adapter: BasePlatformAdapter, *aliases: str) -> None:
        self.adapters[self._normalize_platform(adapter.platform)] = adapter
        for alias in aliases:
            self.adapters[self._normalize_platform(alias)] = adapter

    def get(self, platform: str) -> BasePlatformAdapter:
        key = self._normalize_platform(platform)
        if key not in self.adapters:
            raise KeyError(f"Unsupported adapter platform: {platform}")
        return self.adapters[key]

    def execute(
        self,
        compiled: CompiledQuery,
        http_client: HttpClient | None = None,
        **kwargs: object,
    ) -> SearchExecutionResult:
        adapter = self.get(compiled.platform)
        return adapter.search(compiled, http_client=http_client, **kwargs)

    def _normalize_platform(self, platform: str) -> str:
        key = platform.strip().lower().replace("-", "_").replace(" ", "_")
        return PLATFORM_ALIASES.get(key, key)
