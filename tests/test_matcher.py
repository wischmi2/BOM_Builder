from __future__ import annotations

import unittest

from bom_builder.matcher import (
    compare_boms,
    compare_summary,
    compare_to_csv,
    normalize_key,
)
from bom_builder.models import BomDocument, InventoryDocument, InventoryItem, NeedLine


def _need(lib_ref: str, qty: int = 1, *, name: str = "10k", is_dni: bool = False) -> NeedLine:
    return NeedLine(
        id="n1",
        bom_id="bom1",
        name=name,
        description="",
        designators=["R1"],
        footprint="R0402",
        lib_ref=lib_ref,
        quantity=qty,
        is_dni=is_dni,
    )


class TestMatcher(unittest.TestCase):
    def test_normalize_key_strips_punctuation(self) -> None:
        self.assertEqual(normalize_key("GRM-155R71H104"), normalize_key("grm155r71h104"))

    def test_ok_when_enough_stock(self) -> None:
        bom = BomDocument("bom1", "t.csv", [_need("PART123", qty=5)])
        inv = InventoryDocument(
            items=[InventoryItem(id="i1", lib_ref="PART123", qty_on_hand=10)]
        )
        rows, extra = compare_boms([bom], inv)
        self.assertEqual(rows[0].status, "ok")
        self.assertEqual(rows[0].qty_on_hand, 10)
        self.assertEqual(extra, [])

    def test_partial_and_missing(self) -> None:
        bom = BomDocument(
            "bom1",
            "t.csv",
            [_need("PART-A", qty=10), _need("PART-B", qty=3)],
        )
        inv = InventoryDocument(
            items=[
                InventoryItem(id="i1", lib_ref="PART-A", qty_on_hand=4),
                InventoryItem(id="i2", lib_ref="PART-B", qty_on_hand=0),
            ]
        )
        rows, _ = compare_boms([bom], inv)
        by_ref = {r.need_line.lib_ref: r for r in rows}
        self.assertEqual(by_ref["PART-A"].status, "partial")
        self.assertEqual(by_ref["PART-B"].status, "missing")

    def test_multi_mpn_libref(self) -> None:
        bom = BomDocument(
            "bom1",
            "t.csv",
            [_need("GRM111, GRM222", qty=2)],
        )
        inv = InventoryDocument(
            items=[InventoryItem(id="i1", lib_ref="GRM222", qty_on_hand=5)]
        )
        rows, _ = compare_boms([bom], inv)
        self.assertEqual(rows[0].status, "ok")
        self.assertEqual(rows[0].match_type, "lib_ref")

    def test_dni_status(self) -> None:
        bom = BomDocument("bom1", "t.csv", [_need("X", is_dni=True)])
        rows, _ = compare_boms([bom], InventoryDocument())
        self.assertEqual(rows[0].status, "dni")

    def test_name_fallback_match(self) -> None:
        bom = BomDocument("bom1", "t.csv", [_need("", qty=1, name="UniqueCap")])
        inv = InventoryDocument(
            items=[InventoryItem(id="i1", lib_ref="OTHER", name="UniqueCap", qty_on_hand=2)]
        )
        rows, _ = compare_boms([bom], inv)
        self.assertEqual(rows[0].status, "ok")
        self.assertEqual(rows[0].match_type, "name")

    def test_extra_inventory(self) -> None:
        bom = BomDocument("bom1", "t.csv", [_need("ON-BOM")])
        inv = InventoryDocument(
            items=[
                InventoryItem(id="i1", lib_ref="ON-BOM", qty_on_hand=1),
                InventoryItem(id="i2", lib_ref="OFF-BOM", qty_on_hand=1),
            ]
        )
        _, extra = compare_boms([bom], inv)
        self.assertEqual(len(extra), 1)
        self.assertEqual(extra[0].lib_ref, "OFF-BOM")

    def test_summary_and_csv(self) -> None:
        bom = BomDocument("bom1", "t.csv", [_need("P1"), _need("P2")])
        inv = InventoryDocument(
            items=[InventoryItem(id="i1", lib_ref="P1", qty_on_hand=1)]
        )
        rows, _ = compare_boms([bom], inv)
        summary = compare_summary(rows)
        self.assertEqual(summary.missing, 1)
        self.assertEqual(summary.ok, 1)
        csv_text = compare_to_csv(rows)
        self.assertIn("NeedQty", csv_text)
        self.assertIn("P2", csv_text)


if __name__ == "__main__":
    unittest.main()
