from __future__ import annotations

from dataclasses import dataclass, field

from .compiler_base import BaseQueryCompiler
from .models import CompiledQuery, QueryIntent
from .platforms import (
    FofaCompiler,
    HunterCompiler,
    QuakeCompiler,
    SecurityTrailsCompiler,
    ShodanCompiler,
    UrlscanCompiler,
    WhoisXmlCompiler,
)


PLATFORM_ALIASES = {
    "360_quake": "quake",
    "360-quake": "quake",
}


@dataclass(slots=True)
class CompilerRegistry:
    compilers: dict[str, BaseQueryCompiler] = field(default_factory=dict)

    @classmethod
    def default(cls) -> "CompilerRegistry":
        return cls(
            compilers={
                "fofa": FofaCompiler(),
                "shodan": ShodanCompiler(),
                "quake": QuakeCompiler(),
                "hunter": HunterCompiler(),
                "urlscan": UrlscanCompiler(),
                "securitytrails": SecurityTrailsCompiler(),
                "whoisxml": WhoisXmlCompiler(),
            }
        )

    def compile_for_platform(self, platform: str, intent: QueryIntent) -> CompiledQuery:
        key = self._normalize_platform(platform)
        if key not in self.compilers:
            raise KeyError(f"Unsupported platform: {platform}")
        return self.compilers[key].compile(intent)

    def compile_for_platforms(self, platforms: list[str], intent: QueryIntent) -> list[CompiledQuery]:
        return [self.compile_for_platform(platform, intent) for platform in platforms]

    def _normalize_platform(self, platform: str) -> str:
        key = platform.strip().lower().replace("-", "_").replace(" ", "_")
        return PLATFORM_ALIASES.get(key, key)
