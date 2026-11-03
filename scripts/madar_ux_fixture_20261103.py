"""Deterministic in-memory UX fixture. Never creates or opens a real ledger."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from accounting_core import (
    accounting_view,
    apply_accounting_command,
    empty_rial_accounting_state,
)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    state = empty_rial_accounting_state()
    users = [{"username": "uxqa", "role": "admin", "financeEdit": True, "financeView": True}]
    now = "2026-11-03T09:00:00Z"
    commands = [
        {"type": "party.register", "partyId": "CUSTOMER-UX", "name": "مشتری آزمایشی", "kind": "customer"},
        {"type": "party.register", "partyId": "VENDOR-UX", "name": "تأمین‌کننده آزمایشی", "kind": "vendor"},
        {"type": "invoice.create", "invoiceId": "UX-ISSUED-001", "partyId": "CUSTOMER-UX",
         "documentDate": "2026-11-01", "lines": [{"description": "سرویس نمونه", "quantity": 1, "unitPrice": 300000}]},
        {"type": "invoice.approve", "invoiceId": "UX-ISSUED-001"},
        {"type": "invoice.issue", "invoiceId": "UX-ISSUED-001", "postingDate": "2026-11-02"},
        {"type": "invoice.create", "invoiceId": "UX-DRAFT-002", "partyId": "CUSTOMER-UX",
         "documentDate": "2026-11-02", "lines": [{"description": "در انتظار تأیید", "quantity": 1, "unitPrice": 90000}]},
    ]
    for index, command in enumerate(commands, 1):
        result = apply_accounting_command(
            state, {**command, "eventId": f"UXQA-EVENT-{index}"},
            actor="uxqa", accounts=users, now=now)
        state = result["state"]
    payload = {
        "revision": len(commands),
        "view": accounting_view(state, actor="uxqa", accounts=users),
        "capabilities": {"canManage": True, "canDraft": True, "canAdmin": True},
        "currentUser": {"username": "uxqa", "role": "admin", "jobTitle": "آزمون رابط"},
    }
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
