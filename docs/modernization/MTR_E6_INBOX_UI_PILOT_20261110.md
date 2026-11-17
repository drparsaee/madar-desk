# E6 opt-in internal-only inbox panel, client-side wiring (host still opt-in)

**Original UI pilot, 2026-11-10:** scope was only NEW
`src/mtr_internal_notice_panel.jsx`, NEW
`tests/mtr_internal_notice_panel.test.cjs`, and this NEW document.
In that initial pilot, no existing code, `App.jsx`, LAN adapter, host,
profile, native program, production service, installed EXE, network or
distribution was modified. The owner subsequently authorized a **separate**
client bridge and App UI wiring task, documented at the end of this file.

## Actual endpoint reviewed (READ-ONLY)

Source of contract:

- `lan.py:1620-1627`: optional route
  `POST /api/mtr-notices/v1/command` exists only when an E6 notice adapter
  has been explicitly mounted on an HTTPS LAN host.
- `lan.py:1673-1684,1702-1723,1756-1788`: incoming request must use a
  current authenticated server session, JSON and body of at most 4096 bytes;
  exact envelope is `{schemaVersion:1,action,params}`. `list` accepts
  `{projectId?,limit?}`, `mark-read` exactly
  `{noticeId,manualAction:true}`. `publish` also exists on the host but
  the panel **does not expose or invoke it**. Response for successful list
  and mark-read is `{schemaVersion:1,result}`. Client must **not** send a
  forged actor, organization, recipient, role or permission flag.
- `mtr_lan_notification_adapter.py:316-341`: host revalidates current
  authenticated account, live project grants and opt-in
  `internalNotificationsEnabled` on every list/mark request. It supplies
  the acting principal itself. This UI cannot replace these host checks.
- `mtr_internal_notification_store.py:383-424,426-471`: list `limit`
  is an integer **1..100**, ordered newest first, with optional project filter.
  There is **no server-side page/offset/cursor**. Rows include
  `notice_id,project_id,channel:'internal_only',event_kind,is_read,read_at`
  as well as other internal metadata and optional role-redacted text. Mark
  returns `{notice_id,marked_read:boolean,already_read:boolean}`.
- `src/teamplus.jsx:214-305`: current `NotificationsDialog` is the
  existing general collaboration notification interface, which loads on
  dialog mount and renders freeform messages. The new E6 panel is **separate**
  because no implicit read/on-mount, freeform external/body rendering or
  automatic host publication is appropriate in this pilot.

## Component API and behavior

`<MtrInternalNoticePanel command={authenticatedHostCommand}
projectId={selectedProjectId} limit={50} pageSize={10} />`

`command(envelope)` must be a **trusted, already-authenticated host bridge**
injected by a mounting integration. Its only duties for this pilot are
to forward one exact E6 JSON envelope, return the parsed successful host
envelope, and throw on transport/HTTP errors. It **must** independently manage
HTTPS/certificate pinning, session/bearer, current grants, timeouts and
revocations. The React panel neither fetches credentials nor establishes
TLS, and no callback is invoked on mount.

Controls and boundaries:

1. `projectId` is mandatory and syntactically checked against the server
   identifier convention. List request includes this exact `projectId`
   and an integer `limit` between 1 and 100. A local `pageSize` must be
   between 1 and 20, not exceeding `limit`. Invalid configuration disables
   the UI, fail closed. **A client-supplied project is a filter, not an ACL.**
2. Manual **«دریافت اعلان‌ها»** issues exactly
   `{schemaVersion:1,action:'list',params:{projectId,limit}}` and requires
   `{schemaVersion:1,result:[...]}`. It checks every row's exact
   `project_id`, `internal_only` channel, unique positive integer ID,
   supported event kind and consistent read state. A single invalid/foreign
   item rejects the entire response, with no partial data displayed.
3. A validated list is **project/host-callback/limit/page-size/generation
   scoped**. On switching project, callback or bounds, older rows disappear
   immediately. Any in-flight response from the preceding generation is
   discarded, even after switching back to the original project. Errors
   show generic Persian explanations, never raw host exceptions or tokens.
4. Manual **«خوانده شد»** issues exactly
   `{schemaVersion:1,action:'mark-read',params:{noticeId,manualAction:true}}`.
   Ack must match that notice and must truthfully indicate either
   `marked_read` or `already_read`, not both/neither. The UI changes to read
   only after accepted ack; ambiguous failure does **not** auto-resend.
   One in-flight operation at a time, completed-ID tracking and immediate
   button disabling reduce duplicate clicks.
