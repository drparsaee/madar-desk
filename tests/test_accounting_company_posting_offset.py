"""Synthetic fixed-offset fiscal-date controls; never touches operational books."""
import unittest

from accounting_core import (
    accounting_view, apply_accounting_command, empty_rial_accounting_state,
    validate_accounting_state,
)


USERS = {"admin": {"username": "admin", "role": "admin"}}
PROFILE = {
    "legalName": "Synthetic Company", "address": "", "phone": "",
    "nationalId": "", "economicCode": "", "postalCode": "",
    "reason": "Explicit company posting calendar policy",
}
FIXED_OFFSET_POLICY = {"postingCalendarMode": "fixed-offset-no-dst"}


class CompanyPostingOffsetTests(unittest.TestCase):
    def setUp(self):
        self.state = empty_rial_accounting_state()
        self.seq = 0

    def cmd(self, kind, *, now="2026-11-02T22:00:00Z", **kwargs):
        self.seq += 1
        out = apply_accounting_command(
            self.state, {"type": kind, "eventId": f"tz-{self.seq}", **kwargs},
            actor="admin", accounts=USERS, now=now)
        self.state = out["state"]
        return out

    def test_explicit_tehran_offset_accepts_same_instant_in_utc_or_local_clock(self):
        self.cmd("company.profile.set", **PROFILE, **FIXED_OFFSET_POLICY,
                 postingUtcOffsetMinutes=210)
        self.cmd("funds.deposit", amount=100, accountId="1010",
                 postingDate="2026-11-03", note="Local posting day")
        self.cmd("funds.deposit", amount=50, accountId="1010",
                 postingDate="2026-11-03", note="Same local day",
                 now="2026-11-03T01:30:00+03:30")
        view = accounting_view(self.state, actor="admin", accounts=USERS)
        self.assertEqual([j["date"] for j in view["journals"]],
                         ["2026-11-03", "2026-11-03"])
        self.assertEqual(view["accounts"]["1010"]["debitMinusCredit"], 150)
        self.assertEqual(self.state["events"][1]["at"], "2026-11-02T22:00:00Z")
        self.assertTrue(validate_accounting_state(self.state))

    def test_legacy_utc_behavior_and_existing_profiles_still_replay(self):
        self.cmd("company.profile.set", **PROFILE)
        with self.assertRaisesRegex(ValueError, "future"):
            self.cmd("funds.deposit", accountId="1010", amount=1,
                     postingDate="2026-11-03", note="Legacy UTC boundary")
        self.assertTrue(validate_accounting_state(self.state))
        self.assertNotIn("postingUtcOffsetMinutes",
                         accounting_view(self.state, actor="admin", accounts=USERS)["companyProfile"])

    def test_policy_survives_subsequent_company_identity_edit(self):
        self.cmd("company.profile.set", **PROFILE, **FIXED_OFFSET_POLICY,
                 postingUtcOffsetMinutes=210)
        self.cmd("company.profile.set", **{**PROFILE, "legalName": "Updated Company"})
        view = accounting_view(self.state, actor="admin", accounts=USERS)
        self.assertEqual(view["companyProfile"]["postingUtcOffsetMinutes"], 210)
        self.assertEqual(len(view["companyProfile"]["history"]), 2)
        self.cmd("funds.deposit", accountId="1010", amount=1,
                 postingDate="2026-11-03", note="After profile edit")
        self.assertTrue(validate_accounting_state(self.state))

    def test_negative_utc_offset_rejects_posting_before_company_midnight(self):
        self.cmd("company.profile.set", **PROFILE, **FIXED_OFFSET_POLICY,
                 postingUtcOffsetMinutes=-300,
                 now="2026-11-03T02:00:00Z")
        with self.assertRaisesRegex(ValueError, "future"):
            self.cmd("funds.deposit", accountId="1010", amount=1,
                     postingDate="2026-11-03", note="Premature local day",
                     now="2026-11-03T02:00:00Z")
        self.cmd("funds.deposit", accountId="1010", amount=1,
                 postingDate="2026-11-03", note="After local midnight",
                 now="2026-11-03T05:00:00Z")
        self.assertTrue(validate_accounting_state(self.state))

    def test_year_close_uses_company_day_without_dating_server_clock(self):
        self.cmd("company.profile.set", **PROFILE, **FIXED_OFFSET_POLICY,
                 postingUtcOffsetMinutes=210,
                 now="2025-12-30T21:00:00Z")
        self.cmd("fiscal.year.close", throughDate="2025-12-31",
                 reason="Closing local calendar date", now="2025-12-30T21:00:00Z")
        view = accounting_view(self.state, actor="admin", accounts=USERS)
        self.assertEqual(view["closedThrough"], "2025-12-31")
        self.assertEqual(view["fiscalYears"][0]["closedAt"], "2025-12-30T21:00:00Z")
        self.assertTrue(validate_accounting_state(self.state))

    def test_invalid_offsets_rejected_without_mutating_state(self):
        for bad in (True, 30.0, "210", 211, -721, 841):
            with self.subTest(offset=bad), self.assertRaisesRegex(ValueError, "UTC offset"):
                self.cmd("company.profile.set", **PROFILE,
                         **FIXED_OFFSET_POLICY, postingUtcOffsetMinutes=bad)
            self.assertEqual(self.state["events"], [])

    def test_unsupported_timezone_policy_fails_closed(self):
        for extra in ({"postingUtcOffsetMinutes": 210},
                      {"postingUtcOffsetMinutes": 60,
                       "postingCalendarMode": "Europe/Berlin"},
                      {"postingCalendarMode": "fixed-offset-no-dst"}):
            with self.subTest(extra=extra), self.assertRaisesRegex(ValueError, "calendar"):
                self.cmd("company.profile.set", **PROFILE, **extra)
            self.assertEqual(self.state["events"], [])

    def test_posting_calendar_remains_administrator_only(self):
        editor = {"editor": {"username": "editor", "role": "editor",
                             "financeEdit": True, "financeView": True}}
        command = {"type": "company.profile.set", "eventId": "tz-editor",
                   **PROFILE, **FIXED_OFFSET_POLICY, "postingUtcOffsetMinutes": 210}
        with self.assertRaises(PermissionError):
            apply_accounting_command(self.state, command, actor="editor",
                                     accounts=editor, now="2026-11-02T22:00:00Z")
        self.assertEqual(self.state["events"], [])


if __name__ == "__main__":
    unittest.main()
