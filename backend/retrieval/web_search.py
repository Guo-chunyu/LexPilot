"""Web search tool - supplements local KB with latest legal info."""
import os, httpx
from typing import List

async def search_web(query: str, max_results: int = 5) -> List[dict]:
    serper_key = os.getenv("SERPER_API_KEY", "")
    if not serper_key:
        return []
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://google.serper.dev/search",
            json={"q": f"{query} company law", "num": max_results},
            headers={"X-API-KEY": serper_key},
        )
        if resp.status_code == 200:
            return [{"title": i.get("title",""), "snippet": i.get("snippet",""), "url": i.get("link","")} for i in resp.json().get("organic", [])[:max_results]]
    return []

def format_web_results(results: List[dict]) -> str:
    if not results:
        return ""
    parts = ["\n[Web Search Results]:"]
    for i, r in enumerate(results, 1):
        parts.append(f"{i}. {r['title']}\n   {r['snippet']}\n   Source: {r['url']}")
    return "\n".join(parts)
