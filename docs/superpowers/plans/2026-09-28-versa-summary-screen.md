# Versa — «Сводная по смете» главный экран Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new default-first screen, «Сводная по смете», that renders the смета in its
original row order with one column per participant, full min/max highlighting, per-status
badges, tooltips, expandable hierarchy, and a rubles/VAT-aware totals block — without
touching the existing waterfall/heatmap/summary-bars screen, which moves to a second tab
called «Аналитика».

**Architecture:** All computation (which rows to show at a given detail level, per-cell
values/statuses/highlights/tooltips, VAT split, best-offer picks) lives in a new
`versa/core/summary.py`, exposing one entry point,
`build_summary_table(tender, *, detail_level, expanded_sections, hide_unfilled, money_unit, vat_rate) -> SummaryTable`.
`versa/ui` renders that structure and nothing else — no arithmetic, no status logic, no
highlighting decisions in `versa/ui`. The table itself is a hand-built HTML/CSS block (not
`st.dataframe`/streamlit-aggrid — see the Decisions section below for why), shown via
`st.components.v1.html`.

**Tech Stack:** Same as the rest of the project — Python 3.11+, pandas/openpyxl (already
used by `core`), pytest. No new dependency is added.

**Spec:** The requirements are given verbatim in conversation (no separate spec file);
this plan's "Verified facts" section below is the record of what was checked against the
real sample file, `samples/943-ТУ__Сводная_Казачий_НС_-_фасады_и_ВИС.xlsx`.

## Decisions made before writing this plan (per the user's explicit request to justify them)

**Table implementation: hand-built HTML/CSS (option б), not streamlit-aggrid (option а).**
Reasons:
1. No new dependency — the project's dependency list (pandas, openpyxl, plotly,
   streamlit, pytest) was set deliberately at kickoff; aggrid would add a JS custom
   component wrapping ag-grid community edition.
2. The spec's per-cell rules (exact colors `#C6EFCE`/`#FFC7CE`, exact badge text `≈0`,
   `вкл. в п/п NNN`, `не вкл.`, `паушал`, exact tooltip content) are much easier to hit
   exactly with a template we fully control than with aggrid's `cellStyle`/
   `tooltipValueGetter` JS-code-as-Python-string configuration.
3. Testability: a plain Python function that returns an HTML string can be tested with
   ordinary `assert "background-color:#C6EFCE" in html` string checks — no browser, no
   custom-component test harness. aggrid's JS callbacks cannot be unit-tested this way.
4. Sticky header + sticky left columns + a collapsible tree are all achievable with plain
   CSS (`position: sticky`, `:has()` for the expand/collapse toggle — see Task 4) on any
   evergreen Chromium/Edge/Firefox, which is what an internal corporate tool runs on.

**Per-row "expand only this section" control is implemented as a small native Streamlit
checkbox list above the table (inside `st.expander("Раскрыть отдельные разделы")`), not as
a clickable glyph glued to the sticky "№ раздела" cell.** Reason: `st.components.v1.html`
renders in an isolated iframe — a native Streamlit widget cannot live inside one of its
`<td>` cells and still trigger a Python-side rerun. A pure-CSS checkbox-in-the-cell trick
would need every row down to leaf positions to always be present in the DOM (just hidden),
which for the full template (~1600 rows across 18 sections, most of them unfilled) would
mean shipping a multi-megabyte HTML blob on every page load even at the default "Разделы"
level. Instead, the sidebar's detail-level control genuinely limits how many rows are
generated (matching "только первый уровень, как в смете" literally), and the per-section
checkboxes below the sidebar ask `build_summary_table` to include just that one section's
subtree at full depth on top of the base level. This is flagged here, not decided silently,
because it changes where the interaction physically lives from what the prose describes.

## Verified facts about the sample file (checked directly, not assumed)

- Column B section-code detection must require an actual dotted-numeric pattern
  (`^\d+(\.\d+)*\.?$`). Rows 1608–1644 are a **separate commercial-terms questionnaire**
  block (`B` = free text like `"Аванс"`, `"Гарантия на работы, месяц/год"`,
  `"Резюме команды проекта"`, column A restarting from 1) that the current hierarchy
  builder wrongly turns into 26 bogus top-level "sections" because it treats any non-blank
  `B` as a section number. This must be excluded — it isn't смета data at all.
- Row 14 (`B="1"`, `C=None`, `D="Лот №1 - Казачий 1 оч. НС_Генподряд"`) and row 15
  (`B="1"`, first real section) share the same B-number. The existing stack-based
  hierarchy builder already produces the right shape for this by accident (the lot row
  closes itself the instant the next same-level row arrives, so it comes out as its own
  parentless, childless top-level entry) — `build_summary_table` treats `full_sections[0]`
  as the lot row and `full_sections[1:]` as the 18 real sections, and must special-case
  the lot row's cell values to equal the grand total (see below), since it has no
  descendant positions of its own to sum.
