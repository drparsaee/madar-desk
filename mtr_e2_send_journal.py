"""Isolated, local E2 first-send intent journal for *metadata-only* proposals.

Preparing is not transmitting. On the explicit Send click, the native client
persists an idempotency key *before* its first attempt to publish a proposal.
If the reply disappears, repeating the manual click for the same unchanged
task uses the original key. No finance record, receipt, official party or
ledger is created.

Limitations: this file journal is device-local, not an authenticated Taraz
receipt or host-authoritative financial protocol. An existing journal is never
cleared or automatically replaced, even if the local reviewed folder claims
it was accepted. A genuinely new request must use a separate future
versioned workflow with a verified peer, rather than silently replacing this
authorization. The local user's access to LOCALAPPDATA is assumed.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import threading
import uuid

from taraz_exchange import _assert_safe_path, _build_proposal, _pending_dir


_ACTOR = re.compile(r"[A-Za-z0-9_.:@-]{1,128}\Z", re.ASCII)
_SHA = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_HEX = re.compile(r"[0-9a-f]{32}\Z", re.ASCII)
_MAX_ENTRY_BYTES = 4096
_SAME_PROCESS_MUTEX = threading.RLock()
_KEYS = frozenset((
    "schemaVersion", "requestId", "scopeDigest", "payloadSha256",
    "taskId", "projectId", "expenseId", "createdUtc"
))


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _hash(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _unique_pairs(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("کلید تکراری در سابقه ارسال.")
        result[name] = value
    return result


def _read_entry(path: Path):
    _assert_safe_path(path)
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or info.st_size > _MAX_ENTRY_BYTES or info.st_size == 0):
        raise PermissionError("سابقه درخواست معتبر یا امن نیست.")
    with path.open("rb") as reader:
        raw = reader.read(_MAX_ENTRY_BYTES + 1)
    if len(raw) > _MAX_ENTRY_BYTES:
        raise ValueError("سابقه درخواست بیش از حد بزرگ است.")
    item = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs)
    if (type(item) is not dict or frozenset(item) != _KEYS or
            type(item["schemaVersion"]) is not int or item["schemaVersion"] != 1 or
            type(item["requestId"]) is not str or not _HEX.fullmatch(item["requestId"]) or
            type(item["scopeDigest"]) is not str or not _SHA.fullmatch(item["scopeDigest"]) or
            type(item["payloadSha256"]) is not str or not _SHA.fullmatch(item["payloadSha256"]) or
            type(item["taskId"]) is not str or
            type(item["projectId"]) is not str or
            item["expenseId"] is not None and type(item["expenseId"]) is not str or
            type(item["createdUtc"]) is not str or "T" not in item["createdUtc"]):
        raise ValueError("ساختار سابقه درخواست نامعتبر است.")
    return item


def _request_snapshot(state, task_id, expense_id, actor_scope):
    if type(actor_scope) is not str or not _ACTOR.fullmatch(actor_scope):
        raise ValueError("دامنه حساب معتبر نیست.")
    provisional = _build_proposal(state, task_id, expense_id, "0" * 32)
    projection = {name: value for name, value in provisional.items()
                  if name not in ("id", "createdUtc")}
    scope = {"actor": actor_scope, "taskId": provisional["taskId"],
             "projectId": provisional["projectId"], "expenseId": expense_id}
    return provisional, _hash(scope), _hash(projection)


def assert_prepared_matches_if_present(state, task_id, expense_id, *,
                                       actor_scope, request_id):
    """Defend against saved-task mutation between prepare and queue.

    Older manual retries from history have no journal and retain their
    existing fail-closed source-file comparison. A journal for this actor and
    task must match exact request ID and payload; the caller may never switch
    the token or task contents after preparing it.
    """
    if type(request_id) is not str or not _HEX.fullmatch(request_id):
        raise ValueError("شناسه درخواست نامعتبر است.")
    provisional, scope_digest, payload_digest = _request_snapshot(
        state, task_id, expense_id, actor_scope
    )
    root = _pending_dir().parent
    folder = root / "send-intents"
    for directory in (root, folder):
        _assert_safe_path(directory)
        if directory.exists() and not directory.is_dir():
            raise PermissionError("پوشه درخواست ایمن نیست.")
    path = folder / (scope_digest + ".json")
    _assert_safe_path(path)
    if not path.exists():
        return {"hasPreparedIntent": False}
    prior = _read_entry(path)
    if (prior["scopeDigest"] != scope_digest or
            prior["taskId"] != provisional["taskId"] or
            prior["projectId"] != provisional["projectId"] or
            prior["expenseId"] != expense_id or
            prior["requestId"] != request_id or
            prior["payloadSha256"] != payload_digest):
        raise PermissionError("درخواست آماده‌شده با کارت یا شناسه فعلی مطابقت ندارد.")
    return {"hasPreparedIntent": True}


def prepare_manual_send(state, task_id: str, expense_id=None, *,
                        actor_scope: str):
    """Return an original stable request ID for the same saved task snapshot.

    No task change or unsaved state is accepted as an implicit retry. The
    caller must verify actor, role, project ACL and explicit UI action itself,
    and must never allow an untrusted client to choose actor_scope.
    """
    provisional, scope_digest, payload_digest = _request_snapshot(
        state, task_id, expense_id, actor_scope
    )
    root = _pending_dir().parent
    folder = root / "send-intents"
    with _SAME_PROCESS_MUTEX:
        for location in (root, folder):
            _assert_safe_path(location)
            if location.exists() and not location.is_dir():
                raise PermissionError("پوشه سابقه درخواست معتبر نیست.")
        folder.mkdir(parents=True, exist_ok=True)
        _assert_safe_path(folder)
        path = folder / (scope_digest + ".json")
        _assert_safe_path(path)
        if path.exists():
            entry = _read_entry(path)
            if (entry["scopeDigest"] != scope_digest or
                    entry["taskId"] != task_id or
                    entry["projectId"] != provisional["projectId"] or
                    entry["expenseId"] != expense_id):
                raise RuntimeError("سابقه درخواست با دامنه حساب مطابقت ندارد.")
            if entry["payloadSha256"] != payload_digest:
                raise ValueError("کارت پس از آماده‌سازی تغییر کرده؛ ارسال قبلی نباید با داده جدید تکرار شود.")
            return {"id": entry["requestId"], "prepared": True,
                    "reused": True, "postingPerformed": False}
        request_id = uuid.uuid4().hex
        entry = {"schemaVersion": 1, "requestId": request_id,
                 "scopeDigest": scope_digest, "payloadSha256": payload_digest,
                 "taskId": task_id, "projectId": provisional["projectId"],
                 "expenseId": expense_id, "createdUtc": provisional["createdUtc"]}
        body = _canonical(entry)
        if len(body) > _MAX_ENTRY_BYTES:
            raise ValueError("سابقه درخواست بیش از حد بزرگ است.")
        temp = folder / (uuid.uuid4().hex + ".tmp")
        try:
            with temp.open("xb") as writer:
                writer.write(body)
                writer.flush()
                os.fsync(writer.fileno())
            # Never replace existing intent with a new authorisation.
            os.link(temp, path)
        except FileExistsError:
            if not path.exists():
                raise RuntimeError("پایان نامشخص ثبت درخواست؛ ارسال جدید ممنوع.") from None
            saved = _read_entry(path)
            if saved["scopeDigest"] != scope_digest or saved["payloadSha256"] != payload_digest:
                raise RuntimeError("درخواست دیگری در همین دامنه ثبت شده است.")
            return {"id": saved["requestId"], "prepared": True,
                    "reused": True, "postingPerformed": False}
        finally:
            temp.unlink(missing_ok=True)
        return {"id": request_id, "prepared": True,
                "reused": False, "postingPerformed": False}
