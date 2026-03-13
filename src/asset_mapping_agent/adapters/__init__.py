from .base import BasePlatformAdapter
from .http import HttpClient, UrllibHttpClient
from .models import AdapterRequest, AdapterResponse, SearchExecutionResult
from .platforms.fofa import FofaAdapter, FofaCredentials
from .platforms.hunter import (
    HunterAdapter,
    HunterBatchDownloadResult,
    HunterBatchStatusResult,
    HunterBatchSubmitResult,
    HunterCredentials,
)
from .platforms.quake import QuakeAdapter, QuakeCredentials
from .platforms.securitytrails import SecurityTrailsAdapter, SecurityTrailsCredentials
from .platforms.shodan import ShodanAdapter, ShodanCredentials
from .platforms.urlscan import UrlscanAdapter, UrlscanCredentials
from .platforms.whoisxml import WhoisXmlAdapter, WhoisXmlCredentials
from .service import AdapterRegistry

__all__ = [
    "AdapterRegistry",
    "AdapterRequest",
    "AdapterResponse",
    "BasePlatformAdapter",
    "FofaAdapter",
    "FofaCredentials",
    "HttpClient",
    "HunterAdapter",
    "HunterBatchDownloadResult",
    "HunterBatchStatusResult",
    "HunterBatchSubmitResult",
    "HunterCredentials",
    "QuakeAdapter",
    "QuakeCredentials",
    "SearchExecutionResult",
    "SecurityTrailsAdapter",
    "SecurityTrailsCredentials",
    "ShodanAdapter",
    "ShodanCredentials",
    "UrlscanAdapter",
    "UrlscanCredentials",
    "UrllibHttpClient",
    "WhoisXmlAdapter",
    "WhoisXmlCredentials",
]
