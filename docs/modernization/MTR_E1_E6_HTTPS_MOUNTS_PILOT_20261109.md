# E1 Radar / E6 internal inbox TLS mounts (isolated MadarHost pilot)

All routes described below are **default OFF**. They exist only in the
source worktree and require the trusted Python process to call the mount
methods **after the existing host HTTPS listener starts**. These mounts
do not alter installed MadarHost, launch another server, modify real users,
issue messages to external recipients or contact Taraz.

| Phase | Trusted mount | Opt-in route | Operations |
|---|---|---|---|
| E1 | `LanService.mount_radar_crm_pilot(RadarCrmStore, org_id=trusted)` | POST `/api/radar/v1/command` | Explicit human CRM contact create/edit/note/followup/read/soft delete with CAS and actor/project ACL |
| E6 | `LanService.mount_mtr_notice_pilot(InternalNotificationStore, org_id=trusted, trusted_event_source=host_journal)` | POST `/api/mtr-notices/v1/command` | Publish an existing trusted internal event key, list current recipient inbox, explicit mark-read |

Both require an active TLS socket and original LAN bearer account session.
CRM takes a strictly parsed maximum **8192-byte** command; the notice route
takes maximum **4096 bytes** and rejects duplicate JSON fields, extra command
keys, and client-provided privilege/organization identity. Mount methods
are trusted Python-only and never HTTP operations. The returned status is
redacted to the account's current project/field access. Neither adapter
implements an autonomous scheduler or real finance posting.

**Critical E6 difference:** the notification publisher requires a trusted,
authenticated and persisted host event source, and current user registry
flag `internalNotificationsEnabled`. The normal installed user-management UI
currently does **not** manage that flag or the private-field allowlist. The
HTTPS test sets it manually **only in disposable fake accounts**. Without
an independently verified event journal, a route declaration alone does
not authenticate a financial event and must not imply a Taraz receipt.

E1 retains a user-reported `occurredAt` for idempotency replay; the host
needs its own durable event timestamp scheme before full operational
acceptance. CRM data is stored in its own local synthetic SQLite DB; no
official Taraz party is created or automatically linked.

## Evidence commands

```powershell
py -3.12 -B -m unittest -q tests.test_radar_lan_http_pilot tests.test_radar_host_adapter tests.test_radar_crm_store
py -3.12 -B -m unittest -q tests.test_mtr_notice_lan_http_pilot tests.test_mtr_lan_notification_adapter tests.test_mtr_internal_notification_store tests.test_mtr_internal_notification_policy
```

The HTTP tests exercise **real pinned TLS on loopback** using the repository's
explicitly public test-only certificate and disposable `TemporaryDirectory`
data. A successful loopback pilot is neither an installed EXE test nor an
approval of E1/E6 release gates. No production database was read or changed.
