"""Strict proposed Taraz finance-journal witness verifier. NO official issuer.

The current Taraz source has no production finance-witness issuer, distinct
production finance trust anchor, authenticated journal-signing privilege or
Madar-side durable receipt-ingest authority. All results therefore retain
officialFinanceReceiptVerified=False. Even a valid synthetic HMAC only proves
that the holder of an *operator-provisioned finance-direction key* signed the
given claim; caller-supplied journal bytes cannot prove live Taraz posting.

This source has no external network calls, finance writes, automatic dispatch,
receipt promotion, or signing API. Registration/consumption writes only an
explicit, isolated SQLite challenge journal, never HostRequestStore.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
from threading import RLock

from mtr_peer_envelope import (
    canonical_json, verify_receipt_query, verify_request,
)


_DOMAIN = b"MTR-Taraz-finance-journal-witness-v1\x00"
_HEX32 = re.compile(r"[a-f0-9]{32}\Z", re.ASCII)
_SHA = re.compile(r"[a-f0-9]{64}\Z", re.ASCII)
_IDENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z", re.ASCII)
_ACCT_IDENT = re.compile(r"[A-Za-z0-9._-]{1,100}\Z", re.ASCII)
_ACTOR = re.compile(r"mtr-actor-v1-[a-f0-9]{64}\Z", re.ASCII)
_STAMP = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ\Z", re.ASCII)
_MAX_WIRE = 16384
_MAX_EVENT = 16384
_MAX_SOURCE = 32768
_MAX_CHALLENGES = 10000
_WITNESS_FIELDS = frozenset({
    "protocol", "version", "algorithm", "purpose", "audience",
    "organizationId", "issuerId", "keyId", "requestId", "originalWireSha256",
    "originalPayloadSha256", "queryRequestId", "queryWireSha256",
    "sourceDigest", "taskId", "projectId", "madarActorId",
    "companyId", "invoiceId", "issueEventId", "journalId",
    "currency", "amountRial", "ledgerRevision", "ledgerStateSha256",
    "journalEventSha256", "accountingEventSha256",
    "journalEventType", "journalStatus", "issuedUtc", "expiresUtc",
})
_ORIGINAL_FIELDS = frozenset({
    "id", "taskId", "projectId", "sourceDigest", "companyId",
    "actorId", "invoiceId", "issueEventId", "journalId",
})
_SOURCE_FIELDS = frozenset({
    "schema", "source", "id", "taskId", "projectId", "title",
    "createdUtc", "expenseId", "amountRial",
})


class FinanceWitnessRejected(PermissionError):
    """Untrusted signature, stale proof, malformed journal or replay."""


def _deny(message: str):
    raise FinanceWitnessRejected(message)


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _type_string(value, pattern, label):
    if type(value) is not str or pattern.fullmatch(value) is None:
        _deny("invalid " + label)
    return value


def _now(stamp: datetime | None):
    actual = datetime.now(timezone.utc)
    if stamp is None:
        return actual.replace(microsecond=0)
    if (type(stamp) is not datetime or stamp.tzinfo is None
            or stamp.utcoffset() is None or stamp.microsecond):
        _deny("explicit UTC second-precision time required")
    requested = stamp.astimezone(timezone.utc)
    if abs((requested - actual).total_seconds()) > 5:
        _deny("provided UTC clock differs from trusted current time")
    return requested


def _timestamp(value):
    _type_string(value, _STAMP, "UTC timestamp")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
    except ValueError as exc:
        raise FinanceWitnessRejected("invalid UTC calendar date") from exc


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _deny("duplicate JSON field")
        result[key] = value
    return result


def _invalid_constant(_):
    _deny("nonfinite JSON field")


def _json(raw: bytes, max_bytes: int, *, canonical: bool):
    if type(raw) is not bytes or not 1 <= len(raw) <= max_bytes:
        _deny("missing/oversized witness evidence")
    try:
        parsed = json.loads(raw.decode("utf8"), object_pairs_hook=_unique,
                            parse_constant=_invalid_constant)
        canonical_bytes = canonical_json(parsed)
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise FinanceWitnessRejected("invalid bounded JSON evidence") from exc
    if type(parsed) is not dict or (canonical and raw != canonical_bytes):
        _deny("noncanonical witness/event JSON")
    return parsed


def _amount(value):
    if (type(value) is not str or not 1 <= len(value) <= 16
            or not value.isascii() or not value.isdecimal()
            or (len(value) > 1 and value[0] == "0")
            or not 0 < int(value) <= 9007199254740991):
        _deny("positive canonical RIAL amount required")
    return int(value)


@dataclass(frozen=True, slots=True, repr=False)
class FinanceWitnessTrust:
    """Independent, private, operator-provisioned directional keys.

    This configuration is not a production issuer certificate. No default
    secrets, automatic discovery, public-API booleans or local username
    fallback can create it.
    """
    organization_id: str
    madar_sender_id: str
    madar_key_id: str
    madar_secret: bytes
    taraz_finance_issuer_id: str
    taraz_finance_key_id: str
    taraz_finance_secret: bytes

    def __post_init__(self):
        for label, value in (
                ("org", self.organization_id),
                ("Madar sender", self.madar_sender_id),
                ("Madar key ID", self.madar_key_id),
                ("Taraz finance issuer", self.taraz_finance_issuer_id),
                ("Taraz finance key ID", self.taraz_finance_key_id)):
            _type_string(value, _IDENT, label)
        for field in (self.madar_secret, self.taraz_finance_secret):
            if type(field) is not bytes or not 32 <= len(field) <= 4096:
                _deny("operator-provisioned directional keys must be 32+ bytes")
        if hmac.compare_digest(self.madar_secret, self.taraz_finance_secret):
            _deny("Taraz finance issuer key must differ from Madar HMAC key")

    def __repr__(self):
        return "<FinanceWitnessTrust keys redacted>"

    def __reduce__(self):
        raise TypeError("finance witness keys may not be serialized")


@dataclass(frozen=True, slots=True)
class FinanceWitnessAssessment:
    """Bounded forensic result. Never convertible to an official receipt."""
    decision: str
    originalRequestId: str | None = None
    queryRequestId: str | None = None
    companyId: str | None = None
    journalId: str | None = None
    ledgerRevisionClaimed: int | None = None
    signedFinanceWitnessCryptographyVerified: bool = False
    signedJournalEventBound: bool = False
    oneTimeDurableChallengeConsumed: bool = False
    realTarazIssuerAuthenticated: bool = False
    independentLiveLedgerReadbackVerified: bool = False
    officialFinanceReceiptVerified: bool = False
    financialEventCreatedByVerifier: bool = False
    safeToRetryFinancialPosting: bool = False


def _bindings(original_wire: bytes, query_wire: bytes, source_raw: bytes,
              config: FinanceWitnessTrust, now: datetime):
    original = verify_request(
        original_wire, secret=config.madar_secret, now=now,
        expected_organization_id=config.organization_id,
        expected_sender_id=config.madar_sender_id,
        expected_key_id=config.madar_key_id,
        purpose="finance_review_request",
        allowed_actor_roles=frozenset({"admin", "editor"}))
    query = verify_receipt_query(
        query_wire, secret=config.madar_secret, now=now,
        expected_organization_id=config.organization_id,
        expected_sender_id=config.madar_sender_id,
        expected_key_id=config.madar_key_id,
        allowed_actor_roles=frozenset({"admin", "editor"}))
    payload = original.payload
    if type(payload) is not dict or set(payload) != _ORIGINAL_FIELDS:
        _deny("signed original is not finance-binding-v1")
    if (query.organization_id != original.organization_id
            or query.actor_role != original.actor_role
            or query.sender_id != original.sender_id
            or query.payload != {
                "originalRequestId": original.request_id,
                "originalPayloadSha256": original.payload_sha256,
                "originalPurpose": "finance_review_request",
            }
            or query.request_id == original.request_id):
        _deny("challenge and original differ")
    source = _json(source_raw, _MAX_SOURCE, canonical=False)
    # The actual Madar bridge writes insertion-order, not canonical sorted JSON.
    # Hash the exact bytes as they were exported, never their canonical form.
    if (set(source) != _SOURCE_FIELDS
            or type(payload.get("sourceDigest")) is not str
            or not _SHA.fullmatch(payload["sourceDigest"])
            or source.get("schema") != 1 or type(source.get("schema")) is not int
            or source.get("source") != "madar"
            or source.get("id") != original.request_id
            or source.get("taskId") != payload["taskId"]
            or source.get("projectId") != payload["projectId"]
            or "amountRial" not in source or not
            hmac.compare_digest(payload["sourceDigest"], _hash(source_raw))):
        _deny("Madar proposal bytes/source identity mismatch")
    amount = _amount(source["amountRial"])
    if (type(source["title"]) is not str or not source["title"].strip()
            or len(source["title"]) > 300
            or type(source["expenseId"]) is not str
            or not 1 <= len(source["expenseId"]) <= 180
            or type(source["createdUtc"]) is not str
            or not 1 <= len(source["createdUtc"]) <= 50):
        _deny("invalid exact Madar expense/metadata fields")
    try:
        created = datetime.fromisoformat(source["createdUtc"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise FinanceWitnessRejected("invalid Madar source date") from exc
    if created.tzinfo is None or created.utcoffset() != timedelta(0):
        _deny("Madar source must be UTC")
    _type_string(payload["actorId"], _ACTOR, "immutable Madar actor")
    _type_string(payload["companyId"], _HEX32, "company ID")
    _type_string(payload["invoiceId"], _ACCT_IDENT, "invoice ID")
    _type_string(payload["issueEventId"], _ACCT_IDENT, "journal event ID")
    if (type(payload["journalId"]) is not str
            or payload["journalId"] != "J:" + payload["issueEventId"]):
        _deny("signed invoice event/journal identity mismatch")
    for field in ("taskId", "projectId"):
        if type(payload[field]) is not str or not 1 <= len(payload[field]) <= 180:
            _deny("invalid signed task/project identity")
    return original, query, payload, amount


def _validate_journal(journal_raw: bytes, event_raw: bytes, payload: dict, amount: int):
    journal = _json(journal_raw, _MAX_EVENT, canonical=True)
    event = _json(event_raw, _MAX_EVENT, canonical=True)
    if (set(journal) != {
            "id", "eventId", "sourceType", "sourceId", "date",
            "lines", "reversalOf",
        } or journal["id"] != payload["journalId"]
            or journal["eventId"] != payload["issueEventId"]
            or journal["sourceType"] != "invoice.issue"
            or journal["sourceId"] != payload["invoiceId"]
            or journal["reversalOf"] is not None):
        _deny("journal is not an unreversed invoice.issue witness")
    if (type(journal["date"]) is not str or
            not re.fullmatch(r"\d{4}-\d\d-\d\d", journal["date"])):
        _deny("invalid journal date")
    rows = journal["lines"]
    if type(rows) is not list or not 2 <= len(rows) <= 128:
        _deny("invalid journal row count")
    debit = credit = 0
    for row in rows:
        if (type(row) is not dict
                or not {"accountId", "debit", "credit"} <= set(row)
                or set(row) - {"accountId", "debit", "credit", "partyId"}
                or type(row["accountId"]) is not str
                or type(row["debit"]) is not int
                or type(row["credit"]) is not int
                or (row["debit"] > 0) == (row["credit"] > 0)
                or min(row["debit"], row["credit"]) < 0
                or max(row["debit"], row["credit"]) > 9007199254740991):
            _deny("invalid journal debit/credit line")
        debit += row["debit"]
        credit += row["credit"]
    if debit != credit or debit < amount:
        _deny("unbalanced or underfunded journal")
    if (not {"eventId", "command", "result", "actor"} <= set(event)
            or event["eventId"] != payload["issueEventId"]
            or type(event["actor"]) is not str or not 1 <= len(event["actor"]) <= 100
            or type(event["command"]) is not dict
            or event["command"].get("type") != "invoice.issue"
            or event["command"].get("invoiceId") != payload["invoiceId"]
            or event["command"].get("eventId") != payload["issueEventId"]
            or event["command"].get("postingDate") != journal["date"]
            or type(event["result"]) is not dict
            or event["result"].get("documentId") != payload["invoiceId"]
            or event["result"].get("journalId") != payload["journalId"]
            or type(event["result"].get("total")) is not int
            or event["result"]["total"] != amount):
        _deny("invoice.issue immutable event mismatch")


def _safe_database_path(path: Path):
    if (not isinstance(path, Path) or not path.is_absolute()
            or path.name != "mtr-taraz-finance-witness-queries.sqlite3"):
        _deny("explicit independent private challenge database path required")
    for ancestor in (path.parent, *path.parent.parents):
        try:
            info = ancestor.lstat()
        except (OSError, ValueError) as exc:
            raise FinanceWitnessRejected("missing challenge database parent") from exc
        if (not stat.S_ISDIR(info.st_mode)
                or ancestor.is_symlink()
                or getattr(ancestor, "is_junction", lambda: False)()
                or (getattr(info, "st_file_attributes", 0) &
                    getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))):
            _deny("linked/reparse challenge directory forbidden")
    if os.path.lexists(path):
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or path.is_symlink() or info.st_size > 8 * 1024 * 1024
                or (getattr(info, "st_file_attributes", 0) &
                    getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))):
            _deny("unsafe challenge database")
    return path


class DurableFinanceWitnessChallenges:
    """Single-use, restart-persistent synthetic challenge registry.

    This is independent of the existing HostRequestStore; that store has no
    finance-witness challenge/issuer transaction and cannot promote receipts.
    """

    def __init__(self, path: Path):
        self.path = _safe_database_path(path)
        self._lock = RLock()
        newly_created = not self.path.exists()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                if newly_created:
                    db.execute(
                        "CREATE TABLE challenges ("
                        "query_id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL,"
                        "binding_sha TEXT NOT NULL, original_sha TEXT NOT NULL,"
                        "query_sha TEXT NOT NULL, expires_utc TEXT NOT NULL,"
                        "state TEXT NOT NULL CHECK(state IN ('issued','consumed')),"
                        "witness_sha TEXT)"
                    )
                    db.execute(
                        "CREATE TRIGGER challenges_no_delete "
                        "BEFORE DELETE ON challenges "
                        "BEGIN SELECT RAISE(ABORT,'immutable'); END"
                    )
                    db.execute(
                        "CREATE TRIGGER challenges_immutable "
                        "BEFORE UPDATE ON challenges "
                        "WHEN NEW.query_id!=OLD.query_id OR "
                        "NEW.request_id!=OLD.request_id OR "
                        "NEW.binding_sha!=OLD.binding_sha OR "
                        "NEW.original_sha!=OLD.original_sha OR "
                        "NEW.query_sha!=OLD.query_sha OR "
                        "NEW.expires_utc!=OLD.expires_utc "
                        "BEGIN SELECT RAISE(ABORT,'immutable'); END"
                    )
                    db.execute("PRAGMA user_version=1")
                if db.execute("PRAGMA user_version").fetchone()[0] != 1:
                    _deny("unsupported challenge registry schema")
                objects = {
                    row[0]: row[1] for row in db.execute(
                        "SELECT name,type FROM sqlite_master WHERE name IN "
                        "('challenges','challenges_no_delete',"
                        "'challenges_immutable')"
                    )
                }
                if objects != {
                        "challenges": "table",
                        "challenges_no_delete": "trigger",
                        "challenges_immutable": "trigger"}:
                    _deny("challenge registry schema/triggers missing")
                if db.execute("PRAGMA quick_check(1)").fetchone()[0] != "ok":
                    _deny("corrupt challenge registry")
                db.execute("COMMIT")
            except Exception:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise

    def _connect(self):
        from contextlib import contextmanager

        @contextmanager
        def connection():
            _safe_database_path(self.path)
            db = sqlite3.connect(self.path, timeout=8, isolation_level=None)
            try:
                db.execute("PRAGMA journal_mode=DELETE")
                db.execute("PRAGMA synchronous=FULL")
                db.execute("PRAGMA busy_timeout=8000")
                yield db
            finally:
                db.close()
        return connection()

    @staticmethod
    def _binding(original, query, payload: dict, amount: int):
        return _hash(canonical_json({
            "org": original.organization_id,
            "originalId": original.request_id,
            "originalPayloadSha": original.payload_sha256,
            "queryId": query.request_id,
            "querySha": query.envelope_sha256,
            "companyId": payload["companyId"],
            "taskId": payload["taskId"],
            "projectId": payload["projectId"],
            "actorId": payload["actorId"],
            "invoiceId": payload["invoiceId"],
            "journalId": payload["journalId"],
            "issueEventId": payload["issueEventId"],
            "sourceDigest": payload["sourceDigest"],
            "amountRial": str(amount),
        }))

    def register_manual(self, *, original_wire: bytes, query_wire: bytes,
                        source_raw: bytes, config: FinanceWitnessTrust,
                        explicit_manual_action: bool, now: datetime | None = None):
        if explicit_manual_action is not True:
            _deny("explicit host manual witness-challenge authorization required")
        if type(config) is not FinanceWitnessTrust:
            _deny("trusted configured host sender required")
        timestamp = _now(now)
        original, query, payload, amount = _bindings(
            original_wire, query_wire, source_raw, config, timestamp)
        binding_sha = self._binding(original, query, payload, amount)
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                count = db.execute("SELECT COUNT(*) FROM challenges").fetchone()[0]
                if count >= _MAX_CHALLENGES:
                    _deny("challenge registry full; no automatic pruning or ID reuse")
                db.execute(
                    "INSERT INTO challenges "
                    "(query_id,request_id,binding_sha,original_sha,query_sha,"
                    "expires_utc,state,witness_sha) VALUES (?,?,?,?,?,?,'issued',NULL)",
                    (query.request_id, original.request_id, binding_sha,
                     _hash(original_wire), _hash(query_wire),
                     _json(query_wire, _MAX_WIRE, canonical=True)["expiresUtc"]),
                )
                db.execute("COMMIT")
            except sqlite3.IntegrityError as exc:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise FinanceWitnessRejected("challenge request/query replay") from exc
            except Exception:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise
        return {
            "registered": True, "requestId": original.request_id,
            "challengeId": query.request_id,
            "officialFinanceReceiptVerified": False,
            "safeToRetryFinancialPosting": False,
        }

    def consume(self, *, original, query, payload, amount,
                original_wire: bytes, query_wire: bytes, witness_raw: bytes,
                now: datetime):
        expected = self._binding(original, query, payload, amount)
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                rows = db.execute(
                    "SELECT request_id,binding_sha,original_sha,query_sha,"
                    "expires_utc,state FROM challenges WHERE query_id=?",
                    (query.request_id,),
                ).fetchall()
                if (len(rows) != 1
                        or tuple(rows[0][:4]) != (
                            original.request_id, expected, _hash(original_wire),
                            _hash(query_wire))
                        or rows[0][5] != "issued"
                        or now >= _timestamp(rows[0][4])):
                    _deny("unissued, expired or already-consumed challenge")
                changed = db.execute(
                    "UPDATE challenges SET state='consumed',witness_sha=? "
                    "WHERE query_id=? AND state='issued'",
                    (_hash(witness_raw), query.request_id),
                ).rowcount
                if changed != 1:
                    _deny("challenge concurrent replay")
                db.execute("COMMIT")
            except Exception:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise


class TarazFinanceWitnessVerifier:
    """Verify proposed signed witness, but NEVER grant official receipt status."""
    def __init__(self, *, config: FinanceWitnessTrust | None,
                 challenges: DurableFinanceWitnessChallenges | None):
        if config is not None and type(config) is not FinanceWitnessTrust:
            _deny("private operator-provisioned finance trust required")
        if challenges is not None and type(challenges) is not DurableFinanceWitnessChallenges:
            _deny("durable challenge registry required")
        self._config = config
        self._challenges = challenges

    def inspect_and_consume(
            self, *, signed_witness: bytes, original_wire: bytes,
            query_wire: bytes, source_raw: bytes, journal_raw: bytes,
            accounting_event_raw: bytes, ledger_revision: int,
            ledger_state_sha256: str, now: datetime | None = None
    ) -> FinanceWitnessAssessment:
        if self._config is None:
            return FinanceWitnessAssessment("BLOCKED_NO_OPERATOR_FINANCE_TRUST")
        if self._challenges is None:
            return FinanceWitnessAssessment("BLOCKED_NO_DURABLE_CHALLENGE")
        timestamp = _now(now)
        config = self._config
        original, query, payload, amount = _bindings(
            original_wire, query_wire, source_raw, config, timestamp)
        _validate_journal(journal_raw, accounting_event_raw, payload, amount)
        if (type(ledger_revision) is not int
                or not 1 <= ledger_revision <= 9007199254740991):
            _deny("trusted positive ledger revision required")
        _type_string(ledger_state_sha256, _SHA, "ledger state digest")
        signed = _json(signed_witness, _MAX_WIRE, canonical=True)
        if set(signed) != _WITNESS_FIELDS | {"mac"}:
            _deny("missing/unrecognized witness field")
        expected = {
            "protocol": "mtr-taraz-journal-witness",
            "version": 1,
            "algorithm": "HMAC-SHA256",
            "purpose": "invoice-issue-readback",
            "audience": "madar.finance",
            "organizationId": config.organization_id,
            "issuerId": config.taraz_finance_issuer_id,
            "keyId": config.taraz_finance_key_id,
            "requestId": original.request_id,
            "originalWireSha256": _hash(original_wire),
            "originalPayloadSha256": original.payload_sha256,
            "queryRequestId": query.request_id,
            "queryWireSha256": _hash(query_wire),
            "sourceDigest": payload["sourceDigest"],
            "taskId": payload["taskId"],
            "projectId": payload["projectId"],
            "madarActorId": payload["actorId"],
            "companyId": payload["companyId"],
            "invoiceId": payload["invoiceId"],
            "issueEventId": payload["issueEventId"],
            "journalId": payload["journalId"],
            "currency": "RIAL",
            "amountRial": str(amount),
            "ledgerRevision": ledger_revision,
            "ledgerStateSha256": ledger_state_sha256,
            "journalEventSha256": _hash(journal_raw),
            "accountingEventSha256": _hash(accounting_event_raw),
            "journalEventType": "invoice.issue",
            "journalStatus": "posted",
        }
        if (type(signed["version"]) is not int
                or type(signed["ledgerRevision"]) is not int):
            _deny("invalid witness integer schema")
        for field, value in expected.items():
            if signed.get(field) != value:
                _deny("witness ledger/origin/company/journal field mismatch: " + field)
        issued, expires = _timestamp(signed["issuedUtc"]), _timestamp(signed["expiresUtc"])
        query_envelope = _json(query_wire, _MAX_WIRE, canonical=True)
        query_issued = _timestamp(query_envelope["issuedUtc"])
        query_expiry = _timestamp(query_envelope["expiresUtc"])
        if (expires <= issued or expires - issued > timedelta(seconds=120)
                or issued < query_issued
                or issued > timestamp + timedelta(seconds=30)
                or timestamp >= expires or expires > query_expiry):
            _deny("expired/future or unbounded finance witness")
        supplied_mac = _type_string(signed["mac"], _SHA, "witness signature")
        actual_mac = hmac.new(
            config.taraz_finance_secret,
            _DOMAIN + canonical_json({key: signed[key] for key in _WITNESS_FIELDS}),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(bytes.fromhex(supplied_mac),
                                   bytes.fromhex(actual_mac)):
            _deny("invalid Taraz finance-direction witness signature")
        self._challenges.consume(
            original=original, query=query, payload=payload, amount=amount,
            original_wire=original_wire, query_wire=query_wire,
            witness_raw=signed_witness, now=timestamp)
        # No real Taraz issuing authority or independent ledger readback has
        # been wired. Even well-formed synthetic proof MUST remain nonofficial.
        return FinanceWitnessAssessment(
            "SIGNED_WITNESS_STRUCTURALLY_VERIFIED_OFFICIAL_ISSUER_UNAVAILABLE",
            originalRequestId=original.request_id,
            queryRequestId=query.request_id,
            companyId=payload["companyId"],
            journalId=payload["journalId"],
            ledgerRevisionClaimed=ledger_revision,
            signedFinanceWitnessCryptographyVerified=True,
            signedJournalEventBound=True,
            oneTimeDurableChallengeConsumed=True,
            realTarazIssuerAuthenticated=False,
            independentLiveLedgerReadbackVerified=False,
            officialFinanceReceiptVerified=False,
            financialEventCreatedByVerifier=False,
            safeToRetryFinancialPosting=False,
        )


__all__ = [
    "FinanceWitnessTrust", "FinanceWitnessRejected",
    "DurableFinanceWitnessChallenges", "FinanceWitnessAssessment",
    "TarazFinanceWitnessVerifier",
]
