"""Round-trip typed source archival on synthetic bytes only."""
from hashlib import sha256
from contextlib import closing
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest

from parsian_full_archive_sqlite import create_archive, FullArchiveError


def source(root):
    raw = [
        {"table": "tbl_Goods", "fields": {
            "ID": {"t": "integer", "text": "1"},
            "Price": {"t": "float", "text": "100.0"},
            "Name": {"t": "text", "value": "Synthetic کالا"},
            "Blob": {"t": "binary", "b64": "AAEC"},
            "N": {"t": "null"},
        }},
        {"table": "tbl_Check", "fields": {
            "ID": {"t": "integer", "text": "7"},
            "Amount": {"t": "decimal", "text": "500.125"},
            "Valid": {"t": "bit", "value": False},
        }},
    ]
    archive = root/"raw.jsonl"
    archive.write_text("\n".join(json.dumps(x,ensure_ascii=False)
                                  for x in raw)+"\n", encoding="utf8")
    manifest = {
        "source": "ATTACHED_LIVE_SQL_NOT_RESTORED_BACKUP",
        "snapshotMatchesBackup": False,
        "sourceCurrency": "RIAL_OWNER_CONFIRMED",
        "vendorTableCount": 3, "vendorRowCount": 2,
        "tableCounts": {"tbl_Goods": 1, "tbl_Check": 1, "tbl_Empty": 0},
        "archiveSha256": sha256(archive.read_bytes()).hexdigest(),
    }
    source_manifest = root/"manifest.json"
    source_manifest.write_text(json.dumps(manifest), encoding="utf8")
    return archive, source_manifest


class FullSourceArchiveTests(unittest.TestCase):
    def test_complete_tables_round_trip_with_binary_and_money_types(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw, manifest = source(root)
            target = root/"private-preservation.sqlite3"
            result = create_archive(raw, manifest, target)
            self.assertEqual(result["archivedSourceTables"], 3)
            self.assertEqual(result["archivedSourceRows"], 2)
            self.assertFalse(result["financialOperationalDataImported"])
            with closing(sqlite3.connect(target)) as db:
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                row, stored_digest = db.execute(
                    "SELECT typed_raw_json,row_sha256 FROM archived_rows "
                    "WHERE source_table='tbl_Goods'").fetchone()
                self.assertEqual(sha256(row).hexdigest(), stored_digest)
                self.assertEqual(json.loads(row)["fields"]["Blob"]["b64"], "AAEC")
                self.assertEqual(json.loads(row)["fields"]["Price"]["text"], "100.0")
            with self.assertRaises(FullArchiveError):
                create_archive(raw, manifest, target)

    def test_modified_source_does_not_publish(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw, manifest = source(root)
            raw.write_bytes(raw.read_bytes() + b"extra")
            dest = root/"target.sqlite3"
            with self.assertRaisesRegex(FullArchiveError, "digest"):
                create_archive(raw, manifest, dest)
            self.assertFalse(dest.exists())

    def test_wrong_row_coverage_does_not_publish(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw, manifest = source(root)
            obj = json.loads(manifest.read_text())
            obj["tableCounts"]["tbl_Goods"] = 2
            obj["vendorRowCount"] = 3
            manifest.write_text(json.dumps(obj))
            dest = root/"target.sqlite3"
            with self.assertRaisesRegex(FullArchiveError, "Missing or unexpected"):
                create_archive(raw, manifest, dest)
            self.assertFalse(dest.exists())


if __name__ == "__main__":
    unittest.main()
