from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bom_builder import storage
from bom_builder.need_io import suggest_mpn_from_description
from bom_builder.models import BomDocument, NeedLine


class TestMpnSuggest(unittest.TestCase):
    def test_single_token_description(self) -> None:
        self.assertEqual(
            suggest_mpn_from_description(
                "RC0402FR-07953RL",
                name="953R",
                lib_ref="CMP-2002-07842-1",
            ),
            "RC0402FR-07953RL",
        )

    def test_skips_name_and_internal_lib(self) -> None:
        self.assertIsNone(
            suggest_mpn_from_description("953R", name="953R", lib_ref="CMP-2002-07842-1"),
        )

    def test_embedded_in_long_description(self) -> None:
        desc = "Res Thick Film 0201 274 Ohm 1% 0.05W RC0402FR-07953RL Pad SMD"
        self.assertEqual(
            suggest_mpn_from_description(desc, name="953R", lib_ref="CMP-2002-07842-1"),
            "RC0402FR-07953RL",
        )


class TestNeedLibRefUpdate(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._needs = storage.NEEDS_DIR
        self._data = storage.DATA_DIR
        storage.DATA_DIR = Path(self._tmpdir.name) / "data"
        storage.NEEDS_DIR = storage.DATA_DIR / "needs"
        storage.ensure_data_dirs()

        from main import app

        self.client = app.test_client()
        bom = BomDocument(
            "test-need-mpn",
            "t.csv",
            [
                NeedLine(
                    id="line-1",
                    bom_id="test-need-mpn",
                    name="953R",
                    description="RC0402FR-07953RL",
                    designators=["R29"],
                    footprint="0402",
                    lib_ref="CMP-2002-07842-1",
                    quantity=2,
                )
            ],
        )
        storage.save_bom(bom)

    def tearDown(self) -> None:
        storage.NEEDS_DIR = self._needs
        storage.DATA_DIR = self._data
        self._tmpdir.cleanup()

    def test_need_page_shows_mpn_xref(self) -> None:
        response = self.client.get("/need?bom_id=test-need-mpn")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"RC0402FR-07953RL", response.data)
        self.assertIn(b"apply-mpn-xref", response.data)

    def test_need_update_lib_ref(self) -> None:
        response = self.client.post(
            "/need/test-need-mpn/line/line-1",
            json={"lib_ref": "RC0402FR-07953RL"},
            headers={"Accept": "application/json"},
        )
        self.assertEqual(response.status_code, 200)
        bom = storage.load_bom("test-need-mpn")
        assert bom is not None
        self.assertEqual(bom.lines[0].lib_ref, "RC0402FR-07953RL")


if __name__ == "__main__":
    unittest.main()
