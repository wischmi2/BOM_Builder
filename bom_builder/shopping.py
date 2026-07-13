from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from bom_builder.distributor_cache import cache_key_for_mpn
from bom_builder.matcher import (
    AggregatedCompareRow,
    CompareRow,
    compare_boms,
    compare_boms_aggregated,
    rematch_inventory_for_part,
    split_lib_refs,
)
from bom_builder.models import BomDocument, InventoryDocument
from bom_builder.need_io import find_line
from bom_builder import storage
from bom_builder.inventory_io import add_qty_for_mpn


@dataclass
class ShopAlternate:
    enabled: bool = False
    mpn: str = ""
    name: str = ""
    buy_qty: int = 0
    notes: str = ""
    ordered: bool = False
    received_qty: int = 0

    @property
    def remaining_buy_qty(self) -> int:
        return max(0, self.buy_qty - self.received_qty)

    @property
    def fully_received(self) -> bool:
        return self.buy_qty > 0 and self.received_qty >= self.buy_qty

    @property
    def digikey_url(self) -> str:
        return digikey_search_url(self.mpn) if self.mpn else ""

    @property
    def mouser_url(self) -> str:
        return mouser_search_url(self.mpn) if self.mpn else ""

    @property
    def cache_key(self) -> str:
        return cache_key_for_mpn(self.mpn)


@dataclass
class ShopLine:
    line_id: str
    lib_ref: str
    primary_mpn: str
    alternates_display: str
    name: str
    status: str
    qty_needed: int
    qty_on_hand: int
    default_buy_qty: int
    buy_qty: int
    bom_id: str = ""
    bom_ids_display: str = ""
    designators: str = ""
    notes: str = ""
    ordered: bool = False
    received_qty: int = 0
    digikey_url: str = ""
    mouser_url: str = ""
    search_text: str = ""
    cache_key: str = ""
    storage_key: str = ""
    source_line_ids: list[str] = field(default_factory=list)
    alternate: ShopAlternate = field(default_factory=ShopAlternate)

    @property
    def alternates_extra(self) -> bool:
        return bool(self.alternates_display)

    @property
    def remaining_buy_qty(self) -> int:
        return max(0, self.buy_qty - self.received_qty)

    @property
    def fully_received(self) -> bool:
        return self.buy_qty > 0 and self.received_qty >= self.buy_qty


def shortfall_qty(qty_needed: int, qty_on_hand: int) -> int:
    return max(0, qty_needed - qty_on_hand)


def primary_mpn(lib_ref: str) -> str:
    segments = split_lib_refs(lib_ref)
    return segments[0] if segments else (lib_ref or "").strip()


def alternates_display(lib_ref: str) -> str:
    segments = split_lib_refs(lib_ref)
    if len(segments) <= 1:
        return ""
    return ", ".join(segments[1:])


def effective_part_from_state(
    lib_ref: str,
    name: str,
    state: dict[str, Any] | None,
) -> tuple[str, str, bool]:
    """Return effective MPN, name, and whether a Shop substitute is active."""
    base_mpn = primary_mpn(lib_ref)
    if not state:
        return base_mpn, name, False

    alt = state.get("alternate")
    if isinstance(alt, dict) and alt.get("enabled"):
        alt_mpn = str(alt.get("mpn", "")).strip()
        if alt_mpn:
            alt_name = str(alt.get("name", "")).strip()
            return alt_mpn, alt_name or name, True

    mpn = str(state.get("mpn", "")).strip() or base_mpn
    eff_name = str(state.get("name", "")).strip() or name
    return mpn, eff_name, mpn != base_mpn


def apply_shop_overlay_to_compare_row(
    row: CompareRow,
    saved: dict[str, dict[str, Any]],
    inventory: InventoryDocument,
) -> None:
    shop_line = _shop_line_from_compare(row)
    row.storage_key = shop_line.storage_key
    row.source_line_ids = list(shop_line.source_line_ids)
    state = saved_state_for_line(saved, shop_line)
    eff_mpn, eff_name, is_substitute = effective_part_from_state(
        row.need_line.lib_ref,
        row.need_line.name,
        state,
    )
    row.effective_lib_ref = eff_mpn
    row.effective_name = eff_name
    row.shop_substitute = is_substitute

    if eff_mpn != primary_mpn(row.need_line.lib_ref):
        matched, qty_on_hand, status, match_type = rematch_inventory_for_part(
            eff_mpn,
            eff_name,
            is_dni=row.need_line.is_dni,
            qty_needed=row.qty_needed,
            inventory=inventory,
        )
        row.matched_inventory = matched
        row.qty_on_hand = qty_on_hand
        row.delta = qty_on_hand - row.qty_needed
        row.status = status
        row.match_type = match_type


