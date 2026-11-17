"""Synthetic, disposable Windows-only tests for durable paired-peer mailbox."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import os
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from integration_mailbox_v1 import IntegrationMailbox, sign_counterparties_reply
from integration_key_registry import _private_windows_guard


WORKSPACE = "a" * 32
INSTALL = "b" * 32
OTHER_INSTALL = "c" * 32
COMPANY = "d" * 32
OTHER_COMPANY = "e" * 32
REQUEST = "f" * 32
KEY = "ik_" + "1" * 24
OTHER_KEY = "ik_" + "2" * 24
SECRET = b"mdv1_Synthetic-integration-bearer-do-not-use-in-production-123"
PARTY = {"partyId": "TARAZ-A01", "name": "مشتری آرمان", "kind": "customer"}
SEARCH_PARAMS = {"query": "آرمان", "kind": "customer", "limit": 50,
                 "cursor": None}
SEARCH_RESULT = {"parties": [PARTY], "hasMore": False, "nextCursor": None}


@unittest.skipUnless(os.name == "nt", "Private Windows DACL is required")
class IntegrationMailboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="madar-mailbox-synthetic-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / "test-mailbox.sqlite3"
        self.calls = []
        self.live = {"paired": True, "actor_grant": True, "company": COMPANY}

        def authorize(**scope):
            self.calls.append(scope.copy())
            if not self.live["paired"] or not self.live["actor_grant"]:
                return False
            if (scope["workspace_id"] != WORKSPACE or
                    scope["installation_id"] != INSTALL or
                    scope["company_id"] != self.live["company"]):
                return False
            if scope["action"] in ("poll", "reply", "delivery_ack"):
                if scope["peer_key_id"] != KEY:
                    return False
            else:
                if scope["peer_key_id"] is not None:
                    return False
            if scope["requested_actor"] is not None and scope["requested_actor"] != "qa-actor":
                return False
            if (scope["requested_grant"] is not None and
                    scope["requested_grant"] != "counterparties.read"):
                return False
            return True

        self.authorize = authorize
        self.box = IntegrationMailbox(self.path, authorizer=authorize)

    def enqueue(self, **override):
        args = dict(workspace_id=WORKSPACE, installation_id=INSTALL,
                    company_id=COMPANY, request_id=REQUEST,
                    requested_actor="qa-actor",
                    requested_grant="counterparties.read",
                    operation="Counterparties.Search",
                    parameters=dict(SEARCH_PARAMS), ttl_seconds=180,
                    now=1000)
        args.update(override)
        return self.box.enqueue(**args)

    def poll(self, **override):
        args = dict(workspace_id=WORKSPACE, installation_id=INSTALL,
                    company_id=COMPANY, peer_key_id=KEY, now=1001)
        args.update(override)
        return self.box.poll(**args)

    def reply(self, envelope, result=None, **override):
        result = result if result is not None else dict(SEARCH_RESULT)
        args = dict(workspace_id=WORKSPACE, installation_id=INSTALL,
                    company_id=COMPANY, request_id=REQUEST, peer_key_id=KEY,
                    result=result,
                    signature=sign_counterparties_reply(SECRET, envelope, result),
                    peer_secret=SECRET, now=1002)
        args.update(override)
        return self.box.submit_reply(**args)

    def reconcile(self, **override):
        args = dict(workspace_id=WORKSPACE, installation_id=INSTALL,
                    company_id=COMPANY, request_id=REQUEST,
                    requested_actor="qa-actor", now=1003)
        args.update(override)
        return self.box.reconcile(**args)

    def test_immutable_request_delivery_reply_result_ack_and_restart(self):
        self.assertEqual(self.enqueue(), {
            "requestId": REQUEST, "status": "pending", "reused": False})
        envelope = self.poll()[0]
        self.assertEqual(self.poll()[0], envelope)
        self.assertEqual(set(envelope), {"workspaceId", "installationId",
                         "companyId", "requestId", "requestedActor",
                         "requestedGrant", "operation", "parameters"})
        self.assertEqual(self.box.acknowledge_delivery(
            workspace_id=WORKSPACE, installation_id=INSTALL,
            company_id=COMPANY, request_id=REQUEST, peer_key_id=KEY,
            now=1002)["status"], "pending")
        # Lost delivery ACK does not remove or hide a pending request.
        self.assertEqual(self.poll(now=1003), [envelope])
        self.assertEqual(self.reply(envelope)["status"], "completed")
        self.assertEqual(self.poll(now=1004), [])
        reloaded = IntegrationMailbox(self.path, authorizer=self.authorize)
        found = reloaded.reconcile(
            workspace_id=WORKSPACE, installation_id=INSTALL,
            company_id=COMPANY, request_id=REQUEST,
            requested_actor="qa-actor", now=1100)
        self.assertEqual(found["status"], "completed")
        self.assertEqual(found["result"], SEARCH_RESULT)
        self.assertFalse(found["acknowledged"])
        self.assertEqual(reloaded.acknowledge_result(
            workspace_id=WORKSPACE, installation_id=INSTALL,
            company_id=COMPANY, request_id=REQUEST,
            requested_actor="qa-actor", now=1101)["status"], "completed")
        # A lost ACK response can be replayed; persisted result is never lost.
        self.assertTrue(self.reconcile()["acknowledged"])
        self.assertEqual(self.reply(envelope, now=1250)["status"], "completed")
        self.assertEqual(self.reconcile(now=999999)["result"], SEARCH_RESULT)
        self.assertEqual(self.box.acknowledge_result(
            workspace_id=WORKSPACE, installation_id=INSTALL,
            company_id=COMPANY, request_id=REQUEST,
            requested_actor="qa-actor", now=1250)["acknowledged"], True)

    def test_get_null_and_minimal_party_projection(self):
        self.enqueue(operation="Counterparties.Get",
                     parameters={"partyId": "TARAZ-A01"})
        envelope = self.poll()[0]
        self.assertEqual(self.reply(envelope, {"party": PARTY})["status"],
                         "completed")
        self.assertEqual(self.reconcile()["result"], {"party": PARTY})
        self.assertNotIn("balance", json.dumps(self.reconcile()))
        other_id = "0" * 32
        self.enqueue(request_id=other_id, operation="Counterparties.Get",
                     parameters={"partyId": "UNKNOWN-ID"}, now=1100)
        second = next(item for item in self.poll(now=1101) if
                      item["requestId"] == other_id)
        result = {"party": None}
        self.box.submit_reply(workspace_id=WORKSPACE, installation_id=INSTALL,
                              company_id=COMPANY, request_id=other_id,
                              peer_key_id=KEY, result=result,
                              signature=sign_counterparties_reply(
                                  SECRET, second, result),
                              peer_secret=SECRET, now=1102)
        self.assertEqual(self.box.reconcile(
            workspace_id=WORKSPACE, installation_id=INSTALL,
            company_id=COMPANY, request_id=other_id,
            requested_actor="qa-actor", now=1103)["result"], result)

    def test_idempotency_conflict_duplicate_and_expired_request(self):
        self.enqueue()
        self.assertEqual(self.enqueue(now=1010, ttl_seconds=900),
                         {"requestId": REQUEST, "status": "pending", "reused": True})
        with self.assertRaisesRegex(ValueError, "idempotency collision"):
            self.enqueue(parameters={"query": "different", "kind": "all",
                                     "limit": 5, "cursor": None})
        with self.assertRaisesRegex(PermissionError, "permission denied"):
            self.enqueue(company_id=OTHER_COMPANY)
        with self.assertRaisesRegex(PermissionError, "permission denied"):
            self.enqueue(installation_id=OTHER_INSTALL)
        self.assertEqual(self.poll(now=1181), [])
        self.assertEqual(self.reconcile(now=1181)["status"], "expired")
        self.assertEqual(self.enqueue(now=1181)["status"], "expired")
        envelope = {
            "workspaceId": WORKSPACE, "installationId": INSTALL,
            "companyId": COMPANY, "requestId": REQUEST,
            "requestedActor": "qa-actor", "requestedGrant": "counterparties.read",
            "operation": "Counterparties.Search", "parameters": SEARCH_PARAMS}
        with self.assertRaisesRegex(ValueError, "Expired"):
            self.reply(envelope, now=1181)
        self.assertEqual(self.reconcile(now=1182)["result"], None)

    def test_replay_cross_peer_company_wrong_mac_and_conflicting_reply(self):
        self.enqueue()
        envelope = self.poll()[0]
        with self.assertRaises(PermissionError):
            self.poll(peer_key_id=OTHER_KEY)
        with self.assertRaises(PermissionError):
            self.poll(installation_id=OTHER_INSTALL)
        with self.assertRaises(PermissionError):
            self.poll(company_id=OTHER_COMPANY)
        with self.assertRaises(PermissionError):
            self.reply(envelope, peer_key_id=OTHER_KEY)
        with self.assertRaises(PermissionError):
            self.reply(envelope, company_id=OTHER_COMPANY)
        with self.assertRaises(PermissionError):
            self.reply(envelope, signature="0" * 64)
        substituted = dict(envelope, companyId=OTHER_COMPANY)
        with self.assertRaises(PermissionError):
            self.reply(envelope,
                       signature=sign_counterparties_reply(
                           SECRET, substituted, SEARCH_RESULT))
        self.assertEqual(self.reconcile()["status"], "pending")
        self.reply(envelope)
        modified = {"parties": [{"partyId": "TARAZ-B02", "name": "Other",
                                 "kind": "both"}],
                    "hasMore": False, "nextCursor": None}
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            self.reply(envelope, modified, now=1005)
        self.assertEqual(self.reconcile()["result"], SEARCH_RESULT)

    def test_database_scope_is_strict_even_if_host_authorizer_is_permissive(self):
        self.enqueue()
        permissive = IntegrationMailbox(self.path, authorizer=lambda **_: True)
        with self.assertRaises(PermissionError):
            permissive.reconcile(
                workspace_id=WORKSPACE, installation_id=INSTALL,
                company_id=OTHER_COMPANY, request_id=REQUEST,
                requested_actor="qa-actor", now=1010)
        with self.assertRaises(PermissionError):
            permissive.submit_reply(
                workspace_id=WORKSPACE, installation_id=OTHER_INSTALL,
                company_id=COMPANY, request_id=REQUEST,
                peer_key_id=KEY, result=SEARCH_RESULT,
                signature="0" * 64, peer_secret=SECRET, now=1010)
        self.assertEqual(self.reconcile()["status"], "pending")

    def test_concurrent_idempotent_enqueue_keeps_one_request(self):
        def enqueue(_):
            return self.enqueue()
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(enqueue, range(8)))
        self.assertEqual(sum(not item["reused"] for item in results), 1)
        self.assertTrue(all(item["requestId"] == REQUEST for item in results))
        self.assertEqual(len(self.poll()), 1)

    def test_live_grant_revocation_and_peer_revocation(self):
        self.live["actor_grant"] = False
        with self.assertRaises(PermissionError):
            self.enqueue()
        self.live["actor_grant"] = True
        self.enqueue()
        envelope = self.poll()[0]
        self.live["paired"] = False
        with self.assertRaises(PermissionError):
            self.poll()
        with self.assertRaises(PermissionError):
            self.reply(envelope)
        with self.assertRaises(PermissionError):
            self.reconcile()
        self.live["paired"] = True
        self.live["actor_grant"] = False
        with self.assertRaises(PermissionError):
            self.reconcile()
        with self.assertRaises(PermissionError):
            self.reply(envelope)
        self.live["actor_grant"] = True
        self.assertEqual(self.reconcile()["status"], "pending")

    def test_malformed_request_response_size_and_untrusted_flags(self):
        attempts = (
            {"operation": "Counterparties.Payments", "parameters": {}},
            {"operation": "Counterparties.Search", "parameters":
             {"query": "x", "kind": "all", "limit": 51, "cursor": None}},
            {"operation": "Counterparties.Search", "parameters":
             {"query": "x\n", "kind": "all", "limit": 1, "cursor": None}},
            {"operation": "Counterparties.Search", "parameters":
             {"query": "x" * 121, "kind": "all", "limit": 1, "cursor": None}},
            {"operation": "Counterparties.Get", "parameters":
             {"partyId": "TARAZ-A01", "balance": 100}},
            {"operation": "Counterparties.Get", "parameters":
             {"partyId": "ps.parsian.1405.1"}},
            {"requested_grant": "project.admin"},
            {"request_id": "INVALID"},
            {"ttl_seconds": 100000},
            {"requested_actor": "qa-actor", "isAdmin": True},
        )
        for values in attempts:
            with self.subTest(values=values), self.assertRaises((ValueError, TypeError)):
                self.enqueue(**values)
        self.enqueue()
        envelope = self.poll()[0]
        results = (
            {"parties": [dict(PARTY, accountBalance=4000)],
             "hasMore": False, "nextCursor": None},
            {"parties": [dict(PARTY, name="n" * 500)],
             "hasMore": False, "nextCursor": None},
            {"parties": [dict(PARTY, name="x\n" * 5)],
             "hasMore": False, "nextCursor": None},
            {"parties": [dict(PARTY, partyId="ps.parsian.1405.x")],
             "hasMore": False, "nextCursor": None},
            {"parties": [PARTY] * 51, "hasMore": False, "nextCursor": None},
            {"parties": [PARTY, PARTY], "hasMore": False, "nextCursor": None},
            {"parties": [PARTY], "hasMore": True, "nextCursor": None},
            {"parties": [PARTY], "hasMore": False, "nextCursor": "unexpected"},
            {"parties": [PARTY], "hasMore": False, "nextCursor": None,
             "creditLimit": 1},
        )
        for values in results:
            with self.subTest(result=values), self.assertRaises(ValueError):
                self.reply(envelope, values)
        large_page = {
            "parties": [
                {"partyId": "TARAZ-" + str(i), "name": "😀" * 250,
                 "kind": "both"} for i in range(50)],
            "hasMore": False, "nextCursor": None}
        with self.assertRaisesRegex(ValueError, "Oversized"):
            self.reply(envelope, large_page)
        self.assertEqual(self.reconcile()["status"], "pending")

    def test_transaction_rolls_back_if_authorization_lost_before_commit(self):
        self.enqueue()
        envelope = self.poll()[0]
        original = self.box.authorizer
        seen = {"replies": 0}

        def revoke_before_commit(**kw):
            if kw["action"] == "reply":
                seen["replies"] += 1
                if seen["replies"] == 3:
                    return False
            return original(**kw)

        self.box.authorizer = revoke_before_commit
        with self.assertRaises(PermissionError):
            self.reply(envelope)
        self.assertEqual(seen["replies"], 3)
        self.box.authorizer = original
        # Simulated process loss/reopen must not leave a half-committed reply.
        self.box = IntegrationMailbox(self.path, authorizer=self.authorize)
        self.assertEqual(self.reconcile()["status"], "pending")
        self.reply(envelope)
        self.assertEqual(self.reconcile()["status"], "completed")

    def test_real_child_process_crash_uses_sqlite_hot_journal_recovery(self):
        self.enqueue()
        # Crash the disposable writer after modifying a page but before COMMIT.
        # SQLite's persistent TRUNCATE journal must restore the queued request.
        child_code = (
            "import os,sqlite3,sys\n"
            "db=sqlite3.connect(sys.argv[1], isolation_level=None)\n"
            "db.execute('PRAGMA journal_mode=TRUNCATE')\n"
            "db.execute('BEGIN IMMEDIATE')\n"
            "db.execute(\"UPDATE mailbox SET status='completed' WHERE request_id=?\","
            "(sys.argv[2],))\n"
            "os._exit(17)\n")
        exited = subprocess.run([sys.executable, "-c", child_code,
                                 str(self.path), REQUEST],
                                capture_output=True, timeout=15)
        self.assertEqual(exited.returncode, 17, exited.stderr)
        recovered = IntegrationMailbox(self.path, authorizer=self.authorize)
        self.assertEqual(len(recovered.poll(
            workspace_id=WORKSPACE, installation_id=INSTALL,
            company_id=COMPANY, peer_key_id=KEY, now=1002)), 1)
        self.assertEqual(self.reconcile()["status"], "pending")

    def test_corrupted_disk_record_fails_closed_on_poll_and_reconcile(self):
        self.enqueue()
        with closing(sqlite3.connect(self.path)) as raw:
            raw.execute("PRAGMA journal_mode=TRUNCATE")
            with raw:
                raw.execute("UPDATE mailbox SET scope_hash=? WHERE request_id=?",
                            ("0" * 64, REQUEST))
        with self.assertRaisesRegex(RuntimeError, "integrity"):
            self.poll()
        with self.assertRaisesRegex(RuntimeError, "integrity"):
            self.reconcile()

    def test_corrupted_completed_reply_fails_closed(self):
        self.enqueue()
        envelope = self.poll()[0]
        self.reply(envelope)
        with closing(sqlite3.connect(self.path)) as raw:
            raw.execute("PRAGMA journal_mode=TRUNCATE")
            with raw:
                raw.execute("UPDATE mailbox SET result=? WHERE request_id=?",
                            (json.dumps({"party": {"accountBalance": 9000}}), REQUEST))
        with self.assertRaisesRegex(RuntimeError, "integrity"):
            self.reconcile()

    def test_rejects_unsafe_sqlite_files_and_dacl_failure_before_read(self):
        self.enqueue()
        journal = Path(str(self.path) + "-journal")
        self.assertTrue(journal.is_file())
        for path in (self.path, journal):
            with _private_windows_guard(path):
                pass
            text = subprocess.run(["icacls.exe", str(path)],
                                  text=True, capture_output=True,
                                  check=True, timeout=15).stdout
            self.assertNotIn("(I)", text)
        with patch("integration_mailbox_v1._private_windows_guard",
                   side_effect=PermissionError("synthetic denied")), \
                patch("integration_mailbox_v1.sqlite3.connect") as connect:
            with self.assertRaises(PermissionError):
                self.reconcile()
            connect.assert_not_called()
        linked = self.root / "hardlink.sqlite3"
        try:
            os.link(self.path, linked)
        except OSError:
            self.skipTest("Hardlinks unavailable on this disposable volume")
        with self.assertRaises(PermissionError):
            self.reconcile()

    def test_symlink_and_wal_sidecar_rejected(self):
        target = self.root / "untouched.sqlite3"
        target.write_bytes(b"synthetic-untouched")
        path = self.root / "linked.sqlite3"
        try:
            path.symlink_to(target)
        except OSError:
            self.skipTest("Symlinks unavailable")
        with self.assertRaises(PermissionError):
            IntegrationMailbox(path, authorizer=self.authorize)
        self.assertEqual(target.read_bytes(), b"synthetic-untouched")
        self.enqueue()
        Path(str(self.path) + "-wal").write_bytes(b"synthetic")
        with self.assertRaises(PermissionError):
            self.reconcile()

    def test_unavailable_db_read_does_not_create_private_files(self):
        with self.assertRaises(PermissionError):
            self.reconcile()
        self.assertFalse(self.path.exists())
        self.assertFalse(Path(str(self.path) + "-journal").exists())


if __name__ == "__main__":
    unittest.main()
