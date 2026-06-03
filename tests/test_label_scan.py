from __future__ import annotations

import unittest

from bom_builder.label_scan import parse_label_text


SAMPLE_DIGIKEY_OCR = """
DigiKey
INV# 104130519
SO# 86347941
PN: YAG2587TR-ND
MFR PN: RC0201FR-07301RL
RES 301 OHM 1% 1/20W 0201
10,000
9287
LOT CODE 38K1240007
COO TW
ROHS3 COMP
"""


class TestLabelScan(unittest.TestCase):
    def test_parses_digikey_style_label(self) -> None:
        result = parse_label_text(SAMPLE_DIGIKEY_OCR)
        self.assertEqual(result.lib_ref, "RC0201FR-07301RL")
        self.assertIn("301", result.name)
        self.assertIn("OHM", result.name.upper())
        self.assertEqual(result.qty_on_hand, 9287)
        self.assertIn("YAG2587TR-ND", result.notes)

    def test_prefers_mfr_pn_over_digikey_for_lib_ref(self) -> None:
        result = parse_label_text(SAMPLE_DIGIKEY_OCR)
        self.assertNotEqual(result.lib_ref, "YAG2587TR-ND")

    def test_empty_text_warns(self) -> None:
        result = parse_label_text("")
        self.assertEqual(result.lib_ref, "")
        self.assertTrue(result.warnings)


if __name__ == "__main__":
    unittest.main()
