"""Current-source Madar -> Taraz synthetic P0 finance evidence, never a release.

Only uses temporary synthetic LAN sessions, exchange files, registered company
and ledger SQLite. No subprocess/network, installed binary or real profile.
The trust secrets and transport acknowledgment are *test injected* and NEVER
prove a deployed peer. All official/installed/posting-real flags stay false.
"""
from __future__ import annotations

from contextlib import closing
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import sys
import tempfile
import threading
import time
from unittest.mock import patch


MADAR_ROOT = Path(__file__).resolve().parents[1]
TARAZ_ROOT = Path(r"D:\CoS-Test\000- Taraz\taraz-mtr-e2-isolated-20261109")
REQUIRED = (
    (MADAR_ROOT, "lan.py"), (MADAR_ROOT, "mtr_finance_authenticated_origin.py"),
    (MADAR_ROOT, "mtr_peer_envelope.py"), (MADAR_ROOT, "taraz_exchange.py"),
    (TARAZ_ROOT, "taraz_mtr_peer_registry.py"),
    (TARAZ_ROOT, "taraz_mtr_external_actor_link.py"),
    (TARAZ_ROOT, "taraz_mtr_finance_binding_authority.py"),
    (TARAZ_ROOT, "standalone_accounting_desktop.py"),
)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _check_sources() -> dict:
    result = {}
    optional = (
        (TARAZ_ROOT, "taraz_mtr_finance_witness_issuer.py"),
        (MADAR_ROOT, "mtr_taraz_finance_witness_verifier.py"),
    )
    for root, name in (*REQUIRED, *(p for p in optional if (p[0] / p[1]).is_file())):
        path = root / name
        if not root.is_dir() or root.is_symlink() or not path.is_file() or path.is_symlink():
            raise RuntimeError("required current read-only source unavailable: " + str(path))
        result[("madar/" if root == MADAR_ROOT else "taraz/") + name] = _sha(path.read_bytes())
    return result


class SyntheticMadarBridge:
    def __init__(self):
        self._lock = threading.RLock()
        self.state = {
            "projects": [{"id": "project-synthetic"}],
            "tasks": [{
                "id": "card-synthetic",
                "projectId": "project-synthetic",
                "title": "Only disposable synthetic invoice",
                "checklist": [{"expenseItems": [{
                    "id": "expense-synthetic", "currency": "RIAL",
                    "quantity": 2, "unitPrice": 750,
                }]}],
            }],
        }

    def getState(self):
        return deepcopy(self.state)


