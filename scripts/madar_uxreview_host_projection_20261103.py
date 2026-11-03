"""In-memory real accounting_core projections; no SQL, APPDATA, BAK or files."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from accounting_core import (
    accounting_view, apply_accounting_command, empty_rial_accounting_state,
)

USERS = [
    {"username": "qa-admin", "role": "admin", "financeView": True, "financeEdit": True},
    {"username": "qa-viewer", "role": "viewer", "financeView": True, "financeEdit": False},
    {"username": "qa-revoked", "role": "viewer", "financeView": False, "financeEdit": False},
]
NOW = "2026-11-03T10:00:00Z"


def build_state(company, invoice, customer):
    state = empty_rial_accounting_state()
    suffix = invoice[-1]
    vendor = f"REVIEW-VENDOR-{suffix}"
    bill = f"REVIEW-BILL-{suffix}"
    commands = [
        {"type": "company.profile.set", "legalName": company, "address": "",
         "phone": "", "nationalId": "", "economicCode": "", "postalCode": "",
         "reason": "In-memory UX regression", "postingUtcOffsetMinutes": 210},
        {"type": "party.register", "partyId": customer,
         "name": f"{company} مشتری نمونه", "kind": "customer"},
        {"type": "invoice.create", "invoiceId": invoice, "partyId": customer,
         "documentDate": "2026-11-01", "lines": [
             {"description": "خدمت آزمایشی بدون داده واقعی", "quantity": 1,
              "unitPrice": 320000}]},
        {"type": "invoice.approve", "invoiceId": invoice},
        {"type": "invoice.issue", "invoiceId": invoice,
         "postingDate": "2026-11-02"},
        {"type": "party.register", "partyId": vendor,
         "name": f"{company} فروشنده نمونه", "kind": "vendor"},
        {"type": "bill.create", "billId": bill, "partyId": vendor,
         "documentDate": "2026-11-01", "lines": [
             {"description": "خرید آزمایشی", "quantity": 1, "unitPrice": 40000}]},
        {"type": "bill.approve", "billId": bill},
        {"type": "bill.issue", "billId": bill, "postingDate": "2026-11-02"},
        {"type": "funds.deposit", "accountId": "1010", "amount": 100000,
         "postingDate": "2026-11-02", "note": "تأمین وجه آزمایشی"},
        {"type": "receipt.record", "receiptId": f"REVIEW-REC-{suffix}",
         "partyId": customer, "accountId": "1010", "postingDate": "2026-11-02",
         "allocations": [{"invoiceId": invoice, "amount": 15000}]},
        {"type": "payment.record", "paymentId": f"REVIEW-PAY-{suffix}",
         "partyId": vendor, "accountId": "1010", "postingDate": "2026-11-02",
         "allocations": [{"billId": bill, "amount": 9000}]},
    ]
    for number, command in enumerate(commands, 1):
        state = apply_accounting_command(
            state, {**command, "eventId": f"UXREVIEW-{invoice}-{number}"},
            actor="qa-admin", accounts=USERS, now=NOW)["state"]
    return state, len(commands)


def payload(state, revision, username, role, *, can_manage=False):
    return {"revision": revision,
            "view": accounting_view(state, actor=username, accounts=USERS),
            "currentUser": {"username": username, "role": role, "jobTitle": "QA مصنوعی"},
            "capabilities": {"canManage": can_manage, "canDraft": can_manage,
                             "canAdmin": role == "admin"}}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    primary, revision = build_state("دفتر یک آزمایشی", "REVIEW-INV-A", "REVIEW-CUSTOMER-A")
    secondary, revision_b = build_state("دفتر دو آزمایشی", "REVIEW-INV-B", "REVIEW-CUSTOMER-B")
    admin = payload(primary, revision, "qa-admin", "admin", can_manage=True)
    viewer = payload(primary, revision, "qa-viewer", "viewer")
    other = payload(secondary, revision_b, "qa-admin", "admin", can_manage=True)
    try:
        accounting_view(primary, actor="qa-revoked", accounts=USERS)
    except PermissionError:
        denied = True
    else:
        raise AssertionError("Core did not reject revoked financeView")
    assert "REVIEW-INV-A" in admin["view"]["invoices"]
    assert "REVIEW-INV-B" not in viewer["view"]["invoices"]
    assert "REVIEW-INV-A" not in other["view"]["invoices"]
    assert "REVIEW-REC-A" in viewer["view"]["receipts"]
    assert "REVIEW-PAY-A" in viewer["view"]["payments"]
    journal = next(item["id"] for item in admin["view"]["journals"]
                   if item.get("sourceType") == "invoice.issue")
    assert journal
    accounts = admin["view"]["accounts"]
    account_id = next(key for key in sorted(accounts) if key)
    print(json.dumps({"primaryAdmin": admin, "primaryViewer": viewer,
                      "otherCompany": other, "deniedOnRevocation": denied,
                      "expected": {"invoice": "REVIEW-INV-A", "bill": "REVIEW-BILL-A",
                                   "receipt": "REVIEW-REC-A", "payment": "REVIEW-PAY-A",
                                   "customer": "REVIEW-CUSTOMER-A",
                                   "customerName": admin["view"]["parties"]["REVIEW-CUSTOMER-A"]["name"],
                                   "journal": journal, "account": account_id,
                                   "otherInvoice": "REVIEW-INV-B"}},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
