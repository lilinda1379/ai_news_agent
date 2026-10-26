from app.tools.news import NewsSearchTool


RSS_XML = b"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
  <channel>
    <title>AI News</title>
    <item>
      <title>New Agent Framework - Example AI</title>
      <link>https://example.com/agent</link>
      <description>Framework details</description>
      <pubDate>Mon, 26 Oct 2026 08:00:00 GMT</pubDate>
      <source>Example AI</source>
    </item>
    <item>
      <title>Duplicate</title>
      <link>https://example.com/agent</link>
      <description>Same URL</description>
      <pubDate>Mon, 26 Oct 2026 09:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Multimodal Update</title>
      <link>https://example.com/multimodal</link>
      <description>Model update</description>
      <pubDate>Mon, 26 Oct 2026 10:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""


def test_search_news_builds_query_and_deduplicates_links():
    requested_urls = []

    def fetch(url: str) -> bytes:
        requested_urls.append(url)
        return RSS_XML

    tool = NewsSearchTool(fetch=fetch)

    result = tool.search_news("AI Agent", limit=10)

    assert result["ok"] is True
    assert len(result["data"]["items"]) == 2
    assert result["data"]["items"][0] == {
        "title": "New Agent Framework - Example AI",
        "url": "https://example.com/agent",
        "summary": "Framework details",
        "source": "Example AI",
        "published_at": "Mon, 26 Oct 2026 08:00:00 GMT",
    }
    assert "AI+Agent" in requested_urls[0]


def test_search_news_rejects_empty_query():
    tool = NewsSearchTool(fetch=lambda _: RSS_XML)

    result = tool.search_news("   ")

    assert result == {"ok": False, "data": None, "error": "query is required"}
