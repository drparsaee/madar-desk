"""Read-only document coverage checks for the synthetic MTR acceptance plan.

Reads only the design contract and its companion acceptance matrix. Does not
import an application, access a real profile, contact a service, or mutate a
financial record. A pass proves traceability coverage, NEVER acceptance.
"""

from collections import Counter
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "modernization"
DESIGN = DOCS / "MADAR_TARAZ_RADAR_INTEGRATED_DESIGN_AND_ACCEPTANCE_20261109.md"
MATRIX = DOCS / "MTR_E7_ACCEPTANCE_GATES_20261109.md"
DESIGN_ROW = re.compile(r"^\|\s*\*\*(AC-\d{2}|G-\d{2})\*\*\s*\|")
MATRIX_ROW = re.compile(r"^\|\s*(AC-\d{2}|G-\d{2})\s*\|")
EVIDENCE_REF = re.compile(r"`([A-Z]{2}):test_[a-z0-9_]+`")
CODE_ROW = re.compile(r"^\|\s*`([A-Z]{2})`\s*\|")


def matching_rows(text, pattern):
    return [(match.group(1), line)
            for line in text.splitlines()
            if (match := pattern.match(line))]


class AcceptanceMatrixCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.design = DESIGN.read_text(encoding="utf-8")
        cls.matrix = MATRIX.read_text(encoding="utf-8")
        cls.design_rows = matching_rows(cls.design, DESIGN_ROW)
        cls.matrix_rows = matching_rows(cls.matrix, MATRIX_ROW)
        cls.code_index = {
            match.group(1)
            for line in cls.matrix.splitlines()
            if (match := CODE_ROW.match(line))
        }

    def test_design_contains_exact_32_ac_and_8_g_scenarios(self):
        expected = {f"AC-{i:02d}" for i in range(1, 33)}
        expected |= {f"G-{i:02d}" for i in range(1, 9)}
        self.assertEqual(set(dict(self.design_rows)), expected)
        self.assertEqual(len(self.design_rows), 40)
        self.assertTrue(all(count == 1 for count in
                            Counter(identifier for identifier, _ in self.design_rows).values()))

    def test_matrix_covers_every_design_id_exactly_once(self):
        self.assertEqual(set(dict(self.matrix_rows)),
                         set(dict(self.design_rows)))
        counts = Counter(identifier for identifier, _ in self.matrix_rows)
        self.assertEqual(len(counts), 40)
        self.assertTrue(all(count == 1 for count in counts.values()))

    def test_rows_include_concrete_evidence_and_explicit_open_gate(self):
        for identifier, row in self.matrix_rows:
            with self.subTest(id=identifier):
                parts = [part.strip() for part in row.strip().strip("|").split("|")]
                self.assertEqual(len(parts), 7 if identifier.startswith("AC-") else 6)
                self.assertEqual(parts[-1], "OPEN")
                self.assertIn(parts[-2], {"SLICE", "NONE"})
                evidence = parts[3] if identifier.startswith("AC-") else parts[2]
                missing = parts[4] if identifier.startswith("AC-") else parts[3]
                self.assertTrue(evidence)
                self.assertTrue(missing and missing != "—")
                references = EVIDENCE_REF.findall(evidence)
                self.assertEqual(bool(references), parts[-2] == "SLICE")
                if parts[-2] == "NONE":
                    self.assertTrue(evidence.startswith("—"))
                self.assertTrue(set(references) <= self.code_index)

    def test_matrix_says_coverage_not_acceptance(self):
        self.assertIn("E7 NOT ACCEPTED", self.matrix)
        self.assertIn("E0–E7 NOT COMPLETE", self.matrix)
        self.assertIn("40/40", self.matrix)
        self.assertIn("No row below has passed", self.matrix)
        self.assertIn("Host-authenticated transport", self.matrix)


if __name__ == "__main__":
    unittest.main()
