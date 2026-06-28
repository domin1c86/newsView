from app.keywords import extract_keywords, has_special_trigger, is_ai_related, keyword_score


def test_extract_keywords_handles_chinese_and_english_terms():
    keywords = extract_keywords("OpenAI 发布新的多模态 AI 模型，Nvidia 芯片需求增长")

    assert "openai" in keywords
    assert "ai" in keywords
    assert "nvidia" in keywords


def test_extract_keywords_handles_indirect_ai_hardware_events():
    keywords = extract_keywords("苹果产品涨价与端侧 AI 硬件成本上升有关")

    assert "苹果" in keywords
    assert "涨价" in keywords
    assert "硬件" in keywords


def test_special_trigger_detection():
    assert has_special_trigger("帮我找老岳中转相关入口")


def test_ai_related_filter_handles_direct_and_indirect_events():
    assert is_ai_related("苹果产品涨价与端侧 AI 硬件成本上升有关")
    assert is_ai_related("监管机构讨论生成式 AI 安全评估标准")
    assert not is_ai_related("球队完成夏季转会并公布新赛季赛程")


def test_keyword_score_expands_chinese_ai_synonyms():
    score = keyword_score(["人工智能"], "OpenAI releases a new AI model", ["openai", "ai", "model"])

    assert score > 0
