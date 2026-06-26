from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from bom_builder import storage
from bom_builder.models import BomDocument, InventoryDocument, InventoryItem, NeedLine
from bom_builder.inventory_io import add_qty_for_mpn
from bom_builder.matcher import compare_boms_aggregated
from bom_builder.shopping import (
    alternates_display,
    apply_shop_overlays_to_compare,
    attach_storage_key,
    build_shop_lines,
    digikey_search_url,
    merge_shop_state,
    mouser_search_url,
    primary_mpn,
    receive_shop_parts,
    shop_to_csv,
    shortfall_qty,
    sync_need_lines_mpn_name,
)


def _need(lib_ref: str, qty: int = 5, *, bom_id: str = "test-shop") -> NeedLine:
    return NeedLine(
        id="line-1",
        bom_id=bom_id,
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
        bom = BomDocument("bom1", "t.csv", [_need("PART-A", 10, bom_id="bom1")], board_count=2)
        inv = InventoryDocument(items=[InventoryItem(id="i1", lib_ref="PART-A", qty_on_hand=4)])
        lines = build_shop_lines([bom], inv, "per_board")
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].status, "partial")
        self.assertEqual(lines[0].qty_needed, 20)
        self.assertEqual(lines[0].default_buy_qty, 16)

    def test_merge_shop_state(self) -> None:
        from bom_builder.shopping import ShopLine

        line = attach_storage_key(
            ShopLine(
                line_id="test-shop:line-1",
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
        )
        merge_shop_state([line], {"lib:P": {"buy_qty": 3, "notes": "PO-1", "ordered": True}})
        self.assertEqual(line.buy_qty, 3)
        self.assertEqual(line.notes, "PO-1")
        self.assertTrue(line.ordered)

    def test_saved_state_merges_per_board_notes_into_combined(self) -> None:
        from bom_builder.shopping import ShopLine, saved_state_for_line

        line = attach_storage_key(
            ShopLine(
                line_id="lib:P",
                lib_ref="P",
                primary_mpn="P",
                alternates_display="",
                name="n",
                status="missing",
                qty_needed=10,
                qty_on_hand=0,
                default_buy_qty=10,
                buy_qty=10,
                source_line_ids=["bomA:row-1", "bomB:row-2"],
            )
        )
        saved = {
            "lib:P": {"notes": "", "ordered": False},
            "bomA:row-1": {"notes": "from board A", "updated_at": "2026-01-02T00:00:00+00:00"},
            "bomB:row-2": {"notes": "newer on B", "updated_at": "2026-06-03T00:00:00+00:00"},
        }
        state = saved_state_for_line(saved, line)
        assert state is not None
        self.assertEqual(state["notes"], "newer on B")

    def test_merge_shop_state_mpn_name_override(self) -> None:
        from bom_builder.shopping import ShopLine

        line = attach_storage_key(
            ShopLine(
                line_id="lib:CMP",
                lib_ref="CMP-009-00186-1",
                primary_mpn="CMP-009-00186-1",
                alternates_display="",
                name="CRCW02011K10FKED",
                status="missing",
                qty_needed=1,
                qty_on_hand=0,
                default_buy_qty=1,
                buy_qty=1,
            )
        )
        merge_shop_state([line], {line.storage_key: {"mpn": "CRCW02011K10FKED", "name": "1K 0201"}})
        self.assertEqual(line.primary_mpn, "CRCW02011K10FKED")
        self.assertEqual(line.name, "1K 0201")
        self.assertIn("CRCW02011K10FKED", line.digikey_url)

    def test_merge_shop_state_legacy_line_id(self) -> None:
        from bom_builder.shopping import ShopLine

        line = attach_storage_key(
            ShopLine(
                line_id="test-shop:line-1",
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
        )
        merge_shop_state([line], {"test-shop:line-1": {"notes": "legacy key"}})
        self.assertEqual(line.notes, "legacy key")

    def test_add_qty_for_mpn_merges_existing(self) -> None:
        doc = InventoryDocument(
            items=[InventoryItem(id="i1", lib_ref="ABC-1", name="Old", qty_on_hand=3)]
        )
        item = add_qty_for_mpn(doc, lib_ref="abc-1", qty=5, name="New name")
        self.assertEqual(item.qty_on_hand, 8)
        self.assertEqual(item.name, "Old")

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
        response = self.client.post(
            "/shop/line/lib:BUYME",
            json={"buy_qty": 7, "notes": "cart A", "ordered": True},
            headers={"Accept": "application/json"},
        )
        self.assertEqual(response.status_code, 200)
        saved = storage.load_shopping_list()
        self.assertEqual(saved["lib:BUYME"]["buy_qty"], 7)
        self.assertEqual(saved["lib:BUYME"]["notes"], "cart A")

    def test_combined_view_shows_notes_saved_per_board_only(self) -> None:
        bom = storage.load_bom("test-shop")
        inv = storage.load_inventory()
        line_id = f"{bom.bom_id}:{bom.lines[0].id}"
        storage.save_shopping_list({line_id: {"notes": "board only", "updated_at": "2026-06-03T00:00:00+00:00"}})
        combined = build_shop_lines([bom], inv, "combined")
        merge_shop_state(combined, storage.load_shopping_list())
        self.assertEqual(combined[0].notes, "board only")

    def test_shop_update_mpn_syncs_bom(self) -> None:
        bom = storage.load_bom("test-shop")
        line_id = f"{bom.bom_id}:{bom.lines[0].id}"
        response = self.client.post(
            "/shop/line/lib:BUYME",
            json={
                "mpn": "REAL-MPN-123",
                "name": "Corrected name",
                "source_line_ids": [line_id],
            },
            headers={"Accept": "application/json"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["bom_synced"], 1)
        reloaded = storage.load_bom("test-shop")
        self.assertEqual(reloaded.lines[0].lib_ref, "REAL-MPN-123")
        self.assertEqual(reloaded.lines[0].name, "Corrected name")
        saved = storage.load_shopping_list()
        self.assertEqual(saved["lib:BUYME"]["mpn"], "REAL-MPN-123")

    def test_sync_need_lines_mpn_name(self) -> None:
        bom = storage.load_bom("test-shop")
        line_id = f"{bom.bom_id}:{bom.lines[0].id}"
        count = sync_need_lines_mpn_name([line_id], mpn="NEWMPN", name="New Name")
        self.assertEqual(count, 1)
        bom = storage.load_bom("test-shop")
        self.assertEqual(bom.lines[0].lib_ref, "NEWMPN")

    def test_saved_state_keeps_alternate_when_notes_present(self) -> None:
        from bom_builder.shopping import ShopLine, merge_shop_state

        line = attach_storage_key(
            ShopLine(
                line_id="lib:CRCW0201274RFNED",
                lib_ref="CRCW0201274RFNED",
                primary_mpn="CRCW0201274RFNED",
                alternates_display="",
                name="274 Ohm",
                status="missing",
                qty_needed=500,
                qty_on_hand=0,
                default_buy_qty=500,
                buy_qty=500,
            )
        )
        merge_shop_state(
            [line],
            {
                line.storage_key: {
                    "notes": "No Stock",
                    "updated_at": "2026-06-04T15:56:26+00:00",
                    "alternate": {
                        "enabled": True,
                        "mpn": "RC0201FR-07274RL",
                        "name": "Substitute 274",
                        "buy_qty": 500,
                    },
                }
            },
        )
        self.assertTrue(line.alternate.enabled)
        self.assertEqual(line.alternate.mpn, "RC0201FR-07274RL")

    def test_merge_alternate_state(self) -> None:
        from bom_builder.shopping import ShopLine

        line = attach_storage_key(
            ShopLine(
                line_id="lib:PART",
                lib_ref="PART",
                primary_mpn="PART",
                alternates_display="",
                name="Orig",
                status="missing",
                qty_needed=5,
                qty_on_hand=0,
                default_buy_qty=5,
                buy_qty=5,
            )
        )
        merge_shop_state(
            [line],
            {
                line.storage_key: {
                    "alternate": {
                        "enabled": True,
                        "mpn": "ALT-MPN",
                        "name": "Substitute",
                        "buy_qty": 3,
                        "notes": "Arrow",
                    }
                }
            },
        )
        self.assertTrue(line.alternate.enabled)
        self.assertEqual(line.alternate.mpn, "ALT-MPN")
        self.assertEqual(line.alternate.buy_qty, 3)

    def test_shop_update_alternate(self) -> None:
        response = self.client.post(
            "/shop/line/lib:BUYME",
            json={
                "alternate": {
                    "enabled": True,
                    "mpn": "SUB-123",
                    "name": "Sub part",
                    "buy_qty": 2,
                }
            },
            headers={"Accept": "application/json"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["alternate"]["enabled"])
        self.assertEqual(data["alternate"]["mpn"], "SUB-123")

    def test_shop_receive_route_partial(self) -> None:
        # Do not call save_inventory([]) — use isolated path from setUp; empty file loads as [].
        self.assertNotEqual(
            storage.INVENTORY_PATH.resolve(),
            (Path(__file__).resolve().parent.parent / "data" / "inventory.json").resolve(),
            "Tests must not use the real data/inventory.json",
        )
        self.client.post(
            "/shop/line/lib:BUYME",
            json={"buy_qty": 10},
            headers={"Accept": "application/json"},
        )
        response = self.client.post(
            "/shop/line/lib:BUYME/receive",
            json={"qty": 3, "mpn": "BUYME", "name": "Test part"},
            headers={"Accept": "application/json"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["received_qty"], 3)
        self.assertEqual(data["remaining_qty"], 7)
        self.assertFalse(data["fully_received"])
        inv = storage.load_inventory()
        self.assertEqual(inv.items[0].qty_on_hand, 3)

        response2 = self.client.post(
            "/shop/line/lib:BUYME/receive",
            json={"qty": 7, "mpn": "BUYME", "name": "Test part"},
            headers={"Accept": "application/json"},
        )
        self.assertEqual(response2.status_code, 200)
        data2 = response2.get_json()
        self.assertTrue(data2["fully_received"])
        self.assertEqual(storage.load_inventory().items[0].qty_on_hand, 10)

    def test_shop_receive_reset(self) -> None:
        storage.save_inventory(InventoryDocument(items=[]))
        self.client.post(
            "/shop/line/lib:BUYME",
            json={"buy_qty": 10, "received_qty": 10},
            headers={"Accept": "application/json"},
        )
        response = self.client.post(
            "/shop/line/lib:BUYME/receive",
            json={"action": "reset"},
            headers={"Accept": "application/json"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["received_qty"], 0)
        self.assertEqual(data["remaining_qty"], 10)

    def test_shop_notes_persist_across_views(self) -> None:
        self.client.post(
            "/shop/line/lib:BUYME",
            json={"notes": "same part"},
            headers={"Accept": "application/json"},
        )
        bom = storage.load_bom("test-shop")
        inv = storage.load_inventory()
        saved = storage.load_shopping_list()
        per_board = build_shop_lines([bom], inv, "per_board")
        merge_shop_state(per_board, saved)
        self.assertEqual(per_board[0].notes, "same part")
        combined = build_shop_lines([bom], inv, "combined")
        merge_shop_state(combined, saved)
        self.assertEqual(combined[0].notes, "same part")

    def test_compare_uses_shop_substitute_mpn(self) -> None:
        bom = BomDocument("test-shop", "t.csv", [_need("504L50R0FTNCFT", qty=2)])
        storage.save_bom(bom)
        inv = InventoryDocument(
            items=[
                InventoryItem(id="old", lib_ref="504L50R0FTNCFT", qty_on_hand=10),
                InventoryItem(id="new", lib_ref="FC0402E50R0BTBST1", qty_on_hand=500),
            ]
        )
        saved = {
            "lib:504L50R0FTNCFT": {
                "alternate": {
                    "enabled": True,
                    "mpn": "FC0402E50R0BTBST1",
                    "name": "Replacement 50R",
                }
            }
        }
        agg_rows, _ = compare_boms_aggregated([bom], inv)
        apply_shop_overlays_to_compare(None, agg_rows, inv, saved)
        row = agg_rows[0]
        self.assertEqual(row.display_lib_ref, "FC0402E50R0BTBST1")
        self.assertTrue(row.shop_substitute)
        self.assertEqual(row.qty_on_hand, 500)
        self.assertEqual(row.status, "ok")


if __name__ == "__main__":
    unittest.main()
