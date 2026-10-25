"""Attachment security/backup tests; all disk writes stay in TemporaryDirectory."""

import base64
from contextlib import closing
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import struct
import tempfile
import threading
import unittest
import zlib

from attachments import (AttachmentError, AttachmentStore, MAX_IMAGE_PREVIEW_BYTES,
                         MAX_TEXT_PREVIEW_BYTES, MAX_UPLOAD_BYTES)


NOW = "2026-10-20T18:30:00Z"


def png_pixel(extra_text=b""):
    def chunk(kind, raw):
        return struct.pack(">I", len(raw)) + kind + raw + struct.pack(">I", zlib.crc32(kind + raw))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
            + (chunk(b"tEXt", b"Comment\x00" + extra_text) if extra_text else b"")
            + chunk(b"IEND", b""))


class AttachmentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="madar-attachments-test-")
        self.home = Path(self.temporary.name)
        self.root = self.home / "attachment-storage"
        self.store = AttachmentStore(self.root)
        self.accounts = {
            "admin": {"username": "admin", "role": "admin", "projects": None},
            "alice": {"username": "alice", "role": "editor", "projects": ["p1"]},
            "bob": {"username": "bob", "role": "editor", "projects": ["p1"]},
            "reader": {"username": "reader", "role": "viewer", "projects": ["p1"]},
            "outsider": {"username": "outsider", "role": "editor", "projects": ["p2"]},
        }
        self.projects = [{"id": "p1"}, {"id": "p2"}]
        self.cards = [{"id": "c1", "projectId": "p1"}, {"id": "c2", "projectId": "p2"}]
        self.request_no = 0

    def tearDown(self):
        self.temporary.cleanup()

    def kwargs(self, actor="alice"):
        return {"actor": actor, "accounts": self.accounts,
                "cards": self.cards, "projects": self.projects}

    def upload(self, payload=b"Hello attachment\n", *, actor="alice", card_id="c1",
               filename="notes.txt", request_id=None):
        self.request_no += 1
        return self.store.upload(**self.kwargs(actor), card_id=card_id, filename=filename,
                                 content_base64=base64.b64encode(payload).decode("ascii"),
                                 request_id=request_id or f"req-{self.request_no}", now=NOW)

    def test_upload_list_read_and_plaintext_preview(self):
        item = self.upload("سلام دنیا\n".encode("utf8"), filename="فارسی.txt")
        self.assertEqual(item["projectId"], "p1")
        self.assertEqual(item["mime"], "text/plain")
        self.assertEqual(item["size"], len("سلام دنیا\n".encode("utf8")))
        self.assertEqual(len(self.store.list_card(**self.kwargs("reader"), card_id="c1")), 1)
        content = self.store.read(**self.kwargs("reader"), attachment_id=item["id"])
        self.assertEqual(base64.b64decode(content["contentBase64"]), "سلام دنیا\n".encode("utf8"))
        self.assertEqual(content["contentDisposition"], "attachment")
        self.assertEqual(content["xContentTypeOptions"], "nosniff")
        preview = self.store.preview(**self.kwargs("reader"), attachment_id=item["id"])
        self.assertEqual(preview["content"], "سلام دنیا\n")
        self.assertEqual(preview["kind"], "plain-text")

    def test_png_magic_and_small_image_preview(self):
        raw = png_pixel()
        item = self.upload(raw, filename="picture.PNG")
        self.assertEqual(item["mime"], "image/png")
        result = self.store.preview(**self.kwargs(), attachment_id=item["id"])
        self.assertTrue(result["available"])
        self.assertEqual(base64.b64decode(result["content"]), raw)

    def test_pdf_is_download_only_and_not_active_inline_preview(self):
        raw = b"%PDF-1.4\n1 0 obj<<>>endobj\nstartxref\n0\n%%EOF\n"
        item = self.upload(raw, filename="contract.pdf")
        preview = self.store.preview(**self.kwargs(), attachment_id=item["id"])
        self.assertEqual(preview["kind"], "pdf-download-only")
        self.assertFalse(preview["available"])
        self.assertIsNone(preview["content"])
        result = self.store.read(**self.kwargs(), attachment_id=item["id"])
        self.assertEqual(result["contentType"], "application/pdf")
        self.assertEqual(result["contentDisposition"], "attachment")

    def test_content_addressing_dedupes_bytes_but_not_metadata(self):
        first = self.upload(b"same binary as text", filename="one.txt")
        second = self.upload(b"same binary as text", filename="two.txt")
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(first["sha256"], second["sha256"])
        blobs = [p for p in (self.root / "blobs").rglob("*") if p.is_file()]
        self.assertEqual(len(blobs), 1)
        self.assertEqual(len(self.store.list_card(**self.kwargs(), card_id="c1")), 2)

    def test_upload_replay_persists_after_store_reopen(self):
        first = self.upload(b"unchanged", request_id="keep-request")
        self.store = AttachmentStore(self.root)
        replay = self.upload(b"unchanged", request_id="keep-request")
        self.assertEqual(first, replay)
        self.assertEqual(len(self.store.list_card(**self.kwargs(), card_id="c1")), 1)
        with self.assertRaisesRegex(AttachmentError, "Idempotency key reused"):
            self.upload(b"changed", request_id="keep-request")
        with self.assertRaisesRegex(AttachmentError, "Idempotency key reused"):
            self.upload(b"unchanged", actor="admin", request_id="keep-request")

    def test_reject_unauthorized_upload_read_preview_list_and_delete(self):
        item = self.upload()
        with self.assertRaises(PermissionError):
            self.upload(actor="reader")
        with self.assertRaises(PermissionError):
            self.upload(actor="outsider")
        with self.assertRaises(PermissionError):
            self.store.list_card(**self.kwargs("outsider"), card_id="c1")
        with self.assertRaises(PermissionError):
            self.store.read(**self.kwargs("outsider"), attachment_id=item["id"])
        with self.assertRaises(PermissionError):
            self.store.preview(**self.kwargs("outsider"), attachment_id=item["id"])
        with self.assertRaises(PermissionError):
            self.store.delete(**self.kwargs("reader"), attachment_id=item["id"],
                              request_id="del-reader", now=NOW)
        with self.assertRaises(PermissionError):
            self.store.delete(**self.kwargs("bob"), attachment_id=item["id"],
                              request_id="del-bob", now=NOW)
        self.assertEqual(len(self.store.list_card(**self.kwargs(), card_id="c1")), 1)

    def test_scope_revocation_prevents_further_reads_and_replay(self):
        item = self.upload(request_id="saved-upload")
        self.accounts["alice"]["projects"] = ["p2"]
        with self.assertRaises(PermissionError):
            self.store.read(**self.kwargs(), attachment_id=item["id"])
        with self.assertRaises(PermissionError):
            self.upload(request_id="saved-upload")

    def test_card_move_blocks_stale_scope_content_exposure(self):
        item = self.upload()
        self.cards[0]["projectId"] = "p2"
        with self.assertRaises(PermissionError):
            self.store.read(**self.kwargs("admin"), attachment_id=item["id"])

    def test_delete_tombstone_audit_preserves_bytes_and_admin_history(self):
        item = self.upload()
        deletion = self.store.delete(**self.kwargs(), attachment_id=item["id"],
                                     request_id="del1", now=NOW)
        self.assertTrue(deletion["deleted"])
        self.assertFalse(self.store.list_card(**self.kwargs(), card_id="c1"))
        with self.assertRaises(AttachmentError):
            self.store.read(**self.kwargs(), attachment_id=item["id"])
        deleted = self.store.list_card(**self.kwargs("admin"), card_id="c1", include_deleted=True)
        self.assertEqual(deleted[0]["deletedAt"], NOW)
        self.assertEqual([row["action"] for row in self.store.audit_log(
            **self.kwargs("admin"), project_id="p1")], ["upload", "delete"])
        self.assertTrue(self.store._blob_path(item["sha256"]).exists())
        with self.assertRaises(PermissionError):
            self.store.list_card(**self.kwargs(), card_id="c1", include_deleted=True)

    def test_delete_retry_after_reopen_does_not_duplicate_audit(self):
        item = self.upload()
        first = self.store.delete(**self.kwargs(), attachment_id=item["id"],
                                  request_id="delete-retry", now=NOW)
        self.store = AttachmentStore(self.root)
        repeated = self.store.delete(**self.kwargs(), attachment_id=item["id"],
                                     request_id="delete-retry", now=NOW)
        self.assertEqual(first, repeated)
        self.assertEqual(len(self.store.audit_log(**self.kwargs("admin"), project_id="p1")), 2)

    def test_delete_requires_existing_active_attachment_and_duplicate_key_conflicts(self):
        item = self.upload()
        self.store.delete(**self.kwargs("admin"), attachment_id=item["id"], request_id="del", now=NOW)
        with self.assertRaises(AttachmentError):
            self.store.delete(**self.kwargs("admin"), attachment_id=item["id"], request_id="del-2", now=NOW)
        self.assertEqual(len(self.store.audit_log(**self.kwargs("admin"), project_id="p1")), 2)

    def test_reject_invalid_filename_and_traversal_windows_paths(self):
        filenames = ["../secret.txt", r"C:\\Temp\\x.txt", r"\\server\\share\\x.png",
                     "a/b.txt", "file.svg", "file.html", "CON.txt", "NUL.txt",
                     "doc.pdf:stream", "evil\u202etxt.pdf", "evil..", "", " leading.txt", "tail.txt "]
        for filename in filenames:
            with self.subTest(filename=filename), self.assertRaises(AttachmentError):
                self.upload(filename=filename)
        self.assertFalse(self.store.list_card(**self.kwargs(), card_id="c1"))

    def test_reject_invalid_base64_padding_whitespace_data_uri_and_type(self):
        for payload in ["!!!", "Zg", "Zg==\n", "data:text/plain;base64,Zm9v", "", 123,
                        "A" * (4 * ((MAX_UPLOAD_BYTES + 2) // 3) + 4)]:
            with self.subTest(payload=str(payload)[:32]), self.assertRaises(AttachmentError):
                self.store.upload(**self.kwargs(), card_id="c1", filename="a.txt",
                                  content_base64=payload, request_id="bad", now=NOW)

    def test_reject_mismatched_extensions_active_html_svg_and_malformed_mime(self):
        failures = [
            (png_pixel(), "wrong.jpg"), (b"<svg onload=alert(1)>x</svg>", "fake.txt"),
            (b"<!DOCTYPE html><html>hello", "fake.txt"),
            (b"<script>alert(1)</script>", "fake.txt"),
            (b"notes then <img src=x onerror=alert(1)>", "fake.txt"),
            (b"%PDF-1.7\nno eof", "broken.pdf"),
            (b"\x00\x01\x02", "binary.txt"), (b"\xff\xd8\xffjunk", "bad.jpg"),
            (b"\x89PNG\r\n\x1a\n", "broken.png")
        ]
        for contents, filename in failures:
            with self.subTest(filename=filename), self.assertRaises(AttachmentError):
                self.upload(contents, filename=filename)

    def test_png_rejects_corrupted_crc_and_appended_html(self):
        original = png_pixel()
        corrupted = bytearray(original)
        corrupted[20] ^= 1
        for data in (bytes(corrupted), original + b"<html>evil</html>", original[:-12]):
            with self.subTest(size=len(data)), self.assertRaises(AttachmentError):
                self.upload(data, filename="bad.png")

    def test_four_megabyte_limit_and_bounded_plaintext_preview(self):
        raw = b"x" * MAX_UPLOAD_BYTES
        item = self.upload(raw, filename="maximum.txt")
        self.assertEqual(item["size"], MAX_UPLOAD_BYTES)
        preview = self.store.preview(**self.kwargs(), attachment_id=item["id"])
        self.assertTrue(preview["truncated"])
        self.assertEqual(len(preview["content"].encode("utf8")), MAX_TEXT_PREVIEW_BYTES)
        with self.assertRaises(AttachmentError):
            self.upload(raw + b"x", filename="oversized.txt")

    def test_large_image_preview_is_withheld(self):
        raw = png_pixel(b"x" * MAX_IMAGE_PREVIEW_BYTES)
        item = self.upload(raw, filename="large.png")
        preview = self.store.preview(**self.kwargs(), attachment_id=item["id"])
        self.assertEqual(preview["kind"], "image")
        self.assertFalse(preview["available"])
        self.assertIsNone(preview["content"])

    def test_bad_timestamp_and_invalid_actor_cannot_write(self):
        with self.assertRaises(AttachmentError):
            self.store.upload(**self.kwargs(), card_id="c1", filename="a.txt",
                              content_base64="eA==", request_id="bad-time", now="2026-10-20T18:30:00")
        with self.assertRaises(PermissionError):
            self.upload(actor="nonexistent")

    def test_corrupt_blob_detected_and_rejected_on_read(self):
        item = self.upload(b"important attachment")
        self.store._blob_path(item["sha256"]).write_bytes(b"tampered")
        with self.assertRaisesRegex(AttachmentError, "checksum mismatch"):
            self.store.read(**self.kwargs(), attachment_id=item["id"])
        with self.assertRaises(AttachmentError):
            self.store.backup_to(self.home / "bad-backup", actor="admin", accounts=self.accounts)

    def test_symlink_root_blob_and_database_are_rejected_when_supported(self):
        external = self.home / "external"
        external.mkdir()
        link = self.home / "link"
        try:
            link.symlink_to(external, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation unsupported or requires Windows privileges")
        with self.assertRaises(AttachmentError):
            AttachmentStore(link)
        with self.assertRaises(AttachmentError):
            AttachmentStore(link / "children")
        item = self.upload()
        blob_path = self.store._blob_path(item["sha256"])
        blob_path.unlink()
        blob_path.symlink_to(external / "target")
        with self.assertRaises(AttachmentError):
            self.store.read(**self.kwargs(), attachment_id=item["id"])

    def test_symlink_subdirectory_is_not_followed_when_supported(self):
        outside = self.home / "outside"
        outside.mkdir()
        target = self.root / "blobs" / "ab"
        try:
            target.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation unsupported")
        # A digest with prefix `ab` is needed to test the hostile shard.
        payload = next((f"blob{i}".encode() for i in range(100000)
                        if hashlib.sha256(f"blob{i}".encode()).hexdigest().startswith("ab")))
        with self.assertRaises(AttachmentError):
            self.upload(payload)
        self.assertFalse(list(outside.iterdir()))

    def test_concurrent_same_request_persists_one_metadata_row(self):
        results, errors = [], []
        barrier = threading.Barrier(6)
        def worker():
            try:
                barrier.wait(timeout=5)
                results.append(self.upload(b"concurrent", request_id="single-event"))
            except BaseException as exc:
                errors.append(exc)
        threads = [threading.Thread(target=worker) for _ in range(6)]
        for item in threads:
            item.start()
        for item in threads:
            item.join(timeout=10)
        self.assertFalse(errors)
        self.assertEqual(len(results), 6)
        self.assertEqual(len({item["id"] for item in results}), 1)
        self.assertEqual(len(self.store.list_card(**self.kwargs(), card_id="c1")), 1)

    def test_backup_manifest_and_restore_to_new_root_roundtrip(self):
        first = self.upload(png_pixel(), filename="image.png")
        second = self.upload(b"comment text", filename="comment.txt")
        self.store.delete(**self.kwargs(), attachment_id=second["id"], request_id="del-note", now=NOW)
        backup = self.home / "backup"
        manifest = self.store.backup_to(backup, actor="admin", accounts=self.accounts)
        self.assertEqual(manifest, AttachmentStore.verify_backup(backup))
        self.assertEqual(len(manifest["blobs"]), 2)
        restored = AttachmentStore.restore_backup(backup, self.home / "restored")
        self.assertEqual(restored.list_card(**self.kwargs(), card_id="c1"), [first])
        self.assertEqual(len(restored.list_card(**self.kwargs("admin"), card_id="c1", include_deleted=True)), 2)
        self.assertEqual(len(restored.audit_log(**self.kwargs("admin"), project_id="p1")), 3)
        self.assertEqual(base64.b64decode(restored.read(**self.kwargs(), attachment_id=first["id"])["contentBase64"]), png_pixel())

    def test_backup_cannot_overwrite_existing_or_inside_live_store(self):
        with self.assertRaises(AttachmentError):
            self.store.backup_to(self.root / "backup", actor="admin", accounts=self.accounts)
        with self.assertRaises(AttachmentError):
            self.store.backup_to(self.home, actor="admin", accounts=self.accounts)
        with self.assertRaises(PermissionError):
            self.store.backup_to(self.home / "new", actor="reader", accounts=self.accounts)

    def test_preexisting_unversioned_or_future_sqlite_schema_is_not_modified(self):
        for version in (0, 9):
            dirname = self.home / f"unrecognized-{version}"
            dirname.mkdir()
            database = dirname / "attachments.sqlite3"
            with closing(sqlite3.connect(str(database))) as connection, connection:
                connection.execute("CREATE TABLE existing_data(note TEXT)")
                connection.execute("INSERT INTO existing_data VALUES ('keep-this')")
                connection.execute(f"PRAGMA user_version={version}")
            with self.subTest(version=version), self.assertRaises(AttachmentError):
                AttachmentStore(dirname)
            with closing(sqlite3.connect(str(database))) as connection, connection:
                self.assertEqual(connection.execute("SELECT note FROM existing_data").fetchone()[0], "keep-this")
                self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], version)
                self.assertIsNone(connection.execute("SELECT name FROM sqlite_master WHERE name='attachments'").fetchone())
            # A Windows rename fails with WinError 32 when a connection leaked
            # from either the rejected AttachmentStore or the test fixture.
            probe = dirname / "closed-connection-probe.sqlite3"
            os.replace(database, probe)
            os.replace(probe, database)

    def test_backup_corruption_rejected_and_untouched_destination(self):
        self.upload(b"backup data")
        backup = self.home / "backup"
        self.store.backup_to(backup, actor="admin", accounts=self.accounts)
        blob = next(p for p in (backup / "blobs").rglob("*") if p.is_file())
        blob.write_bytes(b"damaged")
        with self.assertRaises(AttachmentError):
            AttachmentStore.verify_backup(backup)
        restore = self.home / "must-not-exist"
        with self.assertRaises(AttachmentError):
            AttachmentStore.restore_backup(backup, restore)
        self.assertFalse(restore.exists())

    def test_no_attachments_store_writes_outside_supplied_temp_root(self):
        self.upload(b"safe")
        self.assertTrue((self.root / "attachments.sqlite3").is_file())
        self.assertTrue((self.root / "blobs").is_dir())
        self.assertFalse((self.home / "tasks.json").exists())


if __name__ == "__main__":
    unittest.main()
