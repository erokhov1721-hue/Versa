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


def test_only_priced_sections_survive_empty_section_pruning(sample_tender):
    # The file also has a third priced section: B="18" / C="16. Разработка
    # рабочей документации" (rows 1603-1607, 5 positions with real money).
    # Every other section in the full template has zero prices everywhere
    # and must be pruned.
    top_numbers = {s.number for s in sample_tender.sections}
    assert top_numbers == {"6", "10", "18"}


def test_226_positions_in_surviving_sections(sample_tender):
    total = sum(1 for s in sample_tender.sections for _ in s.iter_positions())
    assert total == 226

    by_number = {s.number: s for s in sample_tender.sections}
    facades_and_engineering = sum(
        1 for _ in by_number["6"].iter_positions()
    ) + sum(1 for _ in by_number["10"].iter_positions())
    assert facades_and_engineering == 221  # the control number from the brief


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
