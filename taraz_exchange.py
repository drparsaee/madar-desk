"""User-controlled, one-way task proposals for the separate Taraz application.

Only the selected task and optional existing expense identifier are shared.
No accounting database is opened, modified or posted by this module.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
import threading
import uuid

_REQUEST_ID = re.compile(r"[0-9a-f]{32}\Z")
_MAX_RECORD_BYTES = 32768
_LOCAL_SEND_LOCK = threading.RLock()


def _pending_dir():
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        raise RuntimeError("پوشه محلی کاربر برای تبادل با تراز در دسترس نیست.")
    return Path(local) / "Madar-Taraz-Bridge" / "pending"


def integration_status():
    try:
        folder = _pending_dir()
        pending = sum(1 for candidate in folder.glob("*.json") if candidate.is_file()) if folder.is_dir() else 0
        return {
            "supported": True,
            "mode": "file-proposals",
            "pending": pending,
            "postingEnabled": False,
            "message": "پیشنهادها در صندوق تبادل محلی ذخیره می‌شوند. بازبینی و ثبت فقط در برنامه مستقل تراز انجام می‌شود.",
        }
    except (OSError, RuntimeError) as error:
        return {"supported": False, "mode": "unavailable", "pending": 0,
                "postingEnabled": False, "message": str(error)}


def _valid_identifier(value, name):
    if (not isinstance(value, str) or not 1 <= len(value) <= 180 or
            not value.strip() or any(ord(c) < 32 for c in value)):
        raise ValueError(f"شناسه {name} معتبر نیست.")
    return value


def _find_selected_expense(task, expense_id):
    if expense_id is None:
        return None
    _valid_identifier(expense_id, "هزینه")
    items = []
    for step in task.get("checklist", []):
        if isinstance(step, dict):
            items.extend(step.get("expenseItems", []))
    for group in task.get("checklists", []):
        if isinstance(group, dict):
            for step in group.get("items", []):
                if isinstance(step, dict):
                    items.extend(step.get("expenseItems", []))
    found = [item for item in items if isinstance(item, dict) and item.get("id") == expense_id]
    if len(found) != 1:
        raise ValueError("هزینه انتخاب‌شده در کارت ذخیره‌شده پیدا نشد یا یکتا نیست.")
    return found[0]


def _rial_amount(expense):
    if expense is None or expense.get("currency") != "RIAL":
        return None
    quantity, price = expense.get("quantity"), expense.get("unitPrice")
    if (type(quantity) is not int or type(price) is not int or
            quantity <= 0 or price <= 0 or quantity > 1_000_000 or
            price > 1_000_000_000_000_000 or
            quantity * price > 9_000_000_000_000_000):
        return None
    return str(quantity * price)


def _assert_safe_path(path):
    if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
        raise PermissionError("مسیر صندوق تبادل امن نیست.")
    if path.exists() and (getattr(path.lstat(), "st_file_attributes", 0) &
                          getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        raise PermissionError("مسیر صندوق تبادل بازپارس‌شونده مجاز نیست.")


def _saved_proposal(path):
    _assert_safe_path(path)
    if not path.is_file() or path.stat().st_size > _MAX_RECORD_BYTES:
        raise ValueError("درخواست قبلی ناقص یا بیش از حد بزرگ است.")
    with path.open("rb") as source:
        raw = source.read(_MAX_RECORD_BYTES + 1)
    if len(raw) > _MAX_RECORD_BYTES:
        raise ValueError("درخواست قبلی بیش از حد بزرگ است.")
    def unique(items):
        data = {}
        for name, value in items:
            if name in data:
                raise ValueError("کلید تکراری در درخواست قبلی.")
            data[name] = value
        return data
    record = json.loads(raw.decode("utf8"), object_pairs_hook=unique)
    if (type(record) is not dict or
            type(record.get("createdUtc")) is not str or
            not 1 <= len(record["createdUtc"]) <= 50 or
            "T" not in record["createdUtc"]):
        raise ValueError("درخواست قبلی معتبر نیست.")
    return record


@contextmanager
def _request_lock(directory, identifier):
    """Cooperate with Taraz's per-ID OS lock across local Windows processes.

    The lock file is deliberately retained so a second process never locks a
    different inode for the same request ID during concurrent replay/review.
    """
    _assert_safe_path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    _assert_safe_path(directory)
    lock_path = directory / (identifier + ".lock")
    _assert_safe_path(lock_path)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(lock_path, flags, 0o600)
    locked = False
    try:
        info = os.fstat(fd)
        current = lock_path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
                _assert_unsafe_lock(lock_path, info, current) or info.st_size > 1):
            raise PermissionError("فایل قفل تبادل معتبر نیست.")
        if info.st_size == 0:
            os.write(fd, b"\0")
            os.fsync(fd)
        if os.name == "nt":
            import msvcrt
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX)
        locked = True
        _assert_safe_path(directory)
        current = lock_path.lstat()
        if (_assert_unsafe_lock(lock_path, info, current)):
            raise PermissionError("فایل قفل حین ارسال جایگزین شد.")
        yield
    finally:
        if locked:
            if os.name == "nt":
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _assert_unsafe_lock(path, opened, current):
    _assert_safe_path(path)
    return (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)


def _publish_proposal(proposal, folder, reviewed, explicit_retry, *, old_lock=False):
    identifier = proposal["id"]
    # Critical section is held by caller when explicit_retry is True.
    for location in (folder.parent, folder, reviewed):
        _assert_safe_path(location)
    if folder.exists() and not folder.is_dir():
        raise PermissionError("پوشه ارسال معتبر نیست.")
    if reviewed.exists() and not reviewed.is_dir():
        raise PermissionError("پوشه بررسی معتبر نیست.")
    if explicit_retry:
        observations = [("pending", folder / (identifier + ".json")),
                        ("reviewed", reviewed / (identifier + ".json"))]
        existing = [(place, path) for place, path in observations
                    if path.exists() or path.is_symlink()]
        marker_files = [reviewed / (identifier + suffix)
                        for suffix in (".review.json", ".intent.json")]
        if len(existing) > 1 or (not existing and any(
                p.exists() or p.is_symlink() for p in marker_files)):
            raise RuntimeError("وضعیت درخواست قبلی متعارض یا نامشخص است؛ ارسال جدید ممنوع.")
        if existing:
            place, path = existing[0]
            record = _saved_proposal(path)
            if (record.get("id") != identifier or
                    {k: v for k, v in record.items() if k != "createdUtc"} !=
                    {k: v for k, v in proposal.items() if k != "createdUtc"} or
                    set(record) != set(proposal)):
                raise ValueError("شناسه درخواست برای داده متفاوت استفاده شده است.")
            return {"queued": False, "id": identifier, "replayed": True,
                    "observedLocation": place, "postingPerformed": False}
        if old_lock:
            # Another send/review once reserved this ID but its file is now
            # absent. Without authenticated query, absence is NOT a negative
            # receipt and must not authorize a fresh publication.
            raise RuntimeError("ردپای درخواست قبلی وجود دارد ولی نتیجه نامعلوم است؛ ارسال متوقف شد.")
    folder.mkdir(parents=True, exist_ok=True)
    temp = folder / (uuid.uuid4().hex + ".tmp")
    target = folder / (identifier + ".json")
    try:
        with temp.open("x", encoding="utf8", newline="\n") as stream:
            json.dump(proposal, stream, ensure_ascii=False, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temp, target)  # exclusive publish; never overwrite same ID
    except FileExistsError as exc:
        raise RuntimeError("شناسه درخواست هم‌زمان یا تکراری است؛ وضعیت را استعلام کنید.") from exc
    finally:
        temp.unlink(missing_ok=True)
    return {"queued": True, "id": identifier, "replayed": False,
            "postingPerformed": False}


def _build_proposal(state, task_id, expense_id, identifier):
    """Validate the saved task and build exactly the metadata sent to Taraz.

    Kept separate so the pre-send local intent journal hashes the same schema
    that the transport publishes, without sending or writing during preflight.
    """
    _valid_identifier(task_id, "کارت")
    if not isinstance(state, dict) or not isinstance(state.get("tasks"), list):
        raise ValueError("اطلاعات ذخیره‌شده مدار معتبر نیست.")
    matches = [task for task in state["tasks"]
               if isinstance(task, dict) and task.get("id") == task_id]
    if len(matches) != 1 or matches[0].get("deleted") is True:
        raise ValueError("کارت انتخاب‌شده در اطلاعات ذخیره‌شده وجود ندارد.")
    task = matches[0]
    title = task.get("title")
    project_id = task.get("projectId")
    if not isinstance(title, str) or not title.strip() or len(title) > 300:
        raise ValueError("عنوان کارت ذخیره‌شده معتبر نیست.")
    _valid_identifier(project_id, "پروژه")
    expense = _find_selected_expense(task, expense_id)
    proposal = {
        "schema": 1, "source": "madar", "id": identifier,
        "taskId": task_id, "title": title.strip(), "projectId": project_id,
        "createdUtc": datetime.now(timezone.utc).isoformat(),
    }
    if expense is not None:
        proposal["expenseId"] = expense_id
        amount = _rial_amount(expense)
        if amount is not None:
            proposal["amountRial"] = amount
    return proposal


def queue_saved_task(state, task_id, expense_id=None, *, request_id=None):
    """Explicit retry ID can replay exactly the *same* manual metadata send.

    A missing request_id means a new manually requested proposal, as in v1.
    This is not an authenticated peer acknowledgement or financial operation.
    """
    if request_id is not None and (
        type(request_id) is not str or not _REQUEST_ID.fullmatch(request_id)
    ):
        raise ValueError("شناسه ثابت درخواست برای ارسال مجدد معتبر نیست.")
    identifier = request_id if request_id is not None else uuid.uuid4().hex
    proposal = _build_proposal(state, task_id, expense_id, identifier)
    folder = _pending_dir()
    root = folder.parent
    reviewed = root / "reviewed"
    for location in (root, folder, reviewed):
        _assert_safe_path(location)
    if root.exists() and not root.is_dir():
        raise PermissionError("صندوق تبادل یک پوشه نیست.")
    if folder.exists() and not folder.is_dir():
        raise PermissionError("پوشه ارسال معتبر نیست.")
    if reviewed.exists() and not reviewed.is_dir():
        raise PermissionError("پوشه بررسی معتبر نیست.")
    if request_id is not None:
        # Taraz's isolated reviewed process takes the same OS lock, thus
        # prevents a pending->reviewed move between our query and publication.
        # Win32 byte-range locks are per-process OS locks; serializing callers
        # inside this process avoids spurious resource-deadlock/timeout errors.
        # Taraz in another process still uses the same OS lock path.
        with _LOCAL_SEND_LOCK:
            old_lock = (reviewed / (identifier + ".lock")).exists()
            with _request_lock(reviewed, identifier):
                return _publish_proposal(proposal, folder, reviewed, True,
                                         old_lock=old_lock)
    return _publish_proposal(proposal, folder, reviewed, False)
