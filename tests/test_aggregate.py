import pytest

from versa.core.aggregate import section_totals

CONTROL_TOTALS_MILLIONS = {
    # participant_id: (section 6 total, section 10 total), "за объемы участника"
    "parallel": (1865.9, 757.2),
    "rik": (1480.2, 1681.8),
    "rutek": (2129.2, 1172.3),
    "buro_konstrakshn": (1992.8, 1401.8),
    "ges": (2758.6, 1183.7),
    "fodd": (2784.7, 1551.3),
    "erbek": (2300.9, 1910.4),
}


@pytest.mark.parametrize("pid,expected", CONTROL_TOTALS_MILLIONS.items())
def test_section_6_and_10_participant_volume_totals_match_control_sums(sample_tender, pid, expected):
    by_number = {s.number: s for s in sample_tender.sections}
    expected_6, expected_10 = expected

    totals_6 = section_totals(by_number["6"])
    totals_10 = section_totals(by_number["10"])

    assert totals_6.by_participant_volume[pid] / 1_000_000 == pytest.approx(expected_6, abs=0.1)
    assert totals_10.by_participant_volume[pid] / 1_000_000 == pytest.approx(expected_10, abs=0.1)


def test_section_totals_are_sum_of_child_totals(sample_tender):
    by_number = {s.number: s for s in sample_tender.sections}
    section_6 = by_number["6"]

    totals = section_totals(section_6)
    child_sum = sum(
        section_totals(child).by_participant_volume.get("parallel", 0.0)
        for child in section_6.children
    ) + sum(
        p.participant_prices["parallel"].total_for_participant_volume.total or 0.0
        for p in section_6.positions
    )

    assert totals.by_participant_volume["parallel"] == pytest.approx(child_sum, rel=1e-9)
