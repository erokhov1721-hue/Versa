import pytest

from versa.core.summary import DetailLevel, build_summary_table


def test_sections_level_shows_lot_plus_18_sections_plus_3_totals_plus_best_row(sample_tender):
    table = build_summary_table(sample_tender, detail_level=DetailLevel.SECTIONS)

    kinds = [row.kind for row in table.rows]
    assert kinds.count("lot") == 1
    assert kinds.count("section") == 18
    assert kinds.count("total_incl_vat") == 1
    assert kinds.count("total_vat") == 1
    assert kinds.count("total_excl_vat") == 1
    assert kinds.count("best_by_section") == 1
    # nothing deeper than a top-level section at this detail level
    assert not any(row.kind in ("subsection", "position") for row in table.rows)


def test_row_order_matches_the_original_sheet_order(sample_tender):
    table = build_summary_table(sample_tender, detail_level=DetailLevel.SECTIONS)
    section_rows = [row for row in table.rows if row.kind == "section"]
    numbers_in_order = [row.number for row in section_rows]
    assert numbers_in_order == [str(n) for n in range(1, 19)]


def test_lot_row_shows_the_grand_total_not_zero(sample_tender):
    table = build_summary_table(sample_tender, detail_level=DetailLevel.SECTIONS)
    lot_row = next(row for row in table.rows if row.kind == "lot")
    assert lot_row.cells["parallel"].value == pytest.approx(2_781_947_710.22, abs=1)
    assert lot_row.cells["fodd"].value == pytest.approx(4_489_294_827.70, abs=1)


def test_section_6_min_is_rik_max_is_fodd(sample_tender):
    table = build_summary_table(sample_tender, detail_level=DetailLevel.SECTIONS)
    section_6 = next(row for row in table.rows if row.kind == "section" and row.number == "6")

    assert section_6.cells["rik"].highlight == "min"
    assert section_6.cells["fodd"].highlight == "max"
    assert section_6.cells["rik"].value == pytest.approx(1_480_200_000, rel=1e-3)
    assert section_6.cells["fodd"].value == pytest.approx(2_784_700_000, rel=1e-3)


def test_section_10_min_is_parallel_max_is_erbek_fodd_has_lump_sum_badge(sample_tender):
    table = build_summary_table(sample_tender, detail_level=DetailLevel.SECTIONS)
    section_10 = next(row for row in table.rows if row.kind == "section" and row.number == "10")

    assert section_10.cells["parallel"].highlight == "min"
    assert section_10.cells["erbek"].highlight == "max"
    assert section_10.cells["fodd"].warning is not None
    assert "паушал" in section_10.cells["fodd"].warning.lower()


def test_grand_total_min_parallel_max_fodd(sample_tender):
    table = build_summary_table(sample_tender, detail_level=DetailLevel.SECTIONS)
    total_row = next(row for row in table.rows if row.kind == "total_incl_vat")

    assert total_row.cells["parallel"].highlight == "min"
    assert total_row.cells["fodd"].highlight == "max"
    assert total_row.cells["parallel"].value == pytest.approx(2_781_947_710.22, abs=1)
    assert total_row.cells["fodd"].value == pytest.approx(4_489_294_827.70, abs=1)


def test_vat_and_excl_vat_rows_reconcile_to_the_penny(sample_tender):
    table = build_summary_table(sample_tender, detail_level=DetailLevel.SECTIONS)
    total = next(row for row in table.rows if row.kind == "total_incl_vat")
    vat = next(row for row in table.rows if row.kind == "total_vat")
    excl = next(row for row in table.rows if row.kind == "total_excl_vat")

    for pid in ("parallel", "rik", "rutek", "buro_konstrakshn", "ges", "erbek", "fodd"):
        assert vat.cells[pid].value == pytest.approx(total.cells[pid].value * 22 / 122, abs=1e-6)
        reconciled = excl.cells[pid].value + vat.cells[pid].value
        assert reconciled == pytest.approx(total.cells[pid].value, abs=0.01)


def test_unfilled_sections_are_marked_but_shown_by_default(sample_tender):
    table = build_summary_table(sample_tender, detail_level=DetailLevel.SECTIONS)
    unfilled_numbers = {"1", "2", "3", "4", "5", "7", "8", "9", "11", "12", "13", "14", "15", "16", "17"}
    section_rows = {row.number: row for row in table.rows if row.kind == "section"}

    assert set(section_rows) == unfilled_numbers | {"6", "10", "18"}
    for number in unfilled_numbers:
        assert section_rows[number].is_filled is False
        assert all(cell.status == "na" for cell in section_rows[number].cells.values())


