from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

NAME_ROW = 7
INN_ROW = 8
ADDRESS_ROW = 9
ACCREDITATION_ROW = 11
HEADER_ROW_1 = 12
HEADER_ROW_2 = 13
FIRST_DATA_ROW = 14

BASELINE_LABEL = "Расчетная стоимость"
CONTRACTOR_LABEL = "Наименование контрагента"

QTY_LABEL = "количество"
UNIT_PRICE_LABEL = "Цена за ед"
PARTICIPANT_TOTAL_LABEL = "Стоимость всего"
CUSTOMER_TOTAL_LABEL = "объемы заказчика"
PARTICIPANT_COMMENT_LABEL = "Комментарий участника"
PCT_LABEL = "% от р/с"
MRG_COMMENT_LABEL = "Комментарии"
EXPECTED_COST_LABEL = "Ожидаемая стоимость"

MATERIALS_LABEL = "Материалы"
WORKS_LABEL = "СМР"
OVERHEAD_LABEL = "Косвенные"
TOTAL_LABEL = "Всего"

_ORG_PREFIX_RE = re.compile(r'^(ООО|АО|ЗАО|ПАО)\s*"?|"?$')

_NAME_TO_ID = {
    "ПАРАЛЛЕЛЬ": "parallel",
    "Р.И.К. ИНЖИНИРИНГ": "rik",
    "РУТЕК": "rutek",
    "БЮРО КОНСТРАКШН": "buro_konstrakshn",
    "ГЭС КОНСТРАКШН": "ges",
    "ФОДД": "fodd",
    "ЭРБЕК": "erbek",
}


def _norm(value) -> str:
    return " ".join(str(value or "").split())


@dataclass(frozen=True)
class PriceCols:
    materials: int
    works: int
    overhead: int
    total: int


@dataclass(frozen=True)
class ParticipantBlock:
    participant_id: str
    name: str
    start_col: int
    end_col: int
    qty_col: int
    unit_price_cols: PriceCols
    participant_total_cols: PriceCols
    customer_total_col: int
    participant_comment_col: int
    pct_col: Optional[int]
    mrg_comment_col: int
    expected_cost_col: int


@dataclass(frozen=True)
class BaselineBlock:
    unit_price_cols: PriceCols
    total_cols: PriceCols


@dataclass(frozen=True)
class Layout:
    baseline: BaselineBlock
    participants: list[ParticipantBlock]
    first_data_row: int = FIRST_DATA_ROW


def _find_price_quad(ws, row12: int, row13: int, start_col: int, end_col: int,
                      row12_label: str, occurrence: int) -> PriceCols:
    """Find the 4-column (Материалы/СМР/Косвенные/Всего) group whose row12
    header matches `row12_label`, taking the `occurrence`-th match left to
    right (0-based) within [start_col, end_col]."""
    seen = 0
    for col in range(start_col, end_col + 1):
        header = _norm(ws.cell(row=row12, column=col).value)
        if row12_label in header:
            if seen == occurrence:
                for offset, label in enumerate(
                    (MATERIALS_LABEL, WORKS_LABEL, OVERHEAD_LABEL, TOTAL_LABEL)
                ):
                    sub_col = col + offset
                    actual = _norm(ws.cell(row=row13, column=sub_col).value)
                    assert label in actual, (
                        f"expected {label!r} at col {sub_col}, got {actual!r}"
                    )
                return PriceCols(
                    materials=col, works=col + 1, overhead=col + 2, total=col + 3
                )
            seen += 1
    raise ValueError(f"price quad {row12_label!r} occurrence {occurrence} not found")


def _find_single_col(ws, row: int, start_col: int, end_col: int, label: str) -> Optional[int]:
    for col in range(start_col, end_col + 1):
        if label in _norm(ws.cell(row=row, column=col).value):
            return col
    return None


def _slugify(name: str) -> str:
    stripped = _ORG_PREFIX_RE.sub("", name).strip().strip('"')
    return _NAME_TO_ID.get(stripped, re.sub(r"\W+", "_", stripped.lower()))


