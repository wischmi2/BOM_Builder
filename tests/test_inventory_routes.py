from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path

from main import app
from bom_builder import storage

SAMPLE_CSV = Path(
    r"C:\Brian\ProductionTest\Loadboard_Purchase_2026\DD02040\Parts_Purchase\DD02040.RF300.3_2026.csv"
)


class TestInventoryRoutes(unittest.TestCase):
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

    def test_inventory_page_empty(self) -> None:
        response = self.client.get("/inventory")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Add to inventory", response.data)

    def test_add_update_delete(self) -> None:
        response = self.client.post(
            "/inventory/add",
            data={
                "lib_ref": "GRM155R71H104KE14J",
                "name": "0.1uF",
                "qty_on_hand": "25",
                "location": "Bin 1",
                "notes": "reel",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        doc = storage.load_inventory()
        self.assertEqual(len(doc.items), 1)
        item_id = doc.items[0].id

        response = self.client.post(
            f"/inventory/{item_id}",
            json={"qty_on_hand": 30},
            headers={"Accept": "application/json"},
        )
        self.assertEqual(response.status_code, 200)
        doc = storage.load_inventory()
        self.assertEqual(doc.items[0].qty_on_hand, 30)

        response = self.client.post(
            f"/inventory/{item_id}",
            json={"action": "delete"},
            headers={"Accept": "application/json"},
        )
        self.assertEqual(response.status_code, 200)
        doc = storage.load_inventory()
        self.assertEqual(len(doc.items), 0)

    def test_import_and_export_csv(self) -> None:
        csv_body = "LibRef,Name,QtyOnHand,Location,Notes\nABC123,Part,5,Shelf,\n"
        response = self.client.post(
            "/inventory/import",
            data={"inventory_file": (io.BytesIO(csv_body.encode()), "inv.csv")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        doc = storage.load_inventory()
        self.assertEqual(len(doc.items), 1)

        response = self.client.get("/inventory/export.csv")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"ABC123", response.data)

    def test_search_filter(self) -> None:
        self.client.post(
            "/inventory/add",
            data={"lib_ref": "PART-A", "qty_on_hand": "1"},
        )
        self.client.post(
            "/inventory/add",
            data={"lib_ref": "PART-B", "qty_on_hand": "1"},
        )
        response = self.client.get("/inventory?q=part-a")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"PART-A", response.data)
        self.assertNotIn(b"PART-B", response.data)


if __name__ == "__main__":
    unittest.main()
