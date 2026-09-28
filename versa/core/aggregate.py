from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from versa.core.models import Section, Tender


@dataclass
class SectionTotals:
    by_customer_volume: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    by_participant_volume: dict[str, float] = field(default_factory=lambda: defaultdict(float))

    def add(self, other: "SectionTotals") -> None:
        for pid, value in other.by_customer_volume.items():
            self.by_customer_volume[pid] += value
        for pid, value in other.by_participant_volume.items():
            self.by_participant_volume[pid] += value


def _position_totals(position) -> SectionTotals:
    totals = SectionTotals()
    for pid, price in position.participant_prices.items():
        if price.total_for_customer_volume is not None:
            totals.by_customer_volume[pid] += price.total_for_customer_volume
        if price.total_for_participant_volume.total is not None:
            totals.by_participant_volume[pid] += price.total_for_participant_volume.total
    return totals


def section_totals(section: Section) -> SectionTotals:
    totals = SectionTotals()
    for position in section.positions:
        totals.add(_position_totals(position))
    for child in section.children:
        totals.add(section_totals(child))
    return totals


def grand_totals(tender: Tender) -> SectionTotals:
    totals = SectionTotals()
    for section in tender.sections:
        totals.add(section_totals(section))
    return totals
