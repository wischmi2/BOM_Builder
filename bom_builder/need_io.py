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
    return incoming


def bom_stats(bom: BomDocument) -> dict[str, int]:
    total = len(bom.lines)
    dni = sum(1 for line in bom.lines if line.is_dni)
    acquired = sum(1 for line in bom.lines if line.acquired and not line.is_dni)
    active = total - dni
    return {
        "total": total,
        "dni": dni,
        "active": active,
        "acquired": acquired,
        "remaining": active - acquired,
    }


def find_line(bom: BomDocument, line_id: str) -> NeedLine | None:
    for line in bom.lines:
        if line.id == line_id:
            return line
    return None


def bom_to_csv(bom: BomDocument) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        ["Name", "Description", "Designator", "Footprint", "LibRef", "Quantity", "Acquired", "Notes"]
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
                "Y" if line.acquired else "N",
                line.notes,
            ]
        )
    return buffer.getvalue()
