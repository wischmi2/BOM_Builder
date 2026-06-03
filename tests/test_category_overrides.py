from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bom_builder import category_overrides as co
from bom_builder.category_overrides import group_compare_rows, set_override
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

    def test_clear_override_when_matches_auto(self) -> None:
        line = _line(designators=["R1"], lib_ref="RK73")
        from bom_builder.matcher import part_key_for_need_line

        key = part_key_for_need_line(line)
        set_override(key, "capacitor")
        set_override(key, "resistor", auto_category="resistor")
        self.assertEqual(co.load_overrides(), {})


if __name__ == "__main__":
    unittest.main()
