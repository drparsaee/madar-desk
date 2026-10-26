"""Security contracts for standalone finance, using disposable company folders.

These tests exercise the actual reducer, LAN authorization helpers, independent
desktop request boundary, and the separately implemented local identity module.
They do not open an operator's default APPDATA, installed database, or EXE.

The legacy --data-dir single-admin bypass is documented in
standalone_accounting_security_integration.md; the desktop identity wiring must
be tested separately once that integration is implemented.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import accounting_core as core
import standalone_accounting_identity as identity
from lan import standalone_command_request, standalone_finance_access, standalone_finance_accounts
from standalone_accounting_desktop import AccountingDesktopAPI


NOW = "2026-10-26T00:00:00+00:00"
ROSTER = {
    "owner": {"username": "owner", "role": "admin"},
    "worker": {"username": "worker", "role": "editor", "financeEdit": True},
    "reporter": {"username": "reporter", "role": "viewer", "financeView": True},
    "viewer_with_forged_edit": {
        "username": "viewer_with_forged_edit", "role": "viewer", "financeEdit": True,
    },
    "editor_without_grant": {"username": "editor_without_grant", "role": "editor"},
}


def command(identifier, *, actor=None, **extra):
    payload = {"type": "party.register", "eventId": identifier,
               "partyId": "customer", "name": "Disposable customer", "kind": "customer"}
    if actor is not None:
        payload["actor"] = actor  # Malicious actor inside a business command.
    payload.update(extra)
    return payload


class FinanceAuthorityContracts(unittest.TestCase):
    def setUp(self):
        self.state = core.empty_rial_accounting_state()

    def test_reducer_rejects_missing_actor_and_viewer_role_with_forged_edit_flag(self):
        for actor in ("not-registered", "reporter", "viewer_with_forged_edit",
                      "editor_without_grant"):
            with self.subTest(actor=actor), self.assertRaises(PermissionError):
                core.apply_accounting_command(self.state, command("attempt-1"),
                                              actor=actor, accounts=ROSTER, now=NOW)
        self.assertEqual(self.state["events"], [])

    def test_read_only_role_cannot_gain_write_through_finance_edit_boolean(self):
        self.assertEqual(core.accounting_view(self.state, actor="reporter",
                                              accounts=ROSTER)["currency"], "RIAL")
        with self.assertRaises(PermissionError):
            core.accounting_view(self.state, actor="viewer_with_forged_edit",
                                 accounts=ROSTER)
        with self.assertRaises(PermissionError):
            standalone_finance_access("viewer_with_forged_edit", ROSTER,
                                      mutation=True)
        with self.assertRaises(PermissionError):
            standalone_finance_access("not-registered", ROSTER, mutation=False)

    def test_editor_grant_does_not_permit_admin_only_tax_and_closure(self):
        for forbidden in ("company.profile.set", "tax.rule.set", "period.close",
                          "fiscal.year.close", "inventory.opening", "account.create",
                          "funds.deposit", "future.admin.elevate"):
            with self.subTest(forbidden=forbidden), self.assertRaises(PermissionError):
                core.apply_accounting_command(
                    self.state, {"type": forbidden, "eventId": "forbid-1"},
                    actor="worker", accounts=ROSTER, now=NOW)
        self.assertEqual(self.state["events"], [])

    def test_business_command_cannot_select_actor_or_override_role(self):
        for injected in (command("inject-1", actor="owner"),
                         command("inject-1", role="admin"),
                         command("inject-1", financeEdit=True)):
            with self.subTest(injected=injected), self.assertRaises(ValueError):
                core.apply_accounting_command(self.state, injected,
                                              actor="worker", accounts=ROSTER, now=NOW)
        self.assertEqual(self.state["events"], [])

    def test_event_reuse_with_different_principal_does_not_impersonate(self):
        initial = core.apply_accounting_command(self.state, command("evt-1"),
                                                actor="worker", accounts=ROSTER, now=NOW)
        snapshot = deepcopy(initial["state"])
        self.assertEqual(snapshot["events"][0]["actor"], "worker")
        with self.assertRaises(ValueError):
            core.apply_accounting_command(snapshot, command("evt-1"),
                                          actor="owner", accounts=ROSTER, now=NOW)
        self.assertEqual(snapshot, initial["state"])

    def test_lan_account_projection_strips_passwords_and_rejects_mismatch(self):
        roster = deepcopy(ROSTER)
        roster["owner"]["passwordHash"] = "PRIVATE_PASSWORD_HASH"
        trusted = standalone_finance_accounts(roster)
        self.assertNotIn("PRIVATE_PASSWORD_HASH", repr(trusted))
        self.assertEqual(set(trusted["owner"]),
                         {"username", "role", "financeView", "financeEdit"})
        roster["worker"]["username"] = "owner"
        with self.assertRaises(PermissionError):
            standalone_finance_accounts(roster)


class DesktopRequestBoundaryContracts(unittest.TestCase):
    def test_rejects_browser_supplied_roles_and_cross_company_overrides_before_io(self):
        with tempfile.TemporaryDirectory(prefix="madar-security-desktop-") as tmp:
            book = Path(tmp) / "synthetic-book"
            api = AccountingDesktopAPI(book)
            for addition in ({"actor": "local"}, {"role": "admin"},
                             {"companyId": "other"}, {"financeEdit": True},
                             {"session": "forged"}, {"expectedRevision": True}):
                req = {"command": command("evt-1"), "expectedRevision": 0}
                req.update(addition)
                with self.subTest(addition=addition), self.assertRaises(ValueError):
                    api.standaloneAccountingCommand(req)
            with self.assertRaises(ValueError):
                standalone_command_request({"command": command("evt-1"),
                                            "expectedRevision": 0, "actor": "owner"})
            self.assertFalse(book.exists(), "Rejected requests must not create a DB")


class LocalCompanyIdentityContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="madar-security-company-")
        self.addCleanup(self.temp.cleanup)
        self.hub = Path(self.temp.name)
        self.a = self.hub / "company-a"
        self.b = self.hub / "company-b"
        self.a.mkdir()
        self.b.mkdir()
        # Accelerate synthetic tests only; deployed password KDF remains 600000.
        patcher = patch.object(identity, "_ITERATIONS", 500)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.owner = identity.LocalCompanyIdentity(self.a)
        self.other = identity.LocalCompanyIdentity(self.b)

    def test_initial_admin_is_required_and_secret_never_in_account_projection(self):
        with self.assertRaises(identity.IdentityError):
            self.owner.add_user("reader", "temporary-password-123", "viewer")
        with self.assertRaises(identity.IdentityError):
            self.owner.add_user("owner", "short", "admin")
        self.owner.add_user("owner", "temporary-password-123", "admin")
        self.assertTrue(self.owner.initialized())
        content = (self.a / "local-users.json").read_text(encoding="utf-8")
        self.assertNotIn("temporary-password-123", content)
        account = self.owner.accounting_accounts()["owner"]
        self.assertEqual(account["role"], "admin")
        self.assertNotIn("hash", account)
        self.assertNotIn("salt", account)

    def test_company_scoped_token_is_not_accepted_in_other_company(self):
        self.owner.add_user("owner", "temporary-password-123", "admin")
        self.other.add_user("owner", "temporary-password-456", "admin")
        token = self.owner.login("owner", "temporary-password-123")
        self.assertEqual(self.owner.require_session(token, "admin")["username"], "owner")
        with self.assertRaises(identity.IdentityError):
            self.other.require_session(token, "viewer")
        self.owner.logout(token)
        with self.assertRaises(identity.IdentityError):
            self.owner.require_session(token, "viewer")

    def test_viewer_and_editor_cannot_escalate_to_admin(self):
        self.owner.add_user("owner", "temporary-password-123", "admin")
        owner_token = self.owner.login("owner", "temporary-password-123")
        self.owner.add_user("reader", "temporary-password-456", "viewer",
                            administrator=owner_token)
        self.owner.add_user("editor", "temporary-password-789", "editor",
                            administrator=owner_token)
        viewer_token = self.owner.login("reader", "temporary-password-456")
        editor_token = self.owner.login("editor", "temporary-password-789")
        self.assertEqual(self.owner.require_session(viewer_token, "viewer")["role"],
                         "viewer")
        self.assertEqual(self.owner.require_session(editor_token, "editor")["role"],
                         "editor")
        for token in (viewer_token, editor_token):
            with self.subTest(token_role=self.owner.require_session(token)["role"]):
                with self.assertRaises(identity.IdentityError):
                    self.owner.require_session(token, "admin")
                with self.assertRaises(identity.IdentityError):
                    self.owner.add_user("rogue", "temporary-password-000", "admin",
                                        administrator=token)
        roster = self.owner.accounting_accounts()
        self.assertFalse(roster["reader"]["financeEdit"])
        self.assertTrue(roster["editor"]["financeEdit"])
        self.assertTrue(roster["reader"]["financeView"])

    def test_invalid_or_expired_token_never_creates_accounting_authority(self):
        self.owner.add_user("owner", "temporary-password-123", "admin")
        with self.assertRaises(identity.IdentityError):
            self.owner.require_session("guessed-or-forged-token", "viewer")
        token = self.owner.login("owner", "temporary-password-123")
        # Session clock is not user-controlled; emulate passage of time only in
        # the disposable in-memory fixture, without sleeping.
        username, expiry = self.owner._sessions[token]
        self.owner._sessions[token] = (username, 0.0)
        with self.assertRaises(identity.IdentityError):
            self.owner.require_session(token, "viewer")


class CurrentDesktopIdentityIntegrationContracts(unittest.TestCase):
    """Distinguish current native login wiring from outstanding per-call gates."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="madar-company-api-contract-")
        self.addCleanup(self.temp.cleanup)
        self.company = Path(self.temp.name) / "company"
        self.company.mkdir()
        patcher = patch.object(identity, "_ITERATIONS", 500)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.store = identity.LocalCompanyIdentity(self.company)
        self.store.add_user("owner", "temporary-password-123", "admin")
        owner_token = self.store.login("owner", "temporary-password-123")
        self.store.add_user("reader", "temporary-password-456", "viewer",
                            administrator=owner_token)

    def test_native_authenticated_viewer_has_read_only_capabilities(self):
        token = self.store.login("reader", "temporary-password-456")
        principal = self.store.require_session(token)
        api = AccountingDesktopAPI(self.company, company_name="Synthetic",
                                   identity_store=self.store,
                                   authenticated_user=principal, identity_token=token)
        snapshot = api.standaloneAccountingRead()
        self.assertEqual(snapshot["capabilities"], {
            "canView": True, "canManage": False, "canDraft": False,
            "canAdmin": False,
        })
        with self.assertRaises(PermissionError):
            api.standaloneAccountingCommand({"command": command("evt-1"),
                                             "expectedRevision": 0})
        with self.assertRaises(PermissionError):
            api.standaloneAccountingTemplateSave("invoice", "Fake", {})
        with self.assertRaises(PermissionError):
            api.standaloneAccountingTemplateDelete("invoice", "fake")

    def test_authenticated_constructor_rejects_missing_principal(self):
        with self.assertRaises(PermissionError):
            AccountingDesktopAPI(self.company, identity_store=self.store)

    def test_logout_revocation_invalidates_desktop_api_before_store_io(self):
        token = self.store.login("reader", "temporary-password-456")
        api = AccountingDesktopAPI(self.company, identity_store=self.store,
                                   authenticated_user=self.store.require_session(token),
                                   identity_token=token)
        self.store.logout(token)
        with patch.object(api, "_store") as fake_store:
            with self.assertRaises(identity.IdentityError):
                api.standaloneAccountingRead()
            with self.assertRaises(identity.IdentityError):
                api.standaloneAccountingCommand({"command": command("evt-1"),
                                                 "expectedRevision": 0})
            fake_store.assert_not_called()
        with self.assertRaises(identity.IdentityError):
            api.standaloneAccountingTemplateList("invoice")
        with self.assertRaises(identity.IdentityError):
            api.standaloneAccountingTemplateSave("invoice", "Fake", {})

    def test_authenticated_constructor_denies_forged_principal_even_with_valid_token(self):
        token = self.store.login("reader", "temporary-password-456")
        for spoofed in ({"username": "owner", "role": "admin"},
                        {"username": "reader", "role": "admin"}):
            with self.subTest(spoofed=spoofed), self.assertRaises(PermissionError):
                AccountingDesktopAPI(self.company, identity_store=self.store,
                                     identity_token=token, authenticated_user=spoofed)

    @unittest.expectedFailure
    def test_pending_legacy_data_dir_must_reject_unauthenticated_existing_book(self):
        """Open issue: standalone legacy mode still grants local/admin."""
        legacy = self.company / "legacy-subfolder"
        legacy.mkdir()
        # Seed an actual synthetic ledger before the second unauthenticated
        # open; this is not merely a fresh-directory bootstrap scenario.
        AccountingDesktopAPI(legacy).standaloneAccountingRead()
        self.assertTrue((legacy / "standalone-accounting.sqlite3").is_file())
        api = AccountingDesktopAPI(legacy)
        with self.assertRaises(PermissionError):
            api.standaloneAccountingRead()

    @unittest.expectedFailure
    def test_pending_missing_identity_for_existing_ledger_must_not_bootstrap_admin(self):
        """Open issue: deleting/losing local-users.json makes bootstrap available."""
        legacy = self.company / "restored-book-without-users"
        legacy.mkdir()
        AccountingDesktopAPI(legacy).standaloneAccountingRead()
        self.assertTrue((legacy / "standalone-accounting.sqlite3").is_file())
        recovered = identity.LocalCompanyIdentity(legacy)
        with self.assertRaises(identity.IdentityError):
            recovered.add_user("stranger", "temporary-password-987", "admin")


if __name__ == "__main__":
    unittest.main()
