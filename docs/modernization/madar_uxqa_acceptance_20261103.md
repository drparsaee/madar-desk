# Madar UX-01…10 | automated acceptance gate

**Baseline for this run:** LocalForge `main` commit `6bf687b4b643fb26b0186dc1b0d425f1b2ad0c29`.
**Date:** 2026-11-03. **Environment:** Vite production bundle hosted only on localhost; headless Microsoft Edge (Chromium); exact `axe-core@4.14.0`; in-memory synthetic RIAL ledger containing one issued and unpaid invoice (300,000 RIAL), one draft, one customer and one supplier.

This is a **red acceptance gate**, not a declaration that UX work is complete. The source files, operating-user profile, accounting database, installed EXE and canonical `main` were not modified by the runner. A synthetic bridge deliberately rejects every accounting mutation. Authorization tested here is visible UI capability gating, **not** native-host authorization or data filtering.

## Run exactly the same QA

In a clean Windows worktree, with Python, Node, local Microsoft Edge and Playwright available:

```powershell
npm ci --ignore-scripts
npm install --prefix .qa-uxqa-tools --no-save --no-package-lock --ignore-scripts axe-core@4.14.0
node --test tests/madar_ux_acceptance_rules_20261103.test.cjs
node scripts/madar_ux_completion_audit_20261103.cjs
```

If Playwright is not resolvable from `%APPDATA%\npm\node_modules\playwright`, set `MADAR_UXQA_PLAYWRIGHT` to its installed module directory. `MADAR_UXQA_AXE_PATH` may point to `axe.min.js` from an exact 4.14.0 package. There are no hardcoded worker-worktree paths. The script rebuilds the Vite production bundle and uses an ephemeral localhost preview; it closes the browser and preview server at exit. The final command **must return exit code 1** when any criterion fails, is missing, or remains blocked. A setup or fixture error produces `BLOCKED`, not a fake passing test.

The complete untracked report is `.qa-uxqa-20261103/acceptance.json`, with scope, measured CSS pixels, source SHA, axe violations and each individual verdict. Synthetic screenshots, when taken, also remain in that ignored folder. No screenshot or trace of operational finance data is committed. `tests/madar_ux_acceptance_rules_20261103.test.cjs` validates the verdict logic independently.

## UX acceptance contracts and measured baseline

| ID | Result on `6bf687b` | Evidence and criterion |
|---|---|---|
| UX-01 | **FAIL** | `axe` reports actual `color-contrast` violations in invoice composer. The project asks **≥4.5:1** for normal content text. Some manually sampled backgrounds have gradients/transparency, so their exact computed contrast remains `BLOCKED` for human pixel inspection. |
| UX-02 | **FAIL** | Full-document axe 4.14.0 scans of overview and composer at **390, 560, 768, 1440** in both themes. Serious color contrast appears in dark 390 (1 node), light 390 (2 nodes) and light 560 (1 node). Acceptance is **zero serious/critical** per checkpoint; axe `incomplete` remains separate. |
| UX-03 | **PASS, scoped** | Five named destinations (sales, purchases, receipts/payments, reconciliation, reports) reached through **≤2 actual ribbon clicks**. Five `Ctrl+K`/Enter keyboard routes also reached the intended pages. This is a scripted path, not a novice-human usability study. |
| UX-04 | **PASS, scoped** | The in-memory issued-but-unpaid receivable is represented in the overview's actionable open-document area. Monetary accounting correctness beyond the fixture was not re-audited. |
| UX-05 | **FAIL** | In 390 and 560 widths, light and dark, an active invoice action is visible initially and at the end of the form but **not at its mid-scroll position**. Draft confirmation and refusal-to-discard steps pass separately. Support new guided-step `.sac-wizard-sticky-footer` controls in this gate. |
| UX-06 | **FAIL** | Actual critical button rectangles measured on both overview and invoice screens. Controls shorter than the project's **44×44 CSS px** touch target fail; this is stricter than the WCAG 2.2 minimum target-size requirement. |
| UX-07 | **FAIL** | No overall horizontal document overflow was observed in the 16 measured screens, but narrow ribbon sections overflow without a discoverable accessible scroll/more control. This is an explicit separate failure. |
| UX-08 | **MISSING / partial** | Four scripted keyboard interactions reach and operate real controls; report filter is `BLOCKED` because the synthetic `accounting_core` view lacks `financialReports`. Current search covers **section navigation**, not authenticated record-level search, and a shortcut/help guide control is absent. Viewer/editor UI quick-create gating passes; host-enforced search results were not audited. |
| UX-09 | **MISSING / partial** | Draft versus issued invoice actions match their state; cancelling an unsaved navigation keeps typed content and sends zero backend commands. A novice guide is absent for both simulated restricted roles. Financial posting/reversal must still be checked with an isolated host fixture. |
| UX-10 | **MISSING** | Existing Ribbon/sidebar route buttons do not expose unique stable `data-route-id`, `data-ux-route`, `data-accounting-tab`, `data-tab-id` or equivalent `aria-controls` identity. The gate requires route identity independent of changeable Persian display text. |

