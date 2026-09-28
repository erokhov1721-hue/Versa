from __future__ import annotations

import re

from versa.core.models import PriceStatus

_NOT_INCLUDED_PATTERNS = (
    "не вклю", "не счита", "не учт", "нет в проект", "не вход",
    "в предложение не включ",
)

_INCLUDED_REF_RE = re.compile(
    r"(?:включ|учтен)\S*\s+в\s+п[./]?\s*п?\.?\s*№?\s*(?P<nums>[\d,\s]+)",
    re.IGNORECASE,
)

_TYPO_FIXES = {"вклучено": "включено", "вклучен": "включен"}


def normalize_comment(raw) -> str | None:
    if raw is None:
        return None
    text = " ".join(str(raw).split())
    if not text or text == "0":
        return None
    lowered = text.lower()
    for typo, fix in _TYPO_FIXES.items():
        if typo in lowered:
            lowered = lowered.replace(typo, fix)
    return lowered


def classify_status(unit_price_total, comment) -> tuple[PriceStatus, tuple[int, ...]]:
    normalized = normalize_comment(comment)

    if normalized is not None:
        for pattern in _NOT_INCLUDED_PATTERNS:
            if pattern in normalized:
                return PriceStatus.NOT_INCLUDED, ()

        match = _INCLUDED_REF_RE.search(normalized)
        if match:
            nums = tuple(int(n) for n in re.findall(r"\d+", match.group("nums")))
            if nums:
                return PriceStatus.INCLUDED_ELSEWHERE, nums

    if unit_price_total is None or unit_price_total == 0:
        return PriceStatus.ZERO, ()
    if 0 < unit_price_total < 1:
        return PriceStatus.PLACEHOLDER, ()
    return PriceStatus.PRICED, ()
