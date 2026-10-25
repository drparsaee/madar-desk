"""Deterministic, idempotent due-date events for Madar's allowlisted rules."""
from __future__ import annotations

from datetime import date, datetime
import hashlib
import re

_DATE = re.compile(r"\d{4}-\d\d-\d\d\Z")


def due_events(cards, *, today, horizon_days=7):
    """Emit at most one due_soon event per card/due date/day.

    The caller must validate the card model and authenticate the host actor.
    Idempotency is enforced by the persisted collaboration receipts.
    """
    if isinstance(today, datetime):
        today = today.date()
    if not isinstance(today, date) or type(horizon_days) is not int or not 0 <= horizon_days <= 30:
        raise ValueError("Invalid scheduler date/window")
    if not isinstance(cards, list) or len(cards) > 100000:
        raise ValueError("Invalid scheduler cards")
    result = []
    seen = set()
    for card in cards:
        if not isinstance(card, dict) or not isinstance(card.get("id"), str) or card["id"] in seen:
            raise ValueError("Invalid or duplicate scheduler card")
        seen.add(card["id"])
        if card.get("archived") or card.get("status") == "done":
            continue
        value = card.get("dueDate")
        if not value:
            continue
        if not isinstance(value, str) or not _DATE.fullmatch(value):
            # Other date/time formats need explicit conversion, not guesswork.
            continue
        try:
            delta = (date.fromisoformat(value) - today).days
        except ValueError:
            continue
        if not 0 <= delta <= horizon_days:
            continue
        digest = hashlib.sha256(f"{card['id']}|{value}|{today.isoformat()}".encode("utf8")).hexdigest()[:28]
        result.append({"type": "event.publish", "eventId": "due-" + digest,
                       "cardId": card["id"], "trigger": "due_soon",
                       "data": {"dueWithinDays": delta}})
    return result