- All 18 top-level section titles were read directly and match the user's illustrative
  list by content (several have the already-known B-vs-C numbering drift, e.g. section 11
  is titled `"12. Благоустройство, дороги"` in column C, section 16 is titled
  `"20. MR - SHELL & CORE"`) — hierarchy always follows B, title always follows C with a
  D fallback, unchanged from stage 1.
- Only sections **6, 10, 18** are filled (have any `PRICED`/`LUMP_SUM` position anywhere
  in their subtree, or a baseline) in this sample; sections **1–5, 7–9, 11–17** (15
  sections) are unfilled. The user's own message listed section 18 as unfilled too — that
  was a mistake carried over from before section 18 was discovered in stage 1. **Per the
  user's explicit answer to a clarifying question this session, section 18 is now treated
  as filled everywhere on this screen** (its own row, the ИТОГО sums, and the
  "лучших по разделам" tally).
- Exact grand totals (за объёмы заказчика, all 18 sections), full float precision:
  `parallel=2 781 947 710.2209`, `rik=3 264 855 729.3082`, `rutek=3 479 209 235.0983`,
  `buro_konstrakshn=3 601 746 723.8617`, `ges=3 971 223 755.9214`,
  `erbek=4 211 309 871.0962`, `fodd=4 489 294 827.7035`. Min = parallel (~2781.9 млн),
  max = fodd (~4489.3 млн) — **not** the ~2623.1/~4336.0 млн in the user's message (those
  were section 6+10 only, without section 18; superseded per their answer above).
