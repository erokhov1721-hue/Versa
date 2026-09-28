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
                     participants=[p1], sections=[], full_sections=[], default_vat_rate=22.0,
                     mode=ComparisonMode.PEER, warnings=[])
    assert tender.participant_by_id("parallel") is p1
    assert tender.participant_by_id("missing") is None
