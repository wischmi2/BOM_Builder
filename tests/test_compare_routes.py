from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from main import app
from bom_builder import storage
from bom_builder.inventory_io import add_item
from bom_builder.parser import parse_bom_csv_file

SAMPLE_CSV = Path(
    r"C:\Brian\ProductionTest\Loadboard_Purchase_2026\DD02040\Parts_Purchase\DD02040.RF300.3_2026.csv"
)


class TestCompareRoutes(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._needs = storage.NEEDS_DIR
        self._data = storage.DATA_DIR
        self._inventory = storage.INVENTORY_PATH
        storage.DATA_DIR = Path(self._tmpdir.name) / "data"
        storage.NEEDS_DIR = storage.DATA_DIR / "needs"
        storage.INVENTORY_PATH = storage.DATA_DIR / "inventory.json"
        storage.ensure_data_dirs()
        self.client = app.test_client()

    def tearDown(self) -> None:
        storage.NEEDS_DIR = self._needs
        storage.DATA_DIR = self._data
        storage.INVENTORY_PATH = self._inventory
        self._tmpdir.cleanup()

    def test_compare_page_no_boms(self) -> None:
        response = self.client.get("/compare")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Import a BOM", response.data)

    @unittest.skipUnless(SAMPLE_CSV.exists(), "sample CSV not available")
    def test_compare_with_bom_and_inventory(self) -> None:
        bom = parse_bom_csv_file(SAMPLE_CSV)
        storage.save_bom(bom)
        first_line = bom.lines[0]
        doc = storage.load_inventory()
        add_item(doc, lib_ref=first_line.lib_ref, qty_on_hand=999)
        storage.save_inventory(doc)

        response = self.client.get(f"/compare?bom_id={bom.bom_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"summary-cards", response.data)
        self.assertIn(b"compare-table", response.data)

        response = self.client.get(f"/compare/export.csv?bom_id={bom.bom_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"NeedQty", response.data)
        self.assertIn(b"Status", response.data)


if __name__ == "__main__":
    unittest.main()