5. The UI **whitelists only** `notice_id` (internal React key/mark argument),
   `event_kind` (mapped to fixed Persian labels) and `is_read` for state.
   It never keeps/displays the raw row: no actor, organization, recipient,
   request/amendment/reference IDs, deficiency details, raw status,
   finance/receipt/document labels, links, email, SMS or provider data.
   This means some legitimate host-granted detail is deliberately suppressed.
6. The **page** buttons only slice the fetched bounded list. They neither
   request older notices nor imply that the first 50/100 are the complete
   inbox. The text states this limitation. The section defaults to RTL,
   uses real buttons and explicit headings/labels, has keyboard
   `:focus-visible` styles and `role=status/alert` live feedback.

## Execution and observed validation

```powershell
node --test tests/mtr_internal_notice_panel.test.cjs
```

**Observed: 12/12 PASS, exit code 0.** Node's built-in test runner uses the
installed `esbuild` with `write:false` to compile the actual JSX in memory;
`react-dom/server` performs real React SSR of the panel. A deterministic
hook-state test harness invokes the **actual component event handlers** with
asynchronous host-command fakes. This is more than source-string matching.

Covered positive and negative cases: accessible RTL SSR with zero host
request on initial mount; invalid project/bounds/command fail closed;
exact list and mark-read envelopes with no client authority fields; no raw
finance/recipient/actor leakage; foreign project/duplicate IDs/unknown kind/
oversized result and invalid response shape rejected; local pages capped
without new host requests; simultaneous double clicks issue one operation;
accepted first/read-replay ack; wrong/missing/ambiguous ack rejected;
lost/uncertain ack does not auto-retry or expose error text; stale response
after project switch and return discarded; replacing the authenticated host
callback invalidates previously rendered rows and old action handlers; a
late mark-read acknowledgement cannot restore data from the prior project.

## Original pilot's outstanding integration/security acceptance

**At the original UI-only checkpoint, UNMOUNTED.** No import, route, menu
entry or automatic mount in `App.jsx` existed at that checkpoint. The
current collaboration `NotificationsDialog` was left unchanged. This was
addressed only on the *client side* by the following separately authorized
work; the E6 **host adapter remains explicitly opt-in and not mounted**.

The current LAN `list` response **has no project-scope or session-scope
echo**. The panel validates every row's project and rejects stale responses
locally, but cannot authenticate an empty list's scope or prove that the
injected callback used the intended user/org/session. This is strictly a
host-side contract and future integration gate, not an implicit UI proof.
Likewise mark-read response has only a notice ID/ack flags, not a project echo.

React SSR and in-memory hook tests do not prove actual installed UX,
screen-reader/browser behavior, WebView2, reconnect/timeout handling, physical
LAN/TLS trust, notification opt-in account administration, multi-user grants
or E6 event-journal provisioning. No external sends, official Taraz posting,
real finance receipt or installed service were tested. The broader E0-E7
functional acceptance and deployment gates remain OPEN.

## Owner-authorized follow-up: Windows native bridge + App wiring

**Implemented in source only, on 2026-11-10.** Authorized files:
`native_app.py`, `src/App.jsx`, NEW
`tests/test_mtr_notice_desktop_bridge_20261110.py`, NEW
`tests/mtr_internal_notice_app_wiring.test.cjs`. No edit to the existing
notice backend/store, `lan.py`, `src/teamplus.jsx`, or the prior E6 panel.
The pre-existing dirty modifications from other workers in the first two
files were preserved; there was no reset, commit, push or install.

### Windows bridge contract

- `Bridge.mtrNoticeCommand(envelope)` is explicitly exposed through
  `JS_BRIDGE`. It accepts only exact
  `{schemaVersion:1,action:'list',params:{projectId,limit}}` or
  `{schemaVersion:1,action:'mark-read',params:{noticeId,manualAction:true}}`.
  Project ID syntax is bounded; list limit is integer 1..100; notice ID is
  a positive bounded integer. Extra fields, including actor, org, role,
  recipient or any apparent host-authority proof, are denied *before*
  transport. There is no `publish` action.
