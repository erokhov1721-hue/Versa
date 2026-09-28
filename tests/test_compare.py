import statistics

import pytest

from versa.core.compare import compare_position, compare_section, compare_tender
from versa.core.models import ComparisonMode, PriceStatus


def test_compare_position_only_considers_priced_status_for_min_max(sample_tender):
    section_6 = next(s for s in sample_tender.sections if s.number == "6")
    position = next(
        p for p in section_6.iter_positions()
        if any(pr.status == PriceStatus.PLACEHOLDER for pr in p.participant_prices.values())
    )
    participant_ids = [p.id for p in sample_tender.participants]

    result = compare_position(position, participant_ids, ComparisonMode.PEER)

    priced_ids = {
        pid for pid, price in position.participant_prices.items()
        if price.status == PriceStatus.PRICED
    }
    assert set(result.values.keys()) == priced_ids
    if priced_ids:
        assert result.min == min(result.values.values())
        assert result.median == pytest.approx(statistics.median(result.values.values()))


def test_compare_section_uses_full_sums_including_zero_and_placeholder(sample_tender):
    section_6 = next(s for s in sample_tender.sections if s.number == "6")
    participant_ids = [p.id for p in sample_tender.participants]

    result = compare_section(section_6, participant_ids, ComparisonMode.PEER)

    assert set(result.values.keys()) == set(participant_ids)  # everyone, no filtering
    assert result.min <= result.median <= result.max


def test_compare_tender_reports_peer_mode_and_grand_totals(sample_tender):
    result = compare_tender(sample_tender)

    assert result["mode"] == ComparisonMode.PEER
    assert set(result["totals_by_participant_volume"].keys()) == {
        p.id for p in sample_tender.participants
    }
    assert len(result["warnings"]) > 0
