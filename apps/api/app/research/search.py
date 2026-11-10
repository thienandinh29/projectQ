"""Search adapters; provider filtering plus independent local domain checks."""

import argparse
import asyncio
import json
import os
import re
from collections.abc import Sequence

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.research.agent import ResearchAgent, SearchResult
from app.research.reader import SourceError, validate_url


class _Result(BaseModel):
    title: str = Field(min_length=1)
    url: str = Field(min_length=1)
    content: str = ""


class _Web(BaseModel):
    results: list[_Result] = Field(default_factory=list)


class _Response(BaseModel):
    model_config = ConfigDict(extra="ignore")
    web: _Web = Field(default_factory=_Web)


class _TavilyResponse(BaseModel):
    results: list[_Result]


class BraveSearch:
    def __init__(
        self,
        api_key: str,
        *,
        count: int = 12,
        timeout: float = 15,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key or not 1 <= count <= 20 or timeout <= 0:
            raise ValueError("Brave API key and valid search limits are required")
        self.api_key, self.count, self.timeout = api_key, count, timeout
        self.transport = transport

    async def __call__(self, query: str, domains: Sequence[str]) -> list[SearchResult]:
        if any(not re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", d) for d in domains):
            raise SourceError("Danh sách miền tìm kiếm không hợp lệ.")
        # Discard operators supplied in a learner goal. Query operators come only from config.
        words = re.findall(r"[^\W_]+", query, flags=re.UNICODE)
        scope = (
            "(" + " OR ".join("site:" + d for d in dict.fromkeys(domains)) + ")" if domains else ""
        )
        budget = 600 - len(scope) - 1
        clean = " ".join(words[: max(1, 70 - 2 * len(domains))])[:budget].strip()
        if not clean or budget < 1:
            raise SourceError("Mục tiêu tìm kiếm không hợp lệ.")
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                trust_env=False,
                transport=self.transport,
            ) as client:
                # No automatic retry: each call counts once toward the research search budget.
                response = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    headers={"X-Subscription-Token": self.api_key, "Accept": "application/json"},
                    params={
                        "q": f"{clean} {scope}",
                        "count": self.count,
                        "result_filter": "web",
                        "text_decorations": "false",
                    },
                )
                response.raise_for_status()
                parsed = _Response.model_validate_json(response.content)
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            raise SourceError(
                f"Dịch vụ tìm kiếm trả về lỗi HTTP {status}.",
                retryable=status == 429 or status >= 500,
                code=f"search_http_{status}",
            ) from None
        except (httpx.RequestError, ValidationError):
            raise SourceError("Dịch vụ tìm kiếm tạm thời không khả dụng.", retryable=True) from None
        results: list[SearchResult] = []
        seen: set[str] = set()
        for entry in parsed.web.results[: self.count]:
            try:
                host = validate_url(entry.url)
            except SourceError:
                continue
            if (
                not domains
                or any(host == domain or host.endswith("." + domain) for domain in domains)
            ) and entry.url not in seen:
                results.append(SearchResult(entry.title, entry.url, entry.content))
                seen.add(entry.url)
        return results


class TavilySearch:
    def __init__(
        self,
        api_key: str,
        *,
        count: int = 12,
        timeout: float = 15,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key or not 1 <= count <= 20 or timeout <= 0:
            raise ValueError("Tavily API key and valid search limits are required")
        self.api_key, self.count, self.timeout = api_key, count, timeout
        self.transport = transport

    async def __call__(self, query: str, domains: Sequence[str]) -> list[SearchResult]:
        if any(not re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", d) for d in domains):
            raise SourceError("Danh sách miền tìm kiếm không hợp lệ.")
        # Scope comes only from configuration, never learner-supplied query operators.
        clean = " ".join(re.findall(r"[^\W_]+", query, flags=re.UNICODE))[:400].strip()
        if not clean:
            raise SourceError("Mục tiêu tìm kiếm không hợp lệ.")
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, trust_env=False, transport=self.transport
            ) as client:
                # Fixed basic depth and no retries prevent unbounded credit spending.
                response = await client.post(
                    "https://api.tavily.com/search",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "query": clean,
                        **(
                            {
                                "include_domains": list(dict.fromkeys(domains)),
                                "include_domains_mode": "restrict",
                            }
                            if domains
                            else {}
                        ),
                        "max_results": self.count,
                        "search_depth": "basic",
                        "auto_parameters": False,
                        "include_answer": False,
                        "include_raw_content": False,
                        "include_usage": True,
                    },
                )
                response.raise_for_status()
                parsed = _TavilyResponse.model_validate_json(response.content)
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            raise SourceError(
                f"Dịch vụ tìm kiếm trả về lỗi HTTP {status}.",
                retryable=status == 429 or status >= 500,
                code=f"search_http_{status}",
            ) from None
        except (httpx.RequestError, ValidationError):
            raise SourceError("Dịch vụ tìm kiếm tạm thời không khả dụng.", retryable=True) from None
        results: list[SearchResult] = []
        seen: set[str] = set()
        for entry in parsed.results[: self.count]:
            try:
                host = validate_url(entry.url)
            except SourceError:
                continue
            if (
                not domains
                or any(host == domain or host.endswith("." + domain) for domain in domains)
            ) and entry.url not in seen:
                results.append(SearchResult(entry.title, entry.url, entry.content))
                seen.add(entry.url)
        return results


def configured_search() -> BraveSearch | TavilySearch:
    provider = os.environ.get("SEARCH_PROVIDER", "brave")
    if provider not in {"brave", "tavily"}:
        raise SourceError("Nhà cung cấp tìm kiếm chưa được hỗ trợ.")
    key = os.environ.get("SEARCH_API_KEY", "")
    if not key:
        raise SourceError("Dịch vụ tìm kiếm chưa được cấu hình.")
    return TavilySearch(key) if provider == "tavily" else BraveSearch(key)


def default_agent() -> ResearchAgent:
    from app.content.gateway import P3Gateway
    from app.research.relevance import ResearchRelevance

    return ResearchAgent(
        configured_search(), relevance=ResearchRelevance(P3Gateway()), open_web=True
    )


def configuration() -> dict[str, str | bool]:
    """Process configuration only; never read credential files or expose key values."""
    provider = os.environ.get("SEARCH_PROVIDER", "brave")
    return {
        "provider": provider if provider in {"brave", "tavily"} else "unsupported",
        "api_key_present": bool(os.environ.get("SEARCH_API_KEY")),
    }


async def probe(search: BraveSearch | TavilySearch) -> dict[str, str | int]:
    results = await search("biology cells textbook", ["bio.libretexts.org"])
    if not results:
        raise SourceError("Search probe returned no allowed results")
    return {
        "provider": "tavily" if isinstance(search, TavilySearch) else "brave",
        "status": "ok",
        "allowed_results": len(results),
    }


def main() -> None:
    from app.config import get_settings

    get_settings().export_worker_environment()
    parser = argparse.ArgumentParser(description="Search check; no network without --live")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    config = configuration()
    if not args.live:
        print(json.dumps({"live": False, **config}))
        return
    if config["provider"] == "unsupported" or not config["api_key_present"]:
        print(json.dumps({"live": False, "status": "unconfigured"}))
        raise SystemExit(1)
    try:
        print(json.dumps(asyncio.run(probe(configured_search()))))
    except SourceError:
        print(json.dumps({"provider": config["provider"], "status": "failed"}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
