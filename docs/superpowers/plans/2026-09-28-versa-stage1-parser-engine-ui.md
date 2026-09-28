# Versa — Этап 1 (парсер, движок сравнения, минимальный UI) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the stage-1 skeleton of Versa: a clean `core` package that parses the "сводная таблица" xlsx into a typed data model, computes section/participant comparisons (baseline mode and peer mode), and a minimal Streamlit `ui` that renders it — using the real sample file as the only fixture.

**Architecture:** `versa/core` is pure Python (pandas/openpyxl only, zero Streamlit imports) so it can later sit behind FastAPI unchanged. Parsing is two-staged: `excel_layout.py` discovers *where* things are (participant column blocks, header row 7/12/13 semantics) purely from cell text, never from hardcoded letters; `parser.py` uses that layout to build `Tender`/`Section`/`Position` dataclasses. `hierarchy.py` turns the flat row list into a section tree using column B's dotted numbering. `status.py` classifies each participant's price per position (priced/zero/placeholder/included_elsewhere/not_included/lump_sum) from price value + comment text. `aggregate.py` recomputes every rollup bottom-up from leaf positions (the file's own subtotal formulas and cross-references are never trusted). `compare.py` produces the two comparison modes (against расчётная стоимость, or peer min/max/median). `versa/ui/app.py` is a single Streamlit page that imports only from `versa.core`.

**Tech Stack:** Python 3.11+, pandas, openpyxl (`data_only=True`), plotly, streamlit, pytest. Dependencies pinned in `pyproject.toml`.

**Spec:** This plan implements the requirements given directly in conversation (no separate spec file exists yet) plus the concrete structure of `samples/943-ТУ__Сводная_Казачий_НС_-_фасады_и_ВИС.xlsx`, sheet `3_ ПОДРОБНАЯ`, verified by direct inspection (see Task 0 findings below).

## Verified facts about the sample file (from direct inspection, not assumption)

- Sheet name: `3_ ПОДРОБНАЯ`, dimensions `A1:DQ1647` (121 columns, 1647 rows).
- Row 7: `G7`="Наименование контрагента", `J7`="Расчетная стоимость" (columns J–Q, **entirely zero/empty** in this sample → confirms Mode Б), then one cell per participant marks the start of their block: `S7`=ООО «ПАРАЛЛЕЛЬ», `AH7`=ООО «Р.И.К. ИНЖИНИРИНГ», `AV7`=ООО «РУТЕК», `BK7`=ООО «БЮРО КОНСТРАКШН», `BZ7`=АО «ГЭС КОНСТРАКШН», `CO7`=АО «ФОДД», `DD7`=ООО «ЭРБЕК». Row 8 = ИНН, row 9 = адрес, row 11 = статус аккредитации (can be `None`, e.g. Р.И.К.'s `AH11` is empty).
- Each participant block, discovered via row 12/13 header text, is: qty ("Предлагаемое количество") → 4 unit-price cols (Материалы/СМР/Косвенные/Всего) → 4 participant-volume total cols (same 4 subheaders) → 1 "Стоимость всего за объемы заказчика" col → 1 "Комментарий участника" col → **optional** 1 "% от р/с" col (row 13 only) → 1 "Комментарии" col (МРГ) → 1 "Ожидаемая стоимость" col. Confirmed the Р.И.К. block genuinely has no "% от р/с" column (13 cols vs 14 for everyone else) — column discovery must not assume a fixed block width.
- Column B holds the section/subsection number (e.g. `6`, `6.1`, `6.1.1`); level = number of dot-separated parts. Row 294 is the confirmed real-world example of `B`≠`C` numbering drift: `B='6.8'` but `C='6.10. Декоративные элементы и другие'` — hierarchy must be built from B, title text from C (fallback D).
- Template is fully populated with section rows for the whole building (sections 1–10ish) but only sections **6** ("Фасадные работы", rows 225–316) and **10** ("Инженерные системы", from row 667) contain any prices — every other section is all-zero and must be dropped from the comparison output.
- Р.И.К.'s "Стоимость всего за объемы заказчика" column (`AQ`) is `#DIV/0!` on **385 rows** (basically the whole sheet) — confirms the file-formula bug is pervasive, not a one-off; core must never read `AQ` and must always recompute `customer_qty × unit_price`.
- ГЭС has exactly **99 rows** where the "Всего" unit price (`CD`) is `0.01` — this is the placeholder-price convention ("включено", price < 1 ₽). Two of those (rows 314–315) carry the comment "Задвоение с позициями 225, 226, 229 и 230" (duplicate, not `included_elsewhere` — no п/п number, so it must NOT be parsed as an `included_elsewhere` reference, just a placeholder with a note).
- ФОДД: section 10, rows 667–689 — only row 670 ("Монтаж щитов питания, автоматики и учета") carries the entire section's price (`1 551 310 030.71`); every sibling position in the same section is 0 → this is the confirmed `lump_sum` case, and it's a **section-level** fact about a participant, not a single-position status.
- ГЭС also marks a run of lighting fixture positions (rows 682–689) with comment "Включено в п/п 667" (placeholder price 0.01) — confirms `included_elsewhere` with an extractable referenced position number.
- Real comment text found in the file, beyond what's obvious from the spec: `"Вклучено"` (typo, 104×), `"не Вклучено"` (typo-of-typo, 30× — **contains** the substring "Вклучено" so a naive "includes → included" match would misclassify it as included), `"Не включено в КП."`, `"Нет в проекте."`, `"В предложение не включено"`, `"Не входит в стоимость"`, `"не учтено, нет данных"`, `"учтено в п.288"` (reference without "п/п"), and multi-reference comments like `"Включено в п/п 856, 858, 860 ,862, 864, 868, 870"`.
- The `D` column (наименование работ) uses merged cells `D<r>:E<r>` on almost every position row — openpyxl only puts the value on the anchor cell (`D`), so reads must always go through `D`, never assume `E` might hold it.

## Global Constraints

- Python 3.11+; dependencies (pandas, openpyxl, plotly, streamlit, pytest) declared in `pyproject.toml`, no other runtime deps.
- `versa/core/**` must contain zero `import streamlit` (enforced by a test that greps the package).
- Always load the workbook with `data_only=True`; if a cell that should hold a computed value is `None`, recompute it (`quantity × unit price`) rather than leaving it missing.
- Never read a file-provided subtotal/rollup cell (section header rows, "Стоимость всего за объемы заказчика") for anything used in comparison output — always recompute bottom-up from leaf positions using our own arithmetic.
- Any cell value that is an Excel error string (starts with `#`) becomes `None` and produces a `Warning(type=FORMULA_ERROR, ...)`.
- Participant column blocks and their sub-columns are discovered per-workbook from row 7 (names) and row 12/13 (header text) — no column letters are ever hardcoded in `parser.py`/`aggregate.py`/`compare.py` business logic (only `excel_layout.py` is allowed to touch raw cell coordinates).
- Sections where no participant (and no baseline) has a single `priced` position anywhere in their subtree are dropped from the `Tender.sections` the UI/tests see.
- UI shows money in millions ₽ with 1 decimal by default, with a per-table toggle to full rubles; internal storage is always raw rubles as `float`.
- Nothing in this stage does Excel export, a database, auth, or multi-round (переторжка) comparison — but `Tender`/`Section`/`Position` are designed so a later "round" is just another sibling object of the same shape (see Task 2 note).

## Review Focus

- "не Вклучено" (typo-of-a-typo) must classify as `NOT_INCLUDED`, not `INCLUDED_ELSEWHERE`/priced, even though it contains the substring "Вклучено" — pinned in Task 6's tests.
- Multi-reference `included_elsewhere` comments ("Включено в п/п 856, 858, 860 ,862, 864, 868, 870") must not crash the parser and must retain at least the full list of referenced numbers — pinned in Task 6.
- A participant block missing an optional column (Р.И.К. has no "% от р/с") must not shift-misread neighboring columns or crash layout discovery — pinned in Task 3.
- Merged `D:E` name cells must resolve to the same text as an unmerged row; a naive `ws.cell(row, col=5).value` read (column E) must never be used to fetch the name — pinned in Task 4.
- Mode detection must distinguish "baseline column genuinely absent/all-zero for this tender" (→ Mode Б) from "baseline present but this one position happens to be priced zero" (→ still Mode А) using a tender-wide flag, not a per-position `None` check — pinned in Task 8.

---

## Task 0: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `versa/__init__.py`
- Create: `versa/core/__init__.py`
- Create: `versa/ui/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `.gitignore`

**Interfaces:**
- Produces: importable `versa`, `versa.core`, `versa.ui` packages; a `sample_path` fixture and a session-scoped `sample_tender` fixture placeholder (filled in once `parser.py` exists in Task 5) other tests will consume via `from tests.conftest import ...`-style pytest fixture injection.

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "versa"
version = "0.1.0"
description = "Сравнение коммерческих предложений подрядчиков на тендерах"
requires-python = ">=3.11"
dependencies = [
    "pandas>=2.2",
    "openpyxl>=3.1",
    "plotly>=5.22",
    "streamlit>=1.36",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["versa*"]
```

- [ ] **Step 2: Write `.gitignore`**

```
__pycache__/
*.pyc
.venv/
.pytest_cache/
```

- [ ] **Step 3: Create empty `__init__.py` files**

```python
# versa/__init__.py, versa/core/__init__.py, versa/ui/__init__.py, tests/__init__.py
```
(each file's entire content is empty)

- [ ] **Step 4: Write `tests/conftest.py`**

```python
from pathlib import Path

import pytest

SAMPLE_PATH = (
    Path(__file__).resolve().parents[1]
    / "samples"
    / "943-ТУ__Сводная_Казачий_НС_-_фасады_и_ВИС.xlsx"
)


@pytest.fixture(scope="session")
def sample_path() -> Path:
    assert SAMPLE_PATH.exists(), f"missing sample file: {SAMPLE_PATH}"
    return SAMPLE_PATH


@pytest.fixture(scope="session")
def sample_tender(sample_path):
    from versa.core.parser import parse_tender

    return parse_tender(sample_path)
```

- [ ] **Step 5: Install the package in editable mode and confirm imports resolve**

Run: `pip install -e ".[dev]"`
Then: `python -c "import versa.core, versa.ui; print('ok')"`
Expected: prints `ok` with no import errors.

- [ ] **Step 6: Commit**

```bash
git init
git add pyproject.toml .gitignore versa tests samples
git commit -m "chore: scaffold versa project structure"
```

---

## Task 1: Core data model

**Files:**
- Create: `versa/core/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Produces: `PriceStatus` (Enum), `ComparisonMode` (Enum), `PriceBreakdown`, `ParticipantInfo`, `BaselinePrice`, `PositionPrice`, `Position`, `Section`, `Warning`, `WarningType` (Enum), `Tender` — all frozen where practical, all consumed by every later task.

- [ ] **Step 1: Write the failing test for basic construction and section tree walking**

```python
# tests/test_models.py
from versa.core.models import (
    ParticipantInfo,
    Position,
    PriceBreakdown,
    PriceStatus,
    Section,
    Tender,
    ComparisonMode,
)


def test_section_iter_positions_recurses_into_children():
    leaf_a = Position(row=20, number=None, name="Поз. А", unit="м2",
                       customer_quantity=10.0, customer_comment=None,
                       baseline=None, participant_prices={})
    leaf_b = Position(row=21, number=None, name="Поз. Б", unit="м2",
                       customer_quantity=5.0, customer_comment=None,
                       baseline=None, participant_prices={})
    child = Section(row=19, number="6.1", title="Подраздел", level=2,
                     positions=[leaf_b], children=[])
    root = Section(row=18, number="6", title="Раздел", level=1,
                    positions=[leaf_a], children=[child])

    names = [p.name for p in root.iter_positions()]

    assert names == ["Поз. А", "Поз. Б"]


def test_price_breakdown_defaults_to_none_fields():
    pb = PriceBreakdown()
    assert (pb.materials, pb.works, pb.overhead, pb.total) == (None, None, None, None)


def test_tender_participants_lookup_by_id():
    p1 = ParticipantInfo(id="parallel", name='ООО "ПАРАЛЛЕЛЬ"', inn="9715299145",
                          address="...", accreditation_status="Не аккредитован")
    tender = Tender(subject="...", object_name="...", address="...",
                     participants=[p1], sections=[], mode=ComparisonMode.PEER,
                     warnings=[])
    assert tender.participant_by_id("parallel") is p1
    assert tender.participant_by_id("missing") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'versa.core.models'`

- [ ] **Step 3: Write `versa/core/models.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterator, Optional


class PriceStatus(str, Enum):
    PRICED = "priced"
    ZERO = "zero"
    PLACEHOLDER = "placeholder"
    INCLUDED_ELSEWHERE = "included_elsewhere"
    NOT_INCLUDED = "not_included"
    LUMP_SUM = "lump_sum"


class ComparisonMode(str, Enum):
    BASELINE = "baseline"  # Режим А: сравнение с расчётной стоимостью
    PEER = "peer"          # Режим Б: сравнение участников между собой


class WarningType(str, Enum):
    FORMULA_ERROR = "formula_error"
    LUMP_SUM = "lump_sum"
    PLACEHOLDER = "placeholder"
    INCLUDED_ELSEWHERE = "included_elsewhere"
    VOLUME_MISMATCH = "volume_mismatch"


@dataclass(frozen=True)
class PriceBreakdown:
    materials: Optional[float] = None
    works: Optional[float] = None
    overhead: Optional[float] = None
    total: Optional[float] = None


@dataclass(frozen=True)
class ParticipantInfo:
    id: str
    name: str
    inn: Optional[str]
    address: Optional[str]
    accreditation_status: Optional[str]


@dataclass(frozen=True)
class BaselinePrice:
    unit_price: PriceBreakdown
    total: PriceBreakdown


@dataclass(frozen=True)
class PositionPrice:
    status: PriceStatus
    quantity_offered: Optional[float]
    unit_price: PriceBreakdown
    total_for_participant_volume: PriceBreakdown
    total_for_customer_volume: Optional[float]
    participant_comment: Optional[str]
    mrg_comment: Optional[str]
    pct_of_estimate: Optional[float]
    expected_cost: Optional[float]
    included_in_positions: tuple[int, ...] = ()
    volume_mismatch: bool = False


@dataclass
class Position:
    row: int
    number: Optional[int]
    name: str
    unit: Optional[str]
    customer_quantity: Optional[float]
    customer_comment: Optional[str]
    baseline: Optional[BaselinePrice]
    participant_prices: dict[str, PositionPrice]


@dataclass
class Section:
    row: int
    number: str
    title: str
    level: int
    positions: list[Position] = field(default_factory=list)
    children: list["Section"] = field(default_factory=list)

    def iter_positions(self) -> Iterator[Position]:
        yield from self.positions
        for child in self.children:
            yield from child.iter_positions()

    def iter_sections(self) -> Iterator["Section"]:
        yield self
        for child in self.children:
            yield from child.iter_sections()


@dataclass
class Warning:
    type: WarningType
    row: int
    participant_id: Optional[str]
    message: str


@dataclass
class Tender:
    subject: str
    object_name: str
    address: str
    participants: list[ParticipantInfo]
    sections: list[Section]
    mode: ComparisonMode
    warnings: list[Warning]

    def participant_by_id(self, participant_id: str) -> Optional[ParticipantInfo]:
        for p in self.participants:
            if p.id == participant_id:
                return p
        return None

    def iter_sections(self) -> Iterator[Section]:
        for s in self.sections:
            yield from s.iter_sections()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_models.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add versa/core/models.py tests/test_models.py
git commit -m "feat: add core dataclasses for Tender/Section/Position"
```

---

## Task 2: Excel layout discovery (participant blocks + header columns)

**Files:**
- Create: `versa/core/excel_layout.py`
- Test: `tests/test_excel_layout.py`

**Interfaces:**
- Consumes: an `openpyxl.Workbook` loaded with `data_only=True` (Task 5 owns loading it).
- Produces: `ParticipantBlock` dataclass (`participant_id`, `name_col`, `qty_col`, `unit_price_cols: PriceCols`, `participant_total_cols: PriceCols`, `customer_total_col`, `participant_comment_col`, `pct_col: Optional[int]`, `mrg_comment_col`, `expected_cost_col`), `BaselineBlock` dataclass (`unit_price_cols`, `total_cols`, `present: bool`), `PriceCols` dataclass (`materials`, `works`, `overhead`, `total`), and `discover_layout(ws) -> Layout` where `Layout` has `.baseline: BaselineBlock`, `.participants: list[ParticipantBlock]`, `.header_rows == (7, 8, 9, 11, 12, 13)`, `.first_data_row == 14`.

- [ ] **Step 1: Write the failing test using the real sample sheet**

```python
# tests/test_excel_layout.py
import openpyxl

from versa.core.excel_layout import discover_layout


def test_discovers_seven_participant_blocks(sample_path):
    wb = openpyxl.load_workbook(sample_path, data_only=True)
    ws = wb["3_ ПОДРОБНАЯ"]

    layout = discover_layout(ws)

    assert len(layout.participants) == 7
    names = [p.name for p in layout.participants]
    assert names == [
        'ООО "ПАРАЛЛЕЛЬ"',
        'ООО "Р.И.К. ИНЖИНИРИНГ"',
        'ООО "РУТЕК"',
        'ООО "БЮРО КОНСТРАКШН"',
        'АО "ГЭС КОНСТРАКШН"',
        'АО "ФОДД"',
        'ООО "ЭРБЕК"',
    ]


def test_rik_block_has_no_pct_column_others_do(sample_path):
    wb = openpyxl.load_workbook(sample_path, data_only=True)
    ws = wb["3_ ПОДРОБНАЯ"]

    layout = discover_layout(ws)
    by_name = {p.name: p for p in layout.participants}

    assert by_name['ООО "Р.И.К. ИНЖИНИРИНГ"'].pct_col is None
    assert by_name['ООО "ПАРАЛЛЕЛЬ"'].pct_col is not None
    assert by_name['ООО "РУТЕК"'].pct_col is not None


def test_baseline_block_present_but_columns_located(sample_path):
    wb = openpyxl.load_workbook(sample_path, data_only=True)
    ws = wb["3_ ПОДРОБНАЯ"]

    layout = discover_layout(ws)

    assert layout.baseline.unit_price_cols.total == 13  # column M
    assert layout.baseline.total_cols.total == 17  # column Q
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_excel_layout.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'versa.core.excel_layout'`

- [ ] **Step 3: Write `versa/core/excel_layout.py`**

```python
from __future__ import annotations

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
                sub = {}
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


def _discover_participant_block(ws, start_col: int, end_col: int, participant_id: str,
                                 name: str) -> ParticipantBlock:
    qty_col = _find_single_col(ws, HEADER_ROW_2, start_col, end_col, QTY_LABEL)
    assert qty_col is not None, f"no quantity column for {name!r}"

    unit_price_cols = _find_price_quad(
        ws, HEADER_ROW_1, HEADER_ROW_2, start_col, end_col, UNIT_PRICE_LABEL, occurrence=0
    )
    participant_total_cols = _find_price_quad(
        ws, HEADER_ROW_1, HEADER_ROW_2, start_col, end_col, UNIT_PRICE_LABEL, occurrence=1
    )
    # NB: the second price quad's row12 header is also "Цена за ед..." in this
    # template for the *previous* quad's twin ("Стоимость всего..."); locate it
    # by the distinct row12 label instead for robustness across templates:
    participant_total_cols = _find_price_quad(
        ws, HEADER_ROW_1, HEADER_ROW_2, unit_price_cols.total + 1, end_col,
        PARTICIPANT_TOTAL_LABEL, occurrence=0
    )

    customer_total_col = _find_single_col(
        ws, HEADER_ROW_1, participant_total_cols.total + 1, end_col, CUSTOMER_TOTAL_LABEL
    )
    assert customer_total_col is not None, f"no customer-volume total column for {name!r}"

    participant_comment_col = _find_single_col(
        ws, HEADER_ROW_1, customer_total_col + 1, end_col, PARTICIPANT_COMMENT_LABEL
    )
    assert participant_comment_col is not None

    pct_col = _find_single_col(
        ws, HEADER_ROW_2, participant_comment_col + 1, end_col, PCT_LABEL
    )

    mrg_comment_col = _find_single_col(
        ws, HEADER_ROW_1, participant_comment_col + 1, end_col, MRG_COMMENT_LABEL
    )
    assert mrg_comment_col is not None

    expected_cost_col = _find_single_col(
        ws, HEADER_ROW_1, mrg_comment_col + 1, end_col, EXPECTED_COST_LABEL
    )
    assert expected_cost_col is not None

    return ParticipantBlock(
        participant_id=participant_id,
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


def _slugify(name: str) -> str:
    import re

    ascii_map = {
        "ПАРАЛЛЕЛЬ": "parallel", "Р.И.К. ИНЖИНИРИНГ": "rik", "РУТЕК": "rutek",
        "БЮРО КОНСТРАКШН": "buro_konstrakshn", "ГЭС КОНСТРАКШН": "ges",
        "ФОДД": "fodd", "ЭРБЕК": "erbek",
    }
    stripped = re.sub(r'^(ООО|АО|ЗАО|ПАО)\s*"?|"?$', "", name).strip().strip('"')
    return ascii_map.get(stripped, re.sub(r"\W+", "_", stripped.lower()))


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
        blocks.append(
            _discover_participant_block(ws, col, end_col, _slugify(name), name)
        )

    return Layout(
        baseline=BaselineBlock(
            unit_price_cols=baseline_unit_cols, total_cols=baseline_total_cols
        ),
        participants=blocks,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_excel_layout.py -v`
Expected: PASS (3 passed). If a column-order assumption is wrong for this template, the `assert label in actual` messages in `_find_price_quad` will name the exact column and header text that didn't match — fix the search order/labels, don't hardcode a column letter.

- [ ] **Step 5: Commit**

```bash
git add versa/core/excel_layout.py tests/test_excel_layout.py
git commit -m "feat: discover participant/baseline column blocks from header text"
```

---

## Task 3: Section hierarchy builder

**Files:**
- Create: `versa/core/hierarchy.py`
- Test: `tests/test_hierarchy.py`

**Interfaces:**
- Consumes: a list of `RawRow` tuples `(row_index, b_value, c_value, d_value)` (Task 5's parser will build this list from the worksheet before calling in).
- Produces: `build_section_tree(rows: list[RawRow]) -> list[Section]` (top-level `Section` list; `Section.positions`/`.children` populated, but `Position.participant_prices` left as `{}` — Task 5 fills that in afterwards by mutating the returned `Position` objects, matched by `row`).

- [ ] **Step 1: Write the failing test, including the real B/C-mismatch example**

```python
# tests/test_hierarchy.py
from versa.core.hierarchy import RawRow, build_section_tree


def test_builds_nested_sections_and_attaches_positions():
    rows = [
        RawRow(row=225, b="6", c="6. Фасадные работы", d="Устройство фасадов"),
        RawRow(row=226, b="6.1", c="6.1. Светопрозрачные конструкции", d="..."),
        RawRow(row=227, b="6.1.1", c="6.1.1. Профильная система", d="..."),
        RawRow(row=228, b=None, c=None, d="Витражная система высотой 4550мм"),
        RawRow(row=236, b="6.2", c="6.2. Типовой этаж", d="..."),
    ]

    tree = build_section_tree(rows)

    assert len(tree) == 1
    root = tree[0]
    assert root.number == "6" and root.level == 1
    assert [c.number for c in root.children] == ["6.1", "6.2"]
    sub = root.children[0]
    assert [c.number for c in sub.children] == ["6.1.1"]
    leaf_section = sub.children[0]
    assert [p.name for p in leaf_section.positions] == ["Витражная система высотой 4550мм"]


def test_bc_number_mismatch_uses_c_for_title_but_b_for_hierarchy():
    rows = [
        RawRow(row=287, b="6.7", c="6.7. Мокрый фасад", d="..."),
        RawRow(row=294, b="6.8", c="6.10. Декоративные элементы и другие", d="Декоративные элементы и другие"),
    ]

    tree = build_section_tree(rows)

    numbers = [s.number for s in tree[0].iter_sections()] if False else None
    flat = [s for root in tree for s in root.iter_sections()]
    by_row = {s.row: s for s in flat}
    assert by_row[294].number == "6.8"  # hierarchy follows B
    assert by_row[294].title == "6.10. Декоративные элементы и другие"  # title follows C


def test_title_falls_back_to_d_when_c_empty():
    rows = [RawRow(row=98, b="3.2.1", c=None, d="Постоянный дренаж")]
    tree = build_section_tree(rows)
    assert tree[0].title == "Постоянный дренаж"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_hierarchy.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'versa.core.hierarchy'`

- [ ] **Step 3: Write `versa/core/hierarchy.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple, Optional

from versa.core.models import Position, Section


class RawRow(NamedTuple):
    row: int
    b: Optional[str]
    c: Optional[str]
    d: Optional[str]


def _is_blank(value: Optional[str]) -> bool:
    return value is None or str(value).strip() == ""


def _level(number: str) -> int:
    return len(number.rstrip(".").split("."))


def build_section_tree(rows: list[RawRow]) -> list[Section]:
    roots: list[Section] = []
    stack: list[Section] = []  # top of stack = current deepest open section

    for raw in rows:
        if not _is_blank(raw.b):
            number = str(raw.b).strip().rstrip(".")
            title = raw.c if not _is_blank(raw.c) else raw.d
            level = _level(number)

            while stack and stack[-1].level >= level:
                stack.pop()

            section = Section(row=raw.row, number=number, title=str(title).strip(),
                               level=level)
            if stack:
                stack[-1].children.append(section)
            else:
                roots.append(section)
            stack.append(section)

        elif not _is_blank(raw.d):
            if not stack:
                continue  # position before any section header; nothing to attach to
            position = Position(
                row=raw.row, number=None, name=str(raw.d).strip(), unit=None,
                customer_quantity=None, customer_comment=None, baseline=None,
                participant_prices={},
            )
            stack[-1].positions.append(position)

    return roots
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_hierarchy.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add versa/core/hierarchy.py tests/test_hierarchy.py
git commit -m "feat: build section tree from column-B numbering"
```

---

## Task 4: Price status classification

**Files:**
- Create: `versa/core/status.py`
- Test: `tests/test_status.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (pure functions over primitives).
- Produces: `normalize_comment(raw: Optional[str]) -> Optional[str]`, `classify_status(unit_price_total: Optional[float], comment: Optional[str]) -> tuple[PriceStatus, tuple[int, ...]]` (status + any referenced п/п numbers), used by Task 5's parser per participant per position.

- [ ] **Step 1: Write the failing tests, using the exact real comment strings found in the sample**

```python
# tests/test_status.py
from versa.core.models import PriceStatus
from versa.core.status import classify_status, normalize_comment


def test_normalize_comment_fixes_typo_and_treats_zero_as_empty():
    assert normalize_comment("Вклучено") == "включено"
    assert normalize_comment("0") is None
    assert normalize_comment("  ") is None
    assert normalize_comment(None) is None


def test_priced_when_price_present_and_no_special_comment():
    status, refs = classify_status(unit_price_total=125000.0, comment=None)
    assert status == PriceStatus.PRICED
    assert refs == ()


def test_zero_when_price_missing_or_zero():
    assert classify_status(unit_price_total=None, comment=None)[0] == PriceStatus.ZERO
    assert classify_status(unit_price_total=0.0, comment=None)[0] == PriceStatus.ZERO


def test_placeholder_when_price_below_one_ruble():
    status, _ = classify_status(unit_price_total=0.01, comment=None)
    assert status == PriceStatus.PLACEHOLDER


def test_not_included_typo_of_typo_beats_substring_match():
    # "не Вклучено" contains "Вклучено" but must NOT be read as included
    status, refs = classify_status(unit_price_total=0.01, comment="не Вклучено")
    assert status == PriceStatus.NOT_INCLUDED
    assert refs == ()


def test_not_included_recognizes_real_world_variants():
    variants = [
        "Не считать", "Не включено в КП.", "Нет в проекте.",
        "В предложение не включено", "Не входит в стоимость",
        "не учтено, нет данных", "НЕ включено в соответствии с пояснением Заказчика.",
    ]
    for text in variants:
        status, _ = classify_status(unit_price_total=0.01, comment=text)
        assert status == PriceStatus.NOT_INCLUDED, text


def test_included_elsewhere_extracts_single_reference():
    status, refs = classify_status(unit_price_total=0.01, comment="Включено в п/п 667")
    assert status == PriceStatus.INCLUDED_ELSEWHERE
    assert refs == (667,)


def test_included_elsewhere_extracts_multiple_references():
    status, refs = classify_status(
        unit_price_total=0.01,
        comment="Включено в п/п 856, 858, 860 ,862, 864, 868, 870",
    )
    assert status == PriceStatus.INCLUDED_ELSEWHERE
    assert refs == (856, 858, 860, 862, 864, 868, 870)


def test_included_elsewhere_recognizes_uchteno_variant():
    status, refs = classify_status(unit_price_total=0.01, comment="учтено в п.288")
    assert status == PriceStatus.INCLUDED_ELSEWHERE
    assert refs == (288,)


def test_plain_included_comment_without_reference_does_not_change_status():
    # "Вклучено"/"учтено в стоимости" alone just annotate a normal price,
    # they are not a distinct status.
    status, refs = classify_status(unit_price_total=125000.0, comment="Вклучено")
    assert status == PriceStatus.PRICED
    assert refs == ()


def test_duplicate_note_without_reference_is_still_placeholder():
    status, refs = classify_status(
        unit_price_total=0.01, comment="Задвоение с позициями 225, 226, 229 и 230"
    )
    assert status == PriceStatus.PLACEHOLDER
    assert refs == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_status.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'versa.core.status'`

- [ ] **Step 3: Write `versa/core/status.py`**

```python
from __future__ import annotations

import re

from versa.core.models import PriceStatus

_NOT_INCLUDED_PATTERNS = (
    "не вклю", "не счита", "не учт", "нет в проект", "не вход",
    "в предложение не включ",
)

_INCLUDED_REF_RE = re.compile(
    r"(?:включ|учтен)\S*\s+в\s+п[./]?\s*п?\.?\s*№?\s*(?P<nums>[\d,\s]+)",
    re.IGNORECASE,
)

_PLAIN_INCLUDED_PATTERNS = ("включ", "учтено в стоимости")

_TYPO_FIXES = {"вклучено": "включено", "вклучен": "включен"}


def normalize_comment(raw) -> str | None:
    if raw is None:
        return None
    text = " ".join(str(raw).split())
    if not text or text == "0":
        return None
    lowered = text.lower()
    for typo, fix in _TYPO_FIXES.items():
        if typo in lowered:
            lowered = lowered.replace(typo, fix)
    return lowered


def classify_status(unit_price_total, comment) -> tuple[PriceStatus, tuple[int, ...]]:
    normalized = normalize_comment(comment)

    if normalized is not None:
        for pattern in _NOT_INCLUDED_PATTERNS:
            if pattern in normalized:
                return PriceStatus.NOT_INCLUDED, ()

        match = _INCLUDED_REF_RE.search(normalized)
        if match:
            nums = tuple(int(n) for n in re.findall(r"\d+", match.group("nums")))
            if nums:
                return PriceStatus.INCLUDED_ELSEWHERE, nums

    if unit_price_total is None or unit_price_total == 0:
        return PriceStatus.ZERO, ()
    if 0 < unit_price_total < 1:
        return PriceStatus.PLACEHOLDER, ()
    return PriceStatus.PRICED, ()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_status.py -v`
Expected: PASS (11 passed)

- [ ] **Step 5: Commit**

```bash
git add versa/core/status.py tests/test_status.py
git commit -m "feat: classify per-position price status from price + comment text"
```

---

## Task 5: Parser — assemble `Tender` from the workbook

**Files:**
- Create: `versa/core/parser.py`
- Test: `tests/test_parser.py`

**Interfaces:**
- Consumes: `discover_layout` (Task 2), `build_section_tree`/`RawRow` (Task 3), `classify_status`/`normalize_comment` (Task 4), `Tender`/`Section`/`Position`/`PositionPrice`/`PriceBreakdown`/`ParticipantInfo`/`BaselinePrice`/`Warning`/`WarningType`/`ComparisonMode`/`PriceStatus` (Task 1).
- Produces: `parse_tender(path: str | Path) -> Tender` — the single public entry point everything else (aggregate, compare, UI) is built on.

- [ ] **Step 1: Write the failing test against the real sample**

```python
# tests/test_parser.py
from versa.core.models import ComparisonMode, PriceStatus, WarningType


def test_header_fields(sample_tender):
    assert sample_tender.subject == '№943-ТУ "Казачий 1 оч. НС_Генподряд"'
    assert sample_tender.object_name == "Казачий 1 оч. НС"
    assert "Переулок 1-й Казачий" in sample_tender.address


def test_seven_participants_with_inn_and_accreditation(sample_tender):
    assert len(sample_tender.participants) == 7
    by_name = {p.name: p for p in sample_tender.participants}
    parallel = by_name['ООО "ПАРАЛЛЕЛЬ"']
    assert parallel.inn == "9715299145"
    assert parallel.accreditation_status == "Не аккредитован"
    rik = by_name['ООО "Р.И.К. ИНЖИНИРИНГ"']
    assert rik.accreditation_status is None


def test_mode_is_peer_because_baseline_is_empty(sample_tender):
    assert sample_tender.mode == ComparisonMode.PEER


def test_only_sections_6_and_10_survive_empty_section_pruning(sample_tender):
    top_numbers = {s.number for s in sample_tender.sections}
    assert top_numbers == {"6", "10"}


def test_221_positions_in_surviving_sections(sample_tender):
    count = sum(1 for _ in (p for s in sample_tender.sections for p in s.iter_positions()))
    assert count == 221


def test_rik_customer_total_recomputed_not_read_from_broken_formula(sample_tender):
    section_6 = next(s for s in sample_tender.sections if s.number == "6")
    position = next(p for p in section_6.iter_positions() if p.row == 228)
    rik_price = position.participant_prices["rik"]
    # file's AQ228 is #DIV/0!; we must have recomputed qty(H) * unit_price instead
    assert rik_price.total_for_customer_volume is not None
    expected = position.customer_quantity * rik_price.unit_price.total
    assert abs(rik_price.total_for_customer_volume - expected) < 0.01


def test_formula_error_produces_warning(sample_tender):
    assert any(w.type == WarningType.FORMULA_ERROR for w in sample_tender.warnings)


def test_ges_placeholder_count(sample_tender):
    placeholder_count = sum(
        1
        for section in sample_tender.iter_sections()
        for position in section.positions
        for pid, price in position.participant_prices.items()
        if pid == "ges" and price.status == PriceStatus.PLACEHOLDER
    )
    assert placeholder_count == 99
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_parser.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'versa.core.parser'`

- [ ] **Step 3: Write `versa/core/parser.py`**

```python
from __future__ import annotations

from pathlib import Path

import openpyxl

from versa.core.excel_layout import Layout, PriceCols, discover_layout
from versa.core.hierarchy import RawRow, build_section_tree
from versa.core.models import (
    BaselinePrice,
    ComparisonMode,
    ParticipantInfo,
    Position,
    PositionPrice,
    PriceBreakdown,
    PriceStatus,
    Section,
    Tender,
    Warning,
    WarningType,
)
from versa.core.status import classify_status

SHEET_NAME = "3_ ПОДРОБНАЯ"


def _num(value, row: int, col: int, warnings: list[Warning]) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        if value.startswith("#"):
            warnings.append(Warning(
                type=WarningType.FORMULA_ERROR, row=row, participant_id=None,
                message=f"Ошибка формулы {value!r} в ячейке ({row}, {col})",
            ))
            return None
        try:
            return float(value.replace(",", "."))
        except ValueError:
            return None
    return float(value)


def _read_breakdown(ws, row: int, cols: PriceCols, warnings: list[Warning]) -> PriceBreakdown:
    return PriceBreakdown(
        materials=_num(ws.cell(row=row, column=cols.materials).value, row, cols.materials, warnings),
        works=_num(ws.cell(row=row, column=cols.works).value, row, cols.works, warnings),
        overhead=_num(ws.cell(row=row, column=cols.overhead).value, row, cols.overhead, warnings),
        total=_num(ws.cell(row=row, column=cols.total).value, row, cols.total, warnings),
    )


def _read_header(ws) -> tuple[str, str, str]:
    subject = str(ws.cell(row=3, column=4).value or "").strip()
    object_name = str(ws.cell(row=4, column=4).value or "").strip()
    address = str(ws.cell(row=5, column=4).value or "").strip()
    return subject, object_name, address


def _read_participants(ws, layout: Layout) -> list[ParticipantInfo]:
    participants = []
    for block in layout.participants:
        inn = ws.cell(row=8, column=block.start_col).value
        address = ws.cell(row=9, column=block.start_col).value
        accreditation = ws.cell(row=11, column=block.start_col).value
        participants.append(ParticipantInfo(
            id=block.participant_id,
            name=block.name,
            inn=str(inn).strip() if inn is not None else None,
            address=str(address).strip() if address is not None else None,
            accreditation_status=str(accreditation).strip() if accreditation else None,
        ))
    return participants


def _read_raw_rows(ws, last_row: int) -> list[RawRow]:
    rows = []
    for r in range(14, last_row + 1):
        b = ws.cell(row=r, column=2).value
        c = ws.cell(row=r, column=3).value
        d = ws.cell(row=r, column=4).value
        rows.append(RawRow(row=r, b=b, c=c, d=d))
    return rows


def _fill_position_data(ws, position: Position, layout: Layout, warnings: list[Warning]) -> None:
    row = position.row
    position.unit = ws.cell(row=row, column=7).value
    position.customer_quantity = _num(ws.cell(row=row, column=8).value, row, 8, warnings)
    comment = ws.cell(row=row, column=6).value
    position.customer_comment = str(comment).strip() if comment else None

    baseline_unit = _read_breakdown(ws, row, layout.baseline.unit_price_cols, warnings)
    baseline_total = _read_breakdown(ws, row, layout.baseline.total_cols, warnings)
    if any(v not in (None, 0) for v in (*baseline_unit.__dict__.values(), *baseline_total.__dict__.values())):
        position.baseline = BaselinePrice(unit_price=baseline_unit, total=baseline_total)

    for block in layout.participants:
        qty = _num(ws.cell(row=row, column=block.qty_col).value, row, block.qty_col, warnings)
        unit_price = _read_breakdown(ws, row, block.unit_price_cols, warnings)
        participant_total = _read_breakdown(ws, row, block.participant_total_cols, warnings)
        comment_raw = ws.cell(row=row, column=block.participant_comment_col).value
        comment = str(comment_raw).strip() if comment_raw else None

        status, refs = classify_status(unit_price.total, comment)

        customer_total = None
        if position.customer_quantity is not None and unit_price.total is not None:
            customer_total = position.customer_quantity * unit_price.total

        volume_mismatch = (
            qty is not None
            and position.customer_quantity is not None
            and abs(qty - position.customer_quantity) > 1e-6
        )
        if volume_mismatch:
            warnings.append(Warning(
                type=WarningType.VOLUME_MISMATCH, row=row, participant_id=block.participant_id,
                message=f"У {block.name} объём {qty} отличается от объёма заказчика {position.customer_quantity}",
            ))
        if status == PriceStatus.INCLUDED_ELSEWHERE:
            warnings.append(Warning(
                type=WarningType.INCLUDED_ELSEWHERE, row=row, participant_id=block.participant_id,
                message=f"{block.name}: {comment}",
            ))
        if status == PriceStatus.PLACEHOLDER:
            warnings.append(Warning(
                type=WarningType.PLACEHOLDER, row=row, participant_id=block.participant_id,
                message=f"{block.name}: цена-заглушка {unit_price.total}",
            ))

        pct = None
        if block.pct_col is not None:
            pct = _num(ws.cell(row=row, column=block.pct_col).value, row, block.pct_col, warnings)
        expected_cost = _num(
            ws.cell(row=row, column=block.expected_cost_col).value, row, block.expected_cost_col, warnings
        )

        position.participant_prices[block.participant_id] = PositionPrice(
            status=status,
            quantity_offered=qty,
            unit_price=unit_price,
            total_for_participant_volume=participant_total,
            total_for_customer_volume=customer_total,
            participant_comment=comment,
            mrg_comment=None,
            pct_of_estimate=pct,
            expected_cost=expected_cost,
            included_in_positions=refs,
            volume_mismatch=volume_mismatch,
        )


def _prune_empty_sections(sections: list[Section]) -> list[Section]:
    kept = []
    for section in sections:
        section.children = _prune_empty_sections(section.children)
        has_price = any(
            price.status != PriceStatus.ZERO
            for position in section.iter_positions()
            for price in position.participant_prices.values()
        )
        if has_price or section.children:
            kept.append(section)
    return kept


def _flag_lump_sums(sections: list[Section], participant_ids: list[str], warnings: list[Warning]) -> None:
    for section in sections:
        positions = list(section.iter_positions())
        if len(positions) < 2:
            continue
        for pid in participant_ids:
            priced_rows = [
                p.row for p in positions
                if p.participant_prices[pid].status == PriceStatus.PRICED
            ]
            if len(priced_rows) == 1:
                only_row = priced_rows[0]
                only_position = next(p for p in positions if p.row == only_row)
                only_position.participant_prices[pid] = PositionPrice(
                    **{**only_position.participant_prices[pid].__dict__, "status": PriceStatus.LUMP_SUM}
                )
                warnings.append(Warning(
                    type=WarningType.LUMP_SUM, row=only_row, participant_id=pid,
                    message=f"Участник дал весь раздел {section.number} одной строкой (п/п {only_row})",
                ))


def parse_tender(path: str | Path) -> Tender:
    wb = openpyxl.load_workbook(str(path), data_only=True)
    ws = wb[SHEET_NAME]

    layout = discover_layout(ws)
    warnings: list[Warning] = []

    subject, object_name, address = _read_header(ws)
    participants = _read_participants(ws, layout)

    raw_rows = _read_raw_rows(ws, ws.max_row)
    sections = build_section_tree(raw_rows)

    for section in sections:
        for position in section.iter_positions():
            _fill_position_data(ws, position, layout, warnings)

    sections = _prune_empty_sections(sections)
    _flag_lump_sums(sections, [p.id for p in participants], warnings)

    has_baseline = any(
        position.baseline is not None
        for section in sections
        for position in section.iter_positions()
    )
    mode = ComparisonMode.BASELINE if has_baseline else ComparisonMode.PEER

    return Tender(
        subject=subject, object_name=object_name, address=address,
        participants=participants, sections=sections, mode=mode, warnings=warnings,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_parser.py -v`
Expected: PASS (8 passed). If `test_221_positions_in_surviving_sections` or `test_ges_placeholder_count` fail with a different number, print the actual count and diff against the section-6/10 row ranges found during inspection (225–316, 667–~900) to locate the mismatch — don't adjust the test's expected number without re-checking the sheet.

- [ ] **Step 5: Commit**

```bash
git add versa/core/parser.py tests/test_parser.py
git commit -m "feat: parse workbook into Tender with recomputed totals and warnings"
```

---

## Task 6: Bottom-up aggregation (section and grand totals, both volume bases)

**Files:**
- Create: `versa/core/aggregate.py`
- Test: `tests/test_aggregate.py`

**Interfaces:**
- Consumes: `Tender`/`Section`/`Position`/`PriceStatus` (Task 1), the parsed `sample_tender` fixture (Task 5).
- Produces: `SectionTotals` dataclass (`by_customer_volume: dict[str, float]`, `by_participant_volume: dict[str, float]` — participant_id → rubles, summing **all** statuses, zeros included), `section_totals(section: Section) -> SectionTotals` (recursive, bottom-up), `grand_totals(tender: Tender) -> SectionTotals` (sum of top-level sections).

- [ ] **Step 1: Write the failing test, including the control sums from the task brief**

```python
# tests/test_aggregate.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_aggregate.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'versa.core.aggregate'`

- [ ] **Step 3: Write `versa/core/aggregate.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_aggregate.py -v`
Expected: PASS (8 passed: 7 parametrized + 1). If a control sum is off by more than the `abs=0.1` (100k ₽) tolerance, print `totals_6.by_participant_volume` and `totals_10.by_participant_volume` for the failing participant and compare against a manual `SUMIF` in Excel on that participant's "Стоимость всего" (participant-volume) column filtered to that section's rows — the likely cause is a layout-discovery column off-by-one (Task 2), not this task.

- [ ] **Step 5: Commit**

```bash
git add versa/core/aggregate.py tests/test_aggregate.py
git commit -m "feat: recompute section and grand totals bottom-up from positions"
```

---

## Task 7: Comparison engine (Mode А / Mode Б, min/max/median/mean, deviations)

**Files:**
- Create: `versa/core/compare.py`
- Test: `tests/test_compare.py`

**Interfaces:**
- Consumes: `Tender`, `Section`, `Position`, `PriceStatus`, `ComparisonMode` (Task 1); `section_totals`/`grand_totals`/`SectionTotals` (Task 6).
- Produces: `PositionComparison` (`values: dict[str, float]`, `min`, `max`, `median`, `mean`, `deviation_from_min: dict[str, float]`, `deviation_from_min_pct: dict[str, float]`, `deviation_from_median: dict[str, float]`, `baseline_deviation: Optional[dict[str, float]]`), `SectionComparison` (same shape but over `SectionTotals`, always over the full sum — no status filtering), `compare_position(position, participant_ids, mode) -> PositionComparison`, `compare_section(section, participant_ids, mode) -> SectionComparison`, `compare_tender(tender: Tender) -> dict` (top-level totals per participant + `mode` + `warnings`, ready for the UI to consume directly).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_compare.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_compare.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'versa.core.compare'`

- [ ] **Step 3: Write `versa/core/compare.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_compare.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add versa/core/compare.py tests/test_compare.py
git commit -m "feat: add comparison engine for positions/sections/tender totals"
```

---

## Task 8: `core` purity guard + full test-suite run

**Files:**
- Create: `tests/test_core_purity.py`

**Interfaces:**
- Consumes: nothing new; this is a repo-hygiene check.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_core_purity.py
from pathlib import Path


def test_core_package_never_imports_streamlit():
    core_dir = Path(__file__).resolve().parents[1] / "versa" / "core"
    offenders = []
    for path in core_dir.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "streamlit" in text:
            offenders.append(str(path))
    assert offenders == [], f"streamlit referenced in core: {offenders}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_core_purity.py -v`
Expected: PASS already, actually — there is no streamlit reference yet, so this step's "failure" is confirming the assertion logic itself works. Temporarily add the word `streamlit` to a throwaway comment in `versa/core/compare.py`, rerun to see it FAIL, then remove the comment.

- [ ] **Step 3: No implementation needed** (test targets existing code)

- [ ] **Step 4: Run the entire test suite**

Run: `pytest -v`
Expected: all tests across Tasks 1–8 PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_core_purity.py
git commit -m "test: guard core package against streamlit imports"
```

---

## Task 9: Streamlit UI — upload, header, summary bars, warnings

**Files:**
- Create: `versa/ui/app.py`
- Create: `versa/ui/formatting.py`

**Interfaces:**
- Consumes: `parse_tender` (Task 5), `compare_tender`/`compare_section` (Task 7), `Tender`/`ComparisonMode` (Task 1).
- Produces: `versa/ui/formatting.py::to_millions(value: float | None) -> str` (1 decimal, `"—"` for `None`); a runnable `streamlit run versa/ui/app.py` page.

- [ ] **Step 1: Write `versa/ui/formatting.py`**

```python
from __future__ import annotations


def to_millions(value: float | None, decimals: int = 1) -> str:
    if value is None:
        return "—"
    return f"{value / 1_000_000:.{decimals}f}"


def to_rubles(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.0f}".replace(",", " ")
```

- [ ] **Step 2: Write `versa/ui/app.py`**

```python
from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from versa.core.compare import compare_tender
from versa.core.models import ComparisonMode
from versa.core.parser import parse_tender
from versa.ui.formatting import to_millions

st.set_page_config(page_title="Versa — сравнение КП", layout="wide")
st.title("Versa — сравнение коммерческих предложений")

uploaded = st.file_uploader("Загрузите сводную таблицу (.xlsx)", type=["xlsx"])
if uploaded is None:
    st.info("Загрузите файл, чтобы увидеть сравнение.")
    st.stop()

with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
    tmp.write(uploaded.getbuffer())
    tmp_path = Path(tmp.name)

tender = parse_tender(tmp_path)
comparison = compare_tender(tender)

st.header(tender.subject)
st.subheader(tender.object_name)
st.caption(tender.address)

st.markdown("### Участники")
for participant in tender.participants:
    st.write(
        f"**{participant.name}** · ИНН {participant.inn or '—'} · "
        f"{participant.accreditation_status or 'статус не указан'}"
    )

mode_label = "А (сравнение с расчётной стоимостью)" if tender.mode == ComparisonMode.BASELINE else "Б (сравнение участников между собой)"
mode_choice = st.radio(
    "Режим сравнения", options=["Авто", "А", "Б"], horizontal=True,
    help=f"Определён автоматически: режим {mode_label}",
)
effective_mode = tender.mode if mode_choice == "Авто" else (
    ComparisonMode.BASELINE if mode_choice == "А" else ComparisonMode.PEER
)

st.markdown("### Итоги по участникам (за объёмы заказчика)")
totals = comparison["totals_by_customer_volume"]
ranked = sorted(totals.items(), key=lambda kv: kv[1])
best = ranked[0][1] if ranked else None
for pid, value in ranked:
    name = tender.participant_by_id(pid).name
    deviation = f"+{(value - best) / best * 100:.1f}% от лучшего" if best else ""
    st.write(f"{name}: **{to_millions(value)} млн ₽** {deviation}")

st.markdown("### Предупреждения")
if not tender.warnings:
    st.success("Предупреждений нет")
for warning in tender.warnings[:200]:
    participant_name = (
        tender.participant_by_id(warning.participant_id).name
        if warning.participant_id else "—"
    )
    st.warning(f"[{warning.type.value}] строка {warning.row}, {participant_name}: {warning.message}")
```

- [ ] **Step 3: Run the app and confirm it renders against the real sample**

Run: `streamlit run versa/ui/app.py`
Then in the browser: upload `samples/943-ТУ__Сводная_Казачий_НС_-_фасады_и_ВИС.xlsx`.
Expected: header shows "№943-ТУ ...", 7 participants listed with ИНН, mode shows "Б", summary bars show 7 participants sorted ascending, warnings list is non-empty (formula errors, placeholders, lump_sum, included_elsewhere).

- [ ] **Step 4: Commit**

```bash
git add versa/ui/app.py versa/ui/formatting.py
git commit -m "feat: minimal streamlit page for upload/header/summary/warnings"
```

---

## Task 10: Streamlit UI — sections table, waterfall, heatmap

**Files:**
- Modify: `versa/ui/app.py`
- Create: `versa/ui/charts.py`

**Interfaces:**
- Consumes: `compare_section` (Task 7), `Section.iter_sections()` (Task 1), plotly.
- Produces: `versa/ui/charts.py::waterfall_by_section(tender, participant_id) -> plotly.graph_objects.Figure`, `waterfall_diff(tender, participant_a, participant_b) -> Figure`, `deviation_heatmap(tender, participant_ids) -> Figure`; appended sections to `app.py`.

- [ ] **Step 1: Write `versa/ui/charts.py`**

```python
from __future__ import annotations

import plotly.graph_objects as go

from versa.core.aggregate import section_totals
from versa.core.models import ComparisonMode, Tender


def _top_level_section_values(tender: Tender, participant_id: str) -> dict[str, float]:
    return {
        section.number: section_totals(section).by_customer_volume.get(participant_id, 0.0)
        for section in tender.sections
    }


def waterfall_by_section(tender: Tender, participant_id: str) -> go.Figure:
    values = _top_level_section_values(tender, participant_id)
    labels = list(values.keys()) + ["Итого"]
    measures = ["relative"] * len(values) + ["total"]
    amounts = list(values.values()) + [sum(values.values())]
    fig = go.Figure(go.Waterfall(x=labels, measure=measures, y=amounts))
    fig.update_layout(title=f"Состав итога: {participant_id}")
    return fig


def waterfall_diff(tender: Tender, participant_a: str, participant_b: str) -> go.Figure:
    values_a = _top_level_section_values(tender, participant_a)
    values_b = _top_level_section_values(tender, participant_b)
    labels = list(values_a.keys()) + ["Итого"]
    diffs = [values_a[k] - values_b[k] for k in values_a] 
    diffs.append(sum(diffs))
    fig = go.Figure(go.Waterfall(
        x=labels, measure=["relative"] * (len(labels) - 1) + ["total"], y=diffs
    ))
    fig.update_layout(title=f"Разница по разделам: {participant_a} − {participant_b}")
    return fig


def deviation_heatmap(tender: Tender, participant_ids: list[str]) -> go.Figure:
    section_numbers = [s.number for s in tender.sections]
    z = []
    for pid in participant_ids:
        row = []
        for section in tender.sections:
            totals = section_totals(section).by_customer_volume
            values = [totals.get(p, 0.0) for p in participant_ids if totals.get(p, 0.0)]
            median = sorted(values)[len(values) // 2] if values else 0.0
            value = totals.get(pid, 0.0)
            pct = ((value - median) / median * 100) if median else 0.0
            row.append(pct)
        z.append(row)
    fig = go.Figure(go.Heatmap(z=z, x=section_numbers, y=participant_ids, colorscale="RdYlGn_r"))
    fig.update_layout(title="Отклонение от медианы по разделам, %")
    return fig
```

- [ ] **Step 2: Append the sections table and charts to `versa/ui/app.py`**

```python
# append to versa/ui/app.py
import plotly.graph_objects as go

from versa.core.compare import compare_section
from versa.ui.charts import deviation_heatmap, waterfall_by_section, waterfall_diff

participant_ids = [p.id for p in tender.participants]

st.markdown("### Разделы")
for section in tender.sections:
    result = compare_section(section, participant_ids, effective_mode)
    cols = st.columns(len(participant_ids) + 1)
    cols[0].write(f"**{section.number}. {section.title}**")
    for i, pid in enumerate(participant_ids, start=1):
        value = result.values.get(pid, 0.0)
        is_min = result.min is not None and value == result.min
        is_max = result.max is not None and value == result.max
        style = "background-color: #d4f7d4" if is_min else ("background-color: #f7d4d4" if is_max else "")
        cols[i].markdown(
            f"<div style='{style}'>{tender.participant_by_id(pid).name}<br>{to_millions(value)}</div>",
            unsafe_allow_html=True,
        )

st.markdown("### Водопад по разделам")
selected_participant = st.selectbox("Участник", options=participant_ids,
                                     format_func=lambda pid: tender.participant_by_id(pid).name)
st.plotly_chart(waterfall_by_section(tender, selected_participant), use_container_width=True)

st.markdown("### Разница между двумя участниками")
col_a, col_b = st.columns(2)
participant_a = col_a.selectbox("Участник A", options=participant_ids,
                                 format_func=lambda pid: tender.participant_by_id(pid).name, key="pa")
participant_b = col_b.selectbox("Участник Б", options=participant_ids,
                                 format_func=lambda pid: tender.participant_by_id(pid).name, key="pb")
st.plotly_chart(waterfall_diff(tender, participant_a, participant_b), use_container_width=True)

st.markdown("### Тепловая карта отклонений от медианы")
st.plotly_chart(deviation_heatmap(tender, participant_ids), use_container_width=True)
```

- [ ] **Step 3: Run the app and manually verify against the sample**

Run: `streamlit run versa/ui/app.py`, upload the sample file.
Expected: sections table shows rows "6. Фасадные работы" and "10. Инженерные системы" only, with green/red highlighting on min/max per row; waterfall renders per selected participant; diff waterfall renders for any pair; heatmap shows a 7×2 grid of % deviations.

- [ ] **Step 4: Commit**

```bash
git add versa/ui/app.py versa/ui/charts.py
git commit -m "feat: add sections table, waterfalls and deviation heatmap to UI"
```

---

## Task 11: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`**

```markdown
# Versa

Сравнение коммерческих предложений подрядчиков на тендерах в строительстве.

## Установка

\`\`\`bash
pip install -e ".[dev]"
\`\`\`

## Запуск интерфейса

\`\`\`bash
streamlit run versa/ui/app.py
\`\`\`

Загрузите файл сводной таблицы (.xlsx, лист «3\_ ПОДРОБНАЯ»).

## Тесты

\`\`\`bash
pytest -v
\`\`\`

## Что показалось странным/неоднозначным в образце

- У «Р.И.К. ИНЖИНИРИНГ» формула «Стоимость всего за объёмы заказчика» (`AQ`)
  сломана почти на всех строках (`#DIV/0!`, ~385 из 1650) — судя по всему,
  это протянутая вниз формула `=AD*AL` вместо `=H*AL`. Мы её не читаем и
  всегда пересчитываем сами.
- Заглушки «включено» — не всегда 0.01 ₽: встречаются и просто пустые ячейки
  с текстовым комментарием без числа. Статус определяется по совокупности
  цены и комментария, а не по одному правилу.
- Комментарии написаны свободным текстом с опечатками («Вклучено», а также
  «не Вклучено» — отрицание той же опечатки), без единого словаря
  формулировок. Список подстрок в `status.py` — не исчерпывающий, на новых
  тендерах его почти наверняка придётся расширять.
- Ссылки «включено в п/п NNN» иногда содержат несколько номеров через
  запятую с непоследовательными пробелами («856, 858, 860 ,862»).
- Нумерация раздела в столбце B и его название в столбце C иногда расходятся
  (раздел с номером 6.8 назван «6.10. ...») — судя по всему, разделы
  переносили/перенумеровывали, а текст не обновили.
- Шаблон рассчитан на весь объект целиком (разделы 1–10+), но в конкретном
  тендере заполнены только «Фасадные работы» и часть «Инженерных систем» —
  то есть один и тот же файл может представлять очень разную долю проекта в
  разных тендерах, и «итог по всем разделам» не значит «итог по всему
  зданию».
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README with run instructions and data caveats"
```
