"""Web search through the Tavily API - our own search tool.

Why our own? The built-in web_search tool (lesson 4.3) runs on OpenAI's
servers and is not offered on Azure OpenAI. With function calling
(lesson 4.2) the model asks for a search and *our code* runs it, so it
works with any provider.

Get a key at https://app.tavily.com and put it in .env as TAVILY_API_KEY.
"""
from __future__ import annotations

import os

import requests

TAVILY_URL = "https://api.tavily.com/search"

# Each result's text is cut to this many characters: 5 results x 700 chars
# keeps one search around 1,000 input tokens when it goes back to the model.
MAX_CONTENT_CHARS = 700


def tavily_key() -> str | None:
    return os.getenv("TAVILY_API_KEY") or None


def search_web(
    query: str,
    *,
    max_results: int = 5,
    timeout: float = 20.0,
    session: requests.Session | None = None,
) -> list[dict]:
    """Run one search. Returns a list of {"title", "url", "content"} dicts."""
    key = tavily_key()
    if not key:
        raise RuntimeError("TAVILY_API_KEY is not set. Add it to .env (see docs/step-01b-web-search.md).")

    http = session or requests
    resp = http.post(
        TAVILY_URL,
        headers={"Authorization": f"Bearer {key}"},
        json={
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",  # 1 credit per search ("advanced" = 2)
            "topic": "general",
        },
        timeout=timeout,
    )
    resp.raise_for_status()

    results = []
    for r in resp.json().get("results", []):
        results.append(
            {
                "title": (r.get("title") or "").strip(),
                "url": r.get("url") or "",
                "content": (r.get("content") or "").strip()[:MAX_CONTENT_CHARS],
            }
        )
    return results


def format_results(query: str, results: list[dict]) -> str:
    """Turn results into the text we send back to the model."""
    if not results:
        return f'No results for "{query}".'
    blocks = [f'Search results for "{query}":']
    for i, r in enumerate(results, 1):
        blocks.append(f"[{i}] {r['title']}\nURL: {r['url']}\n{r['content']}")
    return "\n\n".join(blocks)
