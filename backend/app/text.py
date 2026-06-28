from __future__ import annotations

import html
import re


TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")


def clean_text(value: str) -> str:
    without_tags = TAG_RE.sub(" ", value or "")
    decoded = html.unescape(without_tags)
    return WHITESPACE_RE.sub(" ", decoded).strip()
