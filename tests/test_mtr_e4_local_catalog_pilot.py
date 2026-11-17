"""Actual detached Taraz local book -> Radar candidate review; synthetic only."""
from dataclasses import replace
from datetime import datetime, timezone, timedelta
import importlib
import os
from pathlib import Path
import sys
import tempfile
import unittest

from radar_party_review_store import (
    HostPrincipal, PartyReviewStore, ReviewConflict,
)
from mtr_e4_local_catalog_pilot import (
    RadarLocalTarazPartyReviewPilot, LocalCatalogPilotDenied,
)


class LocalTarazRadarIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = os.environ.get("MTR_TARAZ_SOURCE")
        if not source:
            raise unittest.SkipTest("detached MTR_TARAZ_SOURCE required")
        root = Path(source).resolve()
        if not (root / "taraz_mtr_catalog_read.py").is_file():
            raise unittest.SkipTest("detached Taraz source does not have catalog reader")
        sys.path.insert(0, str(root))
        cls.registry_mod = importlib.import_module("standalone_accounting_company_registry")
        cls.identity_mod = importlib.import_module("standalone_accounting_identity")
        cls.accounting_mod = importlib.import_module("standalone_accounting")
        cls.catalog_mod = importlib.import_module("taraz_mtr_catalog_read")
        cls.addClassCleanup(lambda: sys.path.remove(str(root)))

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="e4-crossrepo-catalog-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        hub = self.root / "taraz-test-companies"
        hub.mkdir()
        self.registry = self.registry_mod.StandaloneCompanyRegistry(hub)
        self.company = self.registry.create_company("Synthetic Local Taraz Company")
        self.org = self.company["id"]
        self.book = self.registry.company_data_directory(self.org)
        self.identity = self.identity_mod.LocalCompanyIdentity(self.book)
        self.identity.add_user("reviewer", "test-private-pass", role="admin")
        self.session = self.identity.login("reviewer", "test-private-pass")
        self.accounting = self.accounting_mod.StandaloneAccountingStore(
            self.book / "standalone-accounting.sqlite3", default_currency="RIAL")
        self.accounts = self.identity.accounting_accounts()
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        self.revision = 0
        for record in (
            {"type": "party.register", "eventId": "evt-party-1",
             "partyId": "party-1", "name": "Shared customer", "kind": "customer",
             "creditLimit": 900000000},
            {"type": "party.register", "eventId": "evt-party-2",
             "partyId": "party-2", "name": "Shared customer", "kind": "vendor"},
            {"type": "party.register", "eventId": "evt-party-hidden",
             "partyId": "party-hidden", "name": "Highly private company",
             "kind": "both", "creditLimit": 400000000},
        ):
            updated = self.accounting.command(
                record, actor="reviewer", accounts=self.accounts,
                expected_revision=self.revision,
                now=self.now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
            self.revision = updated["revision"]
        self.scope = self.catalog_mod.HostCatalogScope(
            company_id=self.org, org_id=self.org,
            project_id="project-1",
            project_grants=frozenset({"project-1"}),
            role_grants=frozenset({"admin"}),
            party_fields=frozenset({"id", "name", "kind"}),
            item_fields=frozenset({"id", "name"}),
            party_ids=frozenset({"party-1", "party-2"}),
            item_ids=frozenset(),
            source_revision=self.revision, observed_at=self.now,
        )
        self.catalog = self.catalog_mod.TarazCatalogRead(
            registry=self.registry, identity=self.identity,
            store=self.accounting, host_scope=self.scope,
        )
        self.reviews = PartyReviewStore(self.root / "radar-human-review.sqlite3")
        self.pilot = RadarLocalTarazPartyReviewPilot(
            catalog=self.catalog, reviews=self.reviews,
            local_source_test_only=True,
        )
        self.principal = HostPrincipal(
            user_id="finance", organization_id=self.org,
            session_id="host-session-1", role="taraz_finance_reviewer",
            project_grants=frozenset({"project-1"}),
            capabilities=frozenset({"party_match_read", "party_match_decide"}),
            visible_fields=frozenset({"name"}),
            allowed_candidate_ids=frozenset({"party-1", "party-2"}),
            authenticated=True, active=True,
        )
        self.customer = {"organization_id": self.org,
                         "customer_id": "radar-temporary-1",
                         "name": "Shared customer"}

    def open(self, **changes):
        arguments = {
            "principal": self.principal,
            "local_session_token": self.session,
            "project_id": "project-1",
            "review_id": "synthetic-review-1",
            "temporary_customer": self.customer,
            "event_id": "evt-open-1",
            "now": self.now,
        }
        arguments.update(changes)
        return self.pilot.open_pending(**arguments)

    def decide(self, opened, **changes):
        arguments = {
            "principal": self.principal,
            "local_session_token": self.session,
            "project_id": "project-1",
            "review_id": "synthetic-review-1",
            "temporary_customer": self.customer,
            "action": "select_candidate",
            "candidate_id": "party-1",
            "expected_version": opened["version"],
            "expected_digest": opened["snapshotSha256"],
            "event_id": "evt-decision-1",
            "now": self.now + timedelta(seconds=1),
        }
        arguments.update(changes)
        return self.pilot.decide(**arguments)

    def test_all_authorized_conflicting_names_and_human_selection_no_party_write(self):
        before = self.accounting.read(actor="reviewer", accounts=self.accounts)
        opened = self.open()
        self.assertEqual(opened["state"], "PENDING_HUMAN_REVIEW")
        self.assertEqual(opened["authorizedCandidateIds"], ["party-1", "party-2"])
        self.assertEqual(opened["preview"]["candidate_count"], 2)
        self.assertEqual([candidate["fields"]["name"]["comparison"]
                          for candidate in opened["preview"]["candidates"]],
                         ["equal_after_heuristic_normalization"] * 2)
        self.assertFalse(opened["officialPartyLinked"])
        self.assertFalse(opened["sourceAuthenticityVerifiedByThisModule"])
        outcome = self.decide(opened)
        self.assertEqual(outcome["decision"]["selectedCandidateId"], "party-1")
        self.assertFalse(outcome["officialPartyLinked"])
        self.assertFalse(outcome["officialTarazPartyCreated"])
        self.assertEqual(before, self.accounting.read(actor="reviewer", accounts=self.accounts))
        self.assertNotIn("Highly private company", str(outcome))
        self.assertNotIn("900000000", str(outcome))
        self.assertEqual(self.reviews.read_review(
            principal=self.principal, project_id="project-1",
            review_id="synthetic-review-1") ["decision"]["action"],
            "select_candidate")

    def test_stale_catalog_revision_denies_decision(self):
        opened = self.open()
        self.accounting.command(
            {"type": "party.register", "eventId": "evt-party-new",
             "partyId": "party-3", "name": "A new party", "kind": "customer"},
            actor="reviewer", accounts=self.accounts,
            expected_revision=self.revision,
            now=self.now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        with self.assertRaises(self.catalog_mod.CatalogStale):
            self.decide(opened)
        still = self.reviews.read_review(principal=self.principal,
                                         project_id="project-1",
                                         review_id="synthetic-review-1")
        self.assertEqual(still["state"], "PENDING_HUMAN_REVIEW")

    def test_changed_temporary_customer_rejected_without_source_mutation(self):
        opened = self.open()
        changed = dict(self.customer, name="Different temporary name")
        with self.assertRaises(ReviewConflict):
            self.decide(opened, temporary_customer=changed)
        self.assertEqual(self.reviews.read_review(
            principal=self.principal, project_id="project-1",
            review_id="synthetic-review-1") ["version"], 1)

    def test_revoked_local_taraz_identity_blocks_decision(self):
        opened = self.open()
        self.identity.logout(self.session)
        with self.assertRaises(PermissionError):
            self.decide(opened)

    def test_mismatched_host_grant_and_cross_org_rejected(self):
        other = replace(self.principal, organization_id="unrelated-org")
        with self.assertRaises(PermissionError):
            self.open(principal=other)
        denied = replace(self.principal,
                         allowed_candidate_ids=frozenset({"party-1"}))
        with self.assertRaises(PermissionError):
            self.open(principal=denied)
        with self.assertRaises(PermissionError):
            self.open(project_id="unrelated-project")

    def test_expired_local_catalog_observation_denies_open(self):
        with self.assertRaises(self.catalog_mod.CatalogStale):
            self.open(now=self.now + timedelta(minutes=10))

    def test_local_source_pilot_does_not_allow_production_mode(self):
        with self.assertRaises(LocalCatalogPilotDenied):
            RadarLocalTarazPartyReviewPilot(
                catalog=self.catalog, reviews=self.reviews,
                local_source_test_only=False)


if __name__ == "__main__":
    unittest.main()
