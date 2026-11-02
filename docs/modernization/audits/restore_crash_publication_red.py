"""Isolated RED characterization: a process crash during composite restore.

All paths are temporary, all identity records and SQLite data are synthetic.
This test intentionally demonstrates a current vulnerability; do not include in
the default green regression gate until the restore publication is corrected.
"""

from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

from standalone_accounting import StandaloneAccountingStore
from standalone_accounting_auto_backup import AutomaticStandaloneBackups
from standalone_accounting_identity import LocalCompanyIdentity
from standalone_accounting_restore import restore_standalone_accounting


class CrashPublicationAudit(unittest.TestCase):
    def test_crash_before_identity_publishes_no_accessible_ledger(self):
        with tempfile.TemporaryDirectory(prefix="madar-restore-crash-audit-") as folder:
            root = Path(folder)
            original = root / "source"
            restored = root / "restored"
            original.mkdir()
            restored.mkdir()
            StandaloneAccountingStore(original / "standalone-accounting.sqlite3")
            LocalCompanyIdentity(original).add_user(
                "syntheticadmin", "SyntheticCrashPassword2026", "admin")
            backup = AutomaticStandaloneBackups(
                original, plaintext_acknowledged=True).backup_now()
            self.assertTrue(backup.with_suffix(".users.json").is_file())
            destination = restored / "standalone-accounting.sqlite3"
            child = r'''
import os
from pathlib import Path
import sys
import standalone_accounting_restore as restore

backup = Path(sys.argv[1])
destination = Path(sys.argv[2])
original_link = restore.os.link
def terminate_after_sqlite(source, target, *args, **kwargs):
    result = original_link(source, target, *args, **kwargs)
    if Path(target) == destination:
        os._exit(71)
    return result
restore.os.link = terminate_after_sqlite
restore.restore_standalone_accounting(
    backup, destination, plaintext_acknowledged=True,
    offline_acknowledged=True)
'''
            env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
            completed = subprocess.run(
                [sys.executable, "-B", "-c", child, str(backup), str(destination)],
                cwd=str(Path(__file__).resolve().parents[3]), env=env,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
                check=False)
            self.assertEqual(completed.returncode, 71, completed.stderr.decode(errors="replace"))
            self.assertFalse((restored / "local-users.json").exists())
            # The acceptance requirement fails on the uncorrected implementation:
            # a bare database is published before its identity registry.
            self.assertFalse(destination.exists(),
                             "A restored ledger is visible without its identity registry")
            # A second normal restore should remain possible after a crash.
            restore_standalone_accounting(
                backup, destination, plaintext_acknowledged=True,
                offline_acknowledged=True)


if __name__ == "__main__":
    unittest.main()
