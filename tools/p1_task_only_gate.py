"""P1 task-only Python regression gate; deliberately not a release-wide pass.

Run each explicitly selected task-management module with an independent synthetic
profile. Legacy accounting suites remain in the full audit, never deleted or
silently counted as passing here. No installed Madar, Taraz or user data is read.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

from modernization_python_suite import PROJECT, execute_module
from safe_test_runner import isolated_environment


TASK_ONLY_MODULES = (
    "test_collab.py",
    "test_collab_bridge.py",
    "test_card_dependency_validation.py",
    "test_project_integrity.py",
    "test_p1_project_grants.py",
    "test_p1_active_surfaces.py",
    "test_lan_user_persistence.py",
    "test_safe_test_runner.py",
)

# Additional independently passing task/LAN/backup/sync modules. This is an
# explicit expansion, not automatic skipping of newly failing/unknown modules.
# The old finance-only and task+finance mixed suites remain in the full audit.
EXTENDED_TASK_MODULES = (
    "test_app_storage.py",
    "test_attachment_bridge.py",
    "test_attachments.py",
    "test_automation_due.py",
    "test_automation_events.py",
    "test_automation_full_recovery.py",
    "test_automation_lifecycle_bridge.py",
    "test_automation_storage.py",
    "test_automation_v1.py",
    "test_backup_scope_truth.py",
    "test_bridge_offline.py",
    "test_calendar_interop.py",
    "test_card_completion.py",
    "test_card_order_contract.py",
    "test_cloud_bridge.py",
    "test_cloud_continuity.py",
    "test_data_model.py",
    "test_full_recovery.py",
    "test_host_backup_scheduler.py",
    "test_lan_account_lockout.py",
    "test_lan_auto_reconnect.py",
    "test_lan_delete_partial_registry_save.py",
    "test_lan_delete_partial_state_save.py",
    "test_lan_delete_registry_failure.py",
    "test_lan_delete_state_atomicity.py",
    "test_lan_discovery.py",
    "test_lan_display_role_postpublish_failure.py",
    "test_lan_identity_postpublish_failure.py",
    "test_lan_login_resource_limits.py",
    "test_lan_owner_setup_publication.py",
    "test_lan_partial_account_update_scope.py",
    "test_lan_profile_zero_grant_directory.py",
    "test_lan_read_projection_alias.py",
    "test_lan_security_framing_phase4.py",
    "test_lan_tls.py",
    "test_lan_unknown_account_kdf.py",
    "test_lan_user_creation_flow.py",
    "test_local_state_cas.py",
    "test_m02_reconnect_25_edits.py",
    "test_m07_guard_unit.py",
    "test_m07_host_preflight.py",
    "test_madar_brand_icons.py",
    "test_madar_host_service.py",
    "test_madar_native_close_ux_phase2.py",
    "test_madar_offline_reconciliation_export.py",
    "test_madar_update.py",
    "test_madar_update_contract.py",
    "test_maintenance_recovery.py",
    "test_native.py",
    "test_native_tls.py",
    "test_offline_exchange.py",
    "test_persistent_store.py",
    "test_planner_bridge_integration.py",
    "test_planner_five_node_lan.py",
    "test_planner_persistence.py",
    "test_priority_settings.py",
    "test_profile_cache_acl.py",
    "test_release_automation_host.py",
    "test_release_name_guard.py",
    "test_release_restore_guard.py",
    "test_restore_crash_publication.py",
    "test_role_profiles.py",
    "test_rule_safety.py",
    "test_rule_scheduler_bridge.py",
    "test_simple_backup.py",
    "test_taraz_exchange.py",
    "test_taraz_link_status.py",
    "test_workspace_contract.py",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, help="Optional JSON result path")
    parser.add_argument("--extended", action="store_true",
                        help="Expand to explicitly selected task/LAN/backup/sync regressions")
    args = parser.parse_args()

    selected = TASK_ONLY_MODULES + (EXTENDED_TASK_MODULES if args.extended else ())
    if len(set(selected)) != len(selected):
        raise ValueError("Duplicate selected test module")
    paths = [PROJECT / "tests" / name for name in selected]
    missing = [p.name for p in paths if not p.is_file()]
    if missing:
        print("P1_TASK_ONLY_BLOCKED missing=" + ",".join(missing), flush=True)
        return 2

    with tempfile.TemporaryDirectory(prefix="madar-p1-task-only-") as folder:
        scratch = Path(folder)
        clean_env = isolated_environment(scratch / "parent")
        results = []
        # execute_module spawns isolated children; scrub inherited private
        # environment overrides before it takes its os.environ snapshot.
        with patch.dict(os.environ, clean_env, clear=True):
            for path in paths:
                result = execute_module(path, scratch / "modules", 120, False)
                results.append(result)
                print(f"{result['status'].upper()} {path.name} "
                      f"tests={result['tests']} timeout={result['status']=='timeout'}",
                      flush=True)
                if result["status"] != "pass":
                    # Windows legacy consoles may not encode Persian Unicode.
                    diagnostic = result["diagnostic"].encode(
                        "ascii", errors="backslashreplace").decode("ascii")
                    print(diagnostic[-4000:], flush=True)

    summary = {"executed": len(results),
               "passed": sum(item["status"] == "pass" for item in results),
               "failed": sum(item["status"] == "fail" for item in results),
               "timedOut": sum(item["status"] == "timeout" for item in results),
               "testsReported": sum(item["tests"] or 0 for item in results)}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open("x", encoding="utf-8") as handle:
            json.dump({
                "scope": "P1 explicitly allowlisted task-only, not full source QA",
                "extended": args.extended, "summary": summary, "modules": results
            }, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    print("P1_TASK_ONLY " + json.dumps(summary), flush=True)
    return 0 if summary["passed"] == len(paths) else 1


if __name__ == "__main__":
    raise SystemExit(main())
