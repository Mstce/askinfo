from __future__ import annotations

from dataclasses import dataclass, field

from .models import ComparisonOperator


@dataclass(slots=True)
class PlatformCapability:
    name: str
    supported_fields: set[str]
    supported_operators: set[ComparisonOperator]
    field_mapping: dict[str, str]
    supports_or: bool = True
    supports_not: bool = True
    supports_time_range: bool = False
    supports_aggregation: bool = False
    requires_account_validation: bool = False
    notes: list[str] = field(default_factory=list)


COMMON_OPERATORS = {
    ComparisonOperator.EQ,
    ComparisonOperator.CONTAINS,
    ComparisonOperator.IN,
    ComparisonOperator.EXISTS,
}


PLATFORM_CAPABILITIES: dict[str, PlatformCapability] = {
    "fofa": PlatformCapability(
        name="FOFA",
        supported_fields={
            "keyword",
            "domain",
            "host",
            "ip",
            "port",
            "protocol",
            "title",
            "body",
            "header",
            "product",
            "service",
            "cert_subject",
            "org",
            "icp_org",
            "country",
            "province",
            "city",
        },
        supported_operators=COMMON_OPERATORS,
        field_mapping={
            "keyword": "keyword",
            "domain": "domain",
            "host": "host",
            "ip": "ip",
            "port": "port",
            "protocol": "protocol",
            "title": "title",
            "body": "body",
            "header": "header",
            "product": "product",
            "service": "server",
            "cert_subject": "cert.subject",
            "org": "org",
            "icp_org": "icp",
            "country": "country",
            "province": "province",
            "city": "city",
        },
        supports_or=True,
        supports_not=True,
        supports_aggregation=True,
        requires_account_validation=True,
        notes=[
            "Public API and stats endpoints are available.",
            "Exact field coverage and package limits must be verified with a paid account.",
        ],
    ),
    "shodan": PlatformCapability(
        name="Shodan",
        supported_fields={
            "keyword",
            "host",
            "ip",
            "port",
            "title",
            "product",
            "org",
            "country",
            "city",
            "asn",
            "domain",
        },
        supported_operators={
            ComparisonOperator.EQ,
            ComparisonOperator.CONTAINS,
            ComparisonOperator.IN,
        },
        field_mapping={
            "keyword": "_keyword",
            "host": "hostname",
            "ip": "ip",
            "port": "port",
            "title": "http.title",
            "product": "product",
            "org": "org",
            "country": "country",
            "city": "city",
            "asn": "asn",
            "domain": "hostname",
        },
        supports_or=True,
        supports_not=False,
        supports_aggregation=True,
        notes=[
            "Official Search API is GET /shodan/host/search with key, query, page, minify and optional fields/facets.",
            "Search query credits may be consumed when filters are used or when paging past page 1.",
        ],
    ),
    "quake": PlatformCapability(
        name="360 Quake",
        supported_fields={
            "keyword",
            "domain",
            "host",
            "ip",
            "port",
            "title",
            "body",
            "header",
            "service",
            "product",
            "org",
            "icp_org",
            "country",
            "province",
            "city",
        },
        supported_operators=COMMON_OPERATORS,
        field_mapping={
            "keyword": "keyword",
            "domain": "domain",
            "host": "hostname",
            "ip": "ip",
            "port": "port",
            "title": "title",
            "body": "body",
            "header": "headers",
            "service": "service",
            "product": "app",
            "org": "org",
            "icp_org": "icp_keywords",
            "country": "country_cn",
            "province": "province_cn",
            "city": "city_cn",
        },
        supports_or=True,
        supports_not=True,
        supports_time_range=True,
        supports_aggregation=True,
        notes=[
            "Official Quake v3 API docs are available for quake_service and quake_host.",
            "API Key auth uses the X-QuakeToken header and returned fields depend on account tier.",
        ],
    ),
    "hunter": PlatformCapability(
        name="Hunter",
        supported_fields={
            "keyword",
            "domain",
            "host",
            "ip",
            "port",
            "protocol",
            "title",
            "body",
            "header",
            "service",
            "product",
            "cert_subject",
            "org",
            "icp_org",
            "country",
            "province",
            "city",
        },
        supported_operators=COMMON_OPERATORS,
        field_mapping={
            "keyword": "keyword",
            "domain": "domain",
            "host": "domain",
            "ip": "ip",
            "port": "port",
            "protocol": "protocol",
            "title": "title",
            "body": "body",
            "header": "header",
            "service": "protocol",
            "product": "app",
            "cert_subject": "cert.subject",
            "org": "as.org",
            "icp_org": "icp.name",
            "country": "country",
            "province": "province",
            "city": "city",
        },
        supports_or=True,
        supports_not=False,
        supports_time_range=True,
        notes=[
            "Official Hunter OpenAPI search docs are available at /openApi/search.",
            "Search syntax must be base64url-encoded and authenticated with the api-key query parameter.",
        ],
    ),
    "urlscan": PlatformCapability(
        name="urlscan.io",
        supported_fields={"keyword", "domain", "host", "ip", "title", "url", "country", "asn"},
        supported_operators={
            ComparisonOperator.EQ,
            ComparisonOperator.CONTAINS,
            ComparisonOperator.IN,
        },
        field_mapping={
            "keyword": "_keyword",
            "domain": "page.domain",
            "host": "page.domain",
            "ip": "page.ip",
            "title": "page.title",
            "url": "page.url",
            "country": "country",
            "asn": "asn",
        },
        supports_or=True,
        supports_not=True,
        notes=[
            "Official Search API is GET /api/v1/search/ with q, size, optional offset or search_after, and API-Key header auth.",
            "urlscan.io is modeled as a web intelligence source; this project does not call the scan submission API.",
        ],
    ),
    "securitytrails": PlatformCapability(
        name="SecurityTrails",
        supported_fields={"keyword", "domain", "host"},
        supported_operators={
            ComparisonOperator.EQ,
            ComparisonOperator.CONTAINS,
            ComparisonOperator.IN,
        },
        field_mapping={
            "keyword": "hostname",
            "domain": "hostname",
            "host": "hostname",
        },
        supports_or=False,
        supports_not=False,
        supports_aggregation=False,
        notes=[
            "SecurityTrails is modeled as a domain-centric enrichment source instead of a general asset search engine.",
            "Official v1 docs expose GET /domain/{hostname} and GET /domain/{hostname}/subdomains with APIKEY header auth.",
        ],
    ),
    "whoisxml": PlatformCapability(
        name="WhoisXML API",
        supported_fields={"keyword", "domain", "host"},
        supported_operators={
            ComparisonOperator.EQ,
            ComparisonOperator.CONTAINS,
            ComparisonOperator.IN,
        },
        field_mapping={
            "keyword": "domainName",
            "domain": "domainName",
            "host": "domainName",
        },
        supports_or=False,
        supports_not=False,
        supports_aggregation=False,
        notes=[
            "WhoisXML API is modeled as a domain-centric enrichment source instead of a general asset search engine.",
            "Official product docs expose Whois API and Subdomains Lookup API with apiKey query-parameter authentication.",
        ],
    ),
}
