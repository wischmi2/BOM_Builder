from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field

from bom_builder.models import BomDocument, InventoryDocument, InventoryItem, NeedLine

_STATUS_ORDER = {"missing": 0, "partial": 1, "ok": 2, "dni": 3}


@dataclass
class CompareRow:
    need_line: NeedLine
    matched_inventory: list[InventoryItem] = field(default_factory=list)
    qty_needed: int = 0
    qty_on_hand: int = 0
    delta: int = 0
    status: str = "missing"
    match_type: str = "none"

    @property
    def matched_ids_display(self) -> str:
        if not self.matched_inventory:
            return ""
        parts = []
        for item in self.matched_inventory:
            label = item.location or item.id[:8]
            parts.append(f"{item.lib_ref}@{label}({item.qty_on_hand})")
        return "; ".join(parts)

    @property
    def part_key(self) -> str:
        return part_key_for_need_line(self.need_line)


@dataclass
class AggregatedCompareRow:
    """One row per unique part across all selected BOMs."""

    aggregate_key: str
    lib_ref: str
    name: str
    qty_needed_total: int = 0
    qty_on_hand: int = 0
    leftover: int = 0
    status: str = "missing"
    match_type: str = "none"
    is_dni: bool = False
    bom_ids: list[str] = field(default_factory=list)
    need_by_bom: dict[str, int] = field(default_factory=dict)
    matched_inventory: list[InventoryItem] = field(default_factory=list)
    source_lines: list[NeedLine] = field(default_factory=list)

    @property
    def bom_ids_display(self) -> str:
        return ", ".join(self.bom_ids)

    @property
    def need_breakdown_display(self) -> str:
        return "; ".join(f"{bom_id}: {qty}" for bom_id, qty in sorted(self.need_by_bom.items()))

    @property
    def matched_ids_display(self) -> str:
        if not self.matched_inventory:
            return ""
        parts = []
        for item in self.matched_inventory:
            label = item.location or item.id[:8]
            parts.append(f"{item.lib_ref}@{label}({item.qty_on_hand})")
        return "; ".join(parts)


def normalize_key(value: str) -> str:
    if not value:
        return ""
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def split_lib_refs(lib_ref: str) -> list[str]:
    return [part.strip() for part in lib_ref.split(",") if part.strip()]


def _build_inventory_indexes(
    items: list[InventoryItem],
) -> tuple[dict[str, list[InventoryItem]], dict[str, list[InventoryItem]]]:
    by_lib_ref: dict[str, list[InventoryItem]] = {}
    by_name: dict[str, list[InventoryItem]] = {}
    for item in items:
        lib_key = normalize_key(item.lib_ref)
        if lib_key:
            by_lib_ref.setdefault(lib_key, []).append(item)
        name_key = normalize_key(item.name)
        if name_key:
            by_name.setdefault(name_key, []).append(item)
    return by_lib_ref, by_name


def _match_inventory(
    line: NeedLine,
    by_lib_ref: dict[str, list[InventoryItem]],
    by_name: dict[str, list[InventoryItem]],
) -> tuple[list[InventoryItem], str]:
    seen_ids: set[str] = set()
    matched: list[InventoryItem] = []

    for segment in split_lib_refs(line.lib_ref):
        lib_key = normalize_key(segment)
        if not lib_key:
            continue
        for item in by_lib_ref.get(lib_key, []):
            if item.id not in seen_ids:
                seen_ids.add(item.id)
                matched.append(item)

    if matched:
        return matched, "lib_ref"

    if line.name and not line.is_dni:
        name_key = normalize_key(line.name)
        if name_key:
            for item in by_name.get(name_key, []):
                if item.id not in seen_ids:
                    seen_ids.add(item.id)
                    matched.append(item)
            if matched:
                return matched, "name"

    return [], "none"


def _aggregate_key(line: NeedLine) -> str:
    segments = split_lib_refs(line.lib_ref)
    if segments:
        return "lib:" + normalize_key(segments[0])
    if line.name:
        return "name:" + normalize_key(line.name)
    return f"id:{line.id}"


def part_key_for_need_line(line: NeedLine) -> str:
    return _aggregate_key(line)


def part_key_for_compare_row(row: CompareRow) -> str:
    return row.part_key


def _status_for(qty_needed: int, qty_on_hand: int, is_dni: bool) -> str:
    if is_dni:
        return "dni"
    if qty_on_hand >= qty_needed:
        return "ok"
    if qty_on_hand > 0:
        return "partial"
    return "missing"


def compare_boms(
    boms: list[BomDocument],
    inventory: InventoryDocument,
) -> tuple[list[CompareRow], list[InventoryItem]]:
    by_lib_ref, by_name = _build_inventory_indexes(inventory.items)
    rows: list[CompareRow] = []
    matched_item_ids: set[str] = set()

    for bom in boms:
        for line in bom.lines:
            matched, match_type = _match_inventory(line, by_lib_ref, by_name)
            for item in matched:
                matched_item_ids.add(item.id)

            qty_on_hand = sum(item.qty_on_hand for item in matched)
            qty_needed = line.quantity
            status = _status_for(qty_needed, qty_on_hand, line.is_dni)

            rows.append(
                CompareRow(
                    need_line=line,
                    matched_inventory=matched,
                    qty_needed=qty_needed,
                    qty_on_hand=qty_on_hand,
                    delta=qty_on_hand - qty_needed,
                    status=status,
                    match_type=match_type,
                )
            )

    from bom_builder.part_categories import sort_compare_rows

    rows = sort_compare_rows(rows)

    extra = [item for item in inventory.items if item.id not in matched_item_ids]
    extra.sort(key=lambda i: i.lib_ref.upper())
    return rows, extra


