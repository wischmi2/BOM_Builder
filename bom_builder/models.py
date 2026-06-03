from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class NeedLine:
    id: str
    bom_id: str
    name: str
    description: str
    designators: list[str]
    footprint: str
    lib_ref: str
    quantity: int
    is_dni: bool = False
    acquired: bool = False
    notes: str = ""

    @property
    def designator_display(self) -> str:
        return ", ".join(self.designators)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NeedLine:
        return cls(**data)


@dataclass
class BomDocument:
    bom_id: str
    source_filename: str
    lines: list[NeedLine] = field(default_factory=list)
    board_count: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "bom_id": self.bom_id,
            "source_filename": self.source_filename,
            "board_count": self.board_count,
            "lines": [line.to_dict() for line in self.lines],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BomDocument:
        raw_boards = data.get("board_count", 1)
        try:
            board_count = max(1, int(raw_boards))
        except (TypeError, ValueError):
            board_count = 1
        return cls(
            bom_id=data["bom_id"],
            source_filename=data["source_filename"],
            board_count=board_count,
            lines=[NeedLine.from_dict(line) for line in data["lines"]],
        )


@dataclass
class InventoryItem:
    id: str
    lib_ref: str
    name: str = ""
    qty_on_hand: int = 0
    location: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InventoryItem:
        return cls(**data)


@dataclass
class InventoryDocument:
    items: list[InventoryItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"items": [item.to_dict() for item in self.items]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InventoryDocument:
        return cls(items=[InventoryItem.from_dict(item) for item in data.get("items", [])])
