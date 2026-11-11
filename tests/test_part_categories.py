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

    def test_led_category(self) -> None:
        self.assertEqual(classify_need_line(_line(designators=["LED1"])), "led")
        # D-designated LEDs are found by description or LED part series
        self.assertEqual(
            classify_need_line(_line(designators=["D3"], name="Red 631nm LED Indication - Discrete 2V 0603")),
            "led",
        )
        self.assertEqual(classify_need_line(_line(designators=["D1"], lib_ref="LTST-C171GKT")), "led")
        # Diodes and LED driver ICs stay semiconductors; LED current resistors stay resistors
        self.assertEqual(classify_need_line(_line(designators=["D2"], lib_ref="SS14")), "semiconductor")
        self.assertEqual(classify_need_line(_line(designators=["U4"], name="LED DRIVER IC")), "semiconductor")
        self.assertEqual(classify_need_line(_line(designators=["R9"], name="LED current limit")), "resistor")
        self.assertIn("led", dict(CATEGORY_ORDER))

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

    def test_enclosure_hardware_is_mechanical(self) -> None:
        for name in [
            "M2.5 brass heat-set insert, 4 mm L x 4 mm OD",
            "2 mm silicone o-ring cord, 70A, 10 ft",
            "Adhesive ePTFE breathable vent membrane, 100 sheets",
            "Nylon M6 x 30 thumbscrew (spade head)",
            "Nylon M6 hex nut, white",
            "Nylon M2.5 M-F hex standoff, 8 mm",
        ]:
            self.assertEqual(classify_need_line(_line(name=name, lib_ref="B0XXXXXXXX")), "mechanical", name)

    def test_category_order_matches_display_list(self) -> None:
        passive_ids = [cat for cat, _ in CATEGORY_ORDER[:3]]
        self.assertEqual(passive_ids, ["resistor", "capacitor", "inductor"])


if __name__ == "__main__":
    unittest.main()
