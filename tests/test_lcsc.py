from __future__ import annotations

import unittest
from pathlib import Path

from bom_builder import lcsc_api, shopping
from bom_builder.enrichment import build_enrichment_proposal
from bom_builder.models import BomDocument, NeedLine
from bom_builder.parser import parse_kicad_bom_csv_file

FIXTURE = Path(__file__).parent / "fixtures" / "nrf54l15_soil_moisture.csv"

# Trimmed real response from https://easyeda.com/api/products/C14663/components
DETAIL_RESULT = {
    "title": "CC0603KRX7R9BB104",
    "description": "100nF (104) ±10% 50V",
    "szlcsc": {"number": "C14663", "price": 0.01875, "stock": 8673800,
               "url": "http://www.szlcsc.com/product/details_15331.html"},
    "lcsc": {"number": "C14663", "price": 0.004, "stock": 0,
             "url": "https://lcsc.com/product-detail/x_C14663.html"},
    "dataStr": {"head": {"c_para": {
        "Manufacturer": "YAGEO(国巨)",
        "Manufacturer Part": "CC0603KRX7R9BB104",
        "Supplier Part": "C14663",
    }}},
}

# Trimmed real item from the keyword-search endpoint.
SEARCH_ITEM = {
    "mpn": "CC0603KRX7R9BB104", "number": "C14663", "manufacturer": "YAGEO",
    "package": "0603", "stock": 0, "ifRoHS": True,
    "price": [[50, "0.0195", "0.0195"], [500, "0.0188", "0.0188"]],
    "url": "/product-detail/Multilayer_YAGEO-CC0603KRX7R9BB104_C14663.html",
}


class TestLcscDetection(unittest.TestCase):
    def test_is_lcsc_code(self) -> None:
        self.assertTrue(lcsc_api.is_lcsc_code("C14663"))
        self.assertTrue(lcsc_api.is_lcsc_code("c123"))
        self.assertFalse(lcsc_api.is_lcsc_code("CC0603KRX7R9BB104"))
        self.assertFalse(lcsc_api.is_lcsc_code(""))


class TestLcscNormalize(unittest.TestCase):
    def test_normalize_detail(self) -> None:
        n = lcsc_api._normalize_detail(DETAIL_RESULT, "C14663")
        self.assertEqual(n["distributor"], "lcsc")
        self.assertEqual(n["mpn"], "CC0603KRX7R9BB104")
        self.assertEqual(n["manufacturer"], "YAGEO")          # localized alias stripped
        self.assertEqual(n["lcsc_part"], "C14663")
        self.assertEqual(n["stock"], 8673800)                 # szlcsc stock (lcsc was 0)
        self.assertAlmostEqual(n["price_1"], 0.004)           # lcsc price preferred
        self.assertTrue(n["url"].startswith("https://lcsc.com/"))

    def test_normalize_search_item(self) -> None:
        n = lcsc_api._normalize_search_item(SEARCH_ITEM)
        self.assertEqual(n["mpn"], "CC0603KRX7R9BB104")
        self.assertEqual(n["lcsc_part"], "C14663")
        self.assertAlmostEqual(n["price_1"], 0.0195)          # first price break
        self.assertEqual(n["url"], "https://www.lcsc.com/product-detail/Multilayer_YAGEO-CC0603KRX7R9BB104_C14663.html")
        self.assertEqual(n["kind"], "similar")


class TestLcscLookupPartDispatch(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_code = lcsc_api.lookup_code
        self._orig_search = lcsc_api.search_candidates

    def tearDown(self) -> None:
        lcsc_api.lookup_code = self._orig_code
        lcsc_api.search_candidates = self._orig_search

    def test_cnumber_uses_detail(self) -> None:
        lcsc_api.lookup_code = lambda c: {"found": True, "lcsc_part": c, "kind": "exact"}
        self.assertEqual(lcsc_api.lookup_part("C14663")["lcsc_part"], "C14663")

    def test_mpn_uses_search(self) -> None:
        lcsc_api.search_candidates = lambda q, limit=1: [{"found": True, "mpn": q, "kind": "similar"}]
        r = lcsc_api.lookup_part("CC0603KRX7R9BB104")
        self.assertEqual(r["mpn"], "CC0603KRX7R9BB104")
        self.assertEqual(r["kind"], "exact")  # top search hit promoted to exact


class TestProposalWithLcsc(unittest.TestCase):
    def test_lcsc_only_source(self) -> None:
        results = {
            "digikey": {"found": False},
            "mouser": {"found": False},
            "lcsc": {"found": True, "manufacturer": "YAGEO", "description": "100nF",
                     "datasheet_url": "", "price_1": 0.004, "stock": 8673800},
        }
        p = build_enrichment_proposal(results)
        self.assertTrue(p["found"])
        self.assertEqual(p["source"], "lcsc")
        self.assertEqual(p["manufacturer"], "YAGEO")
        self.assertEqual(p["stock"], 8673800)

    def test_lcsc_wins_on_price(self) -> None:
        results = {
            "digikey": {"found": True, "manufacturer": "YAGEO", "price_1": 0.02, "stock": 100},
            "mouser": {"found": False},
            "lcsc": {"found": True, "manufacturer": "YAGEO", "price_1": 0.004, "stock": 8000000},
        }
        p = build_enrichment_proposal(results)
        self.assertAlmostEqual(p["unit_price"], 0.004)  # cheapest across sources
        self.assertEqual(p["source"], "lcsc")
        self.assertEqual(p["manufacturer"], "YAGEO")    # DigiKey text still preferred


class TestKicadStoresLcsc(unittest.TestCase):
    def test_lcsc_part_captured(self) -> None:
        bom = parse_kicad_bom_csv_file(FIXTURE)
        c1 = next(l for l in bom.lines if "C1" in l.designators)
        self.assertEqual(c1.lcsc_part, "C335106")
        c6 = next(l for l in bom.lines if "C6" in l.designators)
        self.assertEqual(c6.lcsc_part, "C14663")


class TestSyncLcscPart(unittest.TestCase):
    def setUp(self) -> None:
        self.bom = BomDocument(
            bom_id="b1", source_filename="b1.csv",
            lines=[NeedLine(id="L1", bom_id="b1", name="100nF", description="",
                            designators=["C6"], footprint="C0603", lib_ref="OLD", quantity=1)],
        )
        self._saved = None
        self._orig_load, self._orig_save = shopping.storage.load_bom, shopping.storage.save_bom
        shopping.storage.load_bom = lambda bid: self.bom if bid == "b1" else None
        shopping.storage.save_bom = lambda b: setattr(self, "_saved", b)

    def tearDown(self) -> None:
        shopping.storage.load_bom = self._orig_load
        shopping.storage.save_bom = self._orig_save

    def test_replace_updates_lcsc_part(self) -> None:
        shopping.sync_need_lines_details(["b1:L1"], mpn="NEWMPN", lcsc_part="C99999")
        line = self._saved.lines[0]
        self.assertEqual(line.lib_ref, "NEWMPN")
        self.assertEqual(line.lcsc_part, "C99999")


if __name__ == "__main__":
    unittest.main()
