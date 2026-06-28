from __future__ import annotations

import re

from .keywords import EN_STOP_WORDS, extract_keywords, normalize_text

ALIASES = {
    "多模态": "multimodal",
    "人工智能": "ai",
    "生成式ai": "generative-ai",
    "生成式-ai": "generative-ai",
    "大模型": "llm",
    "机器学习": "machine-learning",
    "深度学习": "deep-learning",
    "模型": "model",
    "芯片": "chip",
    "监管": "regulation",
    "安全": "safety",
}

ENTITY_TERMS = {"openai", "anthropic", "google", "microsoft", "nvidia", "meta", "deepseek", "claude", "chatgpt", "gemini"}
GENERIC_TERMS = {
    "ai",
    "new",
    "news",
    "launches",
    "article",
    "appeared",
    "first",
    "decoder",
    "technology",
    "review",
    "发布",
    "推出",
}


def canonical_token(token: str) -> str:
    normalized = token.lower().replace(" ", "-")
    return ALIASES.get(normalized, normalized)


def token_set(title: str, summary: str, keywords: list[str] | None = None) -> set[str]:
    keywords = keywords or []
    text = normalize_text(f"{title} {summary} {' '.join(keywords)}")
    english = {
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9+-]{1,}", text)
        if token.lower() not in EN_STOP_WORDS and token.lower() not in GENERIC_TERMS
    }
    chinese = {token for token in re.findall(r"[\u4e00-\u9fff]{2,6}", text) if token not in GENERIC_TERMS}
    return {
        canonical_token(token)
        for token in [*english, *chinese, *keywords]
        if len(token.strip()) > 1 and canonical_token(token) not in GENERIC_TERMS and canonical_token(token) not in EN_STOP_WORDS
    }


def jaccard_similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def normalized_title(title: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", normalize_text(title))


def is_same_topic(
    title: str,
    summary: str,
    keywords: list[str],
    candidate_title: str,
    candidate_summary: str,
    candidate_keywords: list[str],
) -> bool:
    if normalized_title(title) == normalized_title(candidate_title):
        return True
    left = token_set(title, "", keywords or extract_keywords(title))
    right = token_set(candidate_title, "", candidate_keywords or extract_keywords(candidate_title))
    overlap = left & right
    specific_overlap = overlap - GENERIC_TERMS
    entity_overlap = specific_overlap & ENTITY_TERMS
    topic_overlap = specific_overlap - ENTITY_TERMS
    if len(topic_overlap) >= 2:
        return True
    if entity_overlap and topic_overlap:
        return True
    return False
