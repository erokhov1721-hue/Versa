from __future__ import annotations


def to_millions(value: float | None, decimals: int = 1) -> str:
    if value is None:
        return "—"
    return f"{value / 1_000_000:.{decimals}f}"


def to_rubles(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.0f}".replace(",", " ")