def apply_shop_overlay_to_aggregated_row(
    row: AggregatedCompareRow,
    saved: dict[str, dict[str, Any]],
    inventory: InventoryDocument,
) -> None:
    shop_line = _shop_line_from_aggregated(row)
    row.storage_key = shop_line.storage_key
    row.source_line_ids = list(shop_line.source_line_ids)
    state = saved_state_for_line(saved, shop_line)
    eff_mpn, eff_name, is_substitute = effective_part_from_state(row.lib_ref, row.name, state)
    row.effective_lib_ref = eff_mpn
    row.effective_name = eff_name
    row.shop_substitute = is_substitute

    if eff_mpn != primary_mpn(row.lib_ref):
        matched, qty_on_hand, status, match_type = rematch_inventory_for_part(
            eff_mpn,
            eff_name,
            is_dni=row.is_dni,
            qty_needed=row.qty_needed_total,
            inventory=inventory,
        )
        row.matched_inventory = matched
        row.qty_on_hand = qty_on_hand
        row.leftover = qty_on_hand - row.qty_needed_total
        row.status = status
        row.match_type = match_type


def apply_shop_overlays_to_compare(
    rows: list[CompareRow] | None,
    agg_rows: list[AggregatedCompareRow] | None,
    inventory: InventoryDocument,
    saved: dict[str, dict[str, Any]] | None = None,
) -> None:
    if saved is None:
        saved = storage.load_shopping_list()
    if rows:
        for row in rows:
            apply_shop_overlay_to_compare_row(row, saved, inventory)
    if agg_rows:
        for row in agg_rows:
            apply_shop_overlay_to_aggregated_row(row, saved, inventory)


def digikey_search_url(mpn: str) -> str:
    keyword = quote((mpn or "").strip(), safe="")
    return f"https://www.digikey.com/en/products/result?keywords={keyword}"


def mouser_search_url(mpn: str) -> str:
    keyword = quote((mpn or "").strip(), safe="")
    return f"https://www.mouser.com/c/?q={keyword}"


def attach_storage_key(line: ShopLine) -> ShopLine:
    """Stable key for shopping_list.json (same part across combined/per-board views)."""
    from bom_builder.category_overrides import part_key_for_shop_line

    line.storage_key = part_key_for_shop_line(line)
    return line


def candidate_keys_for_line(line: ShopLine) -> list[str]:
    keys: list[str] = []
    for key in (line.storage_key, line.line_id, *line.source_line_ids, line.cache_key):
        if key and key not in keys:
            keys.append(key)
    return keys


def _pick_best_field(states: list[dict[str, Any]], field: str) -> str:
    best = ""
    best_ts = ""
    for state in states:
        value = str(state.get(field) or "").strip()
        if not value:
            continue
        ts = str(state.get("updated_at") or "")
        if not best or ts > best_ts:
            best = value
            best_ts = ts
    return best


def _pick_best_notes(states: list[dict[str, Any]]) -> str:
    best = ""
    best_ts = ""
    for state in states:
        notes = str(state.get("notes") or "").strip()
        if not notes:
            continue
        ts = str(state.get("updated_at") or "")
        if not best or ts > best_ts:
            best = notes
            best_ts = ts
    return best


