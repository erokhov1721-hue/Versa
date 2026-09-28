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
    full_sections: list[Section]
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
