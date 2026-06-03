from __future__ import annotations

import csv
import io

from bom_builder.models import BomDocument, NeedLine


def merge_bom_state(existing: BomDocument | None, incoming: BomDocument) -> BomDocument:
    """Preserve acquired/notes when re-importing the same BOM."""
    if existing is None:
        return incoming

    state_by_id: dict[str, tuple[bool, str]] = {
        line.id: (line.acquired, line.notes) for line in existing.lines
    }
    for line in incoming.lines:
        if line.id in state_by_id:
            acquired, notes = state_by_id[line.id]
            line.acquired = acquired
            line.notes = notes
    incoming.source_filename = incoming.source_filename or existing.source_filename
    incoming.board_count = existing.board_count
    return incoming


def line_total_quantity(line: NeedLine, board_count: int) -> int:
    return line.quantity * max(1, board_count)


def bom_stats(bom: BomDocument) -> dict[str, int]:
    total = len(bom.lines)
    dni = sum(1 for line in bom.lines if line.is_dni)
    acquired = sum(1 for line in bom.lines if line.acquired)
    boards = max(1, bom.board_count)
    qty_per_board = sum(line.quantity for line in bom.lines if not line.is_dni)
    qty_total = sum(line_total_quantity(line, boards) for line in bom.lines if not line.is_dni)
    return {
        "total": total,
        "dni": dni,
        "active": total,
        "acquired": acquired,
        "remaining": total - acquired,
        "board_count": boards,
        "qty_per_board": qty_per_board,
        "qty_total": qty_total,
    }


def find_line(bom: BomDocument, line_id: str) -> NeedLine | None:
    for line in bom.lines:
        if line.id == line_id:
            return line
    return None


def bom_to_csv(bom: BomDocument) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    boards = max(1, bom.board_count)
    writer.writerow(
        [
            "Name",
            "Description",
            "Designator",
            "Footprint",
            "LibRef",
            "QtyPerBoard",
            "BoardCount",
            "QtyTotal",
            "Acquired",
            "Notes",
        ]
    )
    for line in bom.lines:
        writer.writerow(
            [
                line.name,
                line.description,
                line.designator_display,
                line.footprint,
                line.lib_ref,
                line.quantity,
                boards,
                line_total_quantity(line, boards),
                "Y" if line.acquired else "N",
                line.notes,
            ]
        )
    return buffer.getvalue()
