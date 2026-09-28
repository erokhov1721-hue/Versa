from __future__ import annotations

import html as html_lib

from versa.core.summary import SummaryTable

_UNIT_DIVISORS = {"руб.": 1, "тыс. руб.": 1_000, "млн руб.": 1_000_000}

_CSS = """
<style>
  .versa-summary-wrap { overflow: auto; max-height: 78vh; font-size: 13px; }
  table.versa-summary { border-collapse: collapse; width: max-content; min-width: 100%; }
  table.versa-summary th, table.versa-summary td {
    border: 1px solid #ddd; padding: 4px 8px; white-space: normal; word-break: break-word;
  }
  table.versa-summary thead th {
    position: sticky; top: 0; background: #333; color: #fff; z-index: 3;
  }
  table.versa-summary td.pinned {
    position: sticky; background: #fafafa; z-index: 2;
  }
  table.versa-summary th.pinned {
    position: sticky; background: #333; color: #fff; z-index: 4;
  }
  table.versa-summary td.pinned:nth-child(1), table.versa-summary th.pinned:nth-child(1) { left: 0; width: 70px; }
  table.versa-summary td.pinned:nth-child(2), table.versa-summary th.pinned:nth-child(2) { left: 70px; width: 70px; }
  table.versa-summary td.pinned:nth-child(3), table.versa-summary th.pinned:nth-child(3) { left: 140px; width: 160px; }
  table.versa-summary td.pinned:nth-child(4), table.versa-summary th.pinned:nth-child(4) { left: 300px; width: 280px; }
  table.versa-summary td.pinned:nth-child(5), table.versa-summary th.pinned:nth-child(5) { left: 580px; width: 70px; }
  table.versa-summary td.pinned:nth-child(6), table.versa-summary th.pinned:nth-child(6) { left: 650px; width: 70px; }
  table.versa-summary tbody tr:nth-child(even) td { background-color: #f7f7f7; }
  .versa-lot, .versa-total { background-color: #e6e6e6 !important; font-weight: bold; }
  .versa-level-1 { font-weight: bold; }
  .versa-level-2 { font-weight: 600; }
  .versa-na { color: #999; }
  .versa-dev { display: block; font-size: 11px; color: #555; }
  .versa-warn { color: #9c6f00; margin-left: 4px; }
</style>
"""


def _fmt_money(value, divisor: int) -> str:
    if value is None:
        return "—"
    scaled = value / divisor
    if divisor == 1:
        return f"{scaled:,.0f}".replace(",", " ")
    return f"{scaled:,.1f}".replace(",", " ").replace(".", ",")


def _fmt_pct(value: float) -> str:
    return f"{value:.1f}".replace(".", ",")


def _escape(text) -> str:
    return html_lib.escape(str(text or ""))


def _cell_html(cell, divisor: int) -> str:
    if cell.status == "na":
        return '<td class="versa-na">—</td>'
    bg = ""
    color = ""
    if cell.highlight == "min":
        bg, color = "#C6EFCE", "#006100"
    elif cell.highlight == "max":
        bg, color = "#FFC7CE", "#9C0006"
    style = f"background-color:{bg};color:{color};" if bg else ""
    title_attr = f' title="{_escape(cell.tooltip)}"' if cell.tooltip else ""
    body = _fmt_money(cell.value, divisor) if cell.value is not None else (cell.badge or "—")
    badge_html = (
        f' <span title="{_escape(cell.tooltip)}">{_escape(cell.badge)}</span>'
        if cell.badge and cell.value is not None else ""
    )
    dev_html = f'<span class="versa-dev">{_escape(cell.deviation_label)}</span>' if cell.deviation_label else ""
    warn_html = f'<span class="versa-warn" title="{_escape(cell.warning)}">⚠</span>' if cell.warning else ""
    return f'<td style="{style}"{title_attr}>{body}{badge_html}{warn_html}{dev_html}</td>'


