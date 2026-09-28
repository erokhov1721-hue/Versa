from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Optional

from versa.core.aggregate import grand_totals, section_totals
from versa.core.models import ComparisonMode, PriceStatus, Section, Tender


@dataclass
class Comparison:
    values: dict[str, float] = field(default_factory=dict)
    min: Optional[float] = None
    max: Optional[float] = None
    median: Optional[float] = None
    mean: Optional[float] = None
    deviation_from_min: dict[str, float] = field(default_factory=dict)
    deviation_from_min_pct: dict[str, float] = field(default_factory=dict)
    deviation_from_median: dict[str, float] = field(default_factory=dict)
    baseline_deviation: Optional[dict[str, float]] = None


def _summarize(values: dict[str, float]) -> Comparison:
    result = Comparison(values=values)
    if not values:
        return result
    nums = list(values.values())
    result.min = min(nums)
    result.max = max(nums)
    result.median = statistics.median(nums)
    result.mean = statistics.mean(nums)
    for pid, value in values.items():
        result.deviation_from_min[pid] = value - result.min
        result.deviation_from_min_pct[pid] = (
            ((value - result.min) / result.min * 100) if result.min else 0.0
        )
        result.deviation_from_median[pid] = value - result.median
    return result


def compare_position(position, participant_ids: list[str], mode: ComparisonMode) -> Comparison:
    values = {}
    for pid in participant_ids:
        price = position.participant_prices.get(pid)
        if price is None or price.status != PriceStatus.PRICED:
            continue
        if price.total_for_customer_volume is not None:
            values[pid] = price.total_for_customer_volume

    result = _summarize(values)

    if mode == ComparisonMode.BASELINE and position.baseline is not None:
        baseline_total = position.baseline.total.total
        if baseline_total:
            result.baseline_deviation = {
                pid: (v - baseline_total) for pid, v in values.items()
            }
    return result


def compare_section(section: Section, participant_ids: list[str], mode: ComparisonMode) -> Comparison:
    totals = section_totals(section)
    values = {pid: totals.by_customer_volume.get(pid, 0.0) for pid in participant_ids}
    return _summarize(values)


def compare_tender(tender: Tender) -> dict:
    participant_ids = [p.id for p in tender.participants]
    totals = grand_totals(tender)
    return {
        "mode": tender.mode,
        "totals_by_customer_volume": dict(totals.by_customer_volume),
        "totals_by_participant_volume": dict(totals.by_participant_volume),
        "warnings": tender.warnings,
    }
