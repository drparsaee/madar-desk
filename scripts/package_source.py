"""Bundle source, tests and prebuilt UI without cache or credentials."""
from pathlib import Path
import zipfile
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--output", default="Madar-Desk-v0.5-integration-preview-source.zip",
                    help="Output ZIP filename inside release/")
args = parser.parse_args()
if Path(args.output).name != args.output or not args.output.lower().endswith(".zip"):
    parser.error("Only a ZIP basename inside release/ is allowed")
root = Path(__file__).resolve().parents[1]
output = root / "release" / args.output
output.parent.mkdir(parents=True, exist_ok=True)

files = [
    "README.md", "DESIGN.md", "package.json", "package-lock.json",
    "index.html", "vite.config.js", "native_app.py", "lan.py", "data_model.py", "collab.py", "offline_exchange.py", "cloud_continuity.py", "finance.py", "persistent_store.py", "app_storage.py", "attachments.py", "automation_due.py", "automation_events.py", "COLLAB_API.md", "FINANCE_DOMAIN.md", "PERSISTENT_STORE_API.md", "APP_STORAGE_API.md", "ATTACHMENTS_API.md", "BATCH_03_05_STATUS.md", "INTEGRATION_03_05_REPORT.md", ".gitignore", "NETWORK.md", "README-FA.md", "ROADMAP.md", "PRODUCT_REQUIREMENTS_2026-10-20.md",
    "RC1_RELEASE_STATUS.md", "RC1_EXECUTABLE_QA_20261020.md", "RELEASE_QA_CHECKLIST.md",
    "FINANCE_PREVIEW_QA_20261020.md", "CUSTOM_PREVIEW_QA_20261020.md",
]
for name in (
    "full_recovery.py", "maintenance_recovery.py", "integration_api_v1.py",
    "automation_v1.py", "calendar_interop.py", "src/checklistguard.js",
    "src/planner_identity.js", "FULL_RECOVERY_API.md", "MAINTENANCE_RECOVERY.md",
    "INTEGRATION_API_V1.md", "AUTOMATION_V1_API.md",
    "AUTOMATION_STORAGE_API.md", "CALENDAR_INTEROP_API.md",
    "CARD_COMPLETION_API.md", "PLANNER_API.md",
    "ROADMAP_EXECUTION_2026-10-21.md", "LAN_V1_ACCEPTANCE.md",
    "V1_RC1_VERIFICATION_20261021.md", "SECURITY_API_MOUNT_REVIEW.md",
    "AUTOMATION_RECOVERY_VERIFICATION.md", "GUI_SMOKE_V1.md",
    "MCP_STDIO_V1.md", "mcp_stdio_v1.py",
    "WEBHOOK_OUTBOX_V1.md", "webhook_outbox_v1.py",
    "PORTABLE_INSTALL_V1.md",
    "SECURITY_API_MOUNT_REVIEW.md", "AUTOMATION_RECOVERY_VERIFICATION.md",
    "GUI_SMOKE_V1.md", "mcp_stdio_v1.py", "MCP_STDIO_V1.md",
    "webhook_v1.py", "WEBHOOK_V1_API.md", "webhook_outbox_v1.py",
    "WEBHOOK_OUTBOX_V1.md", "src/calendar_import_state.js",
    "release/Install-Madar-Desk-v1.0-rc1.ps1",
    "release/Install-MadarDesk.ps1", "PORTABLE_INSTALL_V1.md",
    "RELEASE_V1_RC1_VERIFICATION.md",
    "BACKUP_SCOPE_V1.md",
):
    if (root / name).is_file():
        files.append(name)
for subdirectory in ("src", "dist", "assets", "tests", "scripts", "public"):
    files.extend(
        str(p.relative_to(root)).replace("\\", "/")
        for p in (root / subdirectory).rglob("*")
        if p.is_file() and p.suffix not in (".pyc", ".ttf", ".woff", ".woff2", ".otf")
        and "__pycache__" not in p.parts
    )
with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for name in sorted(set(files)):
        archive.write(root / name, arcname=name)
print(f"{output} ({output.stat().st_size:,} bytes)")
