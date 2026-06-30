from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ArticleCandidate:
    source_name: str
    title: str
    summary: str
    url: str
    published_at: str
    content: str = ""
