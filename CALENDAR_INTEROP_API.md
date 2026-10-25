# Madar Desk 1.0: Offline iCalendar (.ics) file interchange

**Implementation:** calendar_interop.py, Python standard library only. This is
an independent file adapter. It has no OAuth, Google/Outlook API, sync, network,
APPDATA, database, native host or UI side effects.

## Existing calendar and task model

data_model.py / native_app.py / src/App.jsx store task.dueDate as optional
Gregorian ISO YYYY-MM-DD. It may be empty. The Jalali calendar preference in
src/productivity.jsx changes display/input only. Shared dates remain Gregorian.

The adapter exports an all-day VEVENT on the task due date; DTEND is the
**exclusive next day**. When importing a timed event, it converts the DTSTART
calendar day (in the supplied event's wall-time convention) to Gregorian ISO.
For example, DTSTART:20261021T233000Z becomes dueDate 2026-10-21. This remains
the UTC wall date even if a viewer in a different time zone might see the
following day. It also returns the original HH:MM and TZID/UTC for review.
It does not resolve offsets, DST or named timezone rules.

## Public API

~~~python
from datetime import datetime, timezone
from calendar_interop import export_ics, import_ics, CalendarInteropError

# Callers must first filter task visibility/authorization.
ics_bytes = export_ics(
    [{"id": "card-1", "title": "جلسه", "dueDate": "2026-10-22"}],
    calendar_name="Madar Desk",
    now=datetime.now(timezone.utc),  # optional; defaults to UTC now
)

# File chooser and user confirmation belong to the host/UI.
preview = import_ics(ics_bytes, existing_keys=())
# {
#  "events": [{
#     "source_key": "<sha256 of external UID>",
#     "title": "جلسه", "dueDate": "2026-10-22",
#     "dateKind": "date", "time": "", "timezone": ""
#  }],
#  "skipped": []
# }
~~~

### export_ics(tasks, *, calendar_name="Madar Desk", now=None) -> bytes

- Takes iterable of dict-like tasks; maximum 1,000 items. Returns UTF-8 CRLF
  bytes ready to save to .ics. Missing due date / archived cards are skipped.
  Invalid dates, duplicate task IDs, invalid archived flags, invalid titles or
  unbounded task lists raise CalendarInteropError before output is returned.
- Reads ONLY id, title, dueDate and archived. Excludes by construction project
  and customer data, descriptions, comments, checklists, assignees, invoices,
  price/tax/cost/finance fields, receipts, attachments, file paths and unknown
  extension properties. **Task titles are visible in exported calendar files.**
  Callers must respect user visibility and obtain confirmation when sharing.
- Writes SUMMARY, UID, UTC DTSTAMP, DTSTART;VALUE=DATE, DTEND;VALUE=DATE.
  UID is SHA-256(task.id) plus @madar.invalid, with no raw task identifier.
  Order and UID are stable; DTSTAMP defaults to the current UTC clock.
- Escapes literal backslashes, semicolons, commas and newlines in text. Uses
  Unicode-safe RFC 5545 physical line folding at most 75 UTF-8 octets.

### import_ics(content, *, existing_keys=()) -> dict

- Input UTF-8 bytes or string, optional UTF-8 BOM; accepts CRLF or LF. Maximum
  2,000,000 UTF-8 bytes, 25,000 physical lines, 16,384 bytes per physical
  line, 32,768 bytes per unfolded line, 1,000 VEVENTs and eight nested
  components. existing_keys is an iterable of up to 20,000 lowercase SHA-256
  hexadecimal strings.
- Returns {"events": [...], "skipped": [...]}. Each accepted event has EXACTLY
  source_key, title, dueDate, dateKind, time and timezone. source_key is
  SHA-256 of the iCalendar UID. The raw UID (often an email) is not returned.
- Each skipped item is {"index": <1-based VEVENT number>, "reason": <text>};
  it never includes raw private event content.
- Handles all-day VALUE=DATE and ISO-style compact iCalendar DATE-TIME
  (UTC Z, floating time, or named TZID such as Asia/Tehran and quoted
  Outlook "Pacific Standard Time"). Parses valid Gregorian year 1900-2100,
  hour/minute/second, and optional DTEND with matching type/timezone and
  positive duration. Supports SUMMARY;LANGUAGE=fa-IR.
- Ignores nested VALARM and attendee/organizer/description/URL/attachment and
  Microsoft/Google vendor extensions. Does not trigger alarms, fetch URLs,
  download attachments or contact people.
- Individually skips unsupported recurring events (RRULE, RDATE, EXDATE,
  RECURRENCE-ID), CANCELLED events, CLASS:PRIVATE/CONFIDENTIAL, invalid event
  dates/times, absent UID/title and duplicate source UIDs. METHOD:CANCEL files
  are rejected as a whole.
- Malformed framing, invalid UTF-8, unsupported calendar scale, excessive
  nesting, oversized input or invalid property syntax raise
  CalendarInteropError. This does NOT write a partial task or file.
- The returned date for a timed event is the date in DTSTART's stated
  clock/timezone, NOT automatically converted to the host's local day.
  TZID is a preserved display label, not validated against a timezone database.

## Recommended Prime integration

1. Native host reads a user-picked .ics file with a 2,000,001-byte upper read
   bound. Require normal workspace/project permissions before proceeding.
2. Gather calendarSourceKey strings from already imported tasks in the
   *authorized target scope*. Pass these source hashes to existing_keys.
3. Display import_ics(...).events, skipped reasons, time and timezone in a
   preview. Ask the user to approve adding each task. Existing cards and
   project state are not mutated by the adapter.
4. On confirmation, create complete native task records through the existing
   transaction and ACL path; allocate new ID/projectId/boardId/listId/status,
   priority, empty checklists and reports, createdAt/updatedAt, and dueDate.
   Set calendarSourceKey to the accepted event's source_key (64 lowercase hex).
   Do not copy any other arbitrary calendar metadata or external UID into task
   fields. Source title should go through the existing task-title validator.
5. Recheck calendarSourceKey uniqueness **inside** the database transaction.
   Adapter-level existing_keys dedupes repeated inputs and same-file UIDs but
   cannot resolve two simultaneous independent imports.

If calendarSourceKey is not saved by the host, idempotence between different
import sessions is not possible. If another user lacks access to cards in
the source project, the caller should not query or expose their source keys.

## Supported subset and limitations

This feature offers **file exchange**, not Google/Outlook account connection.
It does not update/delete existing tasks when an ICS event changes, expand
recurrence, import calendar descriptions, preserve time slots as Madar task
durations, send invitations, schedule notifications, preserve timezone
transition rules or automatically detect duplicate titles. Import requires
an explicit user-approved mapping into valid board tasks.

## Validation performed

Command: python -m unittest discover -s tests -p test_calendar_interop.py -v

Observed on 2026-10-21: 19 tests, 19 PASS, exit code 0. Coverage includes
Gregorian/Jalali representation boundaries, all-day dates and leap years,
sample Google UTC/Outlook Windows TZID files, semicolon inside quoted
parameters, language-tagged SUMMARY, BOM, Persian UTF-8 CRLF folding,
stable hashed UIDs, idempotence, canceled/private/recurring events,
malformed dates, malformed files, size bounds, and a real .ics read/write
round-trip inside a disposable temporary directory. Export tests inject
private financial fields, project/customer data, comments and attachment
paths and verify their absence in the serialized file.

No live Google Calendar, Outlook application, Windows EXE, APPDATA,
network connection or production database was used. Real application
interoperability and host-level integration are not yet independently verified.
