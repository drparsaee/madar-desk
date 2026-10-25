"""Assemble a verified, version-specific Windows RC bundle without user data.

Requires final isolated QA and a separately captured EXE GUI smoke report.
Never reads APPDATA or changes old release binaries. Generates new RC archives
only, refusing an existing destination instead of silently overwriting it.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parent.parent
RELEASE = ROOT / "release"
NAME = "Madar-Desk-v1.0-rc1-backupscope-verified-distribution.zip"
MANIFEST = "Madar-Desk-v1.0-rc1-backupscope-verified-manifest.json"
REQUIRED = (
    "Madar-Desk-v1.0-rc1.exe",
    "Madar-Desk-MCP-v1.exe",
    "Install-MadarDesk.ps1",
    "Install-Madar-Desk-v1.0-rc1.ps1",
    "Madar-Desk-v1.0-rc1-source.zip",
)


def _sha(path: Path) -> str:
    value = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def _qa(path: Path) -> dict:
    raw = path.read_bytes()
    # Windows PowerShell 5.1 uses UTF-16LE for *> transcript redirection.
    # Never interpret that as UTF-8, which would erase all QA markers.
    encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    data = raw.decode(encoding, errors="replace")
    if "PASS: automated release QA." not in data or "PASS: Full Python + JavaScript suite" not in data:
        raise RuntimeError("Full isolated release QA has not passed")
    python = re.findall(r"Ran (\d+) tests in [\d.]+s\s*\nOK", data)
    js_total = re.findall(r"[ℹi]\s*tests\s+(\d+)", data)
    js_pass = re.findall(r"[ℹi]\s*pass\s+(\d+)", data)
    js_fail = re.findall(r"[ℹi]\s*fail\s+(\d+)", data)
    if not python or not js_total or not js_pass or not js_fail:
        raise RuntimeError("Cannot recover exact successful test counts")
    if int(js_total[-1]) != int(js_pass[-1]) or int(js_fail[-1]) != 0:
        raise RuntimeError("JavaScript suite is not fully passing")
    return {"pythonPassed": int(python[-1]), "javascriptPassed": int(js_pass[-1]),
            "javascriptFailed": 0, "sourceLog": path.name}


def _gui(report: Path, screenshot: Path) -> dict:
    # Use the actual tested harness to evaluate all UI and PNG integrity gates.
    report = report.resolve()
    screenshot = screenshot.resolve()
    if not report.is_relative_to(ROOT) or not screenshot.is_relative_to(ROOT):
        raise RuntimeError("GUI evidence must be inside the approved project workspace")
    sys.path.insert(0, str(ROOT / "scripts"))
    from v1_gui_smoke import validate_report
    values = json.loads(report.read_text(encoding="utf-8"))
    checks = validate_report(values, screenshot=True, screenshot_path=screenshot)
    if not checks or any(item["status"] != "PASS" for item in checks.values()):
        raise RuntimeError("GUI evidence contains unverified or failed checks")
    return {"checksPassed": len(checks), "checksFailed": 0,
            "stageCount": values["stageCount"], "cardCount": values["cardCount"],
            "sourceReport": str(report.relative_to(ROOT)),
            "nativeScreenshotCallback": values.get("screenshot", {}).get("done"),
            "note": "PNG validated independently; native callback flag retained"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Assemble Madar Desk v1 RC1 distribution")
    parser.add_argument("--qa-log", type=Path, required=True)
    parser.add_argument("--gui-report", type=Path, required=True)
    parser.add_argument("--gui-screenshot", type=Path, required=True)
    args = parser.parse_args()
    qa_log = args.qa_log.resolve()
    gui_report = args.gui_report.resolve()
    gui_screenshot = args.gui_screenshot.resolve()
    if not all(path.is_relative_to(ROOT) and path.is_file()
               for path in (qa_log, gui_report, gui_screenshot)):
        raise RuntimeError("Evidence must be existing files under this project")
    output = RELEASE / NAME
    manifest = RELEASE / MANIFEST
    if output.exists() or manifest.exists():
        raise RuntimeError("RC distribution already exists; refusing to overwrite")
    sources = [RELEASE / name for name in REQUIRED]
    extras = [ROOT / "RELEASE_V1_RC1_VERIFICATION.md",
              ROOT / "PORTABLE_INSTALL_V1.md", ROOT / "MCP_STDIO_V1.md"]
    if not all(path.is_file() for path in (*sources, *extras)):
        raise FileNotFoundError("Required verified RC artifact or release report is missing")
    qa = _qa(qa_log)
    gui = _gui(gui_report, gui_screenshot)
    files = [{"name": item.name, "bytes": item.stat().st_size, "sha256": _sha(item)}
             for item in sources]
    evidence = [
        (qa_log, "evidence/isolated-qa.log"),
        (gui_report, "evidence/gui-diagnostics.json"),
        (gui_screenshot, "evidence/gui-screenshot.png"),
    ]
    values = {"release": "Madar Desk 1.0 RC1", "status": "release-candidate-not-stable",
              "generatedUtc": datetime.now(timezone.utc).isoformat(),
              "qa": qa, "gui": gui, "files": files,
              "evidence": [{"name": name, "bytes": source.stat().st_size,
                            "sha256": _sha(source)} for source, name in evidence],
              "unverified": ["physical two-computer acceptance", "Google/Outlook OAuth synchronization",
                             "full interactive workflow acceptance", "production install/update"]}
    raw = (json.dumps(values, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=7) as archive:
        for file in sources:
            archive.write(file, arcname=file.name)
        for item in extras:
            archive.write(item, arcname=item.name)
        for source, name in evidence:
            archive.write(source, arcname=name)
        archive.writestr(MANIFEST, raw)
    manifest.write_bytes(raw)
    print(json.dumps({"path": str(output), "bytes": output.stat().st_size,
                      "sha256": _sha(output), "manifest": str(manifest),
                      "qa": qa, "gui": gui}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
