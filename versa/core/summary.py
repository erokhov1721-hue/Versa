from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from versa.core.aggregate import section_totals
from versa.core.models import ComparisonMode, Position, PriceStatus, Section, Tender

_ACTUALLY_PRICED = (PriceStatus.PRICED, PriceStatus.LUMP_SUM)
_WARNING_STATUSES = (PriceStatus.LUMP_SUM, PriceStatus.PLACEHOLDER, PriceStatus.INCLUDED_ELSEWHERE)


class DetailLevel(str, Enum):
    SECTIONS = "sections"        # level 1 only
    SUBSECTIONS = "subsections"  # levels 1-3
    POSITIONS = "positions"      # everything


@dataclass(frozen=True)
class ParticipantColumnMeta:
    id: str
    name: str
    inn: Optional[str]


@dataclass
class SummaryCell:
    status: str  # "priced" | "zero" | "placeholder" | "included_elsewhere" | "not_included" | "lump_sum" | "na"
    value: Optional[float]
    highlight: Optional[str] = None  # "min" | "max" | None
    deviation_label: str = ""
    badge: Optional[str] = None
    tooltip: str = ""
    warning: Optional[str] = None


@dataclass
class BestOffer:
    participant_id: Optional[str]
    participant_name: Optional[str]
    savings_vs_second_rub: Optional[float]
    savings_vs_second_pct: Optional[float]


@dataclass
class SummaryRow:
    kind: str  # "lot" | "section" | "subsection" | "position" | "total_incl_vat" | "total_vat" | "total_excl_vat" | "best_by_section"
    row: Optional[int]
    number: str
    smr_article: str
    name: str
    unit: Optional[str]
    qty: Optional[float]
    level: int
    is_filled: bool
    ancestor_numbers: tuple[str, ...]
    cells: dict[str, SummaryCell] = field(default_factory=dict)
    baseline_cell: Optional[SummaryCell] = None
    best: Optional[BestOffer] = None
    best_by_section_counts: Optional[dict[str, int]] = None


@dataclass
class SummaryTable:
    participants: list[ParticipantColumnMeta]
    has_baseline: bool
    vat_rate: float
    rows: list[SummaryRow]


