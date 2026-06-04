from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bom_builder import category_overrides as co
from bom_builder.category_overrides import group_compare_rows, group_inventory_items, group_need_lines, group_shop_lines, set_override
from bom_builder.shopping import ShopLine
from bom_builder.models import InventoryItem
from bom_builder.models import NeedLine
from bom_builder.part_categories import classify_need_line


def _line(*, designators: list[str] | None = None, lib_ref: str = "PART1") -> NeedLine:
    return NeedLine(
        id="n1",
        bom_id="bom1",
        name="10K",
        description="",
        designators=designators or ["R1"],
        footprint="",
        lib_ref=lib_ref,
        quantity=1,
    )


class TestCategoryOverrides(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path_patch = mock.patch.object(co, "OVERRIDES_PATH", Path(self.tmp.name) / "overrides.json")
        self.path_patch.start()

    def tearDown(self) -> None:
        self.path_patch.stop()
        self.tmp.cleanup()

    def test_override_moves_part_to_new_category(self) -> None:
        from bom_builder.matcher import CompareRow

        row = CompareRow(need_line=_line(designators=["R1"], lib_ref="RK73"))
        auto = classify_need_line(row.need_line)
        self.assertEqual(auto, "resistor")

        set_override(row.part_key, "capacitor")
        groups = group_compare_rows([row], co.load_overrides())
        by_id = {g.category_id: g for g in groups}
        self.assertEqual(len(by_id["capacitor"].rows), 1)
        self.assertEqual(len(by_id["resistor"].rows), 0)

    def test_inventory_grouping_puts_resistors_first(self) -> None:
        items = [
            InventoryItem(id="1", lib_ref="GRM155", name="0.1UF"),
            InventoryItem(id="2", lib_ref="RK73H1", name="10K OHM"),
        ]
        groups = group_inventory_items(items)
        labels = [g.label for g in groups if g.rows]
        self.assertEqual(labels[0], "Resistors")
        self.assertIn("Capacitors", labels)

    def test_need_grouping_uses_designator_rules(self) -> None:
        r_line = _line(designators=["R1"], lib_ref="RK73")
        c_line = _line(designators=["C1"], lib_ref="GRM155")
        c_line.name = "0.1UF"
        lines = [r_line, c_line]
        groups = group_need_lines(lines)
        labels = [g.label for g in groups if g.rows]
        self.assertEqual(labels[0], "Resistors")
        self.assertIn("Capacitors", labels)

    def test_shop_grouping_uses_same_categories(self) -> None:
        lines = [
            ShopLine(
                line_id="lib:RK73",
                lib_ref="RK73",
                primary_mpn="RK73",
                alternates_display="",
                name="10K OHM",
                status="missing",
                qty_needed=10,
                qty_on_hand=0,
                default_buy_qty=10,
                buy_qty=10,
            ),
            ShopLine(
                line_id="lib:GRM155",
                lib_ref="GRM155",
                primary_mpn="GRM155",
                alternates_display="",
                name="0.1UF",
                status="missing",
                qty_needed=5,
                qty_on_hand=0,
                default_buy_qty=5,
                buy_qty=5,
            ),
        ]
        groups = group_shop_lines(lines)
        labels = [g.label for g in groups if g.rows]
        self.assertEqual(labels[0], "Resistors")
        self.assertIn("Capacitors", labels)

    def test_clear_override_when_matches_auto(self) -> None:
        line = _line(designators=["R1"], lib_ref="RK73")
        from bom_builder.matcher import part_key_for_need_line

        key = part_key_for_need_line(line)
        set_override(key, "capacitor")
        set_override(key, "resistor", auto_category="resistor")
        self.assertEqual(co.load_overrides(), {})


if __name__ == "__main__":
    unittest.main()