def _pick_best_alternate(states: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Newest saved alternate sub-record across storage_key and per-board keys."""
    best: dict[str, Any] | None = None
    best_ts = ""
    for state in states:
        alt = state.get("alternate")
        if not isinstance(alt, dict):
            continue
        ts = str(state.get("updated_at") or "")
        if best is None or ts >= best_ts:
            best = alt
            best_ts = ts
    return best


def saved_state_for_line(saved: dict[str, dict[str, Any]], line: ShopLine) -> dict[str, Any] | None:
    """Merge saved shopping state from storage_key, aggregate id, and per-board line ids."""
    states: list[dict[str, Any]] = []
    for key in candidate_keys_for_line(line):
        state = saved.get(key)
        if isinstance(state, dict):
            states.append(state)
    if not states:
        return None

    merged: dict[str, Any] = {}
    for key in (line.storage_key, line.line_id):
        if not key:
            continue
        state = saved.get(key)
        if not isinstance(state, dict):
            continue
        for field in ("buy_qty", "ordered", "received_qty"):
            if field in state and field not in merged:
                merged[field] = state[field]

    for state in states:
        if "ordered" in state and state.get("ordered"):
            merged["ordered"] = True

    notes = _pick_best_notes(states)
    if notes:
        merged["notes"] = notes

    mpn = _pick_best_field(states, "mpn")
    if mpn:
        merged["mpn"] = mpn
    name = _pick_best_field(states, "name")
    if name:
        merged["name"] = name

    alt = _pick_best_alternate(states)
    if alt is not None:
        merged["alternate"] = alt

    if not merged:
        return states[0]
    return merged


def _shop_line_from_compare(row: CompareRow) -> ShopLine:
    line = row.need_line
    mpn = primary_mpn(line.lib_ref)
    default_buy = shortfall_qty(row.qty_needed, row.qty_on_hand)
    search_parts = [line.name, line.lib_ref, line.designator_display, line.bom_id]
    line = ShopLine(
        line_id=f"{line.bom_id}:{line.id}",
        lib_ref=line.lib_ref,
        primary_mpn=mpn,
        alternates_display=alternates_display(line.lib_ref),
        name=line.name,
        status=row.status,
        qty_needed=row.qty_needed,
        qty_on_hand=row.qty_on_hand,
        default_buy_qty=default_buy,
        buy_qty=default_buy,
        bom_id=line.bom_id,
        designators=line.designator_display,
        digikey_url=digikey_search_url(mpn),
        mouser_url=mouser_search_url(mpn),
        search_text=" ".join(search_parts).lower(),
        cache_key=cache_key_for_mpn(mpn),
    )
    line = attach_storage_key(line)
    line.source_line_ids = [line.line_id]
    return line


def _shop_line_from_aggregated(row: AggregatedCompareRow) -> ShopLine:
    mpn = primary_mpn(row.lib_ref)
    default_buy = shortfall_qty(row.qty_needed_total, row.qty_on_hand)
    search_parts = [row.name, row.lib_ref, row.bom_ids_display]
    line = ShopLine(
        line_id=row.aggregate_key,
        lib_ref=row.lib_ref,
        primary_mpn=mpn,
        alternates_display=alternates_display(row.lib_ref),
        name=row.name,
        status=row.status,
        qty_needed=row.qty_needed_total,
        qty_on_hand=row.qty_on_hand,
        default_buy_qty=default_buy,
        buy_qty=default_buy,
        bom_ids_display=row.bom_ids_display,
        digikey_url=digikey_search_url(mpn),
        mouser_url=mouser_search_url(mpn),
        search_text=" ".join(search_parts).lower(),
        cache_key=cache_key_for_mpn(mpn),
        source_line_ids=[f"{src.bom_id}:{src.id}" for src in row.source_lines],
    )
    return attach_storage_key(line)


def build_shop_lines(
    boms: list[BomDocument],
    inventory: InventoryDocument,
    view_mode: str,
    *,
    include_statuses: set[str] | None = None,
) -> list[ShopLine]:
    if include_statuses is None:
        include_statuses = {"missing", "partial"}

    lines: list[ShopLine] = []
    if view_mode == "combined":
        agg_rows, _ = compare_boms_aggregated(boms, inventory)
        for row in agg_rows:
            if row.status not in include_statuses:
                continue
            lines.append(_shop_line_from_aggregated(row))
    else:
        compare_rows, _ = compare_boms(boms, inventory)
        for row in compare_rows:
            if row.status not in include_statuses:
                continue
            lines.append(_shop_line_from_compare(row))

    lines.sort(key=lambda item: (item.status, item.primary_mpn.upper(), item.name.upper()))
    return lines


def refresh_line_lookup_fields(line: ShopLine) -> None:
    mpn = line.primary_mpn
    line.cache_key = cache_key_for_mpn(mpn)
    line.digikey_url = digikey_search_url(mpn)
    line.mouser_url = mouser_search_url(mpn)


def _apply_display_overrides(line: ShopLine, state: dict[str, Any]) -> None:
    if "mpn" in state:
        mpn = str(state.get("mpn", "")).strip()
        if mpn:
            line.primary_mpn = mpn
            refresh_line_lookup_fields(line)
    if "name" in state:
        name = str(state.get("name", "")).strip()
        if name:
            line.name = name
    parts = [line.name, line.primary_mpn, line.lib_ref, line.bom_id or line.bom_ids_display, line.designators]
    line.search_text = " ".join(p for p in parts if p).lower()


def sync_need_lines_mpn_name(source_line_ids: list[str], *, mpn: str, name: str | None) -> int:
    """Update underlying BOM need lines when MPN/name are corrected from Shop."""
    updated = 0
    seen: set[str] = set()
    for source_id in source_line_ids:
        if not source_id or source_id in seen or ":" not in source_id:
            continue
        seen.add(source_id)
        bom_id, line_id = source_id.split(":", 1)
        bom = storage.load_bom(bom_id)
        if bom is None:
            continue
        need_line = find_line(bom, line_id)
        if need_line is None:
            continue
        if mpn:
            need_line.lib_ref = mpn
        if name is not None:
            need_line.name = name
        storage.save_bom(bom)
        updated += 1
    return updated


def sync_need_lines_details(
    source_line_ids: list[str],
    *,
    mpn: str | None = None,
    name: str | None = None,
    manufacturer: str | None = None,
    datasheet_url: str | None = None,
    description: str | None = None,
    unit_price: float | None = None,
    stock: int | None = None,
    enriched_from: str = "",
) -> int:
    """Write enrichment fields (and optionally MPN/name) back to BOM need lines.

    Only non-None arguments are applied, so callers can update a subset of fields.
    Returns the number of need lines updated.
    """
    from datetime import datetime, timezone

    updated = 0
    seen: set[str] = set()
    now = datetime.now(timezone.utc).isoformat()
    for source_id in source_line_ids:
        if not source_id or source_id in seen or ":" not in source_id:
            continue
        seen.add(source_id)
        bom_id, line_id = source_id.split(":", 1)
        bom = storage.load_bom(bom_id)
        if bom is None:
            continue
        need_line = find_line(bom, line_id)
        if need_line is None:
            continue

        touched = False
        if mpn:
            need_line.lib_ref = mpn
            touched = True
        if name is not None:
            need_line.name = name
            touched = True
        if manufacturer is not None:
            need_line.manufacturer = manufacturer
            touched = True
        if datasheet_url is not None:
            need_line.datasheet_url = datasheet_url
            touched = True
        if description is not None:
            need_line.description = description
            touched = True
        if unit_price is not None:
            need_line.unit_price = unit_price
            touched = True
        if stock is not None:
            need_line.stock = stock
            touched = True
        if touched:
            need_line.enriched_from = enriched_from or need_line.enriched_from
            need_line.enriched_at = now
            storage.save_bom(bom)
            updated += 1
    return updated


def _apply_alternate_state(line: ShopLine, alt: dict[str, Any]) -> None:
    line.alternate.enabled = bool(alt.get("enabled"))
    if "mpn" in alt:
        line.alternate.mpn = str(alt.get("mpn", "")).strip()
    if "name" in alt:
        line.alternate.name = str(alt.get("name", "")).strip()
    if "notes" in alt:
        line.alternate.notes = str(alt.get("notes", ""))
    if "ordered" in alt:
        line.alternate.ordered = bool(alt.get("ordered"))
    if "buy_qty" in alt:
        try:
            line.alternate.buy_qty = max(0, int(alt["buy_qty"]))
        except (TypeError, ValueError):
            pass
    if "received_qty" in alt:
        try:
            line.alternate.received_qty = max(0, int(alt["received_qty"]))
        except (TypeError, ValueError):
            pass
    if line.alternate.enabled and not line.alternate.buy_qty:
        line.alternate.buy_qty = line.buy_qty or line.default_buy_qty


def merge_shop_state(lines: list[ShopLine], saved: dict[str, dict[str, Any]]) -> None:
    for line in lines:
        state = saved_state_for_line(saved, line)
        if not state:
            continue
        if "buy_qty" in state:
            try:
                line.buy_qty = max(0, int(state["buy_qty"]))
            except (TypeError, ValueError):
                pass
        if "notes" in state:
            line.notes = str(state.get("notes", ""))
        if "ordered" in state:
            line.ordered = bool(state.get("ordered"))
        if "received_qty" in state:
            try:
                line.received_qty = max(0, int(state["received_qty"]))
            except (TypeError, ValueError):
                pass
        _apply_display_overrides(line, state)
        alt = state.get("alternate")
        if isinstance(alt, dict):
            _apply_alternate_state(line, alt)
        if not line.buy_qty and line.default_buy_qty:
            line.buy_qty = line.default_buy_qty


def shop_stats(lines: list[ShopLine]) -> dict[str, int]:
    return {
        "line_count": len(lines),
        "total_buy_qty": sum(line.buy_qty for line in lines),
        "ordered_count": sum(1 for line in lines if line.ordered),
        "missing_count": sum(1 for line in lines if line.status == "missing"),
        "partial_count": sum(1 for line in lines if line.status == "partial"),
    }


def lines_to_saved_dict(lines: list[ShopLine]) -> dict[str, dict[str, Any]]:
    now = datetime.now(timezone.utc).isoformat()
    out: dict[str, dict[str, Any]] = {}
    for line in lines:
        key = line.storage_key or line.line_id
        entry: dict[str, Any] = {
            "buy_qty": line.buy_qty,
            "notes": line.notes,
            "ordered": line.ordered,
            "received_qty": line.received_qty,
            "updated_at": now,
        }
        if line.primary_mpn != primary_mpn(line.lib_ref):
            entry["mpn"] = line.primary_mpn
        if line.alternate.enabled or line.alternate.mpn or line.alternate.name:
            entry["alternate"] = {
                "enabled": line.alternate.enabled,
                "mpn": line.alternate.mpn,
                "name": line.alternate.name,
                "buy_qty": line.alternate.buy_qty,
                "notes": line.alternate.notes,
                "ordered": line.alternate.ordered,
                "received_qty": line.alternate.received_qty,
            }
        out[key] = entry
    return out


def _receive_targets(entry: dict[str, Any], *, alternate: bool) -> tuple[int, int]:
    if alternate:
        alt = entry.get("alternate") or {}
        buy_qty = int(alt.get("buy_qty") or entry.get("buy_qty") or 0)
        received_qty = int(alt.get("received_qty") or 0)
    else:
        buy_qty = int(entry.get("buy_qty") or 0)
        received_qty = int(entry.get("received_qty") or 0)
    return buy_qty, received_qty


def reset_received_qty(saved: dict[str, dict[str, Any]], storage_key: str, *, alternate: bool = False) -> dict[str, Any]:
    """Clear receive tracking so the user can receive again (does not change inventory)."""
    entry = dict(saved.get(storage_key, {}))
    if alternate:
        alt = dict(entry.get("alternate") or {})
        alt["received_qty"] = 0
        entry["alternate"] = alt
    else:
        entry["received_qty"] = 0
    entry["updated_at"] = datetime.now(timezone.utc).isoformat()
    saved[storage_key] = entry
    return receive_state_from_entry(entry, alternate=alternate)


def receive_shop_parts(
    saved: dict[str, dict[str, Any]],
    storage_key: str,
    qty: int,
    *,
    mpn: str,
    name: str = "",
    alternate: bool = False,
    location: str = "",
    notes: str = "",
) -> dict[str, Any]:
    """Move received quantity from shop line into inventory."""
    entry = dict(saved.get(storage_key, {}))
    buy_qty, received_qty = _receive_targets(entry, alternate=alternate)
    remaining = max(0, buy_qty - received_qty)

    if buy_qty <= 0:
        raise ValueError("Set buy quantity before receiving into inventory.")
    if qty <= 0:
        raise ValueError("Receive quantity must be at least 1.")
    if qty > remaining:
        raise ValueError(f"Cannot receive {qty}; only {remaining} left on this purchase line.")
    mpn = (mpn or "").strip()
    if not mpn:
        raise ValueError("MPN is required to add inventory.")

    doc = storage.load_inventory()
    item = add_qty_for_mpn(
        doc,
        lib_ref=mpn,
        qty=qty,
        name=name,
        location=location,
        notes=notes,
    )
    storage.save_inventory(doc)

    new_received = received_qty + qty
    if alternate:
        alt = dict(entry.get("alternate") or {})
        alt["received_qty"] = new_received
        entry["alternate"] = alt
    else:
        entry["received_qty"] = new_received
    entry["updated_at"] = datetime.now(timezone.utc).isoformat()
    saved[storage_key] = entry

    return {
        "received_qty": new_received,
        "buy_qty": buy_qty,
        "remaining_qty": max(0, buy_qty - new_received),
        "fully_received": buy_qty > 0 and new_received >= buy_qty,
        "inventory_qty": item.qty_on_hand,
        "inventory_id": item.id,
    }


def _merge_alternate_update(entry: dict[str, Any], alt_updates: dict[str, Any]) -> None:
    alt = dict(entry.get("alternate") or {})
    if "enabled" in alt_updates:
        alt["enabled"] = alt_updates["enabled"] in (True, "true", "on", "1", 1)
    if "mpn" in alt_updates:
        alt["mpn"] = str(alt_updates["mpn"]).strip()
    if "name" in alt_updates:
        alt["name"] = str(alt_updates["name"]).strip()
    if "notes" in alt_updates:
        alt["notes"] = str(alt_updates["notes"])
    if "ordered" in alt_updates:
        alt["ordered"] = alt_updates["ordered"] in (True, "true", "on", "1", 1)
    if "buy_qty" in alt_updates:
        try:
            alt["buy_qty"] = max(0, int(alt_updates["buy_qty"]))
        except (TypeError, ValueError):
            raise ValueError("Alternate buy qty must be a number.") from None
    if alt.get("enabled") and not alt.get("buy_qty"):
        alt["buy_qty"] = entry.get("buy_qty", 0)
    entry["alternate"] = alt


def apply_line_update(saved: dict[str, dict[str, Any]], storage_key: str, **updates) -> dict[str, dict[str, Any]]:
    entry = dict(saved.get(storage_key, {}))
    if "buy_qty" in updates:
        entry["buy_qty"] = max(0, int(updates["buy_qty"]))
    if "notes" in updates:
        entry["notes"] = str(updates["notes"])
    if "ordered" in updates:
        entry["ordered"] = bool(updates["ordered"])
    if "received_qty" in updates:
        entry["received_qty"] = max(0, int(updates["received_qty"]))
    if "alternate" in updates and isinstance(updates["alternate"], dict):
        alt_updates = updates["alternate"]
        if "received_qty" in alt_updates:
            alt = dict(entry.get("alternate") or {})
            alt["received_qty"] = max(0, int(alt_updates["received_qty"]))
            entry["alternate"] = alt
    if "mpn" in updates:
        entry["mpn"] = str(updates["mpn"]).strip()
    if "name" in updates:
        entry["name"] = str(updates["name"]).strip()
    if "alternate" in updates and isinstance(updates["alternate"], dict):
        _merge_alternate_update(entry, updates["alternate"])
    entry["updated_at"] = datetime.now(timezone.utc).isoformat()
    saved[storage_key] = entry
    return saved


def alternate_from_entry(entry: dict[str, Any]) -> dict[str, Any]:
    alt = entry.get("alternate")
    if not isinstance(alt, dict):
        return {}
    state = receive_state_from_entry(entry, alternate=True)
    return {
        "enabled": bool(alt.get("enabled")),
        "mpn": str(alt.get("mpn", "")),
        "name": str(alt.get("name", "")),
        "buy_qty": state["buy_qty"],
        "notes": str(alt.get("notes", "")),
        "ordered": bool(alt.get("ordered")),
        **state,
    }


def receive_state_from_entry(entry: dict[str, Any], *, alternate: bool = False) -> dict[str, Any]:
    buy_qty, received_qty = _receive_targets(entry, alternate=alternate)
    remaining = max(0, buy_qty - received_qty)
    return {
        "received_qty": received_qty,
        "buy_qty": buy_qty,
        "remaining_qty": remaining,
        "fully_received": buy_qty > 0 and received_qty >= buy_qty,
    }


def shop_to_csv(lines: list[ShopLine]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        [
            "MPN",
            "Alternates",
            "Name",
            "BuyQty",
            "QtyNeeded",
            "QtyOnHand",
            "Status",
            "BOM",
            "Designators",
            "Ordered",
            "Notes",
            "DigiKeyURL",
            "MouserURL",
        ]
    )
    for line in lines:
        writer.writerow(
            [
                line.primary_mpn,
                line.alternates_display,
                line.name,
                line.buy_qty,
                line.qty_needed,
                line.qty_on_hand,
                line.status,
                line.bom_id or line.bom_ids_display,
                line.designators,
                "Y" if line.ordered else "N",
                line.notes,
                line.digikey_url,
                line.mouser_url,
            ]
        )
        if line.alternate.enabled:
            writer.writerow(
                [
                    line.alternate.mpn,
                    "",
                    line.alternate.name or f"Alternate for {line.primary_mpn}",
                    line.alternate.buy_qty,
                    line.qty_needed,
                    "",
                    "alternate",
                    line.bom_id or line.bom_ids_display,
                    line.designators,
                    "Y" if line.alternate.ordered else "N",
                    line.alternate.notes,
                    line.alternate.digikey_url,
                    line.alternate.mouser_url,
                ]
            )
    return buffer.getvalue()
