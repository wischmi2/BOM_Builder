from __future__ import annotations

import csv
import hashlib
import io
import re
from pathlib import Path

from bom_builder.models import BomDocument, NeedLine

# Altium-style BOM columns (case-insensitive aliases).
_COLUMN_ALIASES: dict[str, str] = {
    "name": "name",
    "description": "description",
    "designator": "designator",
    "ref": "designator",
    "footprint": "footprint",
    "libref": "lib_ref",
    "lib_ref": "lib_ref",
    "quantity": "quantity",
    "qty": "quantity",
}


def bom_id_from_filename(filename: str) -> str:
    stem = Path(filename).stem
    safe = re.sub(r"[^\w.\-]+", "_", stem)
    return safe or "bom"


def _normalize_header(header: str) -> str | None:
    key = header.strip().lower().replace(" ", "_")
    return _COLUMN_ALIASES.get(key)


def _split_designators(raw: str) -> list[str]:
    if not raw or not raw.strip():
        return []
    parts = [part.strip() for part in raw.split(",")]
    return [part for part in parts if part]


def _parse_quantity(raw: str) -> int:
    text = (raw or "").strip()
    if not text:
        return 0
    try:
        return int(float(text))
    except ValueError:
        return 0


def _is_dni(name: str, footprint: str, lib_ref: str) -> bool:
    name_upper = (name or "").strip().upper()
    if name_upper == "DNI":
        return True
    footprint_upper = (footprint or "").upper()
    if "DNI" in footprint_upper:
        return True
    lib_upper = (lib_ref or "").upper()
    return lib_upper.endswith("_DNI") or lib_upper == "DNI"


def _stable_line_id(lib_ref: str, designators: list[str], footprint: str, name: str, row_index: int) -> str:
    designator_key = ",".join(designators)
    payload = f"{lib_ref}|{designator_key}|{footprint}|{name}|{row_index}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"row-{row_index}-{digest}"


def parse_bom_csv(
    file_content: str | bytes,
    *,
    bom_id: str,
    source_filename: str = "",
) -> BomDocument:
    """Parse an Altium-style BOM CSV into a BomDocument."""
    if isinstance(file_content, bytes):
        text = file_content.decode("utf-8-sig")
    else:
        text = file_content.lstrip("\ufeff")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV has no header row")

    field_map: dict[str, str] = {}
    for header in reader.fieldnames:
        canonical = _normalize_header(header)
        if canonical:
            field_map[header] = canonical

    required = {"name", "designator", "footprint", "lib_ref", "quantity"}
    missing = required - set(field_map.values())
    if missing:
        raise ValueError(f"CSV missing required columns: {', '.join(sorted(missing))}")

    lines: list[NeedLine] = []
    for row_index, row in enumerate(reader, start=1):
        normalized: dict[str, str] = {}
        for header, canonical in field_map.items():
            normalized[canonical] = (row.get(header) or "").strip()

        name = normalized.get("name", "")
        description = normalized.get("description", "")
        designators = _split_designators(normalized.get("designator", ""))
        footprint = normalized.get("footprint", "")
        lib_ref = normalized.get("lib_ref", "")
        quantity = _parse_quantity(normalized.get("quantity", ""))

        if not any([name, lib_ref, designators, footprint]):
            continue

        line_id = _stable_line_id(lib_ref, designators, footprint, name, row_index)
        lines.append(
            NeedLine(
                id=line_id,
                bom_id=bom_id,
                name=name,
                description=description,
                designators=designators,
                footprint=footprint,
                lib_ref=lib_ref,
                quantity=quantity,
                is_dni=_is_dni(name, footprint, lib_ref),
            )
        )

    return BomDocument(bom_id=bom_id, source_filename=source_filename, lines=lines)


def _read_text_with_fallback(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def parse_bom_csv_file(path: str | Path, *, bom_id: str | None = None) -> BomDocument:
    path = Path(path)
    resolved_id = bom_id or bom_id_from_filename(path.name)
    content = _read_text_with_fallback(path)
    return parse_bom_csv(content, bom_id=resolved_id, source_filename=path.name)
