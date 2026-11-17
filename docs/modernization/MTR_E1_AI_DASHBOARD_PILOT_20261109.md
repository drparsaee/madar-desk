# E1 AI usage dashboard | isolated React pilot | 2026-11-09

**Status:** Standalone source and synthetic tests. Baseline worktree HEAD: 32bd8ff. No existing app, UI, network or LAN host files changed. This component is not yet mounted or deployed.

## Files and API

New src/ai_usage_admin.jsx exports the named AiUsageAdminPanel and pure budget/snapshot validators. New tests/ai_usage_admin.test.cjs tests its markup, validation and mocked host interactions. This is the third new documentation file.

    AiUsageAdminPanel({
      command, projectId, isAdmin, users,
      cloudConsent: optional_preverified_hint,
      dir: "rtl" // optional "ltr"
    })

Required command(action, data, projectId) is an injected asynchronous host operation. The transport caller must construct versioned JSON, add manualAction:true to mutations and authenticate the LAN session. The host remains the authority for role, project grants, AI entitlement, audit and CAS; isAdmin is merely a presentation flag. The component invokes only grant_get, grant_set and cloud_consent on **explicit** user actions. There are no automatic host calls, model inference, downloads, provider dispatch, API keys, file uploads, billing or browser storage.

The administrator selects an eligible LAN editor/admin account and a provider. The UI requires explicit grant_get before enabling edits; null grant means new CAS version 0. The form has independent AI-enabled and cloud-enabled switches, integer-only monthly request/token/cost-micro ceilings, the loaded grant version, and a manual save button. Every save carries expectedVersion and a crypto.randomUUID-based eventId. Failed transport retries use the same ID unless inputs change. A response must match the submitted values and advance CAS by exactly one before the UI reports success. Invalid host response or stale scope cannot claim a save.

### Own cloud consent

Optional cloudConsent must be an exact five-field object containing:

    { preverified: true,
      projectId: "project-one",
      provider: "openai", // also gemini or anthropic, not local_ollama
      requestId: "32 lowercase hex characters",
      payloadDigest: "64 lowercase hex characters" }

This client prop is a **presentation-only preflight hint**, not proof of actual selected text, genuine click or authorization on the server. The user must explicitly tick a new checkbox before the single cloud_consent action. A successful consent intent cannot be re-submitted for that request during the current mount, including after changing props away and back. The UI never renders raw text, request IDs or digests; it never transmits a prompt to an external provider. The current in-process host pilot has no dispatch action.

## Accessibility and design

Vitrea existing variables are used: --vs-ink, --vs-glass, --vs-accent, --vs-muted, --vs-edge, with fallback colors. Focus-visible outline is scoped to the component. Form controls have associated labels, aria-invalid state, disabled fieldsets, status/error live announcements, explicit buttons and RTL by default. Optional dir=ltr reverses layout direction, while numeric fields retain LTR input. No extra CSS asset or dependency was created.

Only the already-supplied LAN account username and security role are displayed to an administrator for account selection. A username may itself be identifiable; the component does not display optional user display names, email, phone, profiles, client prompt text, passwords or customer PII, and does not persist those fields.

## Observed test scope

- node --test tests/ai_usage_admin.test.cjs: **21 tests passed, 0 failed**. Includes validation bounds, versioned host snapshots, RTL/LTR server-rendered HTML, labelled inputs, forbidden data not rendered, admin-only management, missing/invalid props, explicit read/write CAS, provider/cloud toggle separation, invalid limits, stable retry IDs, response/race fail-closed behavior, explicit one-use consent and no duplicate in-flight calls.
- node --check tests/ai_usage_admin.test.cjs: exit code 0.
- esbuild direct browser-target compilation for src/ai_usage_admin.jsx: success, without writing output into the repository.
- Vite main app build with a **unique Windows TEMP output directory**: exit code 0; 1692 modules transformed in 5.26 s; nonfatal warning for a JavaScript chunk larger than 500 kB. Because App.jsx was deliberately left unchanged, the main application bundle does not yet include this new component. The standalone esbuild compilation checks the component independently.

These are synthetic React SSR and simulated hook interactions, not a real browser with assistive technology, installed Windows WebView2, live LAN TLS, real admin accounts, budgets or cloud costs.

## Remaining gates

Do not equate manualAction:true, isAdmin or preverified:true with actual authorization. The eventual host integration must issue true session/project capability, enforce origin/CSRF/TLS and per-request manual intent, verify the exact selected text and its privacy constraints before considering any cloud transfer, and manage accurate model token/cost ceilings. The current adapter cannot independently prove that an opaque client digest represents safe selected text. No real cloud dispatch is exposed here.

No existing source, App.jsx, lan.py, stores, installed profile, actual customer records, credentials, commit, push or deployment were changed.
