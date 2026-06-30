from __future__ import annotations

from datetime import datetime, timezone
import json
import urllib.parse
import urllib.request

from .models import SearchResult


class SearchProvider:
    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        raise NotImplementedError


class NullSearchProvider(SearchProvider):
    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        return []


class HttpJsonSearchProvider(SearchProvider):
    """Small adapter for Bing/Brave/custom search gateways.

    Expected response shape:
    {"results": [{"title": "...", "url": "...", "snippet": "..."}]}
    or directly a list with the same item shape.
    """

    def __init__(self, endpoint: str, api_key: str | None = None, timeout_seconds: float = 8) -> None:
        self.endpoint = endpoint
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        separator = "&" if "?" in self.endpoint else "?"
        url = self.endpoint + separator + urllib.parse.urlencode({"q": query})
        request = urllib.request.Request(url)
        if self.api_key:
            request.add_header("Authorization", f"Bearer {self.api_key}")
            request.add_header("X-API-Key", self.api_key)
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        items = payload.get("results", payload) if isinstance(payload, dict) else payload
        fetched_at = datetime.now(timezone.utc).isoformat()
        results: list[SearchResult] = []
        for item in items[:limit]:
            title = str(item.get("title") or item.get("name") or "Untitled")
            result_url = str(item.get("url") or item.get("link") or "")
            snippet = str(item.get("snippet") or item.get("description") or item.get("content") or "")
            if result_url and snippet:
                results.append(SearchResult(title=title, url=result_url, snippet=snippet, fetched_at=fetched_at))
        return results
