from __future__ import annotations

import re
from collections import Counter


SPECIAL_TRIGGER = "老岳中转"

EN_STOP_WORDS = {
    "about",
    "after",
    "again",
    "with",
    "from",
    "into",
    "over",
    "under",
    "this",
    "that",
    "these",
    "those",
    "have",
    "has",
    "had",
    "will",
    "would",
    "could",
    "should",
    "their",
    "there",
    "than",
    "then",
    "they",
    "them",
    "and",
    "the",
    "for",
    "but",
    "not",
    "can",
    "all",
    "one",
    "two",
    "out",
    "off",
    "per",
    "via",
    "how",
    "why",
    "who",
    "what",
    "when",
    "where",
    "is",
    "to",
    "of",
    "in",
    "on",
    "at",
    "by",
    "as",
    "a",
    "an",
    "are",
    "was",
    "were",
    "you",
    "your",
    "its",
    "our",
    "new",
    "news",
}

ZH_STOP_WORDS = {
    "一个",
    "一些",
    "以及",
    "关于",
    "如何",
    "这个",
    "这些",
    "他们",
    "我们",
    "你们",
    "进行",
    "发布",
    "推出",
    "最新",
    "近期",
    "新闻",
    "事件",
}

KNOWN_TERMS = [
    "artificial intelligence",
    "generative ai",
    "machine learning",
    "deep learning",
    "openai",
    "anthropic",
    "google",
    "microsoft",
    "nvidia",
    "apple",
    "meta",
    "gemini",
    "chatgpt",
    "claude",
    "gpt",
    "llm",
    "ai",
    "模型",
    "人工智能",
    "生成式ai",
    "生成式 AI",
    "大模型",
    "机器学习",
    "深度学习",
    "智能体",
    "ai-agent",
    "agent",
    "agents",
    "企业ai",
    "机器人",
    "算力",
    "gpu",
    "数据中心",
    "芯片",
    "硬件",
    "端侧ai",
    "端侧 AI",
    "苹果",
    "涨价",
    "产品涨价",
    "成本上升",
    "开源模型",
    "多模态",
    "自动驾驶",
    "训练数据",
    "数据版权",
    "合成数据",
    "数据标注",
    "融资",
    "投资",
    "收购",
    "并购",
    "估值",
    "监管",
    "政策",
    "法规",
    "安全",
]

AI_RELEVANCE_TERMS = {
    "ai",
    "artificial intelligence",
    "generative ai",
    "machine learning",
    "deep learning",
    "llm",
    "gpt",
    "openai",
    "anthropic",
    "claude",
    "gemini",
    "nvidia",
    "gpu",
    "人工智能",
    "生成式",
    "大模型",
    "模型",
    "多模态",
    "智能体",
    "机器人",
    "算力",
    "芯片",
    "数据中心",
    "端侧",
    "硬件",
    "训练数据",
    "合成数据",
    "数据版权",
    "融资",
    "投资",
    "监管",
    "政策",
}

KEYWORD_SYNONYMS = {
    "人工智能": ["ai", "artificial-intelligence", "artificial intelligence"],
    "生成式ai": ["generative-ai", "generative ai"],
    "生成式-ai": ["generative-ai", "generative ai"],
    "大模型": ["llm", "gpt", "large-language-model", "large language model"],
    "模型": ["model", "models", "llm", "gpt"],
    "智能体": ["agent", "agents", "ai-agent"],
    "算力": ["compute", "gpu", "nvidia", "data-center", "data center"],
    "芯片": ["chip", "chips", "gpu", "nvidia"],
    "硬件": ["hardware", "device", "chip", "gpu"],
    "投融资": ["funding", "investment", "venture", "startup"],
    "融资": ["funding", "investment", "venture"],
    "政策": ["policy", "regulation", "governance"],
    "监管": ["regulation", "policy", "governance"],
}


def has_special_trigger(text: str) -> bool:
    return SPECIAL_TRIGGER in text


def normalize_text(text: str) -> str:
    lowered = text.lower()
    lowered = re.sub(r"https?://\S+", " ", lowered)
    lowered = re.sub(r"[\u3000\s]+", " ", lowered)
    return lowered.strip()


def is_ai_related(text: str) -> bool:
    normalized = normalize_text(text)
    return any(term.lower() in normalized for term in AI_RELEVANCE_TERMS)


def extract_keywords(text: str, limit: int = 8) -> list[str]:
    normalized = normalize_text(text.replace(SPECIAL_TRIGGER, " "))
    counts: Counter[str] = Counter()

    for term in KNOWN_TERMS:
        term_normalized = term.lower()
        if term_normalized in normalized:
            counts[term.lower().replace(" ", "-")] += 4

    for token in re.findall(r"[a-zA-Z][a-zA-Z0-9+-]{1,}", normalized):
        token = token.lower()
        if token not in EN_STOP_WORDS:
            counts[token] += 1

    for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", normalized):
        if chunk in ZH_STOP_WORDS:
            continue
        if len(chunk) <= 4:
            counts[chunk] += 1

    return [keyword for keyword, _ in counts.most_common(limit)]


def keyword_score(query_keywords: list[str], text: str, item_keywords: list[str]) -> float:
    if not query_keywords:
        return 0.0
    haystack = normalize_text(" ".join([text, *item_keywords]))
    item_keyword_set = {keyword.lower() for keyword in item_keywords}
    score = 0.0
    for keyword in query_keywords:
        normalized_keyword = keyword.lower()
        variants = [normalized_keyword, *KEYWORD_SYNONYMS.get(normalized_keyword, [])]
        normalized_variants = [variant.lower() for variant in variants]
        if any(variant in item_keyword_set for variant in normalized_variants):
            score += 3.0
        elif any(variant.replace("-", " ") in haystack or variant in haystack for variant in normalized_variants):
            score += 2.0
    return score / max(len(query_keywords), 1)
