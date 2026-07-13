from __future__ import annotations

import unittest
from pathlib import Path

from bom_builder.parser import parse_kicad_bom_csv, parse_kicad_bom_csv_file

FIXTURE = Path(__file__).parent / "fixtures" / "nrf54l15_soil_moisture.csv"


class TestKiCadParserSample(unittest.TestCase):
    def setUp(self) -> None:
        self.bom = parse_kicad_bom_csv_file(FIXTURE)

    def test_parses_all_rows(self) -> None:
        # 42 data rows in the fixture, none flagged Exclude from BOM.
        self.assertEqual(len(self.bom.lines), 42)
        self.assertEqual(self.bom.bom_id, "nrf54l15_soil_moisture")

    def test_multi_reference_row(self) -> None:
        line = next(l for l in self.bom.lines if l.name == "100nF")
        self.assertEqual(line.designators, ["C6", "C14", "C15", "C26", "C28"])
        self.assertEqual(line.quantity, 5)

    def test_lib_ref_from_mpn(self) -> None:
        line = next(l for l in self.bom.lines if "C1" in l.designators)
        self.assertEqual(line.lib_ref, "GRM033R61A225KE47D")

    def test_lib_ref_falls_back_to_value_when_mpn_and_lcsc_blank(self) -> None:
        # nRF54L15 (U6), nPM1300 (U2), USB-C (J1) have no MPN and no LCSC part.
        u6 = next(l for l in self.bom.lines if "U6" in l.designators)
        self.assertEqual(u6.lib_ref, "nRF54L15-QFXX")
        j1 = next(l for l in self.bom.lines if "J1" in l.designators)
        self.assertEqual(j1.lib_ref, "TYPE-C-31-M-12")

    def test_footprint_and_description_preserved(self) -> None:
        line = next(l for l in self.bom.lines if "C4" in l.designators)
        self.assertEqual(line.footprint, "easyeda2kicad:C0402")
        self.assertIn("1uF", line.description)


class TestKiCadParserInline(unittest.TestCase):
    def test_lcsc_fallback_when_mpn_blank(self) -> None:
        csv_text = (
            '"Reference","Qty","Value","DNP","Exclude from BOM","Footprint","LCSC Part","MPN","Description"\n'
            '"C1","1","10uF","","","C0402","C12345","","cap"\n'
        )
        bom = parse_kicad_bom_csv(csv_text, bom_id="t")
        self.assertEqual(bom.lines[0].lib_ref, "C12345")

    def test_dnp_flag_marks_dni(self) -> None:
        csv_text = (
            '"Reference","Qty","Value","DNP","Exclude from BOM","Footprint","MPN","Description"\n'
            '"R1","1","10k","DNP","","R0402","RC0402","res"\n'
        )
        bom = parse_kicad_bom_csv(csv_text, bom_id="t")
        self.assertTrue(bom.lines[0].is_dni)

    def test_exclude_from_bom_rows_skipped(self) -> None:
        csv_text = (
            '"Reference","Qty","Value","DNP","Exclude from BOM","Footprint","MPN","Description"\n'
            '"H1","1","MountingHole","","Exclude from BOM","MountingHole","","hole"\n'
            '"R1","1","10k","","","R0402","RC0402","res"\n'
        )
        bom = parse_kicad_bom_csv(csv_text, bom_id="t")
        self.assertEqual(len(bom.lines), 1)
        self.assertEqual(bom.lines[0].name, "10k")

    def test_qty_falls_back_to_designator_count(self) -> None:
        csv_text = (
            '"Reference","Value","Footprint","MPN","Description"\n'
            '"R1,R2,R3","10k","R0402","RC0402","res"\n'
        )
        bom = parse_kicad_bom_csv(csv_text, bom_id="t")
        self.assertEqual(bom.lines[0].quantity, 3)

    def test_space_separated_references(self) -> None:
        csv_text = (
            '"Reference","Qty","Value","Footprint","MPN","Description"\n'
            '"R1 R2","2","10k","R0402","RC0402","res"\n'
        )
        bom = parse_kicad_bom_csv(csv_text, bom_id="t")
        self.assertEqual(bom.lines[0].designators, ["R1", "R2"])

    def test_rejects_non_kicad_csv(self) -> None:
        csv_text = "Name,Description,Designator,Footprint,LibRef,Quantity\n10k,res,R1,R0402,RC0402,1\n"
        with self.assertRaises(ValueError):
            parse_kicad_bom_csv(csv_text, bom_id="t")


if __name__ == "__main__":
    unittest.main()
