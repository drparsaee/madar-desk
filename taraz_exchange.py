"""User-controlled, one-way task proposals for the separate Taraz application.

Only the selected task and optional existing expense identifier are shared.
No accounting database is opened, modified or posted by this module.
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import uuid


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


def queue_saved_task(state, task_id, expense_id=None):
    """Validate identifiers against persisted state, then atomically queue one proposal."""
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
    identifier = uuid.uuid4().hex
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
    folder = _pending_dir()
    folder.mkdir(parents=True, exist_ok=True)
    temp = folder / (identifier + ".tmp")
    target = folder / (identifier + ".json")
    try:
        with temp.open("x", encoding="utf8", newline="\n") as stream:
            json.dump(proposal, stream, ensure_ascii=False, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        # No user-controlled paths, and no financial database writes.
        if target.exists():
            raise FileExistsError("شناسه پیشنهاد تکراری است.")
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)
    return {"queued": True, "id": identifier, "postingPerformed": False}
