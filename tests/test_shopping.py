from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from bom_builder import storage
from bom_builder.models import BomDocument, InventoryDocument, InventoryItem, NeedLine
from bom_builder.shopping import (
    alternates_display,
    build_shop_lines,
    digikey_search_url,
    merge_shop_state,
    mouser_search_url,
    primary_mpn,
    shop_to_csv,
    shortfall_qty,
)


def _need(lib_ref: str, qty: int = 5) -> NeedLine:
    return NeedLine(
        id="line-1",
        bom_id="bom1",
        name="10K",
        description="",
        designators=["R1"],
        footprint="",
        lib_ref=lib_ref,
        quantity=qty,
    )


class TestShopping(unittest.TestCase):
    def test_shortfall_qty(self) -> None:
        self.assertEqual(shortfall_qty(10, 3), 7)
        self.assertEqual(shortfall_qty(10, 12), 0)

    def test_primary_mpn_and_alternates(self) -> None:
        self.assertEqual(primary_mpn("RK73, GRM155"), "RK73")
        self.assertEqual(alternates_display("RK73, GRM155"), "GRM155")

    def test_distributor_urls_encode(self) -> None:
        url = digikey_search_url("GRM155R71H104")
        self.assertIn("GRM155R71H104", url)
        self.assertTrue(url.startswith("https://www.digikey.com/"))
        self.assertIn("mouser.com", mouser_search_url("GRM155R71H104"))

    def test_build_shop_lines_missing_only(self) -> None:
        bom = BomDocument("bom1", "t.csv", [_need("PART-A", 10)], board_count=2)
        inv = InventoryDocument(items=[InventoryItem(id="i1", lib_ref="PART-A", qty_on_hand=4)])
        lines = build_shop_lines([bom], inv, "per_board")
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].status, "partial")
        self.assertEqual(lines[0].qty_needed, 20)
        self.assertEqual(lines[0].default_buy_qty, 16)

    def test_merge_shop_state(self) -> None:
        from bom_builder.shopping import ShopLine

        line = ShopLine(
            line_id="x",
            lib_ref="P",
            primary_mpn="P",
            alternates_display="",
            name="n",
            status="missing",
            qty_needed=5,
            qty_on_hand=0,
            default_buy_qty=5,
            buy_qty=5,
        )
        merge_shop_state([line], {"x": {"buy_qty": 3, "notes": "PO-1", "ordered": True}})
        self.assertEqual(line.buy_qty, 3)
        self.assertEqual(line.notes, "PO-1")
        self.assertTrue(line.ordered)

    def test_shop_to_csv(self) -> None:
        from bom_builder.shopping import ShopLine

        line = ShopLine(
            line_id="lib:PART",
            lib_ref="PART",
            primary_mpn="PART",
            alternates_display="",
            name="Cap",
            status="missing",
            qty_needed=10,
            qty_on_hand=0,
            default_buy_qty=10,
            buy_qty=10,
            digikey_url=digikey_search_url("PART"),
            mouser_url=mouser_search_url("PART"),
        )
        csv_text = shop_to_csv([line])
        self.assertIn("DigiKeyURL", csv_text)
        self.assertIn("PART", csv_text)


class TestShoppingRoutes(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._needs = storage.NEEDS_DIR
        self._data = storage.DATA_DIR
        self._inventory = storage.INVENTORY_PATH
        self._shopping = storage.SHOPPING_LIST_PATH
        storage.DATA_DIR = Path(self._tmpdir.name) / "data"
        storage.NEEDS_DIR = storage.DATA_DIR / "needs"
        storage.INVENTORY_PATH = storage.DATA_DIR / "inventory.json"
        storage.SHOPPING_LIST_PATH = storage.DATA_DIR / "shopping_list.json"
        storage.ensure_data_dirs()

        from main import app

        self.client = app.test_client()

        bom = BomDocument("test-shop", "t.csv", [_need("BUYME", 5)])
        storage.save_bom(bom)

    def tearDown(self) -> None:
        storage.NEEDS_DIR = self._needs
        storage.DATA_DIR = self._data
        storage.INVENTORY_PATH = self._inventory
        storage.SHOPPING_LIST_PATH = self._shopping
        self._tmpdir.cleanup()

    def test_shop_page_renders(self) -> None:
        response = self.client.get("/shop?bom_id=test-shop")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Shop", response.data)
        self.assertIn(b"DigiKey", response.data)

    def test_shop_update_line(self) -> None:
        bom = storage.load_bom("test-shop")
        assert bom is not None
        line_id = f"{bom.bom_id}:{bom.lines[0].id}"
        response = self.client.post(
            f"/shop/line/{line_id}",
            json={"buy_qty": 7, "notes": "cart A", "ordered": True},
            headers={"Accept": "application/json"},
        )
        self.assertEqual(response.status_code, 200)
        saved = storage.load_shopping_list()
        self.assertEqual(saved[line_id]["buy_qty"], 7)
        self.assertEqual(saved[line_id]["notes"], "cart A")


if __name__ == "__main__":
    unittest.main()
