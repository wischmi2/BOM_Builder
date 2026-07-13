from __future__ import annotations

import unittest

from bom_builder import digikey_api, mouser_api, shopping
from bom_builder.enrichment import build_alternates, build_enrichment_proposal
from bom_builder.models import BomDocument, NeedLine


class TestDistributorNormalizers(unittest.TestCase):
    def test_digikey_normalize_product(self) -> None:
        product = {
            "ManufacturerProductNumber": "GRM155R71H103KA88J",
            "DigiKeyPartNumber": "490-1234-1-ND",
            "Manufacturer": {"Name": "Murata"},
            "Description": {"ProductDescription": "CAP CER 10000PF 50V X7R 0402"},
            "DatasheetUrl": "https://example.com/ds.pdf",
            "ProductUrl": "https://www.digikey.com/product/xyz",
            "QuantityAvailable": 50000,
            "StandardPricing": [{"BreakQuantity": 1, "UnitPrice": 0.012}],
        }
        norm = digikey_api._normalize_product(product, "GRM155R71H103KA88J", kind="exact")
        self.assertEqual(norm["manufacturer"], "Murata")
        self.assertEqual(norm["datasheet_url"], "https://example.com/ds.pdf")
        self.assertEqual(norm["stock"], 50000)
        self.assertAlmostEqual(norm["price_1"], 0.012)
        self.assertEqual(norm["distributor"], "digikey")

    def test_mouser_normalize_part(self) -> None:
        part = {
            "ManufacturerPartNumber": "GRM155R71H103KA88J",
            "MouserPartNumber": "81-GRM155R71H103KA8J",
            "Manufacturer": "Murata Electronics",
            "Description": "Multilayer Ceramic Capacitors MLCC",
            "DataSheetUrl": "https://mouser.com/ds.pdf",
            "ProductDetailUrl": "https://mouser.com/p/xyz",
            "Availability": "12000 In Stock",
            "PriceBreaks": [{"Quantity": 1, "Price": "$0.015"}],
        }
        norm = mouser_api._normalize_part(part, kind="similar")
        self.assertEqual(norm["manufacturer"], "Murata Electronics")
        self.assertEqual(norm["datasheet_url"], "https://mouser.com/ds.pdf")
        self.assertEqual(norm["stock"], 12000)
        self.assertAlmostEqual(norm["price_1"], 0.015)


class TestEnrichmentProposal(unittest.TestCase):
    def test_prefers_digikey_and_picks_lowest_price(self) -> None:
        results = {
            "digikey": {
                "found": True, "manufacturer": "Murata", "description": "DK desc",
                "datasheet_url": "https://dk/ds.pdf", "price_1": 0.02, "stock": 1000,
            },
            "mouser": {
                "found": True, "manufacturer": "Murata Electronics", "description": "MO desc",
                "datasheet_url": "https://mo/ds.pdf", "price_1": 0.015, "stock": 500,
            },
        }
        p = build_enrichment_proposal(results)
        self.assertTrue(p["found"])
        self.assertEqual(p["manufacturer"], "Murata")          # DigiKey wins
        self.assertEqual(p["description"], "DK desc")
        self.assertAlmostEqual(p["unit_price"], 0.015)          # lowest across both
        self.assertEqual(p["source"], "mouser")                 # price source
        self.assertEqual(p["stock"], 500)                       # stock from source

    def test_falls_back_to_mouser_when_digikey_missing(self) -> None:
        results = {
            "digikey": {"found": False},
            "mouser": {"found": True, "manufacturer": "TDK", "description": "d",
                       "datasheet_url": "", "price_1": 0.1, "stock": 3},
        }
        p = build_enrichment_proposal(results)
        self.assertEqual(p["manufacturer"], "TDK")
        self.assertEqual(p["source"], "mouser")

    def test_not_found_when_nothing(self) -> None:
        p = build_enrichment_proposal({"digikey": {"found": False}, "mouser": {"found": False}})
        self.assertFalse(p["found"])
        self.assertIsNone(p["unit_price"])