def _format_price_ru(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{value:,.2f}".replace(",", " ").replace(".", ",")


def _tooltip_for(position: Position, pid: str) -> str:
    price = position.participant_prices[pid]
    lines = [
        f"Цена за ед.: материалы {_format_price_ru(price.unit_price.materials)}, "
        f"СМР {_format_price_ru(price.unit_price.works)}, "
        f"косвенные {_format_price_ru(price.unit_price.overhead)}, "
        f"всего {_format_price_ru(price.unit_price.total)}",
    ]
    if price.volume_mismatch:
        lines.append(
            f"Количество участника: {price.quantity_offered} "
            f"(у заказчика {position.customer_quantity})"
        )
    if price.participant_comment:
        lines.append(f"Комментарий участника: {price.participant_comment}")
    if price.mrg_comment:
        lines.append(f"Замечание МРГ: {price.mrg_comment}")
    return "\n".join(lines)


def _cell_for_position(position: Position, pid: str) -> SummaryCell:
    price = position.participant_prices[pid]
    status = price.status.value
    value = price.total_for_customer_volume

    badge = None
    if price.status == PriceStatus.PLACEHOLDER:
        badge = "≈0"
    elif price.status == PriceStatus.INCLUDED_ELSEWHERE:
        ref = price.included_in_positions[0] if price.included_in_positions else "?"
        badge = f"вкл. в п/п {ref}"
    elif price.status == PriceStatus.NOT_INCLUDED:
        badge = "не вкл."
    elif price.status == PriceStatus.LUMP_SUM:
        badge = "паушал"

    return SummaryCell(
        status=status,
        value=value if price.status != PriceStatus.ZERO else None,
        badge=badge,
        tooltip=_tooltip_for(position, pid),
    )


def _apply_position_highlight(cells: dict[str, SummaryCell], participant_ids: list[str]) -> None:
    priced = {
        pid: cells[pid].value for pid in participant_ids
        if cells[pid].status == "priced" and cells[pid].value is not None
    }
    if len(priced) < 2:
        return
    lo, hi = min(priced.values()), max(priced.values())
    for pid, value in priced.items():
        if value == lo:
            cells[pid].highlight = "min"
        if value == hi:
            cells[pid].highlight = "max"


def _section_warning(section: Section, pid: str) -> Optional[str]:
    for position in section.iter_positions():
        price = position.participant_prices.get(pid)
        if price and price.status in _WARNING_STATUSES:
            return "Неточное сравнение: в разделе есть паушал/заглушка/включено в другую позицию"
    return None


def _cells_for_section(section: Section, participant_ids: list[str]) -> dict[str, SummaryCell]:
    totals = section_totals(section).by_customer_volume
    cells = {}
    for pid in participant_ids:
        value = totals.get(pid, 0.0)
        cells[pid] = SummaryCell(status="priced", value=value, warning=_section_warning(section, pid))
    if len(cells) >= 2:
        lo = min(c.value for c in cells.values())
        hi = max(c.value for c in cells.values())
        for cell in cells.values():
            if cell.value == lo:
                cell.highlight = "min"
            if cell.value == hi:
                cell.highlight = "max"
    return cells


def _set_deviation_labels(
    cells: dict[str, SummaryCell], mode: ComparisonMode, baseline_total: Optional[float],
) -> None:
    values = {pid: c.value for pid, c in cells.items() if c.value is not None and c.status != "na"}
    if not values:
        return
    if mode == ComparisonMode.BASELINE and baseline_total:
        for pid, cell in cells.items():
            if cell.value is None:
                continue
            pct = (cell.value - baseline_total) / baseline_total * 100
            sign = "+" if pct >= 0 else ""
            pct_text = f"{sign}{pct:.1f}".replace(".", ",")
            cell.deviation_label = f"{pct_text}% к р/с"
        return
    minimum = min(values.values())
    for pid, cell in cells.items():
        if cell.value is None:
            continue
        if cell.value == minimum:
            cell.deviation_label = ""
            continue
        pct = (cell.value - minimum) / minimum * 100 if minimum else 0.0
        pct_text = f"+{pct:.1f}".replace(".", ",")
        cell.deviation_label = f"{pct_text}% к мин."


def _best_offer(
    cells: dict[str, SummaryCell], participants: list[ParticipantColumnMeta],
) -> Optional[BestOffer]:
    values = sorted(
        ((pid, c.value) for pid, c in cells.items() if c.value is not None),
        key=lambda kv: kv[1],
    )
    if len(values) < 2:
        return None
    (best_pid, best_value), (_, second_value) = values[0], values[1]
    name = next(p.name for p in participants if p.id == best_pid)
    return BestOffer(
        participant_id=best_pid, participant_name=name,
        savings_vs_second_rub=second_value - best_value,
        savings_vs_second_pct=((second_value - best_value) / second_value * 100) if second_value else 0.0,
    )


def _is_filled(section: Section) -> bool:
    return any(
        price.status in _ACTUALLY_PRICED or position.baseline is not None
        for position in section.iter_positions()
        for price in position.participant_prices.values()
    )


def _should_include_children(
    level: int, detail_level: DetailLevel, section_number: str,
    expanded_sections: frozenset[str], top_level_number: str,
) -> bool:
    if section_number in expanded_sections or top_level_number in expanded_sections:
        return True
    if detail_level == DetailLevel.POSITIONS:
        return True
    if detail_level == DetailLevel.SUBSECTIONS:
        return level < 3
    return False  # DetailLevel.SECTIONS: never descend below level 1 unless expanded


def _walk_section(
    section: Section, participant_ids: list[str], participants: list[ParticipantColumnMeta],
    mode: ComparisonMode, detail_level: DetailLevel, expanded_sections: frozenset[str],
    hide_unfilled: bool, top_level_number: str, ancestors: tuple[str, ...],
    rows: list[SummaryRow],
) -> None:
    is_filled = _is_filled(section)
    if hide_unfilled and not is_filled:
        return  # top-level unfilled sections are skipped by the caller before this is
        # ever reached; this early-return covers unfilled subsections met while descending

    baseline_cell = None
    if is_filled:
        cells = _cells_for_section(section, participant_ids)
        baseline_values = [
            p.baseline.total.total for p in section.iter_positions() if p.baseline is not None
        ]
        baseline_total = sum(v for v in baseline_values if v is not None) if baseline_values else None
        if baseline_total is not None:
            # raw value only — no deviation math against it yet, see plan's Review Focus note
            baseline_cell = SummaryCell(status="priced", value=baseline_total)
        _set_deviation_labels(cells, mode, baseline_total)
        best = _best_offer(cells, participants)
    else:
        cells = {pid: SummaryCell(status="na", value=None) for pid in participant_ids}
        best = None

    kind = "section" if not ancestors else "subsection"
    rows.append(SummaryRow(
        kind=kind, row=section.row, number=section.number,
        smr_article=section.title if section.title else "",
        name=section.title, unit=None, qty=None,
        level=len(ancestors) + 1, is_filled=is_filled,
        ancestor_numbers=ancestors, cells=cells, best=best, baseline_cell=baseline_cell,
    ))

    include_children = _should_include_children(
        len(ancestors) + 1, detail_level, section.number, expanded_sections, top_level_number,
    )
    if not include_children:
        return

    child_ancestors = ancestors + (section.number,)
    for child in section.children:
        _walk_section(
            child, participant_ids, participants, mode, detail_level, expanded_sections,
            hide_unfilled, top_level_number, child_ancestors, rows,
        )
    if (
        detail_level == DetailLevel.POSITIONS
        or section.number in expanded_sections
        or top_level_number in expanded_sections
    ):
        for position in section.positions:
            price_cells = {pid: _cell_for_position(position, pid) for pid in participant_ids}
            _apply_position_highlight(price_cells, participant_ids)
            position_best = _best_offer(price_cells, participants)
            rows.append(SummaryRow(
                kind="position", row=position.row, number="",
                smr_article="", name=position.name, unit=position.unit,
                qty=position.customer_quantity, level=len(child_ancestors) + 1,
                is_filled=is_filled, ancestor_numbers=child_ancestors,
                cells=price_cells, best=position_best,
            ))


def build_summary_table(
    tender: Tender, *, detail_level: DetailLevel = DetailLevel.SECTIONS,
    expanded_sections: frozenset[str] = frozenset(), hide_unfilled: bool = False,
    vat_rate: Optional[float] = None,
) -> SummaryTable:
    participant_ids = [p.id for p in tender.participants]
    participants = [
        ParticipantColumnMeta(id=p.id, name=p.name, inn=p.inn) for p in tender.participants
    ]
    rate = vat_rate if vat_rate is not None else tender.default_vat_rate

    rows: list[SummaryRow] = []
    lot_section, *real_sections = tender.full_sections

    grand_totals: dict[str, float] = {pid: 0.0 for pid in participant_ids}
    for section in real_sections:
        totals = section_totals(section).by_customer_volume
        for pid in participant_ids:
            grand_totals[pid] += totals.get(pid, 0.0)

    lot_cells = {pid: SummaryCell(status="priced", value=grand_totals[pid]) for pid in participant_ids}
    if len(lot_cells) >= 2:
        lo, hi = min(grand_totals.values()), max(grand_totals.values())
        for pid, cell in lot_cells.items():
            if cell.value == lo:
                cell.highlight = "min"
            if cell.value == hi:
                cell.highlight = "max"
    _set_deviation_labels(lot_cells, tender.mode, None)
    rows.append(SummaryRow(
        kind="lot", row=lot_section.row, number="", smr_article="",
        name=lot_section.title, unit=None, qty=None, level=0, is_filled=True,
        ancestor_numbers=(), cells=lot_cells, best=_best_offer(lot_cells, participants),
    ))

    best_by_section_counts = {pid: 0 for pid in participant_ids}
    for section in real_sections:
        if hide_unfilled and not _is_filled(section):
            continue
        before = len(rows)
        _walk_section(
            section, participant_ids, participants, tender.mode, detail_level,
            expanded_sections, hide_unfilled, section.number, (), rows,
        )
        section_row = rows[before]
        if section_row.best is not None:
            best_by_section_counts[section_row.best.participant_id] += 1

    total_cells = {pid: SummaryCell(status="priced", value=grand_totals[pid]) for pid in participant_ids}
    for pid, cell in total_cells.items():
        if cell.value == min(grand_totals.values()):
            cell.highlight = "min"
        if cell.value == max(grand_totals.values()):
            cell.highlight = "max"
    _set_deviation_labels(total_cells, tender.mode, None)
    rows.append(SummaryRow(
        kind="total_incl_vat", row=None, number="", smr_article="",
        name="ИТОГО, руб. с учётом НДС", unit=None, qty=None, level=0, is_filled=True,
        ancestor_numbers=(), cells=total_cells, best=_best_offer(total_cells, participants),
    ))

    vat_cells = {
        pid: SummaryCell(status="priced", value=grand_totals[pid] * rate / (100 + rate))
        for pid in participant_ids
    }
    rows.append(SummaryRow(
        kind="total_vat", row=None, number="", smr_article="", name="В том числе НДС",
        unit=None, qty=None, level=0, is_filled=True, ancestor_numbers=(), cells=vat_cells,
    ))

    excl_cells = {
        pid: SummaryCell(status="priced", value=grand_totals[pid] - vat_cells[pid].value)
        for pid in participant_ids
    }
    rows.append(SummaryRow(
        kind="total_excl_vat", row=None, number="", smr_article="",
        name="ИТОГО, руб. без учёта НДС", unit=None, qty=None, level=0, is_filled=True,
        ancestor_numbers=(), cells=excl_cells,
    ))

    rows.append(SummaryRow(
        kind="best_by_section", row=None, number="", smr_article="",
        name="Лучших предложений по разделам", unit=None, qty=None, level=0,
        is_filled=True, ancestor_numbers=(), cells={},
        best_by_section_counts=best_by_section_counts,
    ))

    has_baseline = any(
        position.baseline is not None
        for section in real_sections
        for position in section.iter_positions()
    )
    return SummaryTable(participants=participants, has_baseline=has_baseline, vat_rate=rate, rows=rows)
