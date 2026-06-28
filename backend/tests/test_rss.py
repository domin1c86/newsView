import pytest

from app.sources.rss import parse_rss


def test_parse_rss_items():
    content = """
    <rss version="2.0">
      <channel>
        <item>
          <title>AI news item</title>
          <link>https://example.com/ai-news</link>
          <description>Summary</description>
          <pubDate>Fri, 26 Jun 2026 10:00:00 GMT</pubDate>
        </item>
      </channel>
    </rss>
    """

    items = parse_rss(content, "Example RSS")

    assert len(items) == 1
    assert items[0].source_name == "Example RSS"
    assert items[0].title == "AI news item"
    assert items[0].url == "https://example.com/ai-news"


def test_parse_invalid_rss_raises():
    with pytest.raises(Exception):
        parse_rss("<rss><broken>", "Broken")
