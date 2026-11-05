"""Check the moving head release without rewriting historical installer fixtures.

Historical 1.0.9–1.0.13 builders must remain immutable. Their regression
tests may verify the live head, but may not freeze it at a 2026-10 snapshot.
"""
import json
from pathlib import Path
import re

import madar_update


def assert_current_release_aligned(case, root: Path, *, minimum="1.0.13"):
    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((root / "package-lock.json").read_text(encoding="utf-8"))
    version = madar_update.CURRENT_VERSION
    case.assertRegex(version, r"^\d+\.\d+\.\d+$")
    case.assertGreaterEqual(madar_update.version_tuple(version),
                            madar_update.version_tuple(minimum))
    case.assertEqual((package["version"], lock["version"],
                      lock["packages"][""]["version"]), (version,) * 3)
    major, minor, patch_version = madar_update.version_tuple(version)
    case.assertEqual(minor, 0, "The current builder naming convention covers 1.0.x releases")
    build_name = f"build_integrated_v{major}{patch_version}.py"
    case.assertTrue((root / "scripts" / build_name).is_file(),
                    "Current release must have its own version-specific wrapper")
    case.assertIn(build_name, package["scripts"]["dist:rc"])
    case.assertEqual(package["scripts"]["dist"], "npm run dist:rc")
    case.assertTrue(re.fullmatch(r"Madar-Desk-\d+\.\d+\.\d+-Setup\.exe",
                    f"Madar-Desk-{version}-Setup.exe"))