class TestAlternates(unittest.TestCase):
    def test_dedupe_exclude_original_and_sort(self) -> None:
        subs = [
            {"mpn": "SUB-A", "kind": "substitute", "price_1": 0.5, "manufacturer": "X"},
            {"mpn": "ORIG", "kind": "substitute", "price_1": 0.1},  # original, dropped
        ]
        similar = [
            {"mpn": "SIM-B", "kind": "similar", "price_1": 0.2},
            {"mpn": "SIM-C", "kind": "similar", "price_1": None},
            {"mpn": "sub-a", "kind": "similar", "price_1": 0.5, "datasheet_url": "ds"},  # dup of SUB-A
        ]
        out = build_alternates(subs, similar, original_mpn="ORIG", limit=10)
        mpns = [a["mpn"] for a in out]
        self.assertNotIn("ORIG", mpns)
        # substitute first, then similar by price ascending (None last)
        self.assertEqual(out[0]["mpn"], "SUB-A")
        self.assertEqual(mpns[1:], ["SIM-B", "SIM-C"])
        # dedup merged the datasheet from the similar duplicate into SUB-A
        self.assertEqual(out[0]["datasheet_url"], "ds")

    def test_limit(self) -> None:
        similar = [{"mpn": f"P{i}", "kind": "similar", "price_1": float(i)} for i in range(20)]
        out = build_alternates([], similar, original_mpn="ORIG", limit=5)
        self.assertEqual(len(out), 5)


class TestSyncNeedLineDetails(unittest.TestCase):
    def setUp(self) -> None:
        self.bom = BomDocument(
            bom_id="b1", source_filename="b1.csv",
            lines=[NeedLine(id="L1", bom_id="b1", name="10uF", description="",
                            designators=["C1"], footprint="C0402", lib_ref="OLD-MPN", quantity=1)],
        )
        self._saved = None
        self._orig_load = shopping.storage.load_bom
        self._orig_save = shopping.storage.save_bom
        shopping.storage.load_bom = lambda bom_id: self.bom if bom_id == "b1" else None
        shopping.storage.save_bom = self._capture_save

    def tearDown(self) -> None:
        shopping.storage.load_bom = self._orig_load
        shopping.storage.save_bom = self._orig_save

    def _capture_save(self, bom: BomDocument) -> None:
        self._saved = bom

    def test_writes_enrichment_fields(self) -> None:
        n = shopping.sync_need_lines_details(
            ["b1:L1"],
            manufacturer="Murata", datasheet_url="https://ds", description="cap",
            unit_price=0.015, stock=500, enriched_from="mouser",
        )
        self.assertEqual(n, 1)
        line = self._saved.lines[0]
        self.assertEqual(line.manufacturer, "Murata")
        self.assertEqual(line.datasheet_url, "https://ds")
        self.assertAlmostEqual(line.unit_price, 0.015)
        self.assertEqual(line.stock, 500)
        self.assertEqual(line.enriched_from, "mouser")
        self.assertTrue(line.enriched_at)
        self.assertEqual(line.lib_ref, "OLD-MPN")  # unchanged (mpn not passed)

    def test_replace_updates_mpn_and_name(self) -> None:
        shopping.sync_need_lines_details(["b1:L1"], mpn="NEW-MPN", name="10uF alt")
        line = self._saved.lines[0]
        self.assertEqual(line.lib_ref, "NEW-MPN")
        self.assertEqual(line.name, "10uF alt")

    def test_none_fields_are_not_written(self) -> None:
        shopping.sync_need_lines_details(["b1:L1"], manufacturer="OnlyThis")
        line = self._saved.lines[0]
        self.assertEqual(line.manufacturer, "OnlyThis")
        self.assertEqual(line.description, "")  # untouched


class TestNeedLineBackwardCompat(unittest.TestCase):
    def test_from_dict_ignores_unknown_and_missing_keys(self) -> None:
        # Old JSON without enrichment fields still loads.
        old = {"id": "L1", "bom_id": "b", "name": "10k", "description": "",
               "designators": ["R1"], "footprint": "R0402", "lib_ref": "X", "quantity": 1}
        line = NeedLine.from_dict(old)
        self.assertEqual(line.manufacturer, "")
        self.assertIsNone(line.unit_price)
        # Future JSON with an unknown key does not crash.
        future = {**old, "some_future_field": 123}
        line2 = NeedLine.from_dict(future)
        self.assertEqual(line2.name, "10k")


if __name__ == "__main__":
    unittest.main()