def test_hide_unfilled_removes_the_15_empty_sections(sample_tender):
    table = build_summary_table(sample_tender, detail_level=DetailLevel.SECTIONS, hide_unfilled=True)
    section_rows = [row for row in table.rows if row.kind == "section"]
    assert {row.number for row in section_rows} == {"6", "10", "18"}


def test_best_by_section_counts_parallel_rik_erbek_one_each(sample_tender):
    table = build_summary_table(sample_tender, detail_level=DetailLevel.SECTIONS)
    best_row = next(row for row in table.rows if row.kind == "best_by_section")
    assert best_row.best_by_section_counts == {
        "parallel": 1, "rik": 1, "rutek": 0, "buro_konstrakshn": 0,
        "ges": 0, "erbek": 1, "fodd": 0,
    }


def test_expanding_one_section_does_not_promote_others(sample_tender):
    table = build_summary_table(
        sample_tender, detail_level=DetailLevel.SECTIONS, expanded_sections=frozenset({"6"}),
    )
    kinds_under_6 = [
        row for row in table.rows
        if row.kind in ("subsection", "position") and row.ancestor_numbers and row.ancestor_numbers[0] == "6"
    ]
    kinds_under_10 = [
        row for row in table.rows
        if row.kind in ("subsection", "position") and row.ancestor_numbers and row.ancestor_numbers[0] == "10"
    ]
    assert len(kinds_under_6) > 0
    assert len(kinds_under_10) == 0


def test_position_level_status_badges(sample_tender):
    table = build_summary_table(sample_tender, detail_level=DetailLevel.POSITIONS)
    position_rows = {row.row: row for row in table.rows if row.kind == "position"}

    # row 682: GES "Включено в п/п 667"
    included_cell = position_rows[682].cells["ges"]
    assert included_cell.status == "included_elsewhere"
    assert included_cell.badge == "вкл. в п/п 667"

    # row 670: ФОДД lump_sum in section 10
    lump_cell = position_rows[670].cells["fodd"]
    assert lump_cell.status == "lump_sum"
    assert "паушал" in lump_cell.badge.lower()


def test_position_tooltip_includes_price_breakdown(sample_tender):
    table = build_summary_table(sample_tender, detail_level=DetailLevel.POSITIONS)
    position_rows = {row.row: row for row in table.rows if row.kind == "position"}
    cell = position_rows[228].cells["parallel"]

    assert "материал" in cell.tooltip.lower()
    assert "смр" in cell.tooltip.lower()


def test_position_tooltip_shows_quantity_only_on_a_real_mismatch(sample_tender):
    table = build_summary_table(sample_tender, detail_level=DetailLevel.POSITIONS)
    position_rows = {row.row: row for row in table.rows if row.kind == "position"}

    # row 228: parallel's offered quantity equals the customer's — no mismatch, no quantity line
    no_mismatch_cell = position_rows[228].cells["parallel"]
    assert "Количество участника" not in no_mismatch_cell.tooltip

    # row 1603: erbek offered qty=20606.16 against a customer qty of 1 — a real, large mismatch
    mismatch_cell = position_rows[1603].cells["erbek"]
    assert "20606.16" in mismatch_cell.tooltip
    assert "Количество участника" in mismatch_cell.tooltip


def test_position_with_fewer_than_two_priced_participants_has_no_highlight(sample_tender):
    table = build_summary_table(sample_tender, detail_level=DetailLevel.POSITIONS)
    position_rows = {row.row: row for row in table.rows if row.kind == "position"}
    # row 678 "Освещение благоустройства с фасадов": nobody has PRICED status
    # (zero/not_included everywhere) — no min/max highlight at position level
    row_678 = position_rows[678]
    assert all(cell.highlight is None for cell in row_678.cells.values())


def test_deviation_label_peer_mode(sample_tender):
    table = build_summary_table(sample_tender, detail_level=DetailLevel.SECTIONS)
    section_6 = next(row for row in table.rows if row.kind == "section" and row.number == "6")
    assert section_6.cells["rik"].deviation_label == ""  # the minimum itself
    assert "к мин." in section_6.cells["fodd"].deviation_label
    assert "+" in section_6.cells["fodd"].deviation_label


def test_best_offer_column_names_the_cheapest_and_savings_vs_runner_up(sample_tender):
    table = build_summary_table(sample_tender, detail_level=DetailLevel.SECTIONS)
    section_6 = next(row for row in table.rows if row.kind == "section" and row.number == "6")
    assert section_6.best.participant_id == "rik"
    assert section_6.best.savings_vs_second_rub > 0
    assert section_6.best.savings_vs_second_pct > 0
