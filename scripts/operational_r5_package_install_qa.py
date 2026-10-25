"""Test R5 installer into disposable Windows paths, never user install/data."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "release" / "Madar-Suite-Accounting-R5-20261025"
FILES = {"madarSha256": "Madar-Desk-R5.exe",
         "accountingSha256": "Madar-Accounting-R5.exe"}


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest().upper()


def main():
    manifest = json.loads((PACKAGE / "manifest.json").read_text(encoding="utf-8"))
    if manifest["version"] != "R5-20261025":
        raise RuntimeError("Unexpected package version")
    with TemporaryDirectory(prefix="madar-r5-package-qa-") as temp:
        test_root = Path(temp)
        install = test_root / "isolated-new-install"
        data = test_root / "isolated-data"
        shortcuts = test_root / "isolated-shortcuts"
        local = test_root / "isolated-localapp"
        local.mkdir()
        env = {**os.environ, "APPDATA": str(test_root / "roaming"),
               "LOCALAPPDATA": str(local), "MADAR_INSTALL_QA": "1"}
        args = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(PACKAGE / "Setup.ps1"),
                "-InstallRoot", str(install), "-DataRoot", str(data),
                "-Silent", "-SkipRuntimeForTest", "-TestShortcutRoot", str(shortcuts)]

        def invoke(parameters=args):
            return subprocess.run(parameters, env=env, cwd=ROOT,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  timeout=120)

        first = invoke()
        if first.returncode:
            raise RuntimeError("Installer failed: " + first.stderr.decode(errors="replace")[-1000:])
        initial_hashes = {name: sha(install / name) for name in FILES.values()}
        checks = {
            "hashes_match": all(initial_hashes[filename] == manifest["apps"][key]
                                for key, filename in FILES.items()),
            "private_empty_accounting": (data / "Accounting").is_dir() and
                                        not list((data / "Accounting").iterdir()),
            "no_task_database": not any(data.rglob("tasks.json")),
            "three_shortcuts_per_location": (
                len(list((shortcuts / "Desktop").glob("*.lnk"))) == 3 and
                len(list((shortcuts / "StartMenu" / "Programs" /
                          "Madar Suite R5").glob("*.lnk"))) == 3),
            # Some Windows automation layers normalize Persian Yeh to Arabic Yeh.
            "recovery_shortcut_exists": any("بازیابی" in p.name.replace("ي", "ی") for p in
                                            (shortcuts / "Desktop").glob("*.lnk")),
        }
        second = invoke()
        checks["same_install_idempotent"] = (
            second.returncode == 0 and all(sha(install / f) == h
                                           for f, h in initial_hashes.items()))
        # Corrupt *copied* package manifest only; originals remain immutable.
        modified = test_root / "tampered-manifest-package"
        shutil.copytree(PACKAGE, modified, dirs_exist_ok=False)
        corrupt = {**manifest, "apps": {**manifest["apps"],
                                        "madarSha256": "0" * 64}}
        (modified / "manifest.json").write_text(json.dumps(corrupt), encoding="utf-8")
        refusal_args = list(args)
        refusal_args[refusal_args.index(str(PACKAGE / "Setup.ps1"))] = str(modified / "Setup.ps1")
        refused = invoke(refusal_args)
        checks["tampered_manifest_refused_no_overwrite"] = (
            refused.returncode != 0 and all(sha(install / f) == h
                                              for f, h in initial_hashes.items()) and
            not list((data / "Accounting").iterdir()))
        print(json.dumps({"checks": checks, "passed": sum(checks.values()),
                          "total": len(checks),
                          "shortcut_names": [p.name for p in (shortcuts / "Desktop").glob("*.lnk")]},
                         indent=2, ensure_ascii=True))
        return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
