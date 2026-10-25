# Madar collaboration service, schema v1

`collab.py` provides pure Python domain functions for v0.4/v0.5 comments,
mentions, subscriptions, notifications, activity history and small deterministic
automation rules. It has **no network routes, browser code, storage connection,
background scheduler or Google Drive connection**. It is intentionally usable
by the future SQLite repository or the existing LAN host.

## Public Python API

```python
from collab import (
    SCHEMA_VERSION, TRIGGERS, empty_state, validate_state,
    extract_mentions, apply_command, list_comments,
    list_notifications, list_activity,
)

state = empty_state()
assert validate_state(state)
result = apply_command(
    state,
    {"type": "comment.add", "eventId": "request-005",
     "cardId": "t-sample", "text": "پیشنهاد جدید برای @sara"},
    actor="editor",                  # from authenticated session, NOT request JSON
    accounts=lan_service.users,       # {username: account}, see lan.py
    cards=current_state["tasks"],    # [{"id", "projectId", ...}]
    projects=current_state["projects"],
    now="2026-10-20T15:30:00Z",       # host-supplied timezone-aware ISO timestamp
)
if result["changed"]:
    persist_atomically(result["state"])
state = result["state"]
comment_id = result["result"]["commentId"]
```

`apply_command` returns `{"state": new_snapshot, "changed": bool,
"result": command_result}`. It copies its input and never performs I/O or
mutates the caller's account/task/project structures. `accounts`, `cards` and
`projects` can each be a list of records or a dictionary indexed by `username`
or `id`, respectively; records must contain the matching key. Other account
properties, including `passwordHash`, are never copied to the result.

`list_comments(state, card_id, *, actor, accounts, cards, projects)` returns
comments including **content-free tombstones** for deleted comments.
`list_notifications(state, *, actor, accounts, cards, projects,
unread_only=False)` returns only the actor's still-authorized notifications.
`list_activity(state, *, actor, accounts, cards, projects, limit=100)` returns
newest-first entries from authorized projects (max 500). All return detached
copies. `extract_mentions(text)` returns unique syntactically valid usernames;
unregistered/out-of-scope mentions are excluded when a comment is committed.

## Commands

Every command requires `type` and a caller-generated **stable** `eventId`
(1–96 characters; ASCII letters, digits, `_`, `.`, `:`, `-`). Do not derive it
from a clock tick or generate a new one on HTTP retry. The host must ensure
authenticated users cannot forge the `actor` argument.

| `type` | Additional fields | Authorization | Result fields |
| --- | --- | --- | --- |
| `comment.add` | `cardId`, `text` | Admin/editor on card project | `commentId`, `notificationIds` |
| `comment.edit` | `commentId`, `text` | Original author, currently admin/editor with project access | `commentId`, `notificationIds` |
| `comment.delete` | `commentId` | Author or admin, with project write access | `commentId`, `notificationIds` |
| `watch.set` | `cardId`, `enabled` (boolean) | Any user who can view project | `watching` |
| `notification.read` | `notificationId` | Notification recipient, still authorized for project | `notificationId`, `readAt` |
| `rule.upsert` | `rule` object below | Admin only | `ruleId` |
| `rule.delete` | `ruleId` | Admin rule owner only | `ruleId` |
| `event.publish` | `cardId`, `trigger`, `data` | Admin/editor on card project | `matchedRules`, `notificationIds` |

**Comments:** text is plain, untrusted UTF-8 text of 1–4,000 characters (no
NUL). `@username` detection is literal, not HTML. New comments notify valid
mentions and currently authorized card watchers once per recipient. Editing
only notifies newly mentioned users. The original comment author can edit;
admin can delete comments for moderation. Deletion clears body and mentions,
retains record ID/time/author and adds a minimal activity event. Existing
notifications are not retroactively recalled.

**Notifications:** `kind` is `mention`, `watch` or `rule`. A notification has
`id`, `recipient`, `projectId`, `cardId`, `kind`, `originId`, `message`,
`createdAt`, `readAt`. The watcher/read operations are available to viewers;
viewers cannot publish events or write comments. Notifications are filtered
again at read time if a user's scope is revoked. The host should also discard
or deactivate stale watcher subscriptions when deleting an account/card.

**Activity:** entries include `id`, `eventId`, `actor`, `action`, `projectId`,
`cardId`, `at`. They deliberately exclude comment content, profile photos,
passwords and other private data. The module treats existing activity as
immutable, but a production adapter must protect stored audit rows from direct
client modification. A client should never submit a full `collab` snapshot.

