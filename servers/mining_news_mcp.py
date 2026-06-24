"""MCP Server 1: mining-news — 矿业新闻搜索与全文获取

Tools:
  - search(query, days)  → 搜索 mining.com 新闻，返回标题/摘要/链接/日期
  - fetch_article(url)   → 抓取任意 URL 全文，返回清洗后的文本

Transport: stdio (for Claude Desktop / local subprocess)
"""

from datetime import datetime, timedelta
from typing import Any

import httpx
from bs4 import BeautifulSoup
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("mining-news")

WP_API = "https://www.mining.com/wp-json/wp/v2/posts"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Safari/605.1.15"
)


@mcp.tool()
async def search(query: str, days: int = 7) -> list[dict[str, Any]]:
    """Search mining news articles by keyword.

    Args:
        query: Search keyword (e.g. 'lithium', 'Pilbara', 'copper')
        days: Number of days to look back (default 7)
    """
    after = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")

    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=30) as client:
        try:
            resp = await client.get(
                WP_API,
                params={
                    "search": query,
                    "after": after,
                    "per_page": 20,
                    "orderby": "relevance",
                    "_fields": "id,title,excerpt,link,date",
                },
            )
            resp.raise_for_status()
            posts = resp.json()
        except Exception as e:
            return [{"error": f"mining.com API failed: {e}"}]

    results = []
    for p in posts:
        title = _strip_html(p.get("title", {}).get("rendered", ""))
        excerpt = _strip_html(p.get("excerpt", {}).get("rendered", ""))
        results.append({
            "title": title,
            "date": p.get("date", ""),
            "url": p.get("link", ""),
            "excerpt": excerpt[:300] if excerpt else "",
        })

    if not results:
        return [{"message": f"No results for '{query}' in the past {days} days."}]
    return results


@mcp.tool()
async def fetch_article(url: str) -> dict[str, Any]:
    """Fetch and extract full text content from a news article URL.

    Args:
        url: The full URL of the article to fetch
    """
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=30) as client:
        try:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
        except Exception as e:
            return {"error": f"Failed to fetch URL: {e}", "url": url}

    soup = BeautifulSoup(resp.text, "lxml")

    # Remove noise elements
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()

    # Try common article selectors
    title = ""
    if soup.title:
        title = soup.title.get_text(strip=True)

    body = ""
    for selector in ["article", ".article-content", ".post-content", ".entry-content", "main", ".content"]:
        el = soup.select_one(selector)
        if el:
            body = el.get_text(separator="\n", strip=True)
            break

    if not body:
        body = soup.body.get_text(separator="\n", strip=True) if soup.body else ""

    # Truncate — the LLM doesn't need 10k words
    if len(body) > 4000:
        body = body[:4000] + "..."

    return {"title": title, "url": url, "content": body, "length": len(body)}


def _strip_html(html: str) -> str:
    """Strip HTML tags and normalize whitespace."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    return soup.get_text(separator=" ", strip=True)


if __name__ == "__main__":
    mcp.run(transport="stdio")
