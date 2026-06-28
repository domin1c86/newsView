from app.dedupe import is_same_topic


def test_same_topic_dedupes_related_titles():
    assert is_same_topic(
        "OpenAI releases multimodal AI model",
        "The model handles text image and speech for developers.",
        ["openai", "multimodal", "ai"],
        "OpenAI 发布新的多模态模型能力",
        "新模型强化文本、图像和语音理解能力。",
        ["openai", "多模态", "ai"],
    )


def test_different_topic_is_not_deduped():
    assert not is_same_topic(
        "AI chip demand grows in data centers",
        "Cloud providers buy accelerators.",
        ["ai", "chip", "data"],
        "Regulators discuss model safety standards",
        "Governments review transparency rules.",
        ["regulation", "safety"],
    )
