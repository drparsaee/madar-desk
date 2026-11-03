"""Read-only double-entry reports from the verified Madar accounting projection.

All reports are company-wide (never silently misrepresented as per-project).
No file, tax policy, external banking integration or source DB access.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date


def _day(value, name):
    if value is None:
        return None
    if type(value) is not str:
        raise ValueError("Invalid " + name)
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("Invalid " + name) from error
    if parsed.isoformat() != value:
        raise ValueError("Invalid " + name)
    return value


def _current_stock_cost_control(view):
    """Conservative live warnings; not an inventory valuation certification.

    Historical inventory-tracking flags are not reconstructed by accounting_view,
    so callers must not use this current-state control for dated snapshots.
    """
    required = ("items", "invoices", "bills", "stockMovements")
    if any(type(view.get(name)) is not dict for name in required):
        return {"scope": "unavailable", "assessment": "not-assessed",
                "profitCertified": False, "sales": [], "purchases": []}

    moves = {}
    for movement in view["stockMovements"].values():
        if movement["type"] not in ("inventory.receive", "inventory.issue") or movement.get("reversed"):
            continue
        key_name = "invoiceId" if movement["type"] == "inventory.issue" else "billId"
        key = (movement["type"], movement[key_name], movement["itemId"])
        moves[key] = moves.get(key, 0) + movement["quantity"]

    warnings = {"sales": [], "purchases": []}
    for document_type, collection, move_type in (
            ("sales", "invoices", "inventory.issue"),
            ("purchases", "bills", "inventory.receive")):
        for document_id, document in sorted(view[collection].items()):
            if document["status"] != "issued":
                continue
            required_by_item = {}
            for index, source in enumerate(document["lines"]):
                item_id = source.get("itemId")
                item = view["items"].get(item_id)
                if not item or item.get("kind") != "goods" or not item.get("stockTracked"):
                    continue
                returned = document.get("returnedQuantities", [0] * len(document["lines"]))[index]
                outstanding = source["quantity"] - returned
                if outstanding < 0:
                    raise ValueError("Stock document returned quantity exceeds issued amount")
                required_by_item[item_id] = required_by_item.get(item_id, 0) + outstanding
            for item_id, expected in sorted(required_by_item.items()):
                posted = moves.get((move_type, document_id, item_id), 0)
                if expected == posted:
                    continue
                reason = ("stock-issue-and-cogs-pending" if document_type == "sales" else
                          "valuation-policy-required" if document["tax"] or document["discount"] else
                          "stock-receipt-pending")
                if posted > expected:
                    reason = "stock-movement-exceeds-document"
                warnings[document_type].append({
                    "documentId": document_id, "itemId": item_id,
                    "expectedQuantity": expected, "postedQuantity": posted,
                    "unpostedQuantity": max(expected - posted, 0), "reason": reason,
                })
    return {"scope": "current-projection",
            "assessment": ("incomplete" if warnings["sales"] or warnings["purchases"]
                           else "no-unmatched-tracked-lines-detected"),
            "profitCertified": False, **warnings}


def ledger_reports(view, *, from_date=None, through_date=None):
    """Trial balance, ledger statements, P&L and balance sheet in exact ledger units.

    A caller MUST supply an authenticated `accounting_view` projection; this
    helper is pure but is not an authorization boundary. Includes historical
    reversal postings (never erases entries). `from_date` bounds movements,
    while ending balances are accumulated from inception through `through_date`.
    """
    if type(view) is not dict or view.get("currency") not in ("TOMAN", "RIAL"):
        raise ValueError("Expected verified RIAL/TOMAN ledger projection")
    first = _day(from_date, "from_date")
    last = _day(through_date, "through_date")
    if first and last and first > last:
        raise ValueError("Report start after end")
    accounts = view.get("accounts")
    journals = view.get("journals")
    if type(accounts) is not dict or type(journals) is not list:
        raise ValueError("Invalid accounting projection")
    initial = {ident: 0 for ident in accounts}
    balances = dict(initial)
    movement = {ident: {"debit": 0, "credit": 0} for ident in accounts}
    # The trial balance includes closing journals. Operational P&L does not:
    # a year-end transfer to retained earnings is not a second sale or cost.
    operating_movement = {ident: {"debit": 0, "credit": 0} for ident in accounts}
    ledger = {ident: [] for ident in accounts}
    party_net = {}
    count = 0
    for entry in sorted(enumerate(journals), key=lambda p: (p[1]["date"], p[0])):
        _, journal = entry
        day = _day(journal["date"], "journal date")
        if last is not None and day > last:
            continue
        count += 1
        for line in journal["lines"]:
            aid = line["accountId"]
            if aid not in accounts:
                raise ValueError("Unknown report account")
            debit, credit = line["debit"], line["credit"]
            if type(debit) is not int or type(credit) is not int or debit < 0 or credit < 0:
                raise ValueError("Invalid report amounts")
            balances[aid] += debit - credit
            if aid in ("1200", "2000"):
                party_id = line.get("partyId")
                if (type(party_id) is not str or not party_id
                        or party_id not in view.get("parties", {})):
                    raise ValueError("Receivable/payable posting requires a known party")
                party_net[(aid, party_id)] = party_net.get((aid, party_id), 0) + debit - credit
            if first is None or day >= first:
                movement[aid]["debit"] += debit
                movement[aid]["credit"] += credit
                if journal["sourceType"] != "fiscal.year.close":
                    operating_movement[aid]["debit"] += debit
                    operating_movement[aid]["credit"] += credit
                ledger[aid].append({"date": day, "journalId": journal["id"],
                                    "sourceType": journal["sourceType"],
                                    "sourceId": journal["sourceId"],
                                    "debit": debit, "credit": credit,
                                    "partyId": line.get("partyId"),
                                    "balanceDebitMinusCredit": balances[aid]})
    rows = []
    for aid, meta in sorted(accounts.items()):
        signed = balances[aid]
        rows.append({"accountId": aid, "name": meta["name"], "kind": meta["kind"],
                     "debit": max(signed, 0), "credit": max(-signed, 0),
                     "debitMovement": movement[aid]["debit"],
                     "creditMovement": movement[aid]["credit"],
                     "balanceDebitMinusCredit": signed})
    debit_total = sum(row["debit"] for row in rows)
    credit_total = sum(row["credit"] for row in rows)
    if debit_total != credit_total:
        raise ValueError("Trial balance mismatch")
    def period_profit(moves):
        revenue = sum(moves[r["accountId"]]["credit"] -
                      moves[r["accountId"]]["debit"] for r in rows
                      if r["kind"] == "revenue")
        expense = sum(moves[r["accountId"]]["debit"] -
                      moves[r["accountId"]]["credit"] for r in rows
                      if r["kind"] == "expense")
        return {"revenue": revenue, "expense": expense, "net": revenue - expense}

    operational_profit = period_profit(operating_movement)
    post_close_profit = period_profit(movement)
    closing_adjustment = post_close_profit["net"] - operational_profit["net"]
    lifetime_net = sum(-balances[r["accountId"]] for r in rows if r["kind"] == "revenue") - sum(
        balances[r["accountId"]] for r in rows if r["kind"] == "expense")
    assets = sum(balances[r["accountId"]] for r in rows if r["kind"] == "asset")
    liabilities = sum(-balances[r["accountId"]] for r in rows if r["kind"] == "liability")
    capital = sum(-balances[r["accountId"]] for r in rows if r["kind"] == "equity")
    if assets != liabilities + capital + lifetime_net:
        raise ValueError("Balance sheet does not reconcile")
    counterparties = []
    parties = view.get("parties", {})
    if type(parties) is not dict:
        raise ValueError("Invalid counterparties")
    for party_id, party in sorted(parties.items()):
        receivable = party_net.get(("1200", party_id), 0)
        payable = -party_net.get(("2000", party_id), 0)
        if receivable < 0 or payable < 0:
            raise ValueError("Negative counterparty control balance")
        if last is None and (party.get("receivable") != receivable or
                             party.get("payable") != payable):
            raise ValueError("Counterparty subledger and GL do not reconcile")
        counterparties.append({"partyId": party_id, "name": party["name"],
                               "receivable": receivable, "payable": payable,
                               "netReceivable": receivable - payable})
    if (sum(x["receivable"] for x in counterparties) != balances.get("1200", 0)
            or sum(x["payable"] for x in counterparties) != -balances.get("2000", 0)):
        raise ValueError("AR/AP control account mismatch")
    liquid_accounts = []
    for account_id, account in sorted(accounts.items()):
        if account["liquid"]:
            liquid_accounts.append({"accountId": account_id, "name": account["name"],
                                    "balance": balances[account_id]})
    stock_cost_control = (_current_stock_cost_control(view) if last is None else {
        "scope": "historical-inventory-tracking-not-reconstructed",
        "assessment": "not-assessed", "profitCertified": False,
        "sales": [], "purchases": [],
    })
    return deepcopy({"currency": view["currency"], "scope": "all-projects",
                     "fromDate": first, "throughDate": last,
                     "journalCountThroughDate": count,
                     "trialBalance": {"rows": rows, "totalDebit": debit_total,
                                      "totalCredit": credit_total},
                     "accountStatements": ledger,
                     "counterpartyBalances": counterparties,
                     "cashBankBalances": liquid_accounts,
                     "stockCostControl": stock_cost_control,
                     "reconciled": True,
                     "profitLoss": operational_profit,
                     "profitLossReconciliation": {
                         "basis": "operational-excludes-fiscal-year-close",
                         "postCloseLedgerMovements": post_close_profit,
                         "closingAdjustmentNet": closing_adjustment,
                         "reconciled": (operational_profit["net"] + closing_adjustment ==
                                        post_close_profit["net"])},
                     "balanceSheet": {"assets": assets, "liabilities": liabilities,
                                      "capital": capital, "unclosedProfitLoss": lifetime_net,
                                      "liabilitiesAndEquity": liabilities + capital + lifetime_net}})
