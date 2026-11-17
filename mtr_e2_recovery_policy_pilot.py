"""Fail-closed E2 *local read-only* recovery policy; no re-login bypass.

The current public HostRequestStore and OneShotDispatchGate readers require
the *original* session. A newly authenticated session MUST NOT be substituted
for that one or used to read their private SQLite files. This pilot validates
what is safely readable today, and explicitly blocks re-login recovery until
the stores expose separately reviewed host-authoritative read-only APIs.

No transport, dispatch grant, peer query, receipt ingest, accounting or route.
"""

from __future__ import annotations

import hashlib

from mtr_e2_dispatch_gate import DispatchGateError, OneShotDispatchGate
from mtr_host_request_store import StoreError
from mtr_lan_finance_adapter import MtrLanFinanceAdapter


class RecoveryPolicyBlocked(PermissionError):
    """Metadata cannot be safely read with the currently authenticated host."""


class MtrE2RecoveryPolicyPilot:
    """A host-internal read-only check, not an endpoint or resend capability."""

    def __init__(self, *, finance_adapter: MtrLanFinanceAdapter,
                 dispatch_gate: OneShotDispatchGate):
        if (type(finance_adapter) is not MtrLanFinanceAdapter
                or type(dispatch_gate) is not OneShotDispatchGate
                or dispatch_gate.outbox is not finance_adapter.store):
            raise TypeError("same authoritative host outbox and gate required")
        self._host = finance_adapter
        self._gate = dispatch_gate

    def inspect_existing(self, *, token: str, task_id: str,
                         request_id: str, base_revision: int,
                         payload_sha256: str, send_key: str) -> dict:
        """Read unchanged, already-reserved evidence under original session.

        The token is authenticated by the existing host adapter; caller cannot
        inject a TrustedPrincipal, original session, org, grants, or source
        evidence. New-session re-login is denied rather than spoofed as old.

        A card title or board move *within its original project* may change
        its current revision without invalidating immutable original evidence.
        A cross-project move currently cannot be recovered here safely.
        """
        if (type(token) is not str or not token
                or type(task_id) is not str or not task_id
                or type(request_id) is not str or not request_id
                or type(base_revision) is not int
                or type(payload_sha256) is not str
                or type(send_key) is not str):
            raise RecoveryPolicyBlocked("Invalid recovery request")
        service = self._host.service
        with service.lock, service.bridge._lock:
            # Only the host currently authenticated principal and live grants
            # can open the request; no client-specified actor/org/ACL.
            try:
                principal, card, _ = self._host._principal_and_task(token, task_id)
                original = self._host.store.request_snapshot(
                    principal=principal, request_id=request_id,
                    expected_base_revision=base_revision,
                )
                if (original.get("requestState") != "MANUAL_SEND_AUTHORIZED"
                        or original.get("orgId") != self._host.org_id
                        or original.get("projectId") != card.get("projectId")
                        or original.get("baseRevision") != base_revision
                        or original.get("payloadSha256") != payload_sha256
                        or original.get("sendKey") != send_key
                        or original.get("payload", {}).get("taskId") != task_id
                        or original["payload"].get("projectId") != original["projectId"]):
                    raise RecoveryPolicyBlocked("Original request evidence differs")
                gate = self._gate.status(
                    principal=principal, request_id=request_id,
                    expected_base_revision=base_revision,
                )
                if (gate.get("requestId") != request_id
                        or gate.get("reservationConsumed") is not True
                        or gate.get("mayDispatch") is not False
                        or gate.get("state") not in (
                            "reserved_before_network", "unknown_after_attempt",
                            "observed_received")):
                    raise RecoveryPolicyBlocked("Unverified original dispatch reservation")
            except (KeyError, PermissionError, StoreError, DispatchGateError) as exc:
                raise RecoveryPolicyBlocked(
                    "Authoritative original session/grants/evidence unavailable; "
                    "re-login recovery requires a new host-only read API"
                ) from exc

            # Local status ONLY. No peer query, MAC signing, send, retry grant,
            # new receipt or audit mutation. Old title and other payload fields
            # are not disclosed. Treat 'not_received' as query-first as well.
            received = (gate["state"] == "observed_received")
            return {
                "requestId": request_id,
                "baseRevision": base_revision,
                "sourceProjectId": original["projectId"],
                "payloadSha256": original["payloadSha256"],
                "sendKeySha256": hashlib.sha256(
                    original["sendKey"].encode("utf-8")
                ).hexdigest(),
                "dispatchState": gate["state"],
                "receiptState": original["receiptState"],
                "reservationConsumed": True,
                "mustQueryFirst": not received,
                "nextAction": ("recover_existing_receipt_only" if received
                               else "query_taraz_first_no_automatic_retry"),
                "mayDispatch": False,
                "canAutoRetry": False,
                "canResend": False,
                "peerQueryPerformed": False,
                "transportCalled": False,
                "financialEventCreated": False,
            }


__all__ = ["MtrE2RecoveryPolicyPilot", "RecoveryPolicyBlocked"]
