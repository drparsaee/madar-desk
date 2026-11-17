"""E2 HOST -> peer metadata integration, *test-only and never LAN-mounted*.

One authorized saved Madar card travels through HostRequestStore,
OneShotDispatchGate, a pinned loopback HTTPS client, and a signed Taraz test
peer. Neither this class nor its dependencies connect to real Taraz finance,
write accounting books, start a service, use real credentials, or create an
official receipt. There is NO automated resend, even after a lost response.

Critically, outbox + dispatch gate live in TWO databases. Locking MadarHost
and per-DB SQLite transactions cannot make their writes atomic with each
other or with TLS; a production peer protocol needs stronger coordination.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hmac
import secrets

from mtr_e2_dispatch_gate import OneShotDispatchGate, DispatchGateConflict
from mtr_e2_query_observation_journal import QueryObservationJournal
from mtr_host_principal_provenance import (
    HostPrincipalProvenance, OUTBOX_RECOVERY, GATE_RECOVERY,
)
from mtr_host_request_store import StoreConflict
from mtr_lan_finance_adapter import MtrLanFinanceAdapter
from mtr_peer_envelope import sign_request
from mtr_peer_https_pilot import PeerLoopbackHttpsPilot, PeerPilotKeys


class HostPeerPilotDenied(ValueError):
    """Missing current host authorization or a mismatched saved request."""


class MtrE2HostPeerPilot:
    """No exposed network endpoint. Caller opts in to synthetic loopback ONLY."""

    def __init__(self, *, finance_adapter: MtrLanFinanceAdapter,
                 dispatch_gate: OneShotDispatchGate,
                 peer: PeerLoopbackHttpsPilot, keys: PeerPilotKeys,
                 synthetic_only: bool,
                 observation_journal: QueryObservationJournal | None = None):
        if synthetic_only is not True:
            raise HostPeerPilotDenied("synthetic-only host-peer pilot")
        if (type(finance_adapter) is not MtrLanFinanceAdapter or
                type(dispatch_gate) is not OneShotDispatchGate or
                type(peer) is not PeerLoopbackHttpsPilot or
                type(keys) is not PeerPilotKeys):
            raise HostPeerPilotDenied("test host, dispatch and peer contracts required")
        if dispatch_gate.outbox is not finance_adapter.store:
            raise HostPeerPilotDenied("dispatch gate must own the same host outbox")
        if observation_journal is not None and (
                type(observation_journal) is not QueryObservationJournal or
                observation_journal.outbox is not finance_adapter.store or
                observation_journal.gate is not dispatch_gate):
            raise HostPeerPilotDenied("journal must bind the same host outbox and gate")
        actual_keys = peer._keys
        if (finance_adapter.org_id != keys.organization_id or
                any(getattr(actual_keys, name) != getattr(keys, name) for name in (
                    "organization_id", "sender_id", "sender_key_id",
                    "peer_id", "peer_key_id")) or
                not hmac.compare_digest(actual_keys.sender_secret, keys.sender_secret) or
                not hmac.compare_digest(actual_keys.peer_secret, keys.peer_secret)):
            raise HostPeerPilotDenied("host/peer/organization identity mismatch")
        self._host = finance_adapter
        self._gate = dispatch_gate
        self._peer = peer
        self._keys = keys
        self._journal = observation_journal
        # F1: bind this outbox to the actual hosting LanService once. A plain
        # forged TrustedPrincipal can never reach public recovery reads.
        issuer = finance_adapter.store._recovery_provenance
        if issuer is None:
            issuer = HostPrincipalProvenance(
                finance_adapter.service, org_id=finance_adapter.org_id,
            )
            finance_adapter.store.bind_recovery_provenance(issuer)
        elif (type(issuer) is not HostPrincipalProvenance or
              issuer._service is not finance_adapter.service or
              issuer._org_id != finance_adapter.org_id):
            raise HostPeerPilotDenied("recovery issuer/host identity mismatch")
        self._provenance = issuer

    def _saved(self, token: str, task_id: str, request_id: str,
               base_revision: int, *, require_unchanged_card: bool = True):
        principal, card, current_revision = self._host._principal_and_task(token, task_id)
        if (type(base_revision) is not int or
                (require_unchanged_card and base_revision != current_revision)):
            raise StoreConflict("saved card revision changed")
        snapshot = self._host.store.request_snapshot(
            principal=principal, request_id=request_id,
            expected_base_revision=base_revision,
        )
        payload = snapshot["payload"]
        if (payload.get("taskId") != card["id"] or
                payload.get("projectId") != card["projectId"] or
                (require_unchanged_card and payload.get("title") != card["title"])):
            raise HostPeerPilotDenied("prepared payload no longer matches saved card")
        return principal, snapshot

    def _sign_host_only(self, snapshot: dict, *, instant: datetime) -> bytes:
        """The browser never supplies a raw signed payload or the MAC key."""
        return sign_request(
            snapshot["payload"],
            organization_id=self._keys.organization_id,
            sender_id=self._keys.sender_id,
            actor_role="editor" if snapshot.get("actorRole") == "editor"
            else snapshot["actorRole"],
            key_id=self._keys.sender_key_id,
            request_id=snapshot["requestId"],
            purpose="finance_review_request",
            issued_at=instant, expires_at=instant + timedelta(seconds=60),
            secret=self._keys.sender_secret,
            authorized=True, explicit_manual_action=True,
        )

    def send_once(self, *, token: str, task_id: str, request_id: str,
                  base_revision: int, payload_sha256: str,
                  send_key: str, explicit_manual_action: bool) -> dict:
        """One durable reservation, ONE synthetic packet. Never a retry.

        The returned peer HTTP metadata acknowledgement is not an authenticated
        official finance receipt. The one-shot gate remains consumed forever.
        """
        if explicit_manual_action is not True:
            raise PermissionError("explicit human action required")
        service = self._host.service
        with service.lock, service.bridge._lock:
            principal, saved = self._saved(token, task_id, request_id, base_revision)
            if (saved["requestState"] != "MANUAL_SEND_AUTHORIZED" or
                    saved["payloadSha256"] != payload_sha256 or
                    saved["sendKey"] != send_key):
                raise HostPeerPilotDenied("original host authorization mismatch")
            # This must commit durably BEFORE even attempting a TLS connection.
            permit = self._gate.reserve_once(
                principal=principal, request_id=request_id,
                expected_payload_sha256=payload_sha256,
                expected_base_revision=base_revision,
                current_server_revision=base_revision,
                send_key=send_key,
            )
            if permit["firstAttemptGranted"] is not True:
                raise DispatchGateConflict("first attempt was not granted")
            instant = datetime.now(timezone.utc).replace(microsecond=0)
            # Role derived from trusted live account, not from browser JSON.
            source = dict(saved)
            source["actorRole"] = principal.role
            signed = self._sign_host_only(source, instant=instant)
        # The host state and permission snapshot was validated under both
        # locks and the irreversible dispatch slot was persisted first. Never
        # hold shared LanService/card locks while a TLS peer can stall. A later
        # revocation cannot reissue the consumed permit or change this packet.
        try:
            result = self._peer.intake_once(
                signed, at=instant,
                explicit_human_action=True,
                host_manual_intent_persisted=True,
            )
        finally:
            # Even success is only metadata arrival, not an official Taraz
            # receipt. Any failure/crash holds the already consumed slot.
            try:
                self._gate.mark_unknown_after_attempt(
                    principal=principal, request_id=request_id,
                    expected_base_revision=base_revision,
                    expected_version=1,
                )
            except (DispatchGateConflict, PermissionError):
                # The durable reservation still forbids a new first send.
                pass
        return {
            "requestId": request_id,
            "metadataArrivalHint": result["received"],
            "dispatchSlotConsumed": True,
            "canAutoRetry": False,
            "officialTarazReceipt": False,
            "financialEventCreated": False,
            "nextAction": "signed_query_first_no_automatic_retry",
        }

    def query_first(self, *, token: str, task_id: str,
                    request_id: str, base_revision: int) -> dict:
        """Separate HMAC-signed Taraz metadata lookup; never a send/replay."""
        service = self._host.service
        with service.lock, service.bridge._lock:
            # Current principal is acquired by the actual host session; the
            # source/gate readers independently bind original actor/org/
            # project and the ORIGINAL session stored in both databases.
            # Re-login cannot mint another dispatch slot and mutable cards
            # need not exist to query the immutable first-send request.
            principal = self._host._recovery_principal(token)
            # Separate single-use HMAC proofs for every protected outbox and
            # gate read; both are bound to the original current host session.
            outbox_seal = self._provenance.issue_recovery(
                token, audience=OUTBOX_RECOVERY,
            )
            snapshot = self._host.store.recovery_snapshot(
                principal=principal, request_id=request_id,
                expected_base_revision=base_revision,
                token=token, seal=outbox_seal,
            )
            if snapshot["payload"].get("taskId") != task_id:
                raise HostPeerPilotDenied("original request task mismatch")
            gate_seal = self._provenance.issue_recovery(
                token, audience=GATE_RECOVERY,
            )
            gate_outbox_seal = self._provenance.issue_recovery(
                token, audience=OUTBOX_RECOVERY,
            )
            self._gate.recovery_status(
                principal=principal, request_id=request_id,
                expected_base_revision=base_revision,
                token=token, gate_seal=gate_seal,
                outbox_seal=gate_outbox_seal,
            )  # Deny if NO previously authorized attempt exists.
            instant = datetime.now(timezone.utc).replace(microsecond=0)
            source = dict(snapshot)
            source["actorRole"] = principal.role
            signed = self._sign_host_only(source, instant=instant)
        # The signed immutable request is prepared while the host snapshot is
        # locked; the read-only peer lookup must not block other LAN users.
        observation = None
        if self._journal is not None:
            def persist_signed_evidence(original_wire, query_wire, receipt_wire):
                nonlocal observation
                # Re-authenticate after network I/O: privileges may have been
                # revoked while TLS was blocked. Never persist a stale ACL.
                with service.lock, service.bridge._lock:
                    if self._host._recovery_principal(token) != principal:
                        raise PermissionError("host actor changed during signed lookup")
                    observation = self._journal.record(
                        principal=principal, request_id=request_id,
                        expected_base_revision=base_revision,
                        original_wire=original_wire, query_wire=query_wire,
                        peer_receipt_wire=receipt_wire,
                        sender_secret=self._keys.sender_secret,
                        peer_secret=self._keys.peer_secret,
                        now=instant,
                        sender_id=self._keys.sender_id,
                        sender_key_id=self._keys.sender_key_id,
                        peer_id=self._keys.peer_id,
                        peer_key_id=self._keys.peer_key_id,
                        token=token,
                    )

            peer = self._peer.query_verified(
                signed, at=instant, query_request_id=secrets.token_hex(16),
                evidence_sink=persist_signed_evidence,
            )
            if (observation is None or
                    observation["signedPeerEnvelopeSha256"] != peer["peerEnvelopeSha256"] or
                    observation["lookupStatus"] != peer["lookupStatus"]):
                raise HostPeerPilotDenied("signed peer result not durably journaled")
        else:
            # A test-only coordinator may deliberately omit the journal. This
            # mode is not an accepted operational query/recovery protocol.
            peer = self._peer.query_verified(
                signed, at=instant, query_request_id=secrets.token_hex(16),
            )
        return {
            "requestId": request_id,
            "lookupStatus": peer["lookupStatus"],
            "signedPeerEnvelopeSha256": peer["peerEnvelopeSha256"],
            "canAutoRetry": False,
            "officialTarazReceipt": False,
            "financialEventCreated": False,
        }


__all__ = ["MtrE2HostPeerPilot", "HostPeerPilotDenied"]
