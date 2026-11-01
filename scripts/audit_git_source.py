"""Non-invasive baseline scan for accidentally committed binary data/secrets.

The output contains paths and issue categories, never matched secret values.
This does not replace a full security penetration test or historical scan.
"""
from __future__ import annotations
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN = {".exe", ".db", ".sqlite", ".sqlite3", ".bak", ".pfx",
             ".p12", ".key", ".pem", ".zip", ".mdf", ".ldf"}
SOURCE_TYPES = {".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".ps1", ".cmd"}
SIGNATURES = [
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("hardcoded-credential", re.compile(
        r"""(?i)\b(?:api[_-]?key|client[_-]?secret|refresh[_-]?token|access[_-]?token)\b\s*[:=]\s*['"][^'"]{16,}['"]"""
    )),
]

def main():
    result = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT,
                            check=True, capture_output=True)
    files = [name.decode("utf-8") for name in result.stdout.split(b"\x00") if name]
    findings = []
    scanned = 0
    for name in files:
        path = ROOT / name
        if path.suffix.lower() in FORBIDDEN or path.name.lower().startswith(".env"):
            findings.append(("sensitive-asset-tracked", name, 0))
        if (path.suffix.lower() not in SOURCE_TYPES or
            name.startswith(("tests/", "docs/", "research/")) or
            not path.is_file() or path.stat().st_size > 1_000_000):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeError:
            continue
        scanned += 1
        for label, expression in SIGNATURES:
            for match in expression.finditer(content):
                findings.append((label, name, content.count("\n", 0, match.start()) + 1))
    print("GIT_TRACKED_FILES", len(files))
    print("SCAN_SOURCE_FILES", scanned)
    print("SUSPICIOUS_ITEMS", len(findings))
    for category, name, line in findings[:20]:
        print("FINDING", category, name, "line", line)
    if findings:
        raise SystemExit(2)

if __name__ == "__main__":
    main()