def _row_display_name(row, money_unit: str, vat_rate: float) -> str:
    if row.kind == "total_vat":
        return f"{row.name} ({_fmt_pct(vat_rate)}%), {money_unit}"
    if row.kind in ("total_incl_vat", "total_excl_vat"):
        return f"{row.name}, {money_unit}"
    return row.name


def _row_class(row) -> str:
    if row.kind == "lot":
        return "versa-lot"
    if row.kind in ("total_incl_vat", "total_vat", "total_excl_vat", "best_by_section"):
        return "versa-total"
    return f"versa-level-{row.level}"


def _best_offer_html(best, divisor: int) -> str:
    if best is None:
        return "<td></td>"
    pct = _fmt_pct(best.savings_vs_second_pct)
    return (
        f"<td>{_escape(best.participant_name)}<br>"
        f"<small>{_fmt_money(best.savings_vs_second_rub, divisor)} (+{pct}%)</small></td>"
    )


def render_summary_html(table: SummaryTable, *, money_unit: str = "руб.") -> str:
    divisor = _UNIT_DIVISORS[money_unit]

    header_cells = "".join(
        f'<th class="pinned">{_escape(label)}</th>'
        for label in ("№ п/п", "№ раздела", "Статья СМР", "Наименование работ", "Ед. изм.", "Кол-во")
    )
    if table.has_baseline:
        header_cells += '<th style="background:#fff3cd;">Расчётная стоимость</th>'
    for p in table.participants:
        header_cells += f'<th>{_escape(p.name)}<br><small>{_escape(p.inn or "")}</small></th>'
    header_cells += "<th>Лучшее предложение</th>"

    body_rows = []
    for row in table.rows:
        if row.kind == "best_by_section":
            counts = ", ".join(
                f"{_escape(p.name)}: {row.best_by_section_counts.get(p.id, 0)}"
                for p in table.participants
            )
            body_rows.append(
                f'<tr class="{_row_class(row)}"><td colspan="6">{_escape(row.name)}</td>'
                f'<td colspan="{len(table.participants) + 1}">{counts}</td></tr>'
            )
            continue

        indent = "&nbsp;" * (row.level * 2)
        pinned = (
            f'<td class="pinned">{row.pp_number if row.pp_number is not None else ""}</td>'
            f'<td class="pinned">{_escape(row.number)}</td>'
            f'<td class="pinned">{_escape(row.smr_article)}</td>'
            f'<td class="pinned">{indent}{_escape(_row_display_name(row, money_unit, table.vat_rate))}</td>'
            f'<td class="pinned">{_escape(row.unit or "")}</td>'
            f'<td class="pinned">{row.qty if row.qty is not None else ""}</td>'
        )
        baseline_html = ""
        if table.has_baseline:
            baseline_html = (
                f'<td style="background:#fff3cd;">{_fmt_money(row.baseline_cell.value, divisor)}</td>'
                if row.baseline_cell else '<td style="background:#fff3cd;">—</td>'
            )
        cells_html = "".join(_cell_html(row.cells[p.id], divisor) for p in table.participants)
        best_html = _best_offer_html(row.best, divisor)
        body_rows.append(f'<tr class="{_row_class(row)}">{pinned}{baseline_html}{cells_html}{best_html}</tr>')

    legend = (
        '<div style="margin-bottom:6px;">'
        '<span style="background:#C6EFCE;padding:2px 6px;">минимум</span> '
        '<span style="background:#FFC7CE;padding:2px 6px;">максимум</span> '
        "&nbsp;⚠ неточное сравнение &nbsp;«паушал» &nbsp;«≈0» &nbsp;«вкл. в п/п»"
        "</div>"
    )

    return (
        _CSS + legend
        + '<div class="versa-summary-wrap"><table class="versa-summary"><thead><tr>'
        + header_cells + "</tr></thead><tbody>" + "".join(body_rows) + "</tbody></table></div>"
    )
