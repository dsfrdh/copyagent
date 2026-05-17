"""Search providers for hotspot discovery.

The provider interface keeps the trend source replaceable. The MVP uses
search-result snippets; future providers can wrap Feigua, Chanmama, or Douyin
Open Platform without changing the AI topic workflow.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, asdict
from html import unescape
from html.parser import HTMLParser
from typing import Iterable
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


@dataclass
class SearchResult:
    title: str
    snippet: str
    url: str
    source: str = ""
    published_at: str = ""
    query: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class HotspotProvider:
    name = "base"

    def search(self, queries: Iterable[str], limit_per_query: int = 5) -> list[SearchResult]:
        raise NotImplementedError


class BingSearchProvider(HotspotProvider):
    name = "bing"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("BING_SEARCH_API_KEY", "")

    def search(self, queries: Iterable[str], limit_per_query: int = 5) -> list[SearchResult]:
        if not self.api_key:
            return []

        results: list[SearchResult] = []
        endpoint = "https://api.bing.microsoft.com/v7.0/search"
        for query in queries:
            params = urlencode({
                "q": query,
                "count": min(limit_per_query, 10),
                "mkt": "zh-CN",
                "setLang": "zh-Hans",
                "freshness": "Month",
                "textDecorations": "false",
                "textFormat": "Raw",
            })
            request = Request(
                f"{endpoint}?{params}",
                headers={"Ocp-Apim-Subscription-Key": self.api_key}
            )
            try:
                with urlopen(request, timeout=8) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
                continue

            for item in payload.get("webPages", {}).get("value", []):
                url = item.get("url", "")
                results.append(SearchResult(
                    title=item.get("name", "").strip(),
                    snippet=item.get("snippet", "").strip(),
                    url=url,
                    source=_host(url),
                    published_at=item.get("dateLastCrawled", ""),
                    query=query,
                ))
        return _dedupe_results(results)


class DuckDuckGoHtmlParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.results: list[dict] = []
        self._in_title = False
        self._in_snippet = False
        self._current: dict = {}
        self._buffer: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        classes = attrs_dict.get("class", "")
        if tag == "a" and "result__a" in classes:
            self._in_title = True
            self._buffer = []
            self._current = {"url": attrs_dict.get("href", "")}
        elif tag in {"a", "div"} and "result__snippet" in classes:
            self._in_snippet = True
            self._buffer = []

    def handle_data(self, data):
        if self._in_title or self._in_snippet:
            self._buffer.append(data)

    def handle_endtag(self, tag):
        if self._in_title and tag == "a":
            self._current["title"] = _clean_text("".join(self._buffer))
            self._in_title = False
            self._buffer = []
        elif self._in_snippet and tag in {"a", "div"}:
            self._current["snippet"] = _clean_text("".join(self._buffer))
            self._in_snippet = False
            self._buffer = []
            if self._current.get("title"):
                self.results.append(self._current)
                self._current = {}


class DuckDuckGoSearchProvider(HotspotProvider):
    name = "duckduckgo_html"

    def search(self, queries: Iterable[str], limit_per_query: int = 5) -> list[SearchResult]:
        results: list[SearchResult] = []
        for query in queries:
            params = urlencode({"q": query, "kl": "cn-zh"})
            request = Request(
                f"https://duckduckgo.com/html/?{params}",
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                    )
                },
            )
            try:
                with urlopen(request, timeout=8) as resp:
                    html = resp.read().decode("utf-8", errors="ignore")
            except (HTTPError, URLError, TimeoutError):
                continue

            parser = DuckDuckGoHtmlParser()
            parser.feed(html)
            for item in parser.results[:limit_per_query]:
                url = _normalize_duckduckgo_url(item.get("url", ""))
                results.append(SearchResult(
                    title=item.get("title", ""),
                    snippet=item.get("snippet", ""),
                    url=url,
                    source=_host(url),
                    query=query,
                ))
            time.sleep(0.2)

        return _dedupe_results(results)


class CompositeSearchProvider(HotspotProvider):
    name = "composite"

    def __init__(self, providers: list[HotspotProvider] | None = None):
        self.providers = providers or [BingSearchProvider(), DuckDuckGoSearchProvider()]

    def search(self, queries: Iterable[str], limit_per_query: int = 5) -> list[SearchResult]:
        query_list = list(queries)
        all_results: list[SearchResult] = []
        for provider in self.providers:
            found = provider.search(query_list, limit_per_query=limit_per_query)
            all_results.extend(found)
            if len(all_results) >= len(query_list) * limit_per_query:
                break
        return _dedupe_results(all_results)


def _dedupe_results(results: list[SearchResult]) -> list[SearchResult]:
    seen = set()
    deduped: list[SearchResult] = []
    for result in results:
        key = result.url or f"{result.title}|{result.snippet[:40]}"
        if not result.title or key in seen:
            continue
        seen.add(key)
        deduped.append(result)
    return deduped


def _host(url: str) -> str:
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value)).strip()


def _normalize_duckduckgo_url(url: str) -> str:
    if not url:
        return ""
    url = unescape(url)
    match = re.search(r"[?&]uddg=([^&]+)", url)
    if match:
        from urllib.parse import unquote
        return unquote(match.group(1))
    return url

