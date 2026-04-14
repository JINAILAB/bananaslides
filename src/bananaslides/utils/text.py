from __future__ import annotations

import re

KOREAN_PATTERN = re.compile(r"[\u1100-\u11ff\u3130-\u318f\uac00-\ud7a3]")
CJK_CHARACTER_PATTERN = re.compile(
    r"[\u1100-\u11ff\u3130-\u318f\uac00-\ud7a3\u2e80-\u2eff\u3000-\u303f\u3040-\u30ff\u31c0-\u31ef\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]"
)


def contains_korean(text: str) -> bool:
    return bool(KOREAN_PATTERN.search(text))


def contains_cjk(text: str) -> bool:
    return bool(CJK_CHARACTER_PATTERN.search(text))


def count_non_empty_lines(text: str) -> int:
    lines = [line for line in text.splitlines() if line.strip()]
    return max(1, len(lines))
