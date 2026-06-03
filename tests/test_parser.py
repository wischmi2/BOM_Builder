from __future__ import annotations

import unittest
from pathlib import Path

from bom_builder.parser import bom_id_from_filename, parse_bom_csv_file

SAMPLE_CSV = Path(
    r"C:\Brian\ProductionTest\Loadboard_Purchase_2026\DD02040\Parts_Purchase\DD02040.RF300.3_2026.csv"
)


@unittest.skipUnless(SAMPLE_CSV.exists(), "sample CSV not available on this machine")
class TestParserSampleCsv(unittest.TestCase):
    def test_parses_all_data_rows(self) -> None:
        bom = parse_bom_csv_file(SAMPLE_CSV)
        self.assertEqual(len(bom.lines), 59)
        self.assertEqual(bom.bom_id, "DD02040.RF300.3_2026")

    def test_first_line_designators_and_quantity(self) -> None:
        bom = parse_bom_csv_file(SAMPLE_CSV)
        first = bom.lines[0]
        self.assertEqual(first.name, "4.7uF 35V")
        self.assertEqual(first.quantity, 5)
        self.assertEqual(first.designators, ["C2", "C4", "C5", "C6", "C8"])
        self.assertEqual(first.lib_ref, "GRM219R6YA475KA73D")

    def test_dni_detection(self) -> None:
        bom = parse_bom_csv_file(SAMPLE_CSV)
        dni_lines = [line for line in bom.lines if line.is_dni]
        self.assertGreater(len(dni_lines), 0)
        self.assertTrue(any(line.name.upper() == "DNI" for line in dni_lines))

    def test_multi_mpn_libref(self) -> None:
        bom = parse_bom_csv_file(SAMPLE_CSV)
        multi = next(line for line in bom.lines if "GRM0335C1H100JA01J" in line.lib_ref and "," in line.lib_ref)
        self.assertIn(",", multi.lib_ref)


class TestParserInline(unittest.TestCase):
    def test_bom_id_from_filename(self) -> None:
        self.assertEqual(bom_id_from_filename("DD02040.RF300.3_2026.csv"), "DD02040.RF300.3_2026")

    def test_minimal_csv(self) -> None:
        from bom_builder.parser import parse_bom_csv

        csv_text = (
            "Name,Description,Designator,Footprint,LibRef,Quantity\n"
            '10k,Resistor,"R4, R7",R0402,RK73H1ETTP1002F,7\n'
        )
        bom = parse_bom_csv(csv_text, bom_id="test", source_filename="test.csv")
        self.assertEqual(len(bom.lines), 1)
        line = bom.lines[0]
        self.assertEqual(line.designators, ["R4", "R7"])
        self.assertEqual(line.quantity, 7)


if __name__ == "__main__":
    unittest.main()
