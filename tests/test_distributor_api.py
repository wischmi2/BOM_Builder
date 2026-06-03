from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from bom_builder import digikey_api, mouser_api
from bom_builder.distributor_cache import (
    cache_key_for_mpn,
    get_cached,
    load_distributor_cache,
    save_distributor_cache,
    set_cached,
)
from bom_builder.distributor_lookup import lookup_batch, lookup_mpn


class TestDistributorCache(unittest.TestCase):
    def test_cache_key_normalizes(self) -> None:
        self.assertEqual(cache_key_for_mpn("  rk73h "), "mpn:RK73H")

    def test_set_and_get_cached(self) -> None:
        entries: dict = {}
        set_cached(entries, "ABC", "digikey", {"stock": 10, "price_1": 0.05})
        cached = get_cached(entries, "abc", "digikey")
        self.assertIsNotNone(cached)
        assert cached is not None
        self.assertEqual(cached["stock"], 10)


class TestMouserApi(unittest.TestCase):
    @patch.dict(os.environ, {"MOUSER_API_KEY": "test-key"})
    @patch("bom_builder.mouser_api.requests.post")
    def test_lookup_part_parses_response(self, mock_post: MagicMock) -> None:
        mock_post.return_value.json.return_value = {
            "SearchResults": {
                "Parts": [
                    {
                        "MouserPartNumber": "123-ABC",
                        "ManufacturerPartNumber": "ABC123",
                        "Description": "Test cap",
                        "Availability": "1,234 In Stock",
                        "ProductDetailUrl": "https://www.mouser.com/ProductDetail/ABC",
                        "PriceBreaks": [{"Quantity": 1, "Price": "$0.0123"}],
                    }
                ]
            }
        }
        mock_post.return_value.raise_for_status = MagicMock()

        result = mouser_api.lookup_part("ABC123")
        self.assertTrue(result["found"])
        self.assertEqual(result["stock"], 1234)
        self.assertAlmostEqual(result["price_1"], 0.0123)
        self.assertIn("mouser.com", result["url"])


class TestDigiKeyApi(unittest.TestCase):
    @patch.dict(
        os.environ,
        {"DIGIKEY_CLIENT_ID": "id", "DIGIKEY_CLIENT_SECRET": "secret"},
    )
    @patch("bom_builder.digikey_api.requests.post")
    def test_lookup_part_parses_response(self, mock_post: MagicMock) -> None:
        token_resp = MagicMock()
        token_resp.json.return_value = {"access_token": "tok", "expires_in": 3600}
        token_resp.raise_for_status = MagicMock()

        search_resp = MagicMock()
        search_resp.json.return_value = {
            "Products": [
                {
                    "DigiKeyPartNumber": "DK-1",
                    "ManufacturerProductNumber": "PART-X",
                    "QuantityAvailable": 50,
                    "ProductUrl": "https://www.digikey.com/en/products/detail/PART-X/1",
                    "Description": {"ProductDescription": "Resistor"},
                    "StandardPricing": [{"BreakQuantity": 1, "UnitPrice": 0.02}],
                }
            ]
        }
        search_resp.raise_for_status = MagicMock()
        mock_post.side_effect = [token_resp, search_resp]

        digikey_api._TOKEN = None
        digikey_api._TOKEN_EXPIRES = 0.0
        result = digikey_api.lookup_part("PART-X")
        self.assertTrue(result["found"])
        self.assertEqual(result["stock"], 50)
        self.assertEqual(result["price_1"], 0.02)


class TestDistributorLookup(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        from bom_builder import distributor_cache as dc

        self._path = dc.DISTRIBUTOR_CACHE_PATH
        dc.DISTRIBUTOR_CACHE_PATH = __import__("pathlib").Path(self._tmpdir.name) / "cache.json"

    def tearDown(self) -> None:
        from bom_builder import distributor_cache as dc

        dc.DISTRIBUTOR_CACHE_PATH = self._path
        self._tmpdir.cleanup()

    @patch.dict(os.environ, {"MOUSER_API_KEY": "k"}, clear=False)
    @patch("bom_builder.distributor_lookup.mouser_api.lookup_part")
    @patch("bom_builder.distributor_lookup.digikey_api.is_configured", return_value=False)
    def test_lookup_uses_cache_second_time(self, _dk_cfg: MagicMock, mock_mouser: MagicMock) -> None:
        mock_mouser.return_value = {
            "found": True,
            "mpn": "Z",
            "url": "https://example.com",
            "stock": 1,
            "price_1": 1.0,
        }
        entries = load_distributor_cache()
        lookup_mpn("Z", distributors=["mouser"], entries=entries)
        self.assertEqual(mock_mouser.call_count, 1)
        lookup_mpn("Z", distributors=["mouser"], entries=entries)
        self.assertEqual(mock_mouser.call_count, 1)
        lookup_mpn("Z", distributors=["mouser"], force=True, entries=entries)
        self.assertEqual(mock_mouser.call_count, 2)


class TestShopLookupRoute(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        from bom_builder import storage

        self._needs = storage.NEEDS_DIR
        self._data = storage.DATA_DIR
        storage.DATA_DIR = __import__("pathlib").Path(self._tmpdir.name) / "data"
        storage.NEEDS_DIR = storage.DATA_DIR / "needs"
        storage.ensure_data_dirs()

        from main import app

        self.client = app.test_client()

    def tearDown(self) -> None:
        from bom_builder import storage

        storage.NEEDS_DIR = self._needs
        storage.DATA_DIR = self._data
        self._tmpdir.cleanup()

    def test_lookup_without_keys_returns_400(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with patch("bom_builder.distributor_lookup.digikey_api.is_configured", return_value=False):
                with patch("bom_builder.distributor_lookup.mouser_api.is_configured", return_value=False):
                    response = self.client.post(
                        "/shop/lookup",
                        json={"mpns": ["TEST"]},
                        headers={"Accept": "application/json"},
                    )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
