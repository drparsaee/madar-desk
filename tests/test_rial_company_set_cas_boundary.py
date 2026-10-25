"""Guard opt-in RIAL company membership inside disposable unified SQLite CAS.

Purely synthetic states, no Bridge initialization, APPDATA or user documents.
"""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from app_storage import UnifiedAppStorage
from collab import empty_state as empty_collab
from finance import empty_finance_state
from ir_finance_v2_extension import HostCompanyProof, _entry, activate_rial_finance
from ir_journal_v2 import FiscalPeriod, new_journal_state
from money_policy import snapshot_sha256
from native_app import initial_state


def empty_rial(company_id):
    return new_journal_state(company_id, (
        FiscalPeriod(company_id, "FY2026", "2026-01-01", "2026-12-31"),
    ))


class CompanySetCASBoundaryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="madar-company-set-synthetic-")
        self.addCleanup(temp.cleanup)
        self.store = UnifiedAppStorage(Path(temp.name) / "synthetic.sqlite3")
        first = self.store.commit({
            "tasks": initial_state(), "collab": empty_collab(),
            "finance": empty_finance_state(), "completion_outbox": [],
        }, expected_revision=0)
        finance = first.bundle["finance"]
        activated = activate_rial_finance(
            finance, empty_rial("company-a"),
            proof=HostCompanyProof("company-a", "local", snapshot_sha256(finance)),
        )
        self.store.commit({**first.bundle, "finance": activated},
                          expected_revision=first.revision)

    def test_direct_second_company_empty_journal_without_registry_mapping_denied(self):
        before = self.store.load()
        candidate = deepcopy(before.bundle)
        candidate["finance"]["rialJournalV2"]["companies"]["company-b"] = _entry(
            empty_rial("company-b"))
        with self.assertRaisesRegex(ValueError, "company|mapping|migration"):
            self.store.commit(candidate, expected_revision=before.revision)
        self.assertEqual(self.store.load().bundle, before.bundle)
        self.assertEqual(self.store.load().revision, before.revision)

    def test_existing_company_journal_cannot_be_deleted(self):
        before = self.store.load()
        candidate = deepcopy(before.bundle)
        candidate["finance"]["rialJournalV2"]["companies"].pop("company-a")
        with self.assertRaises(ValueError):
            self.store.commit(candidate, expected_revision=before.revision)
        self.assertEqual(self.store.load().revision, before.revision)

    def test_ordinary_nonfinancial_bundle_commit_keeps_exact_company_set(self):
        before = self.store.load()
        candidate = deepcopy(before.bundle)
        candidate["tasks"]["settings"]["theme"] = "dark"
        result = self.store.commit(candidate, expected_revision=before.revision)
        self.assertEqual(result.revision, before.revision + 1)
        self.assertEqual(set(result.bundle["finance"]["rialJournalV2"]["companies"]),
                         {"company-a"})


if __name__ == "__main__":
    unittest.main()
