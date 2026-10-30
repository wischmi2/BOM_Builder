from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from main import app
from bom_builder import storage
from bom_builder.excluded_parts import excluded_keys, load_excluded, set_excluded
from bom_builder.models import BomDocument, InventoryDocument, NeedLine
from bom_builder.shopping import build_shop_lines


def _line(line_id: str, name: str, lib_ref: str, designator: str, qty: int = 1) -> NeedLine:
    return NeedLine(
        id=line_id,
        bom_id="board",
        name=name,
        description="",
        designators=[designator],
        footprint="",
        lib_ref=lib_ref,
        quantity=qty,
    )


def _bom() -> BomDocument:
    return BomDocument(
        "board",
        "board.csv",
        [
            _line("l1", "10k", "RC0402FR-0710KL", "R1", 4),
            _line("l2", "VTGT-S1", "GP_Socket", "TP1"),
            _line("l3", "VTGT-S2", "GP_Socket", "TP6"),
            _line("l4", "M2 Bolt MH", "MH_M2_Bolt", "MH14"),
        ],
    )


class _TempData(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._saved = (
            storage.DATA_DIR,
            storage.NEEDS_DIR,
            storage.INVENTORY_PATH,
            storage.SHOPPING_LIST_PATH,
        )
        storage.DATA_DIR = Path(self._tmpdir.name) / "data"
        storage.NEEDS_DIR = storage.DATA_DIR / "needs"
        storage.INVENTORY_PATH = storage.DATA_DIR / "inventory.json"
        storage.SHOPPING_LIST_PATH = storage.DATA_DIR / "shopping_list.json"
        storage.ensure_data_dirs()

    def tearDown(self) -> None:
        (
            storage.DATA_DIR,
            storage.NEEDS_DIR,
            storage.INVENTORY_PATH,
            storage.SHOPPING_LIST_PATH,
        ) = self._saved
        self._tmpdir.cleanup()


class TestExcludedStore(_TempData):
    def test_set_and_restore(self) -> None:
        self.assertEqual(load_excluded(), {})
        set_excluded("lib:GPSOCKET", True, name="VTGT-S2", lib_ref="GP_Socket")
        self.assertEqual(excluded_keys(), {"lib:GPSOCKET"})
        self.assertEqual(load_excluded()["lib:GPSOCKET"]["lib_ref"], "GP_Socket")
        set_excluded("lib:GPSOCKET", False)
        self.assertEqual(excluded_keys(), set())

    def test_build_shop_lines_skips_excluded(self) -> None:
        inv = InventoryDocument()
        hidden: list = []
        for view in ("per_board", "combined"):
            hidden.clear()
            lines = build_shop_lines(
                [_bom()], inv, view,
                excluded_keys={"lib:GPSOCKET", "lib:MHM2BOLT"},
                hidden_out=hidden,
            )
            self.assertEqual([l.primary_mpn for l in lines], ["RC0402FR-0710KL"], view)
            self.assertTrue(all(key in {"lib:GPSOCKET", "lib:MHM2BOLT"} for key, _, _ in hidden))
        # Without exclusions everything missing is on the list.
        self.assertEqual(len(build_shop_lines([_bom()], inv, "per_board")), 4)


class TestExcludedRoutes(_TempData):
    def setUp(self) -> None:
        super().setUp()
        storage.save_bom(_bom())
        self.client = app.test_client()

    def _hide(self, key: str, excluded: bool = True):
        return self.client.post("/parts/exclude", json={"part_key": key, "excluded": excluded,
                                                         "name": "VTGT-S2", "lib_ref": "GP_Socket"})

    def test_hide_removes_from_compare_and_shop(self) -> None:
        for view in ("per_board", "combined"):
            page = self.client.get(f"/compare?bom_id=board&view={view}").get_data(as_text=True)
            self.assertIn("VTGT-S2", page)
            self.assertIn('data-exclude-action="hide"', page)

        self.assertTrue(self._hide("lib:GPSOCKET").get_json()["ok"])

        for view in ("per_board", "combined"):
            compare = self.client.get(f"/compare?bom_id=board&view={view}").get_data(as_text=True)
            self.assertNotIn('data-part-key="lib:GPSOCKET"\n', compare)
            self.assertIn("Not purchased — hidden (1)", compare)
            self.assertIn('data-exclude-action="restore"', compare)

            shop = self.client.get(f"/shop?bom_id=board&view={view}").get_data(as_text=True)
            self.assertNotIn('value="GP_Socket"', shop)
            self.assertIn('value="RC0402FR-0710KL"', shop)
            self.assertIn("Not purchased — hidden (1)", shop)

        csv_text = self.client.get("/shop/export.csv?bom_id=board&view=per_board").get_data(as_text=True)
        self.assertNotIn("GP_Socket", csv_text)
        gap_csv = self.client.get("/compare/export.csv?bom_id=board&view=per_board").get_data(as_text=True)
        self.assertNotIn("GP_Socket", gap_csv)

        # Restore brings it back.
        self.assertTrue(self._hide("lib:GPSOCKET", excluded=False).get_json()["ok"])
        shop = self.client.get("/shop?bom_id=board&view=per_board").get_data(as_text=True)
        self.assertIn('value="GP_Socket"', shop)
        self.assertNotIn("Not purchased — hidden", shop)

    def test_compare_summary_excludes_hidden(self) -> None:
        self._hide("lib:GPSOCKET")
        self._hide("lib:MHM2BOLT")
        page = self.client.get("/compare?bom_id=board&view=per_board").get_data(as_text=True)
        self.assertIn("Not purchased — hidden (2)", page)
        # Only the resistor line remains in the table.
        self.assertEqual(page.count('class="compare-row '), 1)

    def test_missing_part_key_rejected(self) -> None:
        response = self.client.post("/parts/exclude", json={"excluded": True})
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
