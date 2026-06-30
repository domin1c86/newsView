from app.article_text import extract_article_text, should_fetch_article_content


def test_extract_article_text_ignores_media_and_scripts():
    html = """
    <html>
      <body>
        <script>alert("bad")</script>
        <figure><img src="flower.jpg"><figcaption>image caption</figcaption></figure>
        <article>
          <p>第一段正文，介绍 Bedrock 平台的数据共享要求。</p>
          <p>第二段正文，说明 Anthropic 模型的数据保留策略。</p>
        </article>
      </body>
    </html>
    """

    text = extract_article_text(html)

    assert "第一段正文" in text
    assert "第二段正文" in text
    assert "flower.jpg" not in text
    assert "alert" not in text
    assert "image caption" not in text


def test_should_fetch_article_content_for_placeholder_summary():
    assert should_fetch_article_content("点击查看原文>")
    assert should_fetch_article_content("short")
    assert not should_fetch_article_content(
        "This is a complete article summary with enough background, actors, actions, outcomes, and context for a preview. "
        "It is intentionally long enough that the service does not need to fetch the original page body."
    )
