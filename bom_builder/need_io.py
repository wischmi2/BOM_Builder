from __future__ import annotations

import csv
import io
import re

from bom_builder.models import BomDocument, NeedLine

_INTERNAL_LIB_PREFIXES = ("CMP-", "INT-", "INTERNAL-")


def looks_like_internal_lib_ref(lib_ref: str) -> bool:
    ref = (lib_ref or "").strip().upper()
    return any(ref.startswith(prefix) for prefix in _INTERNAL_LIB_PREFIXES)


def suggest_mpn_from_description(
    description: str,
    *,
    name: str = "",
    lib_ref: str = "",
) -> str | None:
    """Guess manufacturer PN embedded in BOM description (e.g. RC0402FR-07953RL)."""
    desc = (description or "").strip()
    if not desc:
        return None

    name_key = (name or "").strip().upper()
    lib_key = (lib_ref or "").strip().upper()

    compact = re.sub(r"\s+", "", desc)
    if re.match(r"^[A-Za-z0-9][A-Za-z0-9\-/.]{5,}$", compact) and any(ch.isdigit() for ch in compact):
        candidate = compact
        if candidate.upper() not in (name_key, lib_key) and not looks_like_internal_lib_ref(candidate):
            return candidate

    candidates: list[str] = []
    for match in re.finditer(r"\b([A-Za-z]{2,}\d{3,}[A-Za-z0-9\-]+)\b", desc):
        candidates.append(match.group(1))
    for match in re.finditer(r"\b([A-Z]{2,4}\d{4}[A-Z]{2,}-[\dA-Z]+)\b", desc.upper()):
        candidates.append(match.group(1))

    seen: set[str] = set()
    for raw in candidates:
        token = raw.strip()
        key = token.upper()
        if key in seen or len(token) < 8:
            continue
        seen.add(key)
        if key in (name_key, lib_key):
            continue
        if looks_like_internal_lib_ref(token):
            continue
        return token
    return None


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