def run_crosssource_synthetic(*, root: Path | None = None,
                              include_finance_witness: bool = False) -> dict:
    """Build a complete *synthetic* signed-to-journal observation, fail closed."""
    if type(include_finance_witness) is not bool:
        raise TypeError("explicit boolean witness mode required")
    source_pins = _check_sources()
    # No package installs, live filesystem roots or network. Import the exact
    # two local source trees; do not copy/edit modules owned by other workers.
    for directory in (str(TARAZ_ROOT), str(MADAR_ROOT)):
        if directory not in sys.path:
            sys.path.insert(0, directory)
    from lan import LanService, make_account
    from mtr_account_lineage import principal_actor_id
    from mtr_finance_authenticated_origin import (
        FinanceOriginDenied, HostAuthenticatedFinanceOrigin,
    )
    from mtr_peer_envelope import (
        verify_request, verify_receipt_query, verify_peer_receipt,
    )
    from taraz_exchange import queue_saved_task
    from standalone_accounting_company_registry import StandaloneCompanyRegistry
    from standalone_accounting_desktop import AccountingDesktopAPI
    from standalone_accounting_identity import LocalCompanyIdentity
    from taraz_desktop import TarazAPI
    from taraz_mtr_peer_registry import PeerConfig, TarazPeerRegistry
    from taraz_mtr_external_actor_link import (
        ExternalActorLinkDenied, ManualExternalActorLinks,
    )
    from taraz_mtr_finance_binding_authority import ManualFinanceBindingAuthority

    def execute(disposable: Path) -> dict:
        if (not disposable.is_absolute() or disposable.is_symlink()
                or any(disposable.iterdir())):
            raise ValueError("an existing empty, nonlinked temporary directory is required")
        local = disposable / "LOCALAPPDATA"
        local.mkdir()
        env = {
            "LOCALAPPDATA": str(local),
            "APPDATA": str(disposable / "APPDATA"),
            "USERPROFILE": str(disposable),
            "HOME": str(disposable),
        }
        (disposable / "APPDATA").mkdir()
        with patch.dict(os.environ, env):
            bridge = SyntheticMadarBridge()
            service = LanService(bridge, disposable / "private-lan-users.json")
            actor = make_account("qa-admin", "synthetic-only-password", "admin",
                                 ["project-synthetic"])
            actor["financeEdit"] = True
            service.users = {"qa-admin": actor}
            token = secrets.token_urlsafe(32)
            service.sessions[token] = ("qa-admin", time.time() + 3600)
            if service.account_for(token) is not actor:
                raise AssertionError("private LanService token did not authorize current account")

            company_root = disposable / "registered-companies"
            company_root.mkdir()
            companies = StandaloneCompanyRegistry(company_root)
            company_id = companies.create_company("SYNTHETIC QA COMPANY ONLY")["id"]
            book = companies.company_data_directory(company_id)
            identity = LocalCompanyIdentity(book)
            identity.add_user("qaadmin", "synthetic-admin-password", role="admin")
            admin_token = identity.login("qaadmin", "synthetic-admin-password")
            identity.add_user("qaeditor", "synthetic-editor-password", role="editor",
                              administrator=admin_token)
            editor_token = identity.login("qaeditor", "synthetic-editor-password")
            taraz = TarazAPI(book)
            taraz._identity_store = identity
            taraz._identity_token = editor_token
            taraz._actor = "qaeditor"
            taraz._accounts = identity.accounting_accounts()
            editor_host = AccountingDesktopAPI(
                book, company_workspace_id=company_id,
                authenticated_user=identity.require_session(editor_token),
                identity_store=identity, identity_token=editor_token)

            request_id = secrets.token_hex(16)
            invoice_id = "synthetic-invoice-qa"
            issue_event_id = "synthetic-issue-qa"
            journal_id = "J:" + issue_event_id
            secret = secrets.token_bytes(48)
            peer = PeerConfig(
                organization_id="qa-synthetic-madar-org",
                madar_sender_id="qa-synthetic-madar",
                madar_key_id="qa-synthetic-madar-key",
                taraz_sender_id="qa-synthetic-taraz",
                taraz_key_id="qa-synthetic-taraz-key",
                madar_secret=secret, taraz_secret=secrets.token_bytes(48))
            registry = TarazPeerRegistry(disposable / "registered-peer.sqlite3", peer)
            signer = HostAuthenticatedFinanceOrigin(
                service, organization_id=peer.organization_id,
                sender_id=peer.madar_sender_id, key_id=peer.madar_key_id,
                signing_key=secret, company_id=company_id)

            # Actual current _publish_proposal writes insertion-order UTF-8,
            # NOT canonical sort-key envelope JSON. Use the exact persisted bytes.
            result = queue_saved_task(bridge.getState(), "card-synthetic",
                                      "expense-synthetic", request_id=request_id)
            if result.get("queued") is not True or result["id"] != request_id:
                raise AssertionError("actual Madar source publication failed")
            pending = local / "Madar-Taraz-Bridge" / "pending" / (request_id + ".json")
            raw = pending.read_bytes()
            decoded = json.loads(raw)
            expected = json.dumps(decoded, ensure_ascii=False, separators=(",", ":")).encode("utf8")
            if expected != raw or decoded.get("amountRial") != "1500":
                raise AssertionError("published bytes or RIAL amount changed")
            source_sha = _sha(raw)

            seal = signer.prepare_manual(
                token, raw, invoice_id=invoice_id,
                issue_event_id=issue_event_id, explicit_manual_action=True)
            original_wire = signer.sign_original_manual(
                token, seal, raw, explicit_manual_action=True)
            original = verify_request(
                original_wire, secret=secret, now=datetime.now(timezone.utc).replace(microsecond=0),
                expected_organization_id=peer.organization_id,
                expected_sender_id=peer.madar_sender_id,
                expected_key_id=peer.madar_key_id,
                purpose="finance_review_request",
                allowed_actor_roles=frozenset({"admin"}))
            if original.payload != {
                "id": request_id, "taskId": "card-synthetic",
                "projectId": "project-synthetic", "sourceDigest": source_sha,
                "companyId": company_id, "actorId": principal_actor_id(actor),
                "invoiceId": invoice_id, "issueEventId": issue_event_id,
                "journalId": journal_id,
            }:
                raise AssertionError("private host signer payload mismatch")
            # Missing/lost ACK: simulate only by discarding the first *return*
            # from this same registry (no network); repeat exactly same wire.
            first = registry.intake(
                original_wire, now=datetime.now(timezone.utc).replace(microsecond=0),
                verified_transport_peer=True)
            retry = registry.intake(
                original_wire, now=datetime.now(timezone.utc).replace(microsecond=0),
                verified_transport_peer=True)
            if (first["idempotent"] is not False
                    or retry["idempotent"] is not True
                    or first["financialEventCreated"] is not False):
                raise AssertionError("lost ACK replay duplicated original")
            challenge = secrets.token_hex(16)
            query_wire = signer.sign_query_manual(
                token, original_wire, raw, query_request_id=challenge,
                explicit_manual_action=True)
            verified_query = verify_receipt_query(
                query_wire, secret=secret, now=datetime.now(timezone.utc).replace(microsecond=0),
                expected_organization_id=peer.organization_id,
                expected_sender_id=peer.madar_sender_id,
                expected_key_id=peer.madar_key_id,
                allowed_actor_roles=frozenset({"admin"}))
            stamp = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(seconds=2)
            reply = registry.query_receipt(
                query_wire, now=stamp, verified_transport_peer=True)
            reply_retry = registry.query_receipt(
                query_wire, now=stamp, verified_transport_peer=True)
            confirmed = verify_peer_receipt(
                reply, original=original, query=verified_query,
                secret=peer.taraz_secret, now=stamp,
                expected_peer_id=peer.taraz_sender_id,
                expected_peer_key_id=peer.taraz_key_id)
            if (confirmed.payload["lookupStatus"] != "received"
                    or reply != reply_retry):
                raise AssertionError("signed registry lookup lost-ACK replay mismatch")
            with closing(sqlite3.connect(registry.path)) as conn:
                entries = conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
                lookups = conn.execute("SELECT COUNT(*) FROM queries").fetchone()[0]
            if (entries, lookups) != (1, 1):
                raise AssertionError("duplicate registered request or query")
            try:
                signer.sign_query_manual(
                    token, original_wire, raw,
                    query_request_id=secrets.token_hex(16), explicit_manual_action=True)
            except FinanceOriginDenied:
                query_reissue_denied = True
            else:
                raise AssertionError("second query incorrectly authorized")

            review = taraz.tarazIntegrationReview(request_id, "reviewed")
            if review["financialEventCreated"] is not False:
                raise AssertionError("metadata review posted a finance record")
            reviewed = local / "Madar-Taraz-Bridge" / "reviewed"
            reviewed_raw = (reviewed / (request_id + ".json")).read_bytes()
            intent = json.loads((reviewed / (request_id + ".intent.json")).read_bytes())
            review_raw = (reviewed / (request_id + ".review.json")).read_bytes()
            if (reviewed_raw != raw or intent["sourceDigest"] != source_sha
                    or json.loads(review_raw)["state"] != "reviewed"):
                raise AssertionError("Taraz review changed source bytes or binding")

            # Explicit independently logged-in COMPANY ADMIN uses the real
            # accounting command facade, writing ONLY disposable SQLite.
            admin_host = AccountingDesktopAPI(
                book, company_workspace_id=company_id,
                authenticated_user=identity.require_session(admin_token),
                identity_store=identity, identity_token=admin_token)
            revision = admin_host.standaloneAccountingRead()["revision"]
            day = datetime.now(timezone.utc).date().isoformat()
            commands = (
                {"type": "party.register", "eventId": "synthetic-party",
                 "partyId": "synthetic-customer", "kind": "customer",
                 "name": "Synthetic customer only"},
                {"type": "invoice.create", "eventId": "synthetic-create",
                 "invoiceId": invoice_id, "partyId": "synthetic-customer",
                 "documentDate": day, "sourceType": "madar", "sourceId": request_id,
                 "lines": [{"description": "Synthetic only", "quantity": 1,
                            "unitPrice": 1500}]},
                {"type": "invoice.approve", "eventId": "synthetic-approve",
                 "invoiceId": invoice_id},
                {"type": "invoice.issue", "eventId": issue_event_id,
                 "invoiceId": invoice_id, "postingDate": day},
            )
            for command in commands:
                committed = admin_host.standaloneAccountingCommand(
                    {"command": command, "expectedRevision": revision})
                revision = committed["revision"]
            db_path = book / "standalone-accounting.sqlite3"
            if not db_path.is_file() or not db_path.is_relative_to(disposable):
                raise AssertionError("company ledger was not confined to temporary directory")
            with closing(sqlite3.connect(db_path)) as conn:
                row = conn.execute(
                    "SELECT revision,state,digest FROM standalone_accounting WHERE id=1"
                ).fetchone()
            if row is None or row[0] != revision or _sha(row[1]) != row[2]:
                raise AssertionError("persisted accounting SQLite digest mismatch")
            journal_state = json.loads(row[1])
            matching = [e for e in journal_state["events"]
                        if e.get("eventId") == issue_event_id]
            if len(matching) != 1 or matching[0]["command"]["type"] != "invoice.issue":
                raise AssertionError("synthetic invoice issue journal not durable and unique")

            link_dir = disposable / "private-external-link"
            link_dir.mkdir()
            used = disposable / "private-finance-consumed"
            used.mkdir()
            links = ManualExternalActorLinks(
                accounting_host=admin_host, peer_registry=registry,
                trusted_config=peer, reviewed_root=local / "Madar-Taraz-Bridge",
                link_db_path=link_dir / "external-actor-links.sqlite3")
            grant = links.authorize_manual(
                signed_madar_original=original_wire,
                signed_madar_query_challenge=query_wire,
                company_id=company_id, administrator_token=admin_token,
                explicit_manual_action=True, now=stamp)
            if (grant["decision"] != "EXTERNAL_ACTOR_LINK_ADMITTED_ONCE"
                    or grant["officialFinanceReceiptVerified"] is not False):
                raise AssertionError("explicit admin external actor link denied/unsafe")
            binding_replay_denied = False
            witness_extra = {}
            if include_finance_witness:
                # Current worker-19/18 source modules are used directly and
                # independently, but with FRESH SYNTHETIC trust. Their output
                # explicitly forbids any official/live-Taraz-success claim.
                from taraz_mtr_finance_witness_issuer import (
                    FinanceIssuerTrust, ManualTarazFinanceWitnessIssuer,
                    FinanceWitnessIssueDenied,
                )
                from mtr_taraz_finance_witness_verifier import (
                    FinanceWitnessTrust, DurableFinanceWitnessChallenges,
                    TarazFinanceWitnessVerifier, FinanceWitnessRejected,
                )
                finance_key = secrets.token_bytes(48)
                finance_issuer_id = "qa-finance-issuer"
                finance_key_id = "qa-finance-key"
                issuer_trust = FinanceIssuerTrust(
                    peer.organization_id, finance_issuer_id,
                    finance_key_id, finance_key)
                verifier_trust = FinanceWitnessTrust(
                    organization_id=peer.organization_id,
                    madar_sender_id=peer.madar_sender_id,
                    madar_key_id=peer.madar_key_id,
                    madar_secret=secret,
                    taraz_finance_issuer_id=finance_issuer_id,
                    taraz_finance_key_id=finance_key_id,
                    taraz_finance_secret=finance_key)
                issued_folder = disposable / "private-finance-issuance"
                issued_folder.mkdir()
                challenges_folder = disposable / "private-finance-challenges"
                challenges_folder.mkdir()
                challenges = DurableFinanceWitnessChallenges(
                    challenges_folder / "mtr-taraz-finance-witness-queries.sqlite3")
                registered = challenges.register_manual(
                    original_wire=original_wire, query_wire=query_wire,
                    source_raw=raw, config=verifier_trust,
                    explicit_manual_action=True, now=stamp)
                if registered.get("registered") is not True:
                    raise AssertionError("Madar one-time finance challenge was not registered")
                issuer = ManualTarazFinanceWitnessIssuer(
                    accounting_host=admin_host, peer_registry=registry,
                    trusted_config=peer, finance_trust=issuer_trust,
                    external_actor_links=links,
                    reviewed_root=local / "Madar-Taraz-Bridge",
                    issued_db_path=issued_folder / "mtr-taraz-finance-witness-issued.sqlite3")
                kwargs = dict(
                    signed_madar_original=original_wire,
                    signed_madar_query_challenge=query_wire,
                    company_id=company_id, administrator_token=admin_token,
                    expected_revision=revision,
                    explicit_manual_action=True, now=stamp)
                issued = issuer.issue_manual(**kwargs)
                verifier = TarazFinanceWitnessVerifier(
                    config=verifier_trust, challenges=challenges)
                assessed = verifier.inspect_and_consume(
                    signed_witness=issued.signed_witness,
                    original_wire=issued.original_wire, query_wire=issued.query_wire,
                    source_raw=issued.source_raw,
                    journal_raw=issued.journal_raw,
                    accounting_event_raw=issued.accounting_event_raw,
                    ledger_revision=issued.ledger_revision,
                    ledger_state_sha256=issued.ledger_state_sha256,
                    now=stamp)
                if (assessed.signedFinanceWitnessCryptographyVerified is not True
                        or assessed.signedJournalEventBound is not True
                        or assessed.oneTimeDurableChallengeConsumed is not True
                        or assessed.officialFinanceReceiptVerified is not False
                        or assessed.realTarazIssuerAuthenticated is not False
                        or assessed.independentLiveLedgerReadbackVerified is not False):
                    raise AssertionError("unverified or falsely official finance witness")
                try:
                    verifier.inspect_and_consume(
                        signed_witness=issued.signed_witness,
                        original_wire=issued.original_wire,
                        query_wire=issued.query_wire,
                        source_raw=issued.source_raw,
                        journal_raw=issued.journal_raw,
                        accounting_event_raw=issued.accounting_event_raw,
                        ledger_revision=issued.ledger_revision,
                        ledger_state_sha256=issued.ledger_state_sha256,
                        now=stamp)
                except FinanceWitnessRejected:
                    witness_verifier_replay_denied = True
                else:
                    raise AssertionError("durable witness verification challenge reused")
                try:
                    issuer.issue_manual(**kwargs)
                except (FinanceWitnessIssueDenied, PermissionError):
                    witness_issuer_replay_denied = True
                else:
                    raise AssertionError("issuer created a second finance witness")
                witness_extra = {
                    "syntheticFinanceWitnessCryptographyVerified": True,
                    "syntheticFinanceWitnessBoundToExactJournal": True,
                    "oneTimeDurableWitnessChallengeConsumed": True,
                    "witnessIssuerReplayDenied": witness_issuer_replay_denied,
                    "witnessVerifierReplayDenied": witness_verifier_replay_denied,
                    "financeWitnessSignedWireSha256": _sha(issued.signed_witness),
                    "financeWitnessJournalRawSha256": _sha(issued.journal_raw),
                    "financeWitnessEventRawSha256": _sha(issued.accounting_event_raw),
                    "financeWitnessAssessment": assessed.decision,
                }
                observed = {"oneTimeAdminExternalActorLinkConsumed": True}
                if admin_host.standaloneAccountingRead()["revision"] != revision:
                    raise AssertionError("finance witness issuer mutated an existing journal")
            else:
                authority = ManualFinanceBindingAuthority(
                    accounting_host=admin_host, peer_registry=registry,
                    trusted_config=peer, reviewed_root=local / "Madar-Taraz-Bridge",
                    consumed_bindings_dir=used, external_actor_links=links)
                bind_args = dict(
                    signed_madar_original=original_wire,
                    signed_madar_query_challenge=query_wire,
                    madar_request_id=request_id, company_id=company_id,
                    invoice_id=invoice_id, issue_event_id=issue_event_id,
                    journal_id=journal_id, expected_revision=revision,
                    explicit_manual_action=True, now=stamp,
                    external_link_admin_token=admin_token)
                observed = authority.bind_preexisting_manual(**bind_args)
                if (observed["decision"] !=
                        "SIGNED_BINDING_TO_EXISTING_JOURNAL_OBSERVED_NOT_OFFICIAL"
                        or observed["persistedInvoiceJournalVerified"] is not True
                        or observed["officialFinanceReceiptVerified"] is not False
                        or observed["financialEventCreatedByThisOperation"] is not False):
                    raise AssertionError("signed evidence binding falsely promoted finance status")
                try:
                    authority.bind_preexisting_manual(**bind_args)
                except (PermissionError, ExternalActorLinkDenied):
                    binding_replay_denied = True
                else:
                    raise AssertionError("one-time finance evidence could be rebound")
                if admin_host.standaloneAccountingRead()["revision"] != revision:
                    raise AssertionError("binding operation mutated invoice journal")

            issuer_module = TARAZ_ROOT / "taraz_mtr_finance_witness_issuer.py"
            return {
                "decision": (
                    "SYNTHETIC_FINANCE_WITNESS_STRUCTURAL_ONLY_NOT_OFFICIAL"
                    if include_finance_witness else
                    "SYNTHETIC_JOURNAL_OBSERVED_NOT_OFFICIAL"),
                "sourceModulesSha256": source_pins,
                "currentPrivateLanAccountForTokenVerified": True,
                "syntheticPeerTransportTrustInjected": True,
                "syntheticTestKeysOnly": True,
                "sourceRawSha256": source_sha,
                "reviewedRawSha256": _sha(reviewed_raw),
                "reviewMarkerSha256": _sha(review_raw),
                "signedOriginalWireSha256": _sha(original_wire),
                "signedQueryWireSha256": _sha(query_wire),
                "signedPeerLookupSha256": _sha(reply),
                "ledgerStateSha256": row[2],
                "invoiceIssueEventSha256": _sha(
                    json.dumps(matching[0], ensure_ascii=False,
                               sort_keys=True, separators=(",", ":")).encode("utf8")),
                "sameOriginalIntakeCount": entries,
                "sameQueryCount": lookups,
                "lostAckIntakeIdempotent": retry["idempotent"] is True,
                "lostAckQueryIdentical": reply == reply_retry,
                "secondHostQueryDenied": query_reissue_denied,
                "externalActorLinkGrantedByCurrentTarazAdmin": True,
                "externalActorLinkConsumed": observed["oneTimeAdminExternalActorLinkConsumed"],
                "nonfinancialManualReviewSourceBound": True,
                "persistedSyntheticInvoiceIssueJournal": True,
                "ledgerRevision": revision,
                "manualFinanceBindingReplayDenied": binding_replay_denied,
                "manualFinanceBindingRun": not include_finance_witness,
                **witness_extra,
                "financeWitnessIssuer": (
                    "SOURCE_PRESENT_UNINTEGRATED" if issuer_module.is_file()
                    else "UNAVAILABLE_NO_CURRENT_TARAZ_ISSUER"),
                "financeWitnessMadarVerifierSourcePresent": (
                    MADAR_ROOT / "mtr_taraz_finance_witness_verifier.py").is_file(),
                "officialFinanceReceiptVerified": False,
                "independentlyAuthenticatedMadarActorVerified": False,
                "trustedMadarInvoiceBindingVerified": False,
                "financialPostingReal": False,
                "installed": False,
                "mayRelease": False,
                "mayDeploy": False,
            }

    if root is None:
        with tempfile.TemporaryDirectory(prefix="mtr-finance-crosssource-qa-") as folder:
            return execute(Path(folder))
    return execute(root)


def main(*, include_finance_witness: bool = False) -> int:
    try:
        outcome = run_crosssource_synthetic(include_finance_witness=include_finance_witness)
    except Exception as error:
        print(json.dumps({
            "decision": "BLOCKED_SYNTHETIC_EXECUTION",
            "errorType": type(error).__name__, "reason": str(error)[:300],
            "officialFinanceReceiptVerified": False,
            "financialPostingReal": False, "installed": False,
            "mayRelease": False,
        }, ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps(outcome, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("binding", "witness"),
                        default="binding", help="isolated synthetic one-time path")
    args = parser.parse_args()
    raise SystemExit(main(include_finance_witness=args.mode == "witness"))
