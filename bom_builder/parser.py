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


def _decode_bytes(raw: bytes) -> str:
    """Decode CSV bytes from Altium exports (often UTF-8 or Windows-1252)."""
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def parse_bom_csv(
    file_content: str | bytes,
    *,
    bom_id: str,
    source_filename: str = "",
) -> BomDocument:
    """Parse an Altium-style BOM CSV into a BomDocument."""
    if isinstance(file_content, bytes):
        text = _decode_bytes(file_content)
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


def parse_bom_csv_file(path: str | Path, *, bom_id: str | None = None) -> BomDocument:
    path = Path(path)
    resolved_id = bom_id or bom_id_from_filename(path.name)
    content = _decode_bytes(path.read_bytes())
    return parse_bom_csv(content, bom_id=resolved_id, source_filename=path.name)


# --------------------------------------------------------------------------- #
# KiCad BOM import
# --------------------------------------------------------------------------- #

# KiCad "Grouped By Value" CSV columns (case-insensitive). KiCad uses different
# header names than Altium and has no LibRef, so lib_ref is derived from the
# manufacturer part number (falling back to LCSC part #, then Value).
_KICAD_COLUMN_ALIASES: dict[str, str] = {
    "reference": "designator",
    "references": "designator",
    "qty": "quantity",
    "quantity": "quantity",
    "value": "value",
    "footprint": "footprint",
    "description": "description",
    "mpn": "mpn",
    "manufacturer_part_number": "mpn",
    "lcsc_part": "lcsc",
    "lcsc": "lcsc",
    "lcsc_part_number": "lcsc",
    "dnp": "dnp",
    "exclude_from_bom": "exclude_from_bom",
}

# KiCad references are separated by commas or spaces (e.g. "C6,C14,C15" or "R1 R2").
_KICAD_REF_SPLIT = re.compile(r"[,\s]+")


def _kicad_normalize_header(header: str) -> str | None:
    key = header.strip().lower().replace(" ", "_")
    return _KICAD_COLUMN_ALIASES.get(key)


def _kicad_split_designators(raw: str) -> list[str]:
    if not raw or not raw.strip():
        return []
    parts = [part.strip() for part in _KICAD_REF_SPLIT.split(raw.strip())]
    return [part for part in parts if part]


def _kicad_flag_is_set(raw: str) -> bool:
    """KiCad writes empty for unset boolean fields; anything else means set."""
    text = (raw or "").strip().lower()
    if not text:
        return False
    return text not in ("0", "false", "no", "n")


def _kicad_lib_ref(mpn: str, lcsc: str, value: str) -> str:
    """Match key for KiCad rows: MPN, then LCSC part #, then Value."""
    for candidate in (mpn, lcsc, value):
        text = (candidate or "").strip()
        if text:
            return text
    return ""


def parse_kicad_bom_csv(
    file_content: str | bytes,
    *,
    bom_id: str,
    source_filename: str = "",
) -> BomDocument:
    """Parse a KiCad "Grouped By Value" BOM CSV into a BomDocument.

    Maps KiCad columns onto the app's model: Reference->designators, Qty->quantity,
    Value->name, Footprint/Description carried through. lib_ref (the match key) is
    derived from MPN, falling back to the LCSC part number, then Value. Rows flagged
    "Exclude from BOM" are skipped; rows flagged DNP are marked do-not-install.
    """
    if isinstance(file_content, bytes):
        text = _decode_bytes(file_content)
    else:
        text = file_content.lstrip("﻿")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV has no header row")

    field_map: dict[str, str] = {}
    for header in reader.fieldnames:
        canonical = _kicad_normalize_header(header)
        # First header wins for a given canonical field (KiCad's nrf export has
        # both "MANUFACTURER" and "Manufacturer"; neither maps, so this is safe,
        # but guard against duplicate real columns just in case).
        if canonical and canonical not in field_map.values():
            field_map[header] = canonical

    canonical_present = set(field_map.values())
    # A KiCad BOM must at least have references and a value to be usable.
    required = {"designator", "value"}
    missing = required - canonical_present
    if missing:
        raise ValueError(
            "CSV does not look like a KiCad BOM (missing columns: "
            f"{', '.join(sorted(missing))}). Expected Reference and Value columns."
        )

    lines: list[NeedLine] = []
    for row_index, row in enumerate(reader, start=1):
        normalized: dict[str, str] = {}
        for header, canonical in field_map.items():
            normalized[canonical] = (row.get(header) or "").strip()

        # Honor KiCad's "Exclude from BOM" flag — these parts are not purchased.
        if _kicad_flag_is_set(normalized.get("exclude_from_bom", "")):
            continue

        value = normalized.get("value", "")
        description = normalized.get("description", "")
        designators = _kicad_split_designators(normalized.get("designator", ""))
        footprint = normalized.get("footprint", "")
        mpn = normalized.get("mpn", "")
        lcsc = normalized.get("lcsc", "")
        lib_ref = _kicad_lib_ref(mpn, lcsc, value)
        is_dni = _kicad_flag_is_set(normalized.get("dnp", ""))

        quantity = _parse_quantity(normalized.get("quantity", ""))
        # KiCad exports sometimes omit Qty; fall back to the designator count.
        if quantity == 0 and designators:
            quantity = len(designators)

        if not any([value, lib_ref, designators, footprint]):
            continue

        line_id = _stable_line_id(lib_ref, designators, footprint, value, row_index)
        lines.append(
            NeedLine(
                id=line_id,
                bom_id=bom_id,
                name=value,
                description=description,
                designators=designators,
                footprint=footprint,
                lib_ref=lib_ref,
                quantity=quantity,
                is_dni=is_dni or _is_dni(value, footprint, lib_ref),
                lcsc_part=lcsc,
            )
        )

    return BomDocument(bom_id=bom_id, source_filename=source_filename, lines=lines)


def parse_kicad_bom_csv_file(path: str | Path, *, bom_id: str | None = None) -> BomDocument:
    path = Path(path)
    resolved_id = bom_id or bom_id_from_filename(path.name)
    content = _decode_bytes(path.read_bytes())
    return parse_kicad_bom_csv(content, bom_id=resolved_id, source_filename=path.name)