def _discover_participant_block(ws, start_col: int, end_col: int, name: str) -> ParticipantBlock:
    qty_col = _find_single_col(ws, HEADER_ROW_2, start_col, end_col, QTY_LABEL)
    assert qty_col is not None, f"no quantity column for {name!r}"

    unit_price_cols = _find_price_quad(
        ws, HEADER_ROW_1, HEADER_ROW_2, start_col, end_col, UNIT_PRICE_LABEL, occurrence=0
    )
    participant_total_cols = _find_price_quad(
        ws, HEADER_ROW_1, HEADER_ROW_2, unit_price_cols.total + 1, end_col,
        PARTICIPANT_TOTAL_LABEL, occurrence=0,
    )

    customer_total_col = _find_single_col(
        ws, HEADER_ROW_1, participant_total_cols.total + 1, end_col, CUSTOMER_TOTAL_LABEL
    )
    assert customer_total_col is not None, f"no customer-volume total column for {name!r}"

    participant_comment_col = _find_single_col(
        ws, HEADER_ROW_1, customer_total_col + 1, end_col, PARTICIPANT_COMMENT_LABEL
    )
    assert participant_comment_col is not None, f"no participant comment column for {name!r}"

    pct_col = _find_single_col(
        ws, HEADER_ROW_2, participant_comment_col + 1, end_col, PCT_LABEL
    )

    mrg_comment_col = _find_single_col(
        ws, HEADER_ROW_1, participant_comment_col + 1, end_col, MRG_COMMENT_LABEL
    )
    assert mrg_comment_col is not None, f"no MRG comments column for {name!r}"

    expected_cost_col = _find_single_col(
        ws, HEADER_ROW_1, mrg_comment_col + 1, end_col, EXPECTED_COST_LABEL
    )
    assert expected_cost_col is not None, f"no expected-cost column for {name!r}"

    return ParticipantBlock(
        participant_id=_slugify(name),
        name=name,
        start_col=start_col,
        end_col=end_col,
        qty_col=qty_col,
        unit_price_cols=unit_price_cols,
        participant_total_cols=participant_total_cols,
        customer_total_col=customer_total_col,
        participant_comment_col=participant_comment_col,
        pct_col=pct_col,
        mrg_comment_col=mrg_comment_col,
        expected_cost_col=expected_cost_col,
    )


def discover_layout(ws) -> Layout:
    max_col = ws.max_column

    name_cells = []
    for col in range(1, max_col + 1):
        value = ws.cell(row=NAME_ROW, column=col).value
        if value is None:
            continue
        text = _norm(value)
        if text in (CONTRACTOR_LABEL, BASELINE_LABEL) or not text:
            continue
        name_cells.append((col, text))

    baseline_col = None
    for col in range(1, max_col + 1):
        if _norm(ws.cell(row=NAME_ROW, column=col).value) == BASELINE_LABEL:
            baseline_col = col
            break
    assert baseline_col is not None, "could not find 'Расчетная стоимость' header"

    first_participant_col = name_cells[0][0] if name_cells else max_col + 1
    baseline_unit_cols = _find_price_quad(
        ws, HEADER_ROW_1, HEADER_ROW_2, baseline_col, first_participant_col - 1,
        UNIT_PRICE_LABEL, occurrence=0,
    )
    baseline_total_cols = _find_price_quad(
        ws, HEADER_ROW_1, HEADER_ROW_2, baseline_unit_cols.total + 1,
        first_participant_col - 1, PARTICIPANT_TOTAL_LABEL, occurrence=0,
    )

    blocks: list[ParticipantBlock] = []
    for i, (col, name) in enumerate(name_cells):
        end_col = (name_cells[i + 1][0] - 2) if i + 1 < len(name_cells) else max_col
        blocks.append(_discover_participant_block(ws, col, end_col, name))

    return Layout(
        baseline=BaselineBlock(
            unit_price_cols=baseline_unit_cols, total_cols=baseline_total_cols
        ),
        participants=blocks,
    )


_VAT_RATE_RE = re.compile(r"НДС\s*(\d+(?:[.,]\d+)?)\s*%")


def discover_vat_rate(ws, default: float = 22.0) -> float:
    for row in (HEADER_ROW_1, HEADER_ROW_2):
        for col in range(1, ws.max_column + 1):
            text = _norm(ws.cell(row=row, column=col).value)
            match = _VAT_RATE_RE.search(text)
            if match:
                return float(match.group(1).replace(",", "."))
    return default
