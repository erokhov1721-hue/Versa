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
