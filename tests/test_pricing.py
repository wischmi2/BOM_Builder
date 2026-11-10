from __future__ import annotations

import unittest

from bom_builder.pricing import best_offer, unit_price_at

DK = {
    "found": True,
    "stock": 5000,
    "price_1": 0.11,
    "price_breaks": [
        {"BreakQuantity": 1, "UnitPrice": 0.11},
        {"BreakQuantity": 10, "UnitPrice": 0.034},
        {"BreakQuantity": 50, "UnitPrice": 0.023},
    ],
}
MOUSER = {
    "found": True,
    "stock": 20000,
    "price_1": 0.10,
    "price_breaks": [
        {"Quantity": 1, "Price": "$0.10"},
        {"Quantity": 10, "Price": "$0.03"},
        {"Quantity": 100, "Price": "$0.02"},
    ],
}


class TestPricing(unittest.TestCase):
    def test_unit_price_uses_break_for_quantity(self) -> None:
        self.assertEqual(unit_price_at(DK, 1), 0.11)
        self.assertEqual(unit_price_at(DK, 85), 0.023)
        self.assertEqual(unit_price_at(MOUSER, 12), 0.03)

    def test_cheaper_distributor_wins(self) -> None:
        offer = best_offer({"digikey": DK, "mouser": MOUSER}, 85)
        self.assertEqual(offer.distributor, "DigiKey")  # 0.023 vs 0.03
        self.assertAlmostEqual(offer.total, 85 * 0.023)
        offer = best_offer({"digikey": DK, "mouser": MOUSER}, 200)
        self.assertEqual(offer.distributor, "Mouser")  # 0.02 vs 0.023

    def test_distributor_with_stock_wins_over_cheaper_without(self) -> None:
        dk_empty = {**DK, "stock": 0}
        offer = best_offer({"digikey": dk_empty, "mouser": {**MOUSER, "price_breaks": [{"Quantity": 1, "Price": "$0.50"}]}}, 10)
        self.assertEqual(offer.distributor, "Mouser")
        self.assertEqual(offer.note, "")

    def test_only_source_used_and_flagged_when_short(self) -> None:
        offer = best_offer({"digikey": {**DK, "stock": 3}}, 10)
        self.assertEqual(offer.distributor, "DigiKey")
        self.assertEqual(offer.note, "low stock")

    def test_no_price(self) -> None:
        offer = best_offer({"digikey": {"found": False}}, 5)
        self.assertFalse(offer.known)
        self.assertEqual(offer.total, 0.0)


if __name__ == "__main__":
    unittest.main()