def compare_boms_aggregated(
    boms: list[BomDocument],
    inventory: InventoryDocument,
) -> tuple[list[AggregatedCompareRow], list[InventoryItem]]:
    """Sum need per unique part across BOMs, compare once against inventory."""
    by_lib_ref, by_name = _build_inventory_indexes(inventory.items)

    @dataclass
    class _Bucket:
        key: str
        lib_ref: str
        name: str
        lines: list[NeedLine] = field(default_factory=list)
        qty_needed_total: int = 0
        need_by_bom: dict[str, int] = field(default_factory=dict)
        all_dni: bool = True

    buckets: dict[str, _Bucket] = {}

    for bom in boms:
        for line in bom.lines:
            key = _aggregate_key(line)
            if key not in buckets:
                buckets[key] = _Bucket(key=key, lib_ref=line.lib_ref, name=line.name)
            bucket = buckets[key]
            bucket.lines.append(line)
            if not line.is_dni:
                bucket.all_dni = False
                bucket.qty_needed_total += line.quantity
                bucket.need_by_bom[bom.bom_id] = bucket.need_by_bom.get(bom.bom_id, 0) + line.quantity
                bucket.lib_ref = line.lib_ref
                bucket.name = line.name

    rows: list[AggregatedCompareRow] = []
    matched_item_ids: set[str] = set()

    for bucket in buckets.values():
        representative = next((line for line in bucket.lines if not line.is_dni), bucket.lines[0])
        matched, match_type = _match_inventory(representative, by_lib_ref, by_name)
        for item in matched:
            matched_item_ids.add(item.id)

        qty_on_hand = sum(item.qty_on_hand for item in matched)
        qty_needed = bucket.qty_needed_total
        is_dni = bucket.all_dni
        leftover = qty_on_hand - qty_needed
        status = _status_for(qty_needed, qty_on_hand, is_dni)

        rows.append(
            AggregatedCompareRow(
                aggregate_key=bucket.key,
                lib_ref=bucket.lib_ref,
                name=bucket.name,
                qty_needed_total=qty_needed,
                qty_on_hand=qty_on_hand,
                leftover=leftover,
                status=status,
                match_type=match_type,
                is_dni=is_dni,
                bom_ids=sorted({line.bom_id for line in bucket.lines}),
                need_by_bom=dict(bucket.need_by_bom),
                matched_inventory=matched,
                source_lines=bucket.lines,
            )
        )

    from bom_builder.part_categories import sort_aggregated_rows

    rows = sort_aggregated_rows(rows)
    extra = [item for item in inventory.items if item.id not in matched_item_ids]
    extra.sort(key=lambda i: i.lib_ref.upper())
    return rows, extra


@dataclass
class CompareSummary:
    total: int = 0
    ok: int = 0
    partial: int = 0
    missing: int = 0
    dni: int = 0


def compare_summary(rows: list[CompareRow]) -> CompareSummary:
    return _summary_from_statuses(row.status for row in rows)


def compare_summary_aggregated(rows: list[AggregatedCompareRow]) -> CompareSummary:
    summary = _summary_from_statuses(row.status for row in rows)
    summary.total = len(rows)
    return summary


def _summary_from_statuses(statuses) -> CompareSummary:
    summary = CompareSummary()
    for status in statuses:
        summary.total += 1
        if status == "ok":
            summary.ok += 1
        elif status == "partial":
            summary.partial += 1
        elif status == "dni":
            summary.dni += 1
        else:
            summary.missing += 1
    return summary


def compare_to_csv(rows: list[CompareRow]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        ["LibRef", "Name", "NeedQty", "OnHand", "Delta", "Status", "BOM", "Designators", "MatchType", "MatchedInventory"]
    )
    for row in rows:
        line = row.need_line
        writer.writerow(
            [
                line.lib_ref,
                line.name,
                row.qty_needed,
                row.qty_on_hand,
                row.delta,
                row.status,
                line.bom_id,
                line.designator_display,
                row.match_type,
                row.matched_ids_display,
            ]
        )
    return buffer.getvalue()


def compare_aggregated_to_csv(rows: list[AggregatedCompareRow]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        [
            "LibRef",
            "Name",
            "TotalNeedQty",
            "OnHand",
            "Leftover",
            "Status",
            "BOMs",
            "NeedByBOM",
            "MatchType",
            "MatchedInventory",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row.lib_ref,
                row.name,
                row.qty_needed_total,
                row.qty_on_hand,
                row.leftover,
                row.status,
                row.bom_ids_display,
                row.need_breakdown_display,
                row.match_type,
                row.matched_ids_display,
            ]
        )
    return buffer.getvalue()
