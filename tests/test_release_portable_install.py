"""Per-user RC installer dry-run and in-sandbox versioned copy tests."""
import hashlib
import json
from pathlib import Path
import os
import subprocess
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT / 'release' / 'Install-Madar-Desk-v1.0-rc1.ps1'
EXE = PROJECT / 'release' / 'Madar-Desk-v1.0-rc1.exe'


@unittest.skipUnless(os.name == 'nt', 'Windows installer only')
class PortableInstallerTests(unittest.TestCase):
    def test_dry_run_and_versioned_install_are_non_destructive(self):
        if not EXE.is_file():
            self.skipTest('RC binary not available')
        with tempfile.TemporaryDirectory(prefix='madar-installer-') as name:
            root = Path(name)
            install = root / 'Programs' / 'MadarDesk'
            appdata = root / 'Roaming'
            appdata.mkdir()
            marker = appdata / 'MadarDesk' / 'user.json'
            marker.parent.mkdir()
            marker.write_text('DO NOT MODIFY', encoding='utf8')
            expected = hashlib.sha256(EXE.read_bytes()).hexdigest()
            env = dict(os.environ, APPDATA=str(appdata),
                       LOCALAPPDATA=str(root / 'Local'))

            def run(*flags, expected_sha=expected):
                cmd = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                       '-File', str(SCRIPT), '-Source', str(EXE),
                       '-InstallRoot', str(install), '-ExpectedSha256', expected_sha,
                       *flags]
                return subprocess.run(cmd, env=env, cwd=PROJECT, capture_output=True,
                                      text=True, timeout=45, check=False)

            dry = run('-DryRun')
            self.assertEqual(dry.returncode, 0, dry.stderr)
            self.assertEqual(json.loads(dry.stdout)['status'], 'dry_run')
            self.assertFalse(install.exists())
            self.assertEqual(marker.read_text(encoding='utf8'), 'DO NOT MODIFY')

            active = run()
            self.assertEqual(active.returncode, 0, active.stderr)
            self.assertEqual(json.loads(active.stdout)['status'], 'installed')
            deployed = install / EXE.name
            self.assertEqual(hashlib.sha256(deployed.read_bytes()).hexdigest(), expected)

            again = run()
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertEqual(json.loads(again.stdout)['status'], 'already_installed')
            self.assertEqual(marker.read_text(encoding='utf8'), 'DO NOT MODIFY')

            bad = run(expected_sha='0' * 64)
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn('SHA-256', bad.stderr)
            self.assertEqual(hashlib.sha256(deployed.read_bytes()).hexdigest(), expected)


if __name__ == '__main__':
    unittest.main()
