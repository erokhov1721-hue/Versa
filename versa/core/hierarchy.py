from __future__ import annotations

import re
from typing import NamedTuple, Optional

from versa.core.models import Position, Section

_SECTION_NUMBER_RE = re.compile(r"^\d+(\.\d+)*\.?$")


class RawRow(NamedTuple):
    row: int
    b: Optional[str]
    c: Optional[str]
    d: Optional[str]
    a: Optional[object] = None  # real "№ п/п" from column A, distinct from the sheet row index


def _is_blank(value: Optional[str]) -> bool:
    return value is None or str(value).strip() == ""


def _is_section_number(value: Optional[str]) -> bool:
    if _is_blank(value):
        return False
    return bool(_SECTION_NUMBER_RE.match(str(value).strip()))


def _level(number: str) -> int:
    return len(number.rstrip(".").split("."))


def build_section_tree(rows: list[RawRow]) -> list[Section]:
    roots: list[Section] = []
    stack: list[Section] = []  # top of stack = current deepest open section

    for raw in rows:
        if _is_section_number(raw.b):
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

        elif _is_blank(raw.b) and not _is_blank(raw.d):
            if not stack:
                continue  # position before any section header; nothing to attach to
            number = None
            if raw.a is not None:
                try:
                    number = int(raw.a)
                except (TypeError, ValueError):
                    number = None
            position = Position(
                row=raw.row, number=number, name=str(raw.d).strip(), unit=None,
                customer_quantity=None, customer_comment=None, baseline=None,
                participant_prices={},
            )
            stack[-1].positions.append(position)

    return roots
