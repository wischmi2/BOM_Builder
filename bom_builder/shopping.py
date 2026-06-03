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
    split_lib_refs,
)
from bom_builder.models import BomDocument, InventoryDocument


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
    digikey_url: str = ""
    mouser_url: str = ""
    search_text: str = ""
    cache_key: str = ""

    @property
    def alternates_extra(self) -> bool:
        return bool(self.alternates_display)


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


def digikey_search_url(mpn: str) -> str:
    keyword = quote((mpn or "").strip(), safe="")
    return f"https://www.digikey.com/en/products/result?keywords={keyword}"


def mouser_search_url(mpn: str) -> str:
    keyword = quote((mpn or "").strip(), safe="")
    return f"https://www.mouser.com/c/?q={keyword}"


def _shop_line_from_compare(row: CompareRow) -> ShopLine:
    line = row.need_line
    mpn = primary_mpn(line.lib_ref)
    default_buy = shortfall_qty(row.qty_needed, row.qty_on_hand)
    search_parts = [line.name, line.lib_ref, line.designator_display, line.bom_id]
    return ShopLine(
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


def _shop_line_from_aggregated(row: AggregatedCompareRow) -> ShopLine:
    mpn = primary_mpn(row.lib_ref)
    default_buy = shortfall_qty(row.qty_needed_total, row.qty_on_hand)
    search_parts = [row.name, row.lib_ref, row.bom_ids_display]
    return ShopLine(
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
    )


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


def merge_shop_state(lines: list[ShopLine], saved: dict[str, dict[str, Any]]) -> None:
    for line in lines:
        state = saved.get(line.line_id)
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
    return {
        line.line_id: {
            "buy_qty": line.buy_qty,
            "notes": line.notes,
            "ordered": line.ordered,
            "updated_at": now,
        }
        for line in lines
    }


def apply_line_update(saved: dict[str, dict[str, Any]], line_id: str, **updates) -> dict[str, dict[str, Any]]:
    entry = dict(saved.get(line_id, {}))
    if "buy_qty" in updates:
        entry["buy_qty"] = max(0, int(updates["buy_qty"]))
    if "notes" in updates:
        entry["notes"] = str(updates["notes"])
    if "ordered" in updates:
        entry["ordered"] = bool(updates["ordered"])
    entry["updated_at"] = datetime.now(timezone.utc).isoformat()
    saved[line_id] = entry
    return saved


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
    return buffer.getvalue()