- It requires `connection.mode='client'`, no local LAN host,
  `_validate_lan_target(url)` with actual `https` scheme (never HTTP,
  including loopback), the full 64-character SHA-256 certificate fingerprint,
  an 8..512-character current session token, connected network state and a
  host-returned user identity/role/project grant. Only then it uses the
  **existing** `_remote_request('/api/mtr-notices/v1/command',envelope)`
  transport. That existing function invokes `pinned_https_json` for HTTPS;
  this E6 wrapper forbids its general HTTP alternative.
- After the host response it rechecks the same endpoint, pin, token, network,
  user/role, grant snapshot and absence of a local host, denying stale
  session/permission changes (including mutable grant changes). Server-side
  bearer authentication, live grants and recipient ACL remain essential:
  the desktop bridge does not forge or issue host privileges.
- The only successful **list** result sent to WebView2 is a fresh array of
  `notice_id,project_id,channel:'internal_only',event_kind,is_read,read_at`;
  it must match the current recipient and selected project, support only
  the three established event kinds and contain unique, valid notice IDs.
  The only successful **mark-read** result is a matching note ID plus
  mutually exclusive `marked_read` / `already_read` booleans. Unknown
  fields never survive, including raw finance state, status, actor, receipt,
  request, documents, phone/email, links or arbitrary note text.

### App integration

- The opt-in E6 button appears only inside a **native Windows client** with
  a current connected HTTPS status, full valid fingerprint, usable host API,
  and an explicitly selected project present in the existing permitted
  project list. It is separate from the existing general notifications bell.
- User click opens a dedicated `Modal` containing the prior
  `MtrInternalNoticePanel`, with stable memoized authenticated bridge
  callback, explicit close and the existing manual receive/mark controls.
  The component neither loads on mount nor auto-sends on session startup.
  Scope is tied to the actual `lanStatus` object reference and selected
  project: a refresh, changed session, changed account/grant or different
  project immediately hides the old modal; the callback also rejects stale
  actions. All successful host payloads are presentation-only.
- This does **not** mount or turn on the server's E6
  `MtrLanNotificationAdapter`. The operator must separately configure it
  on a TLS host and enable `internalNotificationsEnabled` on authorized
  accounts. With no host mount, the button may open in a connected client,
  but a manual list attempt receives a generic error (route disabled).

### Exact offline synthetic tests

```powershell
py -3.12 -B -m unittest -v tests.test_js_bridge_surface tests.test_mtr_notice_desktop_bridge_20261110
node --test tests/mtr_internal_notice_app_wiring.test.cjs tests/mtr_internal_notice_panel.test.cjs
```

**Observed results:** Python **11/11 PASS, exit 0** (10 new synthetic
bridge tests plus the existing JS bridge surface test); Node **17/17 PASS,
exit 0** (5 new App wiring/guard/compile tests plus 12 earlier E6 panel
SSR and event tests). The complete `App.jsx` import tree, including CSS,
was compiled **in memory only**, using esbuild `write:false`,
`outdir:'in-memory-mtr-e6-check'` and the test-only `.css` empty
loader. No built installer/application assets were written.

The Python tests instantiate `Bridge.__new__(Bridge)` with deliberately
synthetic connection/token/user and monkeypatch **only**
`_remote_request`. They never create a profile, instantiate a host,
run a socket, authenticate a real account, or contact a URL. Tests cover
exact bounded request and returned allowlist, rejection of solo/server,
loopback HTTP, invalid fingerprint, absent token, off-network mode,
untrusted fields, unknown/foreign responses, duplicate notice IDs,
grant violations and mid-flight session/pin/user changes.
In-place mutation of the host account's project grant list is specifically
tested; a copy of the grant snapshot is compared before returning data.
HTTP/host exception bodies are replaced by a generic E6 error before they
can expose a raw receipt or account value to the renderer.

Node tests run a no-output-path **in-memory esbuild compile** of the real
`App.jsx` import graph plus the E6 panel, execute the pure client-eligibility
guard with a synthetic LAN status, and inspect scope, modal, callback and
legacy notification separation. The prior E6 component SSR + actual event
handler tests remain independently runnable.

**Limitation:** source-level UI wiring and a synthetic method-level test
are not installed integration acceptance. No real WebView2 command bridge,
pinned HTTPS request to a mounted E6 host, offline/reconnect session,
multi-PC grants, user provisioning, browser screen-reader journey, installer
or Taraz financial receipt was exercised. Server `list` does not echo
session/org scope for an empty list and `mark-read` does not echo project;
only the authenticated host can supply those guarantees. E0–E7 overall
functional acceptance remains OPEN pending explicit host provisioning and
installed end-to-end testing.
