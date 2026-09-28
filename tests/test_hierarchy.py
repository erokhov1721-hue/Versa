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

    flat = [s for root in tree for s in root.iter_sections()]
    by_row = {s.row: s for s in flat}
    assert by_row[294].number == "6.8"  # hierarchy follows B
    assert by_row[294].title == "6.10. Декоративные элементы и другие"  # title follows C


def test_title_falls_back_to_d_when_c_empty():
    rows = [RawRow(row=98, b="3.2.1", c=None, d="Постоянный дренаж")]
    tree = build_section_tree(rows)
    assert tree[0].title == "Постоянный дренаж"
