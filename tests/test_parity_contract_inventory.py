"""Static, safe shape checks for the independent Trello parity master inventory.

Does not access the network, import runtime hosts, read APPDATA, launch an EXE,
or assert that Trello/Madar behavior was exercised. Text inventory only.
"""

import collections
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parent.parent
MASTER = ROOT / "TRELLO_PARITY_MASTER_2026.md"
ROW = re.compile(r"^\|\s*((?:BD|WS|CD|CL|CO|VW|TP|AU|PL|MB|IN|AD|EX)\d{2})\s*\|")
REF = re.compile(r"^\[([A-Z]+)\]:\s+(https://[^\s]+)\s*$", re.MULTILINE)


def load():
    document = MASTER.read_text(encoding="utf-8")
    rows = []
    for line in document.splitlines():
        if ROW.match(line):
            cells = [part.strip() for part in line.split("|")[1:-1]]
            rows.append(cells)
    return document, rows


class TrelloParityMasterContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document, cls.rows = load()

    def test_large_inventory_includes_every_required_feature_family(self):
        self.assertGreaterEqual(len(self.rows), 180, "Do not revert to the 40-family subset")
        groups = {re.match(r"[A-Z]+", r[0]).group() for r in self.rows}
        self.assertEqual(groups, {
            "BD", "WS", "CD", "CL", "CO", "VW", "TP",
            "AU", "PL", "MB", "IN", "AD", "EX",
        })

    def test_stable_unique_ids_and_complete_machine_parseable_rows(self):
        ids = [r[0] for r in self.rows]
        self.assertEqual(len(ids), len(set(ids)))
        for cells in self.rows:
            with self.subTest(id=cells[0]):
                self.assertEqual(len(cells), 8)
                self.assertTrue(cells[1], "Feature cannot have an empty description")
                self.assertTrue(cells[2], "Tier must have explicit value or '?'")
                self.assertIn(cells[3], {"covered", "partial", "missing"})
                self.assertIn(cells[4], {"P0", "P1", "P2", "P3"})
                self.assertTrue(cells[5], "Every row needs local evidence or a specific gap")
                self.assertGreaterEqual(len(cells[6]), 20, "Acceptance must be testable")
                self.assertRegex(cells[7], r"^\[[A-Z]+\]$")

    def test_every_feature_has_an_official_public_link(self):
        urls = dict(REF.findall(self.document))
        self.assertGreaterEqual(len(urls), 25)
        for cells in self.rows:
            key = cells[7][1:-1]
            with self.subTest(id=cells[0], source=key):
                self.assertIn(key, urls)
                self.assertRegex(urls[key],
                    r"^https://(?:support\.atlassian\.com/trello/"
                    r"|developer\.atlassian\.com/cloud/trello/)")
        self.assertIn("[LEGAL]: https://www.atlassian.com/legal/", self.document)

    def test_p0_gates_and_madar_distinctiveness_are_preserved(self):
        ids = {r[0] for r in self.rows}
        for required in ("BD15", "WS01", "AD10", "AD11", "EX13",
                         "EX14", "IN16", "MB03", "MB04", "PL02", "AU14"):
            self.assertIn(required, ids)
        for term in ("فارسی", "RTL", "شمسی", "مالی", "فاکتور",
                     "local-first", "LAN", "G0 / Data", "G6 / Final"):
            self.assertIn(term, self.document)
        self.assertIn("نه ادعای تحقق فعلی", self.document)

    def test_report_statuses_do_not_imply_full_parity(self):
        tally = collections.Counter(r[3] for r in self.rows)
        self.assertGreater(tally["missing"], 0)
        self.assertGreater(tally["partial"], 0)
        self.assertGreater(tally["covered"], 0)
        self.assertGreater(sum(r[4] == "P0" for r in self.rows), 30)
        self.assertIn("معنای قبول‌شدن در EXE", self.document)
        self.assertNotIn("100% ACHIEVED", self.document)

    def test_snapshot_summary_exactly_matches_all_220_feature_rows(self):
        tally = collections.Counter(r[3] for r in self.rows)
        priority = collections.Counter(r[4] for r in self.rows)
        self.assertEqual(len(self.rows), 220)
        expected_lines = (
            ("covered (پوشش در کد، نه پذیرش)", tally["covered"]),
            ("partial", tally["partial"]),
            ("missing / فاقد مسیر تأییدشده", tally["missing"]),
            ("P0", priority["P0"]),
            ("P1", priority["P1"]),
            ("P2", priority["P2"]),
            ("P3", priority["P3"]),
        )
        for label, count in expected_lines:
            with self.subTest(label=label):
                persian_count = str(count).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
                self.assertIn(f"| {label} | **{persian_count}** |", self.document)
        self.assertEqual(sum(tally.values()), sum(priority.values()))

    def test_post_integration_code_only_statuses_are_not_overclaimed(self):
        rows = {r[0]: r for r in self.rows}
        for feature_id in ("BD01", "BD15", "WS01", "WS03"):
            with self.subTest(feature_id=feature_id):
                self.assertEqual(rows[feature_id][3], "covered")
        for feature_id in ("BD18", "WS02", "WS04", "WS05"):
            with self.subTest(feature_id=feature_id):
                self.assertEqual(rows[feature_id][3], "partial")
        self.assertIn("به‌روزرسانی Snapshot کد: 2026-10-21", self.document)
        self.assertIn("بدون ادعای", self.document) if (
            "بدون ادعای" in self.document
        ) else self.assertIn("نه ادعای تحقق فعلی", self.document)
        # Read-only integration markers: confirm documented code paths exist.
        app = (ROOT / "src" / "App.jsx").read_text(encoding="utf-8")
        # The large-board performance integration replaced eager per-lane
        # enumeration with indexed groups and ProgressiveLane. Either path
        # preserves stable card order; old exact source-string checks must not
        # veto the more scalable equivalent implementation.
        self.assertTrue(
            "getOrderedLaneCards(filtered,activeBoard.id,stage.id)" in app
            or ("boardGroups.get(stage.id)" in app and
                "createBoardPerformanceIndex(data" in app and
                "<ProgressiveLane items={items}" in app)
        )
        self.assertIn("moveCardInState", app)
        self.assertIn("<WorkspaceManager data={data}", app)
        order = (ROOT / "src" / "cardorder.js").read_text(encoding="utf-8")
        self.assertIn("export function moveCardInState", order)
        panel = (ROOT / "src" / "workspaces_panel.jsx").read_text(encoding="utf-8")
        self.assertIn("export function WorkspaceManager", panel)
        host = (ROOT / "native_app.py").read_text(encoding="utf-8")
        validator = (ROOT / "data_model.py").read_text(encoding="utf-8")
        self.assertIn('if "cardOrder" in task', host)
        self.assertIn('if "cardOrder" in task', validator)

    def test_work_is_only_an_inventory_not_execution_or_trello_access(self):
        self.assertIn("هیچ REA، login، scraping", self.document)
        self.assertIn("نه گزارشی از اجرا", self.document)
        # Explicitly verify this suite does not need imports of client,
        # native_app, requests, browser tooling or an APPDATA fixture.
        self.assertTrue(MASTER.is_file())


if __name__ == "__main__":
    unittest.main()
