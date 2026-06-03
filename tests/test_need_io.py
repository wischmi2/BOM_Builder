from __future__ import annotations

import unittest

from bom_builder.models import BomDocument, NeedLine
from bom_builder.need_io import bom_stats, bom_to_csv, merge_bom_state


def _line(line_id: str, *, acquired: bool = False, notes: str = "") -> NeedLine:
    return NeedLine(
        id=line_id,
        bom_id="test",
        name="R1",
        description="",
        designators=["R1"],
        footprint="R0402",
        lib_ref="PART1",
        quantity=1,
        acquired=acquired,
        notes=notes,
    )


class TestNeedIo(unittest.TestCase):
    def test_merge_preserves_acquired_state(self) -> None:
        existing = BomDocument(
            bom_id="test",
            source_filename="old.csv",
            lines=[_line("row-1", acquired=True, notes="ordered")],
        )
        incoming = BomDocument(
            bom_id="test",
            source_filename="new.csv",
            lines=[_line("row-1", acquired=False, notes="")],
        )
        merged = merge_bom_state(existing, incoming)
        self.assertTrue(merged.lines[0].acquired)
        self.assertEqual(merged.lines[0].notes, "ordered")

    def test_bom_stats_excludes_dni_from_active(self) -> None:
        bom = BomDocument(
            bom_id="test",
            source_filename="t.csv",
            lines=[
                _line("a", acquired=True),
                NeedLine(
                    id="b",
                    bom_id="test",
                    name="DNI",
                    description="",
                    designators=["C1"],
                    footprint="C0402",
                    lib_ref="X",
                    quantity=1,
                    is_dni=True,
                ),
            ],
        )
        stats = bom_stats(bom)
        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["dni"], 1)
        self.assertEqual(stats["active"], 1)
        self.assertEqual(stats["acquired"], 1)

    def test_bom_to_csv_includes_acquired_column(self) -> None:
        bom = BomDocument(
            bom_id="test",
            source_filename="t.csv",
            lines=[_line("a", acquired=True, notes="ok")],
        )
        csv_text = bom_to_csv(bom)
        self.assertIn("Acquired", csv_text)
        self.assertIn(",Y,", csv_text)
        self.assertIn("ok", csv_text)


if __name__ == "__main__":
    unittest.main()
