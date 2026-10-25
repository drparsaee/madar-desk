"""Offline acceptance/regression tests for limited Google/Outlook .ics files."""

import hashlib
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from calendar_interop import (
    MAX_EVENTS,
    MAX_ICS_BYTES,
    CalendarInteropError,
    export_ics,
    import_ics,
)


NOW = datetime(2026, 10, 21, 12, 34, 56, tzinfo=timezone.utc)


def calendar(*event_bodies, headers=""):
    return ("\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0",
        "PRODID:-//Google Inc//Google Calendar 70.9054//EN",
        headers,
        *(line for event in event_bodies for line in
          ("BEGIN:VEVENT", *event.splitlines(), "END:VEVENT")),
        "END:VCALENDAR", "",
    ])).encode("utf-8").replace(b"\r\n\r\n", b"\r\n")


def event(uid="id-1@example.org", start="DTSTART;VALUE=DATE:20261021",
          end="DTEND;VALUE=DATE:20261022", summary="SUMMARY:Review task", extra=""):
    return "\n".join(filter(None, ["UID:" + uid, start, end, summary, extra]))


class CalendarInteropTest(unittest.TestCase):
    def test_roundtrip_preserves_jalali_display_independent_iso_due_date(self):
        # The UI displays Jalali, while task dueDate remains ISO Gregorian.
        tasks = [{"id": "t1", "title": "جلسه فردا", "dueDate": "2026-10-21"}]
        encoded = export_ics(tasks, now=NOW)
        self.assertIn(b"DTSTART;VALUE=DATE:20261021", encoded)
        self.assertIn(b"DTEND;VALUE=DATE:20261022", encoded)
        self.assertIn(b"DTSTAMP:20261021T123456Z", encoded)
        result = import_ics(encoded)
        self.assertEqual(len(result["events"]), 1)
        self.assertEqual(result["events"][0]["title"], "جلسه فردا")
        self.assertEqual(result["events"][0]["dueDate"], "2026-10-21")
        self.assertEqual(result["events"][0]["dateKind"], "date")
        self.assertEqual(result["events"][0]["time"], "")
        self.assertEqual(result["events"][0]["timezone"], "")

    def test_export_allows_only_public_calendar_task_fields(self):
        # Financial fields and identifiers might be sensitive; no raw ID.
        task = {
            "id": "invoice-no-keep-this-private", "title": "Follow up",
            "dueDate": "2026-10-21", "cost": 912341,
            "costCategory": "confidential-cost", "sale": {"total": 819201},
            "projectId": "private-project", "projectName": "secret-name",
            "description": "private-description", "reports": [{"summary": "secret-report"}],
            "checklist": [{"cost": 737232, "text": "secret-checklist"}],
            "customer": {"phone": "PRIVATE-123456"}, "assignees": ["secret-person"],
            "fileLinks": [{"path": "\\\\secret-server\\customer\\file"}],
            "calendarSourceKey": "secret-calendar-key",
        }
        original = repr(task)
        output = export_ics([task], now=NOW).decode("utf-8")
        self.assertIn("SUMMARY:Follow up", output)
        for secret in (
            task["id"], "912341", "819201", "private-project", "secret-name",
            "private-description", "secret-report", "secret-checklist",
            "737232", "PRIVATE-123456", "secret-person", "secret-server",
            "secret-calendar-key",
        ):
            self.assertNotIn(secret, output)
        self.assertEqual(repr(task), original)

    def test_all_day_exclusive_end_at_month_and_year_boundary(self):
        output = export_ics([
            {"id": "task-one", "title": "A", "dueDate": "2026-12-31"},
            {"id": "task-two", "title": "B", "dueDate": "2028-02-29"},
            {"id": "task-max", "title": "Max range", "dueDate": "2100-12-31"},
        ], now=NOW).decode()
        self.assertIn("DTEND;VALUE=DATE:20270101", output)
        self.assertIn("DTEND;VALUE=DATE:20280301", output)
        self.assertIn("DTEND;VALUE=DATE:21010101", output)
        self.assertEqual(len(import_ics(output)["events"]), 3)

    def test_skip_archived_and_empty_due_date_without_emitting_private_details(self):
        tasks = [
            {"id": "n", "title": "No date", "dueDate": "", "cost": 1},
            {"id": "a", "title": "Archived", "dueDate": "2026-10-21", "archived": True},
            {"id": "d", "title": "Due", "dueDate": "2026-10-21", "archived": False},
        ]
        events = import_ics(export_ics(tasks, now=NOW))["events"]
        self.assertEqual([e["title"] for e in events], ["Due"])

    def test_export_uid_and_order_are_stable_across_shuffled_tasks(self):
        a = {"id": "a", "title": "Alpha", "dueDate": "2026-10-21"}
        b = {"id": "b", "title": "Beta", "dueDate": "2026-10-21"}
        self.assertEqual(export_ics([a, b], now=NOW), export_ics([b, a], now=NOW))
        uid = hashlib.sha256(b"a").hexdigest() + "@madar.invalid"
        unfolded = export_ics([a], now=NOW).replace(b"\r\n ", b"")
        self.assertIn(("UID:" + uid).encode(), unfolded)

    def test_newlines_escape_and_utf8_octet_folding_are_standard_compliant(self):
        title = "پروژه، پیگیری; ساعت\\جلسه\nبعدی 💡" * 12
        # Max 300 characters; vary with string length rather than bytes.
        title = title[:280]
        output = export_ics([{"id": "a", "title": title, "dueDate": "2026-10-21"}],
                            now=NOW)
        self.assertTrue(output.endswith(b"\r\n"))
        self.assertNotIn(b"\r\nBEGIN:VEVENT\r\nBEGIN:VEVENT", output)
        for physical in output.rstrip(b"\r\n").split(b"\r\n"):
            self.assertLessEqual(len(physical), 75)
            physical.decode("utf-8")  # Folding never splits a UTF-8 codepoint.
        self.assertEqual(import_ics(output)["events"][0]["title"], title)

    def test_file_roundtrip_uses_only_temp_directory(self):
        with tempfile.TemporaryDirectory(prefix="madar-ics-offline-") as directory:
            ics = Path(directory, "export.ics")
            ics.write_bytes(export_ics(
                [{"id": "a", "title": "Task", "dueDate": "2026-10-21"}], now=NOW))
            result = import_ics(ics.read_bytes())
            self.assertEqual(result["events"][0]["dueDate"], "2026-10-21")

    def test_google_timed_utc_and_outlook_quoted_timezone_keep_wall_calendar_date(self):
        data = calendar(
            event("google-event", "DTSTART:20261021T233000Z",
                  "DTEND:20261022T003000Z", "SUMMARY:UTC event"),
            event("outlook-event", 'DTSTART;TZID="Pacific Standard Time":20261020T090000',
                  'DTEND;TZID="Pacific Standard Time":20261020T100000',
                  "SUMMARY:Outlook appointment",
                  'ORGANIZER;CN="Smith; John":mailto:john@example.org'),
            headers="METHOD:PUBLISH",
        )
        results = import_ics(data)
        self.assertEqual(len(results["events"]), 2)
        self.assertEqual(results["events"][0]["dueDate"], "2026-10-21")
        self.assertEqual(results["events"][0]["time"], "23:30")
        self.assertEqual(results["events"][0]["timezone"], "UTC")
        self.assertEqual(results["events"][1]["dueDate"], "2026-10-20")
        self.assertEqual(results["events"][1]["timezone"], "Pacific Standard Time")
        self.assertNotIn("john@example.org", repr(results))

    def test_tzid_iana_and_nested_valarm_are_accepted_but_not_executed(self):
        result = import_ics(calendar(event(
            start="DTSTART;TZID=Asia/Tehran:20261021T130000",
            end="DTEND;TZID=Asia/Tehran:20261021T140000",
            extra="BEGIN:VALARM\nTRIGGER:-PT15M\nACTION:DISPLAY\nDESCRIPTION:Finance $9999\nEND:VALARM"
        )))
        self.assertEqual(result["events"][0]["timezone"], "Asia/Tehran")
        self.assertNotIn("$9999", repr(result))

    def test_outlook_summary_language_parameter_and_utf8_bom(self):
        data = calendar(event(summary="SUMMARY;LANGUAGE=fa-IR:جلسه"))
        result = import_ics(b"\xef\xbb\xbf" + data)
        self.assertEqual(result["events"][0]["title"], "جلسه")

    def test_no_oauth_drive_or_network_calls_required(self):
        result = import_ics(calendar(event(extra="ATTACH:https://example.org/data\nURL:https://example.org/")))
        self.assertEqual(len(result["events"]), 1)
        self.assertNotIn("https://", repr(result))

    def test_idempotent_existing_source_key_and_duplicate_uid(self):
        one = calendar(event("stable@example.org"))
        first = import_ics(one)
        key = first["events"][0]["source_key"]
        second = import_ics(one, existing_keys=[key])
        self.assertEqual(second["events"], [])
        self.assertEqual(second["skipped"][0]["reason"], "duplicate_source")
        duplicate = import_ics(calendar(event("same@a"), event("same@a", summary="SUMMARY:Other")))
        self.assertEqual(len(duplicate["events"]), 1)
        self.assertEqual(duplicate["skipped"][0]["reason"], "duplicate_source")

    def test_cancelled_private_and_recurrence_not_silently_imported(self):
        result = import_ics(calendar(
            event("a", extra="STATUS:CANCELLED"),
            event("b", extra="CLASS:PRIVATE"),
            event("c", extra="CLASS:CONFIDENTIAL"),
            event("d", extra="RRULE:FREQ=DAILY;COUNT=12"),
            event("e", extra="RECURRENCE-ID:20261021T090000Z"),
            event("f", extra="RDATE;VALUE=DATE:20261023"),
        ))
        self.assertEqual(result["events"], [])
        self.assertEqual(len(result["skipped"]), 6)
        self.assertIn("recurring", repr(result))
        with self.assertRaisesRegex(CalendarInteropError, "cancellation"):
            import_ics(calendar(event(), headers="METHOD:CANCEL"))

    def test_date_kind_timezone_or_end_order_errors_skip_individual_event(self):
        cases = [
            event("bad-date", "DTSTART;VALUE=DATE:20260229"),
            event("bad-clock", "DTSTART:20261021T256000Z"),
            event("bad-zone", "DTSTART;TZID=../../etc/passwd:20261021T090000"),
            event("conflict", "DTSTART;TZID=Europe/Berlin:20261021T090000",
                  "DTEND:20261021T100000Z"),
            event("end-before", "DTSTART;VALUE=DATE:20261021",
                  "DTEND;VALUE=DATE:20261021"),
            event("kind-mismatch", "DTSTART;VALUE=DATE:20261021",
                  "DTEND:20261021T180000Z"),
        ]
        output = import_ics(calendar(*cases, event("good")))
        self.assertEqual(len(output["skipped"]), len(cases))
        self.assertEqual(len(output["events"]), 1)

    def test_malformed_properties_and_duplicate_required_property_rejected(self):
        result = import_ics(calendar(event("uid", extra="UID:other")))
        self.assertEqual(result["events"], [])
        self.assertEqual(result["skipped"][0]["reason"], "duplicate UID")
        text = calendar(event()).replace(b"SUMMARY:Review task", b"SUMMARY:Review task\\q")
        self.assertIn("escape", str(import_ics(text)["skipped"]))
        text = calendar(event()).replace(b"UID:id-1@example.org", b"UID:id-1@example.org\nX-BAD")
        with self.assertRaises(CalendarInteropError):
            import_ics(text)

    def test_reject_malformed_utf8_cr_controls_and_oversize(self):
        for data in (b"\xff", b"BEGIN:VCALENDAR\rX", b"\x00", b" " + calendar(event())):
            with self.subTest(data=data[:10]), self.assertRaises(CalendarInteropError):
                import_ics(data)
        with self.assertRaises(CalendarInteropError):
            import_ics(b"x" * (MAX_ICS_BYTES + 1))

    def test_reject_malformed_component_hierarchy_and_multiple_roots(self):
        original = calendar(event())
        with self.assertRaises(CalendarInteropError):
            import_ics(original.replace(b"END:VEVENT", b"END:VTIMEZONE"))
        with self.assertRaises(CalendarInteropError):
            import_ics(original + original)
        with self.assertRaises(CalendarInteropError):
            import_ics(original.replace(b"VERSION:2.0\r\n", b""))
        with self.assertRaises(CalendarInteropError):
            import_ics(original.replace(b"BEGIN:VEVENT", b"BEGIN:VTODO"))
        with self.assertRaisesRegex(CalendarInteropError, "Gregorian"):
            import_ics(calendar(event(), headers="CALSCALE:HEBREW"))

    def test_export_rejects_invalid_dates_duplicate_ids_and_mutations(self):
        bad = {"id": "x", "title": "Task", "dueDate": "1405/07/29"}
        with self.assertRaises(CalendarInteropError):
            export_ics([bad], now=NOW)
        bad["dueDate"] = "2026-02-30"
        with self.assertRaises(CalendarInteropError):
            export_ics([bad], now=NOW)
        bad["dueDate"] = "2026-10-21"
        with self.assertRaises(CalendarInteropError):
            export_ics([bad, bad], now=NOW)
        with self.assertRaises(CalendarInteropError):
            export_ics([bad], now=datetime(2026, 10, 21))
        with self.assertRaises(CalendarInteropError):
            export_ics([{"id": "x", "title": "A\nBEGIN:VEVENT", "dueDate": "2026-10-21",
                         "cost": 999} for _ in range(MAX_EVENTS + 1)], now=NOW)

    def test_limits_apply_to_existing_keys_and_large_fields(self):
        with self.assertRaises(CalendarInteropError):
            import_ics(calendar(event()), existing_keys=["not-a-hash"])
        with self.assertRaises(CalendarInteropError):
            import_ics(calendar(event()), existing_keys=None)
        long_uid = "x" * 513
        skipped = import_ics(calendar(event(uid=long_uid)))
        self.assertEqual(skipped["events"], [])
        self.assertEqual(len(skipped["skipped"]), 1)
        large_title = "T" * 400
        self.assertEqual(len(import_ics(calendar(event(summary="SUMMARY:" + large_title)))["skipped"]), 1)
        with self.assertRaises(CalendarInteropError):
            export_ics([{"id": "a", "title": "x", "dueDate": "2026-10-21", "archived": "true"}], now=NOW)


if __name__ == "__main__":
    unittest.main()
