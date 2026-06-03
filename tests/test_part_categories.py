from __future__ import annotations

import unittest

from bom_builder.matcher import compare_boms
from bom_builder.models import BomDocument, InventoryDocument, NeedLine
from bom_builder.category_overrides import group_compare_rows
from bom_builder.part_categories import CATEGORY_ORDER, classify_need_line


def _line(
    *,
    designators: list[str] | None = None,
    name: str = "",
    lib_ref: str = "",
    is_dni: bool = False,
) -> NeedLine:
    return NeedLine(
        id="n1",
        bom_id="bom1",
        name=name,
        description="",
        designators=designators or [],
        footprint="",
        lib_ref=lib_ref,
        quantity=1,
        is_dni=is_dni,
    )


class TestPartCategories(unittest.TestCase):
    def test_designator_prefixes(self) -> None:
        self.assertEqual(classify_need_line(_line(designators=["R12"])), "resistor")
        self.assertEqual(classify_need_line(_line(designators=["C3"])), "capacitor")
        self.assertEqual(classify_need_line(_line(designators=["L1"])), "inductor")

    def test_dni_category(self) -> None:
        self.assertEqual(classify_need_line(_line(is_dni=True)), "dni")

    def test_passive_keywords(self) -> None:
        self.assertEqual(
            classify_need_line(_line(name="10K OHM", lib_ref="RK73H1ETTP1002F")),
            "resistor",
        )
        self.assertEqual(
            classify_need_line(_line(name="0.1UF", lib_ref="GRM155R71H104")),
            "capacitor",
        )

    def test_group_order_puts_passives_first(self) -> None:
        lines = [
            _line(designators=["U1"], name="ADC", lib_ref="ADL5902"),
            _line(designators=["C1"], name="0.1UF", lib_ref="GRM155"),
            _line(designators=["R1"], name="10K", lib_ref="RK73"),
            _line(designators=["L1"], name="1NH", lib_ref="LQP03"),
        ]
        bom = BomDocument("bom1", "t.csv", lines)
        rows, _ = compare_boms([bom], InventoryDocument())
        groups = group_compare_rows(rows)
        labels = [g.label for g in groups]
        self.assertEqual(labels[:3], ["Resistors", "Capacitors", "Inductors"])
        self.assertIn("Semiconductors", labels)

    def test_category_order_matches_display_list(self) -> None:
        passive_ids = [cat for cat, _ in CATEGORY_ORDER[:3]]
        self.assertEqual(passive_ids, ["resistor", "capacitor", "inductor"])


if __name__ == "__main__":
    unittest.main()