- "Лучших предложений по разделам" (full sums, section 18 included): `parallel: 1`
  (section 10), `rik: 1` (section 6), `erbek: 1` (section 18) — **not** just
  parallel/rik as in the user's message. Verified why erbek "wins" section 18: row 1603
  ("Рабочая документация, корректировка") has `customer_quantity=1.0` but erbek/ges both
  offered `quantity_offered=20606.16` — a huge, already-flagged `volume_mismatch` — and
  erbek additionally marked 3 of that section's 5 positions `NOT_INCLUDED` (declined to
  price them), so their nominal section-18 sum is a mere 4 500 ₽ against 29–207 million ₽
  for everyone who actually priced it. This is a real, if narrow, gap in the spec's ⚠
  rule (⚠ only covers паушал/заглушки/включено-в-другую, not "opted out of most of the
  section") — flagged here, not silently patched, since the user only asked to check the
  customer-vs-participant-volume tolerance, not to change the full-sum comparison rule.
- **Customer-volume vs participant-volume tolerance, as requested:** for
  parallel/rik/rutek/buro_konstrakshn/fodd the two grand totals differ by at most **1
  kopeck** (floating-point noise from 0.01 ₽ placeholder prices) — matches the user's
  "на копейки" expectation. For **ges** and **erbek** the difference is **not** a
  rounding artifact: **≈168 412 978 ₽** (ges) and **≈92 723 219 ₽** (erbek), both driven
  entirely by the same row 1603/1604 volume mismatch described above (customer wants
  `qty=1`, ges/erbek quoted a price meant for `qty≈20 606`). Both are already surfaced by
  the existing `volume_mismatch` warning; this plan doesn't change that, just confirms
  the size of the effect the user asked about.
- VAT rate text is only present in participant column headers
  (`"Цена за ед. изм., RUB, ОСН, с учетом НДС 22%"`, row 12); the расчётная стоимость
  header has no `%` (`"...с учетом НДС"` only). Extraction must scan all row-12 headers
  for a `НДС\s*(\d+(?:[.,]\d+)?)\s*%` pattern and default to 22 if none is found (this
  sample has no расчётная стоимость, so the baseline header never carries the rate here,
  but a future tender's might).

## Global Constraints

- No new runtime dependency; `versa/ui` performs no computation, only formatting/layout.
- `Tender.sections` (pruned, used by the existing Analytics tab and its tests) must keep
  its exact current meaning and must not be mutated by anything this plan adds — the new
  `Tender.full_sections` is a second, independent, unpruned tree.
- Section-number detection (`^\d+(\.\d+)*\.?$`) applies everywhere `build_section_tree` is
  used — the commercial-terms block must never appear as a section, in either tree.
- Money values inside `SummaryTable`/`SummaryCell` are always raw rubles (`float`); unit
  conversion (`руб.`/`тыс. руб.`/`млн руб.`) and locale formatting (space thousands
  separator, comma decimal point) happen only in `versa/ui`.
- Position-level min/max/best-offer only considers `PRICED` status (existing rule,
  reused via `versa.core.compare`); section/lot/total-level comparisons use full sums
  with no status filtering (existing rule, reused via `versa.core.aggregate`).
- A row's cells get no highlight at all when fewer than 2 participants have a comparable
  value at that row's comparison granularity (existing rule from `compare.py`, reused).

## Review Focus

- The commercial-terms block (rows 1608–1644) must never leak into either section tree as
  bogus sections — pinned by a hierarchy test with the real section-code regex.
- The lot row (row 14) must show the grand total, not zero, even though it has no
  descendant positions of its own — pinned in `build_summary_table`'s test.
- `hide_unfilled` must default to **showing** unfilled sections greyed out with `—` in
  every participant cell (not hiding them) — the spec is explicit that structure integrity
  matters more than compactness by default; only the sidebar checkbox hides them.
- `detail_level="Разделы"` must still let `expanded_sections` pull in a deeper subtree for
  one specific section without promoting every other section too — pinned by a
  `build_summary_table` test that expands section 6 while `detail_level` stays at the
  top level and checks section 10 still has no visible children.
- НДС/без-НДС totals must reconcile to the penny with the ИТОГО-with-VAT row for every
  participant (`total == excl_vat + vat`), not just look approximately right — pinned by
  an exact-arithmetic test, not an `abs=...` tolerance one.
- The "Расчётная стоимость" column (first, separate background, only when
  `tender.mode == BASELINE`) has no real sample to validate full Mode-А math against —
  this plan deliberately renders the column and its raw value when present, without
  computing a validated deviation number for it (see the self-review note at the end).
  This is a real, acknowledged gap, not silently dropped: Task 4 adds a synthetic-data
  test proving the column at least appears; Task 3's `baseline_total` stays hardcoded
  `None` until a real Mode-А sample exists to TDD the actual deviation math against.

---

## Task 1: Full section tree, non-destructive pruning, numeric-only section codes

**Files:**
- Modify: `versa/core/hierarchy.py`
- Modify: `versa/core/parser.py`
- Modify: `versa/core/models.py`
- Test: `tests/test_hierarchy.py`, `tests/test_parser.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `Tender.full_sections: list[Section]` (unpruned — all 18 real top-level
  sections plus the lot row, none dropped for being empty); `Tender.sections` keeps its
  existing (pruned) meaning and existing tests must keep passing unchanged.

- [ ] **Step 1: Write the failing hierarchy test for the numeric-code filter**

```python
# append to tests/test_hierarchy.py
def test_non_numeric_b_value_is_not_treated_as_a_section():
    rows = [
        RawRow(row=225, a=211, b="6", c="6. Фасадные работы", d="Устройство фасадов"),
        RawRow(row=1608, a=1, b="Аванс", c=None, d=None),
        RawRow(row=1609, a=2, b="Гарантия на работы, месяц/год", c=None, d=None),
    ]

    tree = build_section_tree(rows)

    assert [s.number for s in tree] == ["6"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_hierarchy.py::test_non_numeric_b_value_is_not_treated_as_a_section -v`
Expected: FAIL — `assert ['6', 'Аванс', 'Гарантия на работы, месяц/год'] == ['6']`

- [ ] **Step 3: Add the numeric-code guard in `versa/core/hierarchy.py`**

```python
import re

_SECTION_NUMBER_RE = re.compile(r"^\d+(\.\d+)*\.?$")


def _is_section_number(value: Optional[str]) -> bool:
    if _is_blank(value):
        return False
    return bool(_SECTION_NUMBER_RE.match(str(value).strip()))
```

Change the branch condition in `build_section_tree` from `if not _is_blank(raw.b):` to
`if _is_section_number(raw.b):`, and the position branch's guard from
`elif not _is_blank(raw.d):` to also skip rows where `raw.b` is non-blank but not a
section number (they are neither a section nor a position — e.g. row 1608's `d` is also
`None` in the real file, so the existing `elif not _is_blank(raw.d)` already skips it; the
test above pins this explicitly so a future template with text in `D` on such a row can't
silently start attaching it as a position under whatever section happens to be open).

```python
def build_section_tree(rows: list[RawRow]) -> list[Section]:
    roots: list[Section] = []
    stack: list[Section] = []

    for raw in rows:
        if _is_section_number(raw.b):
            ...  # unchanged body
        elif _is_blank(raw.b) and not _is_blank(raw.d):
            ...  # unchanged position body
        # else: neither a valid section header nor a position row — skip entirely
    return roots
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_hierarchy.py -v`
Expected: all hierarchy tests PASS (5 passed).

- [ ] **Step 5: Write the failing parser test for the full/pruned tree split**

```python
# append to tests/test_parser.py
def test_full_sections_includes_all_18_real_sections_plus_lot(sample_tender):
    numbers = [s.number for s in sample_tender.full_sections]
    assert len(numbers) == 19  # lot row + 18 real top-level sections
    assert numbers.count("1") == 2  # the lot row and section "1" share a B-number


def test_full_sections_excludes_the_commercial_terms_block(sample_tender):
    names = {s.title for s in sample_tender.full_sections if s.title}
    assert "Аванс" not in names
    assert not any(s.number == "Аванс" for s in sample_tender.full_sections)


def test_pruned_sections_are_unaffected_by_full_sections_existing(sample_tender):
    # exact same assertion as the existing stage-1 test — full_sections must not
    # change what Tender.sections means
    top_numbers = {s.number for s in sample_tender.sections}
    assert top_numbers == {"6", "10", "18"}
```

- [ ] **Step 6: Run test to verify it fails**

Run: `pytest tests/test_parser.py::test_full_sections_includes_all_18_real_sections_plus_lot -v`
Expected: FAIL — `AttributeError: 'Tender' object has no attribute 'full_sections'`

- [ ] **Step 7: Add `full_sections` to `Tender` in `versa/core/models.py`**

```python
@dataclass
class Tender:
    subject: str
    object_name: str
    address: str
    participants: list[ParticipantInfo]
    sections: list[Section]
    full_sections: list[Section]
    mode: ComparisonMode
    warnings: list[Warning]
```
(add the field between `sections` and `mode`; update the two existing test call sites in
`tests/test_models.py` that construct a bare `Tender(...)` to pass `full_sections=[]`
alongside `sections=[]`.)

- [ ] **Step 8: Make `_prune_empty_sections` non-mutating in `versa/core/parser.py`**

```python
from dataclasses import replace

def _prune_empty_sections(sections: list[Section]) -> list[Section]:
    kept = []
    for section in sections:
        pruned_children = _prune_empty_sections(section.children)
        has_price = any(
            price.status in _ACTUALLY_PRICED or position.baseline is not None
            for position in section.iter_positions()
            for price in position.participant_prices.values()
        )
        if has_price or pruned_children:
            kept.append(replace(section, children=pruned_children))
    return kept
```

(This replaces the old in-place-mutating version. `positions` is intentionally left
shared between the full tree and the pruned copy — nothing mutates a `Position` after this
point except `_flag_lump_sums`, which must now run on `full_sections` — see next step.)

- [ ] **Step 9: Wire `full_sections` into `parse_tender`**

```python
    sections = build_section_tree(raw_rows)   # full tree: lot + 18 sections

    for section in sections:
        for position in section.iter_positions():
            _fill_position_data(ws, position, layout, warnings)

    full_sections = sections
    _flag_lump_sums(full_sections, [p.id for p in participants], warnings)

    pruned_sections = _prune_empty_sections(full_sections)

    has_baseline = any(
        position.baseline is not None
        for section in pruned_sections
        for position in section.iter_positions()
    )
    mode = ComparisonMode.BASELINE if has_baseline else ComparisonMode.PEER

    return Tender(
        subject=subject, object_name=object_name, address=address,
        participants=participants, sections=pruned_sections, full_sections=full_sections,
        mode=mode, warnings=warnings,
    )
```

- [ ] **Step 10: Run test to verify it passes**

Run: `pytest tests/test_parser.py tests/test_models.py -v`
Expected: all PASS, including the 3 new tests from Step 5.

- [ ] **Step 11: Run the full suite to confirm the refactor changed nothing observable**

Run: `pytest -v`
Expected: 50 passed (same count as before this task — `full_sections` is purely additive).

- [ ] **Step 12: Commit**

```bash
git add versa/core/hierarchy.py versa/core/parser.py versa/core/models.py tests/test_hierarchy.py tests/test_parser.py tests/test_models.py
git commit -m "feat: expose full unpruned section tree, reject non-numeric section codes"
```

---

## Task 2: VAT-rate extraction

**Files:**
- Modify: `versa/core/excel_layout.py`
- Test: `tests/test_excel_layout.py`

**Interfaces:**
- Produces: `discover_vat_rate(ws, default: float = 22.0) -> float`, called once by
  `parse_tender` and stored — but since `Tender` already has no natural "settings" slot
  and the sidebar must let the user **override** it, the parsed rate is exposed as
  `Layout.vat_rate: float` (discovered at parse time) and threaded through to
  `build_summary_table`'s `vat_rate` parameter, which the UI defaults from
  `tender` metadata but the user can change. To avoid re-plumbing `Tender`, expose it as
  `Tender.default_vat_rate: float` (Task 1's `models.py` edit is amended here rather than
  reopening Task 1 wholesale — see Step 4).

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_excel_layout.py
from versa.core.excel_layout import discover_vat_rate


def test_discovers_vat_rate_from_participant_header(sample_path):
    wb = openpyxl.load_workbook(sample_path, data_only=True)
    ws = wb["3_ ПОДРОБНАЯ"]

    assert discover_vat_rate(ws) == 22.0


def test_vat_rate_defaults_when_not_found():
    class FakeCell:
        value = None

    class FakeWs:
        max_row = 13
        max_column = 5

        def cell(self, row, column):
            return FakeCell()

    assert discover_vat_rate(FakeWs()) == 22.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_excel_layout.py -k vat_rate -v`
Expected: FAIL — `ImportError: cannot import name 'discover_vat_rate'`

- [ ] **Step 3: Implement in `versa/core/excel_layout.py`**

```python
import re

_VAT_RATE_RE = re.compile(r"НДС\s*(\d+(?:[.,]\d+)?)\s*%")


def discover_vat_rate(ws, default: float = 22.0) -> float:
    for row in (HEADER_ROW_1, HEADER_ROW_2):
        for col in range(1, ws.max_column + 1):
            text = _norm(ws.cell(row=row, column=col).value)
            match = _VAT_RATE_RE.search(text)
            if match:
                return float(match.group(1).replace(",", "."))
    return default
```

- [ ] **Step 4: Run test to verify it passes, then thread it into `Tender`**

Run: `pytest tests/test_excel_layout.py -v`
Expected: PASS.

Add `default_vat_rate: float` to `Tender` in `versa/core/models.py` (after
`full_sections`); in `parse_tender`, compute
`default_vat_rate = discover_vat_rate(ws)` right after `layout = discover_layout(ws)` and
pass it into the returned `Tender(...)`. Update the two `Tender(...)` construction sites
in `tests/test_models.py` to pass `default_vat_rate=22.0`.

- [ ] **Step 5: Add a parser-level test and run the full suite**

```python
# append to tests/test_parser.py
def test_default_vat_rate_is_22_percent(sample_tender):
    assert sample_tender.default_vat_rate == 22.0
```

Run: `pytest -v`
Expected: all pass (55 total: 50 + 3 from Task 1 + 2 from this task).

- [ ] **Step 6: Commit**

```bash
git add versa/core/excel_layout.py versa/core/models.py versa/core/parser.py tests/test_excel_layout.py tests/test_parser.py tests/test_models.py
git commit -m "feat: discover VAT rate from column headers, expose on Tender"
```

---

## Task 3: `versa/core/summary.py` — data model and `build_summary_table`

**Files:**
- Create: `versa/core/summary.py`
- Test: `tests/test_summary.py`

**Interfaces:**
- Consumes: `Tender`, `Section`, `Position`, `PriceStatus`, `ComparisonMode` (models.py);
  `section_totals`/`SectionTotals` (aggregate.py); `Comparison`/`compare_position`/
  `compare_section` (compare.py).
- Produces: `DetailLevel` (Enum: `SECTIONS`, `SUBSECTIONS`, `POSITIONS`),
  `ParticipantColumnMeta`, `SummaryCell`, `BestOffer`, `SummaryRow`, `SummaryTable`,
  `build_summary_table(tender, *, detail_level=DetailLevel.SECTIONS, expanded_sections=frozenset(), hide_unfilled=False, vat_rate=None) -> SummaryTable`.
  This is the only function `versa/ui` calls for this screen.

- [ ] **Step 1: Write the failing tests (the bulk of this task's verification)**

```python
# tests/test_summary.py
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


def test_position_tooltip_includes_price_breakdown_and_comment(sample_tender):
    table = build_summary_table(sample_tender, detail_level=DetailLevel.POSITIONS)
    position_rows = {row.row: row for row in table.rows if row.kind == "position"}
    cell = position_rows[228].cells["parallel"]

    assert "материал" in cell.tooltip.lower()
    assert "смр" in cell.tooltip.lower()
    assert "1061.86" in cell.tooltip or "1 061.86" in cell.tooltip


def test_position_with_fewer_than_two_priced_participants_has_no_highlight(sample_tender):
    table = build_summary_table(sample_tender, detail_level=DetailLevel.POSITIONS)
    position_rows = {row.row: row for row in table.rows if row.kind == "position"}
    # row 670 (ФОДД lump_sum, the section's only PRICED row) — only one PRICED
    # participant, so no min/max highlight at position level
    row_670 = position_rows[670]
    assert all(cell.highlight is None for cell in row_670.cells.values())


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_summary.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'versa.core.summary'`

- [ ] **Step 3: Write `versa/core/summary.py`**

```python
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from versa.core.aggregate import section_totals
from versa.core.models import ComparisonMode, Position, PriceStatus, Section, Tender

_ACTUALLY_PRICED = (PriceStatus.PRICED, PriceStatus.LUMP_SUM)
_WARNING_STATUSES = (PriceStatus.LUMP_SUM, PriceStatus.PLACEHOLDER, PriceStatus.INCLUDED_ELSEWHERE)


class DetailLevel(str, Enum):
    SECTIONS = "sections"       # level 1 only
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


_BADGE_TEXT = {
    PriceStatus.ZERO: "—",
    PriceStatus.NOT_INCLUDED: "не вкл.",
}


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
    priced = {pid: cells[pid].value for pid in participant_ids if cells[pid].status == "priced" and cells[pid].value is not None}
    if len(priced) < 2:
        return
    lo, hi = min(priced.values()), max(priced.values())
    for pid, value in priced.items():
        if value == lo:
            cells[pid].highlight = "min"
        if value == hi:
            cells[pid].highlight = (cells[pid].highlight or "max") if value != lo else cells[pid].highlight
    # tie at both ends (all equal) is possible when only 2 tie; handle explicitly:
    if lo == hi:
        for pid in priced:
            cells[pid].highlight = "min"
    else:
        for pid, value in priced.items():
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
    values = list({c.value for c in cells.values()})
    if len(cells) >= 2:
        lo, hi = min(v.value for v in cells.values()), max(v.value for v in cells.values())
        for cell in cells.values():
            if cell.value == lo:
                cell.highlight = "min"
            if cell.value == hi:
                cell.highlight = "max" if cell.highlight != "min" or lo == hi else cell.highlight
    return cells


def _set_deviation_labels(cells: dict[str, SummaryCell], mode: ComparisonMode, baseline_total: Optional[float]) -> None:
    values = {pid: c.value for pid, c in cells.items() if c.value is not None and c.status not in ("na",)}
    if not values:
        return
    if mode == ComparisonMode.BASELINE and baseline_total:
        for pid, cell in cells.items():
            if cell.value is None:
                continue
            pct = (cell.value - baseline_total) / baseline_total * 100
            sign = "+" if pct >= 0 else ""
            cell.deviation_label = f"{sign}{pct:.1f}%".replace(".", ",") + " к р/с"
        return
    minimum = min(values.values())
    for pid, cell in cells.items():
        if cell.value is None:
            continue
        if cell.value == minimum:
            cell.deviation_label = ""
            continue
        pct = (cell.value - minimum) / minimum * 100 if minimum else 0.0
        cell.deviation_label = f"+{pct:.1f}%".replace(".", ",") + " к мин."


def _best_offer(cells: dict[str, SummaryCell], participants: list[ParticipantColumnMeta]) -> Optional[BestOffer]:
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


def _should_include_children(level: int, detail_level: DetailLevel, section_number: str, expanded_sections: frozenset[str], top_level_number: str) -> bool:
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
    is_filled = any(
        price.status in _ACTUALLY_PRICED or position.baseline is not None
        for position in section.iter_positions()
        for price in position.participant_prices.values()
    )
    if hide_unfilled and not is_filled and ancestors:
        return  # never hides a top-level section row itself (handled by caller)

    baseline_cell = None
    if is_filled:
        cells = _cells_for_section(section, participant_ids)
        baseline_values = [
            p.baseline.total.total for p in section.iter_positions() if p.baseline is not None
        ]
        baseline_total = sum(baseline_values) if baseline_values else None
        if baseline_total is not None:
            # raw value only — no deviation math against it yet, see Review Focus note
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
    if detail_level == DetailLevel.POSITIONS or section.number in expanded_sections or top_level_number in expanded_sections:
        for position in section.positions:
            price_cells = {pid: _cell_for_position(position, pid) for pid in participant_ids}
            _apply_position_highlight(price_cells, participant_ids)
            best = _best_offer(price_cells, participants)
            rows.append(SummaryRow(
                kind="position", row=position.row, number="",
                smr_article="", name=position.name, unit=position.unit,
                qty=position.customer_quantity, level=len(child_ancestors) + 1,
                is_filled=is_filled, ancestor_numbers=child_ancestors,
                cells=price_cells, best=best,
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
```

- [ ] **Step 4: Run tests, debug against real data until green**

Run: `pytest tests/test_summary.py -v`
Expected: all PASS. Given the size of this function, expect at least one or two
mismatches against the real file on the first pass (e.g. exact highlight tie-breaking,
exact deviation-label wording) — use `superpowers:systematic-debugging`: print the
actual `SummaryCell`/`SummaryRow` values for the failing assertion and compare against a
fresh independent read of the same rows via `openpyxl` directly, the same way the plan's
own research scripts did, rather than adjusting the test's expected numbers without
re-verifying them against the sheet.

- [ ] **Step 5: Run the full suite**

Run: `pytest -v`
Expected: all pass (55 + ~15 new = ~70).

- [ ] **Step 6: Commit**

```bash
git add versa/core/summary.py tests/test_summary.py
git commit -m "feat: build_summary_table — smeta-order comparison rows with highlighting, badges, VAT split"
```

---

## Task 4: HTML/CSS renderer

**Files:**
- Create: `versa/ui/summary_render.py`
- Test: `tests/test_summary_render.py`

**Interfaces:**
- Consumes: `SummaryTable`/`SummaryRow`/`SummaryCell`/`DetailLevel` (Task 3).
- Produces: `render_summary_html(table: SummaryTable, *, money_unit: str = "руб.") -> str`
  — a complete, self-contained HTML fragment (inline `<style>` + `<table>`) suitable for
  `st.components.v1.html`. `money_unit` is one of `"руб."`, `"тыс. руб."`, `"млн руб."`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_summary_render.py
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
        cells={"a": SummaryCell(status="priced", value=1.0, tooltip="цена за ед: 1,00")},
    )
    html = render_summary_html(_table([row]))

    assert 'title="цена за ед: 1,00"' in html


def test_money_unit_millions_divides_and_formats_one_decimal():
    row = SummaryRow(
        kind="lot", row=None, number="", smr_article="", name="Лот", unit=None, qty=None,
        level=0, is_filled=True, ancestor_numbers=(),
        cells={"a": SummaryCell(status="priced", value=1_500_000.0)},
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

    assert 'ООО "А"' in html
    assert "33,3%" in html
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_summary_render.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'versa.ui.summary_render'`

- [ ] **Step 3: Write `versa/ui/summary_render.py`**

```python
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
  table.versa-summary td.pinned, table.versa-summary th.pinned {
    position: sticky; left: 0; background: #fafafa; z-index: 2;
  }
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
    badge_html = f" <span title=\"{_escape(cell.tooltip)}\">{_escape(cell.badge)}</span>" if cell.badge and cell.value is not None else ""
    dev_html = f'<span class="versa-dev">{_escape(cell.deviation_label)}</span>' if cell.deviation_label else ""
    warn_html = f'<span class="versa-warn" title="{_escape(cell.warning)}">⚠</span>' if cell.warning else ""
    return f'<td style="{style}"{title_attr}>{body}{badge_html}{warn_html}{dev_html}</td>'


def _row_class(row) -> str:
    if row.kind == "lot":
        return "versa-lot"
    if row.kind in ("total_incl_vat", "total_vat", "total_excl_vat", "best_by_section"):
        return "versa-total"
    return f"versa-level-{row.level}"


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
    header_cells += '<th>Лучшее предложение</th>'

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
            f'<td class="pinned">{row.row or ""}</td>'
            f'<td class="pinned">{_escape(row.number)}</td>'
            f'<td class="pinned">{_escape(row.smr_article)}</td>'
            f'<td class="pinned">{indent}{_escape(row.name)}</td>'
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
        if row.best:
            best_html = (
                f'<td>{_escape(row.best.participant_name)}<br>'
                f'<small>{_fmt_money(row.best.savings_vs_second_rub, divisor)} '
                f'(+{row.best.savings_vs_second_pct:.1f}%)</small></td>'
            ).replace(".", ",", 1)  # percent uses comma per spec; money already formatted
        else:
            best_html = "<td></td>"
        body_rows.append(f'<tr class="{_row_class(row)}">{pinned}{baseline_html}{cells_html}{best_html}</tr>')

    legend = (
        '<div style="margin-bottom:6px;">'
        '<span style="background:#C6EFCE;padding:2px 6px;">минимум</span> '
        '<span style="background:#FFC7CE;padding:2px 6px;">максимум</span> '
        '&nbsp;⚠ неточное сравнение &nbsp;«паушал» &nbsp;«≈0» &nbsp;«вкл. в п/п»'
        '</div>'
    )

    return (
        _CSS + legend +
        '<div class="versa-summary-wrap"><table class="versa-summary"><thead><tr>'
        + header_cells + '</tr></thead><tbody>' + "".join(body_rows) + '</tbody></table></div>'
    )
```

- [ ] **Step 4: Run tests, fix formatting mismatches until green**

Run: `pytest tests/test_summary_render.py -v`
Expected: PASS. Pay particular attention to the percent-formatting test
(`"33,3%"` — comma decimal) since Python's default `f"{x:.1f}"` uses a period; the
`.replace(".", ",", 1)` in the best-offer cell only fixes the first occurrence found,
which happens to be the percent since money is formatted before this line runs — if a
test catches a case where money also contains a `.` before the percent do, switch to
formatting the percent string in isolation before concatenating (build the percent text
with its own `f"{pct:.1f}".replace('.', ',')` call rather than a blanket string-level
replace).

- [ ] **Step 5: Run the full suite**

Run: `pytest -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add versa/ui/summary_render.py tests/test_summary_render.py
git commit -m "feat: hand-built sticky HTML/CSS renderer for the summary table"
```

---

## Task 5: Wire into the UI — tabs, sidebar, per-section expand

**Files:**
- Modify: `versa/ui/app.py`
- Modify: `versa/ui/formatting.py` (add a thousands formatter used by the money-unit toggle)
- Test: `tests/test_ui_smoke.py` (extend)

**Interfaces:**
- Consumes: `build_summary_table`/`DetailLevel` (Task 3), `render_summary_html` (Task 4).
- Produces: nothing new consumed elsewhere; this is the top of the call graph.

- [ ] **Step 1: Add `to_thousands` to `versa/ui/formatting.py`**

```python
def to_thousands(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value / 1_000:,.0f}".replace(",", " ")
```

- [ ] **Step 2: Restructure `versa/ui/app.py` into two tabs**

Wrap everything from `st.markdown("### Разделы")` through the end of the file (the
existing waterfall/heatmap/section-table/warnings content) in a variable holding the
*second* tab, and build the new first tab above it:

```python
import streamlit.components.v1 as components

from versa.core.summary import DetailLevel, build_summary_table
from versa.ui.formatting import to_thousands
from versa.ui.summary_render import render_summary_html

# ... existing upload/parse/cache/error-handling block stays exactly as-is, producing `tender` ...

with st.sidebar:
    st.markdown("### Настройки сводной таблицы")
    detail_choice = st.radio("Уровень детализации", ["Разделы", "Подразделы", "Все позиции"])
    detail_level = {
        "Разделы": DetailLevel.SECTIONS,
        "Подразделы": DetailLevel.SUBSECTIONS,
        "Все позиции": DetailLevel.POSITIONS,
    }[detail_choice]
    hide_unfilled = st.checkbox("Скрыть незаполненные разделы")
    money_unit = st.radio("Единицы", ["руб.", "тыс. руб.", "млн руб."], horizontal=True)
    vat_rate_override = st.number_input(
        "Ставка НДС, %", value=float(tender.default_vat_rate), min_value=0.0, max_value=100.0, step=1.0,
    )
    top_level_numbers = [s.number for s in tender.full_sections[1:]]
    with st.expander("Раскрыть отдельные разделы"):
        expanded = {
            number for number in top_level_numbers
            if st.checkbox(number, key=f"expand_{number}")
        }

tab_summary, tab_analytics = st.tabs(["Сводная по смете", "Аналитика"])

with tab_summary:
    summary_table = build_summary_table(
        tender, detail_level=detail_level, expanded_sections=frozenset(expanded),
        hide_unfilled=hide_unfilled, vat_rate=vat_rate_override,
    )
    components.html(
        render_summary_html(summary_table, money_unit=money_unit),
        height=800, scrolling=True,
    )

with tab_analytics:
    # ... move the ENTIRE existing block here unchanged: participant list header repeat
    # is unnecessary (already shown above the tabs alongside subject/object/address),
    # keep header/subheader/caption above the tabs (shared context for both), and move
    # mode caption + summary bars + section table + waterfalls + heatmap + warnings here.
    ...
```

Keep `st.header(tender.subject)` / `st.subheader` / `st.caption` / the participant list
above the tabs (shared context useful on both), so only the mode caption onward
(currently starting at `if tender.mode == ComparisonMode.BASELINE:`) moves into
`tab_analytics`.

- [ ] **Step 3: Extend `tests/test_ui_smoke.py`**

```python
def test_summary_tab_is_the_default_and_renders_without_exception(sample_path):
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=60)
    at.get("file_uploader")[0].upload(
        sample_path.name, sample_path.read_bytes(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    at.run(timeout=60)

    assert not at.exception
    assert len(at.tabs) == 2
    assert at.tabs[0].label == "Сводная по смете"
    assert at.tabs[1].label == "Аналитика"


def test_analytics_tab_still_has_the_old_charts(sample_path):
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=60)
    at.get("file_uploader")[0].upload(
        sample_path.name, sample_path.read_bytes(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    at.run(timeout=60)

    assert not at.exception
    assert len(at.get("plotly_chart")) == 3  # waterfall, diff, heatmap — unchanged from before
```

- [ ] **Step 4: Run and manually verify**

Run: `pytest tests/test_ui_smoke.py -v`
Expected: PASS.

Then a headless AppTest pass uploading the real sample and reading back the rendered
`components.html` call's `html` argument (available via
`at.get("iframe")`/inspecting the component's serialized args — if `AppTest` cannot see
inside `components.html`, verify instead by calling `build_summary_table` +
`render_summary_html` directly in a throwaway script against `sample_tender`, as this
plan's own research scripts did, and visually confirm row count/order/highlight cells
match the Task 3 test assertions).

- [ ] **Step 5: Run the full suite**

Run: `pytest -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add versa/ui/app.py versa/ui/formatting.py tests/test_ui_smoke.py
git commit -m "feat: add Сводная-по-смете tab as the default screen, move charts to Аналитика"
```

---

## Task 6: README update and final check

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document the new screen and the section-18/best-count correction**

Add a short section describing the two tabs, the detail-level/hide-unfilled/money-unit/
VAT-rate sidebar controls, and a note (mirroring the existing "что показалось странным"
section) that section 18 counts toward ИТОГО and "лучших по разделам" per the user's
explicit confirmation this session, including the erbek/section-18 near-empty-bid quirk.

- [ ] **Step 2: Run the full suite one last time**

Run: `pytest -v`
Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document the Сводная-по-смете screen and its controls"
```

---

## Self-review notes (for the executor to re-check once implementing)

- `_apply_position_highlight` and the lot/total tie-break logic above have slightly
  fiddly tie-handling (`lo == hi` cases) written inline in the plan's sample code — when
  implementing, prefer reusing `versa.core.compare._summarize`'s already-tested min/max
  logic instead of re-deriving it, if its `Comparison` shape can be adapted cheaply
  (its `deviation_from_min`/`deviation_from_median` fields aren't quite what this screen
  needs, but its min/max detection is exactly the same rule already covered by
  `tests/test_compare.py`) — a ruling for the executor to make and ledger either way.
- Mode А (baseline) section-level deviation is explicitly deferred in `_walk_section`
  (hardcoded `baseline_total = None`) since — as already ledgered in the stage-1 fix
  pass — no real Mode-А sample exists to validate section-level baseline math against.
  This plan's tests all run in Mode Б; if a Mode-А sample ever arrives, wiring
  `baseline_total` per section is a follow-up, not silently done here without a test.
