# Madar Accounting 1.0.13 — Dashboard company/user isolation browser gate

**Scope:** synthetic headless Chrome + Vite against isolated Git base `90e331bd1b92c650de7a703af5618841944c59dc`.
**Implementation owner:** prime agent. This QA branch intentionally contains **only a new test and this document**, not the implementation fix.

## Source-grounded contract

- The host must supply `response.view.companyWorkspaceId`: an immutable, opaque **32-character lowercase hexadecimal** identifier. Do not key a user's card layout by `companyWorkspaceLabel` or `companyProfile.legalName`; different companies may have identical human-readable names.
- The preference namespace must bind both the **authenticated** `currentUser.username` and verified `view.companyWorkspaceId`. Unknown, missing, or untrusted identity must not fall back to a human-readable label or a shared global key. Preferences are local UI state only; they cannot write to financial ledgers.
- A successful host read may show the current book; a rejected/failed read or permission revocation must clear the previously rendered book's dashboard, financial amounts, and mutation CTA. It must not silently retain prior-company state while showing an error.
- A viewer must have no financial mutation path. The browser's fake `standaloneAccountingCommand` rejects all calls and records attempts. **This is UI-level regression evidence, not proof of host ACL enforcement**.

## Exact executable gate

Run at the candidate checkout with installed Chrome and Playwright:

```powershell
node --test tests/accounting_action_home_company_isolation_browser_20261103.test.cjs
```

The new test starts local Vite on a random loopback port, launches installed Chrome with fresh isolated browser contexts, and injects `window.madar` *before* the React app loads. The synthetic book contains an issued, entirely unpaid 123,000-rial invoice in company A and a separate 456,000-rial invoice in company B. Both companies share the exact visible name `Synthetic Same-Name Company` but have distinct opaque book IDs (`aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa` and `bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb`). No real DB, APPDATA finance profile, desktop host, installer, production service, or user records are opened. Dates use a fixed synthetic clock.

The eight required acceptance scenarios are:

1. Same user, **same display name**, distinct company IDs: customized cards in A survive reload, B starts with its own default layout, B customization persists independently, returning to A restores A's choices. Exactly two distinct preference keys, no label-key fallback.
2. Two authenticated usernames, same company ID: each user's card choices remain private across reloads; other user's changes do not alter the first user's choices.
3. Failed *initial* read because of denied permission: no dashboard, monetary values, or action links render.
4. Denied read on **full reload after a prior successful company A visit**: no previous financial values or action dashboard are rehydrated from saved display preferences.
5. Missing `view.companyWorkspaceId`: a read-only dashboard may render, but preferences must never persist under the company display name fallback.
6. `localStorage.getItem` throws while reading action-home preferences: the dashboard renders safe defaults and clicking a viewer navigation link issues zero accounting commands.
7. Previously loaded company A and editor rights, then switch context to company B with revoked finance access: clicking refresh must clear A's dashboard, old receivable and financial-create shortcut; zero mutation calls.
8. Previously loaded company A then generic read error on refresh: the old dashboard must disappear rather than survive with an error banner.

## Baseline execution (before prime's production patch)

**Command executed:** `node --test tests/accounting_action_home_company_isolation_browser_20261103.test.cjs`.

**Result:** 9 reported tests (one parent, eight browser subtests); **4 PASS, 5 FAIL**; no skips. The parent is FAIL because four subtests failed. Duration reported: **12,058.6853 ms**. This is a deliberate **red acceptance gate**, not a successful release or a claim of a fixed bug.

| Scenario | Base `90e331b` | Exact evidence |
| --- | --- | --- |
| Two company IDs, same visible label | **FAIL** | B inherited A's hidden card: expected 6 visible cards, actual 5 (`ensureHome`, test line 116) |
| Two usernames, same company ID | PASS | Independent user preferences in isolated Chrome context |
| Initial permission denial | PASS | No action dashboard rendered |
| Denied reload after prior success | PASS | No prior-company dashboard rehydrated |
| Missing company ID | **FAIL** | Local storage still wrote `viewer.one|Synthetic Same-Name Company` encoded key instead of refusing label fallback |
| Unreadable local card preference storage | PASS | Dashboard fallback and zero command bridge calls |
| Permission revoked after successful A read | **FAIL** | Old `.sac-ah` remains: expected 0, actual 1 (`test` line 257) |
| Generic read error after successful A read | **FAIL** | Old `.sac-ah` remains: expected 0, actual 1 (`test` line 275) |

**Source evidence at this baseline:** `src/standalone_accounting_workspace.jsx` builds `preferenceKey` from `currentUser.username + '|' + view.companyWorkspaceLabel` (lines 1541–1542), not stable ID. `refresh()` catches host read failures but does not clear `snapshot`/`latest` on failure (lines 840–855). These are identified in source; the runtime failures above are additional browser evidence.

## Integration and acceptance limits

After cherry-picking **only** the new test and document to the actual integrated candidate containing the prime's production fix, run the command again. **All 9 tests must PASS**. Do not alter expected assertions to accommodate a missing company ID or stale ledger. Existing accounting UI/browser suites and the production build must also remain green before release. This isolated red baseline alone says nothing about whether the patch in another worktree passes.

The browser stubs a trusted host response rather than testing the real host's registry validation, authentication or authorization. Manual installed-application QA, multi-machine behavior, real migrated Parsian accounts, and production release remain outside this test's scope.
