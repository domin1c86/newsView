from __future__ import annotations

import re
from typing import Literal


TitleLanguage = Literal["zh", "en", "unknown"]

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_LATIN_RE = re.compile(r"[A-Za-z]")


def detect_title_language(title: str) -> TitleLanguage:
    cjk_count = len(_CJK_RE.findall(title))
    latin_count = len(_LATIN_RE.findall(title))
    text_count = cjk_count + latin_count

    if text_count == 0:
        return "unknown"
    if cjk_count / text_count > 0.4:
        return "zh"
    if cjk_count == 0 and latin_count > 0:
        return "en"
    return "unknown"
