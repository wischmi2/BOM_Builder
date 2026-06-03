from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from main import app
from bom_builder import storage
from bom_builder.parser import parse_bom_csv_file

SAMPLE_CSV = Path(
    r"C:\Brian\ProductionTest\Loadboard_Purchase_2026\DD02040\Parts_Purchase\DD02040.RF300.3_2026.csv"
)


class TestNeedRoutes(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._needs = storage.NEEDS_DIR
        self._data = storage.DATA_DIR
        storage.DATA_DIR = Path(self._tmpdir.name) / "data"
        storage.NEEDS_DIR = storage.DATA_DIR / "needs"
        storage.INVENTORY_PATH = storage.DATA_DIR / "inventory.json"
        storage.ensure_data_dirs()
        self.client = app.test_client()

    def tearDown(self) -> None:
        storage.NEEDS_DIR = self._needs
        storage.DATA_DIR = self._data
        storage.INVENTORY_PATH = self._data / "inventory.json"
        self._tmpdir.cleanup()

    def test_need_page_empty(self) -> None:
        response = self.client.get("/need")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Upload an Altium", response.data)

    @unittest.skipUnless(SAMPLE_CSV.exists(), "sample CSV not available")
    def test_upload_and_toggle_line(self) -> None:
        bom = parse_bom_csv_file(SAMPLE_CSV)
        storage.save_bom(bom)
        line_id = bom.lines[0].id

        response = self.client.get(f"/need?bom_id={bom.bom_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"need-table", response.data)

        response = self.client.post(
            f"/need/{bom.bom_id}/line/{line_id}",
            json={"acquired": True},
            headers={"Accept": "application/json"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["acquired"])

        reloaded = storage.load_bom(bom.bom_id)
        assert reloaded is not None
        self.assertTrue(reloaded.lines[0].acquired)

    @unittest.skipUnless(SAMPLE_CSV.exists(), "sample CSV not available")
    def test_export_csv(self) -> None:
        bom = parse_bom_csv_file(SAMPLE_CSV)
        storage.save_bom(bom)
        response = self.client.get(f"/need/{bom.bom_id}/export.csv")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Acquired", response.data)
        self.assertTrue(response.mimetype.startswith("text/csv"))

    def test_upload_invalid_file(self) -> None:
        data = {"bom_file": (io.BytesIO(b"not,a,valid\n"), "bad.csv")}
        response = self.client.post("/need/upload", data=data, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 302)


if __name__ == "__main__":
    unittest.main()