## Interpretation and release limits

- The audit covers **16 axe-backed DOM states** (overview and invoice composer × 4 widths × 2 themes), plus keyboard routes, restricted-role views and simulated unsaved changes. It does **not** certify all 18 accounting screens or the installed WebView2 build.
- The test deliberately records `PASS`, `FAIL`, `MISSING` and `BLOCKED` separately, then computes the final UX status. Any absent or unmeasured required feature prevents a full pass. One criterion can contain passing safety subchecks while its overall status is still missing.
- **Axe is not a full accessibility certification.** Its incomplete checks, gradient-background contrast, actual screen-reader behaviour, physical touch, cognitive task difficulty and business-relevant financial permissions require additional review.
- The synthetic host has **no `view.financialReports`**, so report-form operation cannot be claimed passed or broken by this run. The native host must be substituted with a distinct authorized test fixture before issuing a result on that particular workflow.
- Source branches delivering new navigation IDs, guided invoicing, global search or other controls can be merged into the prime's integration worktree and this audit rerun. The verdict must come from the **new run's source SHA and measured output**, not a claim inherited from this baseline.

## Integrated UX 1.0.13 rerun: `7d45c11643f7d9082221750e97e3ad673161e7fe`

The baseline table above remains historical evidence for `6bf687b` only. The revised runner (`format: 2`) targets the **new** default simple navigation; it does not wait for hidden advanced Ribbon buttons. `Ctrl+K` now opens a labelled dialog with a combobox and options. Desktop advanced Ribbon is explicitly checked after changing mode; mobile navigation must preserve an accessible **More** control. The six actual home actions are tested at all eight width/theme combinations, with no more than one click to reach their respective workflow.

The synthetic fixture now includes a legitimate read-only `financialReports` projection produced by the production `standalone_financial_report_host.attach_verified_reports` adapter, with a reconciled 300,000-RIAL debit/credit ledger. This permits the fifth reports workflow to be inspected without inventing sums or touching a database. The UI's record index must still be populated by the production integration wiring. The runner checks lookup of both `UX-ISSUED-001` and `CUSTOMER-UX`, without treating a navigation-only search as a passing record search.

The invoice is audited at all **five actual stages** (document, lines, tax, due/payment, review), including validation before advancing, preservation of edited invoice ID and line description when returning to earlier steps, visible financial-impact warning before save, 44 px targets, action-bar visibility and zero synthetic backend mutation calls. The runner takes **48 axe-core 4.14.0 scans** across four widths (390/560/768/1440), both themes and six UI surfaces per combination: home plus each of the five invoice stages. Each scan records serious/critical violations and `incomplete` separately.

**Measured results on `7d45c11` before prime's pending `searchView`/`onSearchSelect` integration:** UX-03/04/05/07/09/10 PASS within automated synthetic scope; UX-01/02/06 FAIL; UX-08 MISSING. Full acceptance correctly exits with code 1. The exact counts and source SHA are generated in `.qa-uxqa-20261103/acceptance.json` by each fresh run.

Specific open source fixes required before a green rerun:

- **UX-01 / UX-02:** in the light invoice wizard, `.sac-wizard-heading-top > div:nth-child(1) > span`, `.sac-wizard-step-hint` and `.sac-wizard-sticky-amount > small` produce serious `color-contrast` findings. Desktop/medium `.sac-nav-search-trigger` also produces serious axe `label-content-name-mismatch`. Target is zero serious/critical in each checkpoint, and ≥4.5:1 for normal text. Backgrounds with translucency remain separately unresolved until their rendered contrast can be reliably measured.
- **UX-06:** 390 px critical search trigger measures about 38×36 CSS px; simple/advanced display toggles roughly 31×30 and 43×30; exit about 43×36; some overview buttons are only 35–38 px high. The project design target is at least 44×44 CSS px for critical controls.
- **UX-08:** only section results appear in the global search until the host-authorized company `searchView` and role-gated `onSearchSelect` are actually wired. Merely rendering an input that mentions invoice/customer/account does not meet the record lookup requirement. Native host ACL remains a separately required release gate.

**Limitations:** These are headless browser observations on a synthetic RIAL fixture, not verified native WebView2 / real user acceptance or proof of native permission enforcement. One or more individual contrast samples may be `BLOCKED` for complex/translucent backgrounds even when the overall UX-01 verdict is `FAIL` due to verified axe violations. No source edits, accounting host calls, or financial persistence were made by the QA repair branch.