## Allowlisted automation (limited v0.5 foundation)

Only admins can create/edit/delete a rule. The server always chooses `owner`
and `createdAt`; the caller supplies exactly these six rule fields:

```json
{
  "id": "rule-done",
  "projectId": "p-sample",
  "trigger": "card_moved",
  "conditions": [{"field": "toColumnId", "equals": "done"}],
  "actions": [
    {"type": "notify", "users": ["sara"], "message": "کارت تکمیل شد"},
    {"type": "comment", "text": "کارت وارد ستون انجام‌شده شد."}
  ],
  "enabled": true
}
```

Supported trigger strings are `card_created`, `card_moved`, `due_soon`,
`label_changed`, `checklist_completed`, `custom_field_changed`. The external
host must publish an event only **after validating the corresponding real
card change**, ideally within the same transaction. The rule engine does not
compare old/new task snapshots or schedule `due_soon` events itself.

`data` may contain only `fromColumnId`, `toColumnId`, `labelId`, `checklistId`,
`fieldId`, `priority`, `completed`, `dueWithinDays`. Values must be short strings,
integers or booleans. Up to eight conditions are matched by exact equality
against these fields; no regex, expressions, user input interpolation or
dynamic code is supported.

Only two action types run: `notify` (one to 20 usernames and fixed text up to
240 characters), and `comment` (fixed text up to 4,000 characters). Actions
are limited to five per rule, 100 rules per snapshot, 20 matching rules and
50 actions per event. Rules run in sorted ID order, and generated comments
do not recursively dispatch events. Rule owners must still hold admin access
at execution time; changed permissions cause a `skipped_scope` run record.
Even admin rules can send notices only to users with current project access.

**No arbitrary Python, shell, HTTP, webhooks, SQL, cross-project mutations,
task edits or scheduling** exist in this service. Those need separate reviewed
domain adapters, authorization and durable scheduler state. The generated
comment's actor is the verified event publisher; the `runs` ledger records
rule identity and outcome.

## Storage, retry, and integration contract

`empty_state()` produces a JSON-serializable envelope:

```json
{
  "schemaVersion": 1,
  "comments": [],
  "notifications": [],
  "activity": [],
  "watchers": {},
  "rules": [],
  "runs": [],
  "receipts": {}
}
```

The `receipts` dictionary remembers each `eventId` with a SHA-256 fingerprint
of `(actor, command)`, original project, action's authorization level and
original result. An identical retry returns `changed: false` with the
original result (including after JSON reload) if the user **still holds the
necessary permission**. Reusing an ID for a different command or actor is an
error. Keep receipts as long as the action could be replayed. Never prune
them while a client might retry. `validate_state` validates the envelope and
rejects unexpected keys, unsupported schema versions and invalid records.

**Adapter requirements before switching on v0.4/v0.5 UI:**

1. Keep collaboration records, event receipts and task changes in one
   authoritative host database or durable snapshot. Serialize read/validate/
   `apply_command`/commit under a single host lock or SQLite transaction.
   For a new SQLite schema, use unique constraints for event IDs, comment IDs,
   notification IDs and rule run IDs. Preserve old JSON data during migration.
2. Obtain `actor` from an authenticated LAN session (or trusted solo-mode
   profile) and `now` from the host. Supply the **authoritative current**
   accounts, projects and cards. Do not accept any of these from a client.
3. For `event.publish`, validate the actual saved business change, create the
   event key from its durable change ID, then publish in the same transaction.
   Otherwise a malicious editor could claim a move happened when it did not.
4. Add authorized API routes in `lan.py`/`native_app.py`, with per-command
   input limits and HTTP `400` / `403` / `409` mapping for validation, access
   denial and concurrent updates, respectively. Never expose the full
   `collab` envelope or receipts to ordinary clients.
5. In the React UI, render comments as plain text or use an independently
   sanitized Markdown renderer. Escape user text and notification messages;
   never feed stored text into HTML, script evaluation or a shell.
6. Add migration, import/export and backup support for this state. The
   separate LAN accounts file and any account secrets require independent
   backup handling. Cross-device offline Drive continuation and actual Google
   OAuth authentication are outside this module's verification scope.

Test with `python -m unittest discover -s tests -p test_collab.py -v`; the
repository's existing `npm test` command also discovers these tests. Tests
cover authorization, scope isolation, role revocation, retry behavior,
validation, automation allowlists and activity integrity. They are domain
tests, **not** tests of a live LAN integration, physical two-device session,
Google authentication or persistent multi-process transactions.
