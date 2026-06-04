from __future__ import annotations

import re
from dataclasses import dataclass
from bom_builder.models import InventoryItem, NeedLine

# Display order on Compare page
CATEGORY_ORDER: list[tuple[str, str]] = [
    ("resistor", "Resistors"),
    ("capacitor", "Capacitors"),
    ("inductor", "Inductors"),
    ("semiconductor", "Semiconductors"),
    ("connector", "Connectors"),
    ("filter_rf", "Filters / Couplers"),
    ("test_point", "Test Points"),
    ("mechanical", "Mechanical"),
    ("other", "Other"),
    ("dni", "DNI"),
]

_CATEGORY_RANK = {cat_id: index for index, (cat_id, _) in enumerate(CATEGORY_ORDER)}


@dataclass
class CompareGroup:
    category_id: str
    label: str
    rows: list


def classify_need_line(line: NeedLine) -> str:
    if line.is_dni:
        return "dni"

    name = line.name or ""
    description = line.description or ""
    footprint = line.footprint or ""
    lib_ref = line.lib_ref or ""
    text = f"{name} {description} {footprint} {lib_ref}".upper()

    designator = line.designators[0].upper() if line.designators else ""

    if _matches_resistor(text, designator):
        return "resistor"
    if _matches_capacitor(text, designator):
        return "capacitor"
    if _matches_inductor(text, designator):
        return "inductor"
    if _matches_connector(text, designator):
        return "connector"
    if _matches_filter_rf(text):
        return "filter_rf"
    if _matches_test_point(text, designator):
        return "test_point"
    if _matches_semiconductor(text, designator):
        return "semiconductor"
    if _matches_mechanical(text):
        return "mechanical"
    return "other"


def category_for_compare_row(row) -> str:
    return classify_need_line(row.need_line)


def category_for_aggregated_row(row) -> str:
    if row.is_dni:
        return "dni"
    for line in row.source_lines:
        if not line.is_dni:
            return classify_need_line(line)
    if row.source_lines:
        return classify_need_line(row.source_lines[0])
    return classify_from_text(row.name, row.lib_ref, "")


def category_for_inventory_item(item: InventoryItem) -> str:
    return classify_from_text(item.name, item.lib_ref, "")


def category_for_shop_line(line) -> str:
    return classify_from_text(line.name, line.lib_ref, "")


def category_for_need_line(line: NeedLine) -> str:
    return classify_need_line(line)


def classify_from_text(name: str, lib_ref: str, footprint: str) -> str:
    fake = NeedLine(
        id="x",
        bom_id="x",
        name=name,
        description="",
        designators=[],
        footprint=footprint,
        lib_ref=lib_ref,
        quantity=1,
    )
    return classify_need_line(fake)


def _matches_resistor(text: str, designator: str) -> bool:
    if designator.startswith("R") and designator[1:2].isdigit():
        return True
    return bool(
        re.search(r"\bRES\b", text)
        or re.search(r"\b\d+\s*OHM\b", text)
        or re.search(r"\bOHMS?\b", text)
        or "RK73" in text
        or "CRG0" in text
        or "ERA-" in text
        or re.search(r"\b\d+K\s*OHM", text)
    )


def _matches_capacitor(text: str, designator: str) -> bool:
    if designator.startswith("C") and len(designator) > 1 and designator[1].isdigit():
        return True
    return bool(
        re.search(r"\bCAP\b", text)
        or re.search(r"\b\d+\s*UF\b", text)
        or re.search(r"\b\d+\s*PF\b", text)
        or re.search(r"\b\d+\s*NF\b", text)
        or "GRM" in text
        or "GCM" in text
        or "GCJ" in text
        or "TPSA" in text
        or "TANT" in text
    )


def _matches_inductor(text: str, designator: str) -> bool:
    if designator.startswith("L") and len(designator) > 1 and designator[1].isdigit():
        return True
    return bool(
        re.search(r"\bIND\b", text)
        or re.search(r"\b\d+\s*NH\b", text)
        or re.search(r"\b\d+\s*UH\b", text)
        or "INDUCTOR" in text
        or "WIREWOUND" in text
        or "LQP03" in text
    )


def _matches_semiconductor(text: str, designator: str) -> bool:
    if designator.startswith(("U", "Q", "D", "MO")):
        return True
    return bool(
        re.search(r"\b(IC|MOSFET|TRANSISTOR|DIODE|REGULATOR|ADC|DAC|MCU)\b", text)
        or re.search(r"\bADL\d", text)
        or re.search(r"\bHMC\d", text)
        or "MOSFET" in text
    )


def _matches_connector(text: str, designator: str) -> bool:
    if designator.startswith(("J", "P", "JP")):
        return True
    return bool(
        re.search(r"\b(CONN|CONNECTOR|SMA|HEADER|SAMTEC)\b", text)
        or "SMA" in text
        or "HDR" in text
    )


def _matches_filter_rf(text: str) -> bool:
    return bool(
        re.search(r"\b(FILTER|COUPLER|LPF|BPF|ATTENUATOR)\b", text)
        or "LFCN" in text
        or "DCW-" in text
        or "PE42553" in text
    )


def _matches_test_point(text: str, designator: str) -> bool:
    if designator.startswith("TP"):
        return True
    return "TEST POINT" in text or designator.startswith("TP")


def _matches_mechanical(text: str) -> bool:
    return bool(
        re.search(r"\b(MOUSE_BITE|BOLT|SCREW|STANDOFF|HEATSINK)\b", text)
        or "MOUSE_BITES" in text
    )


def _status_rank(status: str) -> int:
    return {"missing": 0, "partial": 1, "ok": 2, "dni": 3}.get(status, 9)


def sort_compare_rows(rows: list) -> list:
    return sorted(
        rows,
        key=lambda r: (
            _CATEGORY_RANK.get(category_for_compare_row(r), 99),
            _status_rank(r.status),
            r.need_line.lib_ref.upper(),
            r.need_line.name.upper(),
        ),
    )


def sort_aggregated_rows(rows: list) -> list:
    return sorted(
        rows,
        key=lambda r: (
            _CATEGORY_RANK.get(category_for_aggregated_row(r), 99),
            _status_rank(r.status),
            r.lib_ref.upper(),
            r.name.upper(),
        ),
    )


def sort_inventory_items(items: list) -> list:
    return sorted(items, key=lambda i: (i.lib_ref.upper(), i.location.upper(), i.name.upper()))


def sort_shop_lines(lines: list) -> list:
    return sorted(
        lines,
        key=lambda line: (
            _status_rank(line.status),
            line.primary_mpn.upper(),
            line.name.upper(),
        ),
    )


def sort_need_lines(lines: list) -> list:
    return sorted(
        lines,
        key=lambda line: (
            line.acquired,
            line.is_dni,
            (line.designators[0].upper() if line.designators else ""),
            line.lib_ref.upper(),
            line.name.upper(),
        ),
    )


