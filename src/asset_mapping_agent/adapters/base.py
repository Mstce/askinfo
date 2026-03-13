from __future__ import annotations

from abc import ABC, abstractmethod

from asset_mapping_agent.adapters.http import HttpClient, UrllibHttpClient
from asset_mapping_agent.adapters.models import AdapterRequest, AdapterResponse, SearchExecutionResult
from asset_mapping_agent.query.models import CompiledQuery


class BasePlatformAdapter(ABC):
    platform: str

    @abstractmethod
    def build_search_request(self, compiled: CompiledQuery, **kwargs: object) -> AdapterRequest:
        raise NotImplementedError

    @abstractmethod
    def parse_search_response(self, response: AdapterResponse) -> SearchExecutionResult:
        raise NotImplementedError

    def search(
        self,
        compiled: CompiledQuery,
        http_client: HttpClient | None = None,
        **kwargs: object,
    ) -> SearchExecutionResult:
        client = http_client or UrllibHttpClient()
        request = self.build_search_request(compiled, **kwargs)
        response = client.execute(request)
        return self.parse_search_response(response)
