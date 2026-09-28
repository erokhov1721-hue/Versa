from versa.core.summary import BestOffer, ParticipantColumnMeta, SummaryCell, SummaryRow, SummaryTable
from versa.ui.summary_render import render_summary_html


def _table(rows):
    return SummaryTable(
        participants=[
            ParticipantColumnMeta(id="a", name='ООО "А"', inn="111"),
            ParticipantColumnMeta(id="b", name='ООО "Б"', inn="222"),
        ],
        has_baseline=False, vat_rate=22.0, rows=rows,
    )


def test_min_max_colors_appear_in_output():
    row = SummaryRow(
        kind="section", row=1, number="1", smr_article="1. Раздел", name="1. Раздел",
        unit=None, qty=None, level=1, is_filled=True, ancestor_numbers=(),
        cells={
            "a": SummaryCell(status="priced", value=100.0, highlight="min"),
            "b": SummaryCell(status="priced", value=200.0, highlight="max"),
        },
    )
    html = render_summary_html(_table([row]))

    assert "#C6EFCE" in html
    assert "#FFC7CE" in html


def test_placeholder_and_not_included_badges_render():
    row = SummaryRow(
        kind="position", row=2, number="", smr_article="", name="Поз.", unit="м2",
        qty=1.0, level=2, is_filled=True, ancestor_numbers=("1",),
        cells={
            "a": SummaryCell(status="placeholder", value=0.01, badge="≈0"),
            "b": SummaryCell(status="not_included", value=None, badge="не вкл."),
        },
    )
    html = render_summary_html(_table([row]))

    assert "≈0" in html
    assert "не вкл." in html


def test_tooltip_is_a_title_attribute():
    row = SummaryRow(
        kind="position", row=3, number="", smr_article="", name="Поз.", unit="м2",
        qty=1.0, level=2, is_filled=True, ancestor_numbers=("1",),
        cells={
            "a": SummaryCell(status="priced", value=1.0, tooltip="цена за ед: 1,00"),
            "b": SummaryCell(status="priced", value=1.0, tooltip="цена за ед: 1,00"),
        },
    )
    html = render_summary_html(_table([row]))

    assert 'title="цена за ед: 1,00"' in html


def test_money_unit_millions_divides_and_formats_one_decimal():
    row = SummaryRow(
        kind="lot", row=None, number="", smr_article="", name="Лот", unit=None, qty=None,
        level=0, is_filled=True, ancestor_numbers=(),
        cells={
            "a": SummaryCell(status="priced", value=1_500_000.0),
            "b": SummaryCell(status="priced", value=1_500_000.0),
        },
    )
    html = render_summary_html(_table([row]), money_unit="млн руб.")

    assert "1,5" in html


def test_sticky_css_present_for_header_and_pinned_columns():
    html = render_summary_html(_table([]))
    assert "position: sticky" in html or "position:sticky" in html


def test_baseline_column_appears_only_when_present():
    row = SummaryRow(
        kind="section", row=1, number="1", smr_article="1. Раздел", name="1. Раздел",
        unit=None, qty=None, level=1, is_filled=True, ancestor_numbers=(),
        cells={"a": SummaryCell(status="priced", value=100.0), "b": SummaryCell(status="priced", value=120.0)},
        baseline_cell=SummaryCell(status="priced", value=110.0),
    )
    table_with = SummaryTable(
        participants=[ParticipantColumnMeta(id="a", name="А", inn=None), ParticipantColumnMeta(id="b", name="Б", inn=None)],
        has_baseline=True, vat_rate=22.0, rows=[row],
    )
    html_with = render_summary_html(table_with)
    assert "Расчётная стоимость" in html_with

    table_without = SummaryTable(
        participants=table_with.participants, has_baseline=False, vat_rate=22.0, rows=[row],
    )
    html_without = render_summary_html(table_without)
    assert "Расчётная стоимость" not in html_without


def test_best_offer_column_renders_name_and_savings():
    row = SummaryRow(
        kind="section", row=1, number="1", smr_article="1. Раздел", name="1. Раздел",
        unit=None, qty=None, level=1, is_filled=True, ancestor_numbers=(),
        cells={
            "a": SummaryCell(status="priced", value=100.0, highlight="min"),
            "b": SummaryCell(status="priced", value=150.0, highlight="max"),
        },
        best=BestOffer(participant_id="a", participant_name='ООО "А"',
                        savings_vs_second_rub=50.0, savings_vs_second_pct=33.3),
    )
    html = render_summary_html(_table([row]))

    assert "ООО &quot;А&quot;" in html
    assert "33,3%" in html
