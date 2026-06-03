from __future__ import annotations

import unittest

from bom_builder.inventory_io import (
    add_item,
    delete_item,
    inventory_to_csv,
    merge_import,
    parse_inventory_csv,
)
from bom_builder.models import InventoryDocument


class TestInventoryIo(unittest.TestCase):
    def test_add_requires_lib_ref(self) -> None:
        doc = InventoryDocument()
        with self.assertRaises(ValueError):
            add_item(doc, lib_ref="  ")

    def test_parse_and_export_csv(self) -> None:
        csv_text = "LibRef,Name,QtyOnHand,Location,Notes\nPART1,Cap,10,Bin A,ok\n"
        rows = parse_inventory_csv(csv_text)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["qty_on_hand"], 10)

        doc = InventoryDocument()
        add_item(doc, lib_ref="PART1", name="Cap", qty_on_hand=10, location="Bin A", notes="ok")
        exported = inventory_to_csv(doc)
        self.assertIn("PART1", exported)
        self.assertIn("QtyOnHand", exported)

    def test_merge_import_updates_by_location(self) -> None:
        doc = InventoryDocument()
        add_item(doc, lib_ref="PART1", qty_on_hand=5, location="Bin A")
        added, updated = merge_import(
            doc,
            [{"lib_ref": "PART1", "name": "", "qty_on_hand": 20, "location": "Bin A", "notes": ""}],
        )
        self.assertEqual(added, 0)
        self.assertEqual(updated, 1)
        self.assertEqual(doc.items[0].qty_on_hand, 20)

    def test_merge_import_adds_new_location(self) -> None:
        doc = InventoryDocument()
        add_item(doc, lib_ref="PART1", location="Bin A")
        added, updated = merge_import(
            doc,
            [{"lib_ref": "PART1", "name": "", "qty_on_hand": 3, "location": "Bin B", "notes": ""}],
        )
        self.assertEqual(added, 1)
        self.assertEqual(updated, 0)
        self.assertEqual(len(doc.items), 2)

    def test_delete_item(self) -> None:
        doc = InventoryDocument()
        item = add_item(doc, lib_ref="X")
        self.assertTrue(delete_item(doc, item.id))
        self.assertEqual(len(doc.items), 0)


if __name__ == "__main__":
    unittest.main()
