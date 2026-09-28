import io

from versa.core.models import ComparisonMode, PriceStatus, WarningType
from versa.core.parser import parse_tender


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


def test_only_priced_sections_survive_empty_section_pruning(sample_tender):
    # The file also has a third priced section: B="18" / C="16. Разработка
    # рабочей документации" (rows 1603-1607, 5 positions with real money).
    # Every other section in the full template has zero prices everywhere
    # and must be pruned.
    top_numbers = {s.number for s in sample_tender.sections}
    assert top_numbers == {"6", "10", "18"}


def test_positions_in_surviving_sections(sample_tender):
    # 226 leaf positions exist under sections 6/10/18, but 12 of them sit in
    # subsections where nobody actually priced anything (only ZERO/
    # NOT_INCLUDED) — those subsections are pruned too, per the Global
    # Constraint, leaving 214.
    total = sum(1 for s in sample_tender.sections for _ in s.iter_positions())
    assert total == 214

    by_number = {s.number: s for s in sample_tender.sections}
    facades_and_engineering = sum(
        1 for _ in by_number["6"].iter_positions()
    ) + sum(1 for _ in by_number["10"].iter_positions())
    # The brief's control totals (section 6/10 sums) were computed against
    # the full 221 positions before this pruning fix, but the removed
    # positions there all had a price of 0 for every participant, so the
    # money-sum control numbers in test_aggregate.py are unaffected.
    assert facades_and_engineering == 209


def test_rik_customer_total_recomputed_not_read_from_broken_formula(sample_tender):
    section_6 = next(s for s in sample_tender.sections if s.number == "6")
    position = next(p for p in section_6.iter_positions() if p.row == 228)
    rik_price = position.participant_prices["rik"]
    # file's AQ228 is #DIV/0!; we must have recomputed qty(H) * unit_price instead
    assert rik_price.total_for_customer_volume is not None
    expected = position.customer_quantity * rik_price.unit_price.total
    assert abs(rik_price.total_for_customer_volume - expected) < 0.01


def test_num_converts_excel_formula_error_to_none_with_warning():
    from versa.core.parser import _num

    warnings = []
    result = _num("#DIV/0!", row=42, col=5, warnings=warnings)

    assert result is None
    assert len(warnings) == 1
    assert warnings[0].type == WarningType.FORMULA_ERROR
    assert warnings[0].row == 42


def test_pct_of_estimate_divide_by_zero_does_not_spam_formula_error_warnings(sample_tender):
    # "% от р/с" divides by an empty расчётная стоимость (Mode Б), so it is
    # #DIV/0! on every single row by construction — not an actionable
    # data-quality warning. It must not drown out the warnings that are
    # (lump_sum, included_elsewhere, volume_mismatch, genuine placeholders).
    formula_errors = [w for w in sample_tender.warnings if w.type == WarningType.FORMULA_ERROR]
    assert len(formula_errors) == 0
    assert any(w.type == WarningType.LUMP_SUM for w in sample_tender.warnings)
    assert any(w.type == WarningType.INCLUDED_ELSEWHERE for w in sample_tender.warnings)


def test_position_number_is_the_real_pp_from_column_a(sample_tender):
    # Sheet row 670 is real п/п 656 (column A) — a 14-row offset from the
    # openpyxl row index. Anything that reports "п/п N" to the user must
    # use this, not the row.
    section_10 = next(s for s in sample_tender.sections if s.number == "10")
    position = next(p for p in section_10.iter_positions() if p.row == 670)
    assert position.number == 656


def test_lump_sum_warning_cites_real_pp_not_sheet_row(sample_tender):
    lump_sum_warnings = [w for w in sample_tender.warnings if w.type == WarningType.LUMP_SUM]
    assert len(lump_sum_warnings) == 1
    warning = lump_sum_warnings[0]
    assert warning.participant_id == "fodd"
    assert "п/п 656" in warning.message
    assert "п/п 670" not in warning.message


def test_subsection_with_no_priced_position_anywhere_is_pruned(sample_tender):
    # 6.5 "Устройство модульного фасада": every participant is either ZERO
    # or NOT_INCLUDED on every position — nobody actually priced anything
    # here. The Global Constraint says drop it, but the old rule only
    # checked "status != ZERO", which NOT_INCLUDED satisfies without any
    # real price.
    def find(number, sections):
        for s in sections:
            if s.number == number:
                return s
            found = find(number, s.children)
            if found:
                return found
        return None

    assert find("6.5", sample_tender.sections) is None


def test_parse_tender_accepts_a_file_like_object_not_just_a_path(sample_path):
    # The Streamlit UI has an uploaded file's bytes in memory; forcing a
    # round-trip through a temp file on disk is both slow to avoid caching
    # and a way to leak copies of confidential tender pricing to /tmp.
    with open(sample_path, "rb") as f:
        buffer = io.BytesIO(f.read())

    tender = parse_tender(buffer)

    assert tender.subject == '№943-ТУ "Казачий 1 оч. НС_Генподряд"'


def test_full_sections_includes_all_18_real_sections_plus_lot(sample_tender):
    numbers = [s.number for s in sample_tender.full_sections]
    assert len(numbers) == 19  # lot row + 18 real top-level sections
    assert numbers.count("1") == 2  # the lot row and section "1" share a B-number


def test_full_sections_excludes_the_commercial_terms_block(sample_tender):
    names = {s.title for s in sample_tender.full_sections if s.title}
    assert "Аванс" not in names
    assert not any(s.number == "Аванс" for s in sample_tender.full_sections)


def test_pruned_sections_are_unaffected_by_full_sections_existing(sample_tender):
    top_numbers = {s.number for s in sample_tender.sections}
    assert top_numbers == {"6", "10", "18"}


def test_default_vat_rate_is_22_percent(sample_tender):
    assert sample_tender.default_vat_rate == 22.0


def test_ges_placeholder_count(sample_tender):
    # 99 GES cells are priced at 0.01 ₽ in the raw sheet, but most carry a
    # comment that reclassifies them: 80 say "включено в п/п NNN"
    # (INCLUDED_ELSEWHERE) and 17 say "не включено..." (NOT_INCLUDED).
    # Only the 2 rows whose comment is a plain duplicate note ("Задвоение
    # с позициями ...", no redirect) remain genuine placeholders.
    placeholder_count = sum(
        1
        for section in sample_tender.iter_sections()
        for position in section.positions
        for pid, price in position.participant_prices.items()
        if pid == "ges" and price.status == PriceStatus.PLACEHOLDER
    )
    assert placeholder_count == 2
