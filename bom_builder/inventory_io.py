from __future__ import annotations

import csv
import io
import uuid
from typing import Any

from bom_builder.models import InventoryDocument, InventoryItem

_INVENTORY_COLUMNS: dict[str, str] = {
    "libref": "lib_ref",
    "lib_ref": "lib_ref",
    "mpn": "lib_ref",
    "name": "name",
    "qtyonhand": "qty_on_hand",
    "qty_on_hand": "qty_on_hand",
    "quantity": "qty_on_hand",
    "qty": "qty_on_hand",
    "location": "location",
    "notes": "notes",
}


def _normalize_header(header: str) -> str | None:
    key = header.strip().lower().replace(" ", "_")
    return _INVENTORY_COLUMNS.get(key)


def _parse_qty(raw: str) -> int:
    text = (raw or "").strip()
    if not text:
        return 0
    try:
        return max(0, int(float(text)))
    except ValueError:
        return 0


def _merge_key(lib_ref: str, location: str) -> str:
    return f"{lib_ref.strip().upper()}|{location.strip().upper()}"


def new_item_id() -> str:
    return str(uuid.uuid4())


def find_item(doc: InventoryDocument, item_id: str) -> InventoryItem | None:
    for item in doc.items:
        if item.id == item_id:
            return item
    return None


def add_qty_for_mpn(
    doc: InventoryDocument,
    *,
    lib_ref: str,
    qty: int,
    name: str = "",
    location: str = "",
    notes: str = "",
) -> InventoryItem:
    """Add quantity to inventory, merging into an existing row with the same MPN when possible."""
    from bom_builder.matcher import normalize_key

    lib_ref = lib_ref.strip()
    if not lib_ref:
        raise ValueError("MPN (LibRef) is required.")
    if qty <= 0:
        raise ValueError("Quantity must be at least 1.")

    lib_key = normalize_key(lib_ref)
    loc_key = location.strip().upper()
    matches = [item for item in doc.items if normalize_key(item.lib_ref) == lib_key]
    if loc_key:
        for item in matches:
            if item.location.strip().upper() == loc_key:
                item.qty_on_hand += qty
                if name.strip() and not item.name.strip():
                    item.name = name.strip()
                if notes.strip():
                    item.notes = notes.strip() if not item.notes.strip() else f"{item.notes}; {notes.strip()}"
                return item
    for item in matches:
        item.qty_on_hand += qty
        if name.strip() and not item.name.strip():
            item.name = name.strip()
        if notes.strip():
            item.notes = notes.strip() if not item.notes.strip() else f"{item.notes}; {notes.strip()}"
        return item

    return add_item(
        doc,
        lib_ref=lib_ref,
        name=name,
        qty_on_hand=qty,
        location=location,
        notes=notes,
    )


def add_item(
    doc: InventoryDocument,
    *,
    lib_ref: str,
    name: str = "",
    qty_on_hand: int = 0,
    location: str = "",
    notes: str = "",
) -> InventoryItem:
    lib_ref = lib_ref.strip()
    if not lib_ref:
        raise ValueError("LibRef is required.")

    item = InventoryItem(
        id=new_item_id(),
        lib_ref=lib_ref,
        name=name.strip(),
        qty_on_hand=max(0, qty_on_hand),
        location=location.strip(),
        notes=notes.strip(),
    )
    doc.items.append(item)
    return item


def update_item(
    item: InventoryItem,
    *,
    lib_ref: str | None = None,
    name: str | None = None,
    qty_on_hand: int | None = None,
    location: str | None = None,
    notes: str | None = None,
) -> None:
    if lib_ref is not None:
        lib_ref = lib_ref.strip()
        if not lib_ref:
            raise ValueError("LibRef is required.")
        item.lib_ref = lib_ref
    if name is not None:
        item.name = name.strip()
    if qty_on_hand is not None:
        item.qty_on_hand = max(0, qty_on_hand)
    if location is not None:
        item.location = location.strip()
    if notes is not None:
        item.notes = notes.strip()


def delete_item(doc: InventoryDocument, item_id: str) -> bool:
    for index, item in enumerate(doc.items):
        if item.id == item_id:
            doc.items.pop(index)
            return True
    return False


def inventory_stats(doc: InventoryDocument) -> dict[str, int]:
    total_qty = sum(item.qty_on_hand for item in doc.items)
    # Use part_count — dict key "items" breaks Jinja (stats.items is dict.items method).
    return {"part_count": len(doc.items), "total_qty": total_qty}


def parse_inventory_csv(content: str | bytes) -> list[dict[str, Any]]:
    if isinstance(content, bytes):
        text = _decode_bytes(content)
    else:
        text = content.lstrip("\ufeff")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV has no header row")

    field_map: dict[str, str] = {}
    for header in reader.fieldnames:
        canonical = _normalize_header(header)
        if canonical:
            field_map[header] = canonical

    if "lib_ref" not in field_map.values():
        raise ValueError("CSV must include a LibRef column.")

    rows: list[dict[str, Any]] = []
    for row in reader:
        normalized: dict[str, str] = {}
        for header, canonical in field_map.items():
            normalized[canonical] = (row.get(header) or "").strip()

        lib_ref = normalized.get("lib_ref", "")
        if not lib_ref:
            continue

        rows.append(
            {
                "lib_ref": lib_ref,
                "name": normalized.get("name", ""),
                "qty_on_hand": _parse_qty(normalized.get("qty_on_hand", "0")),
                "location": normalized.get("location", ""),
                "notes": normalized.get("notes", ""),
            }
        )
    return rows


def merge_import(doc: InventoryDocument, imported_rows: list[dict[str, Any]]) -> tuple[int, int]:
    """Merge imported rows by lib_ref + location. Returns (added, updated)."""
    index = {_merge_key(item.lib_ref, item.location): item for item in doc.items}
    added = 0
    updated = 0

    for row in imported_rows:
        key = _merge_key(row["lib_ref"], row.get("location", ""))
        existing = index.get(key)
        if existing:
            update_item(
                existing,
                lib_ref=row["lib_ref"],
                name=row.get("name", ""),
                qty_on_hand=row.get("qty_on_hand", 0),
                location=row.get("location", ""),
                notes=row.get("notes", ""),
            )
            updated += 1
        else:
            item = add_item(doc, **row)
            index[key] = item
            added += 1

    return added, updated


def inventory_to_csv(doc: InventoryDocument) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["LibRef", "Name", "QtyOnHand", "Location", "Notes"])
    for item in sorted(doc.items, key=lambda i: (i.lib_ref.upper(), i.location.upper())):
        writer.writerow([item.lib_ref, item.name, item.qty_on_hand, item.location, item.notes])
    return buffer.getvalue()


def _decode_bytes(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")
