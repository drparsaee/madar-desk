# UX-01 Chromium rendered-raster stability at the 768px breakpoint

**Task baseline:** official integration `057786a` (2026-11-03). **Ownership:** `scripts/madar_ux_completion_audit_20261103.cjs`, the dedicated synthetic browser test, and this QA document only. No CSS, accounting source, live profile or installer changes.

## Reproduction and cause

On unmodified `057786a`, a targeted Chromium/axe 4.14.0 run at width 768 in both dark and light modes reproduced **only** the final invoice wizard review-caption anomaly: UID `r68`, text `پیش‌نویس ذخیره‌نشده · مرحله ۵/۵`, `glyphPixels=558`, `unstablePixels=730`, `ratio=null`, reason `screenshot changed after removing text mask`. Other measured text was passing. The initial failure was not a WCAG contrast violation, but a failure to prove screenshot restoration was identical.

Root cause in the QA measuring procedure: it unconditionally ran `scrollIntoView({block:'center',inline:'nearest',behavior:'instant'})` before capturing **every** target, including an already-visible `position:sticky` footer. At the 768px layout breakpoint, that unnecessary forced scroll perturbed the sticky element's layout/paint between the original and restored frames. The correct fix preserves layout: **skip scrolling when the target is fully inside the viewport and its midpoint is not occluded**. Continue scrolling offscreen or occluded targets. Do not edit the element's styles or weaken raster validation.

The algorithm still captures before, masked-background and restored screenshots, and keeps its strict rule that **more than two changed pixels between original and restored images means `ratio=null` and `BLOCKED`**. No WCAG threshold was lowered, no unknown result is coerced to PASS and no masked or otherwise unstable screenshot is accepted.

## Validation on the unchanged integrated source

With the corrected QA helper, the independent in-memory accounting fixture and the same Chromium/axe version were used at width **768 in both themes**:

| Case | Measured status | Rendered caption ratio | Glyph pixels |
| --- | --- | ---: | ---: |
| Dark 768, invoice wizard review, `r68` | **PASS** | **12.965:1** | 558 |
| Light 768, invoice wizard review, `r68` | **PASS** | **9.450:1** | 558 |

All ten UX-01 measured checkpoints for these two viewport/theme pairs passed, and their related axe scans reported no severe failures. This was a **targeted diagnostic**, not proof that all eight viewport/theme combinations have passed: the gate deliberately marks the six omitted scopes `BLOCKED` for UX-01/02/06. A full integration rerun, with the scoped environment variables unset, is needed for the final acceptance decision.

The actual Chromium regression test additionally asserts that an already-visible sticky caption does **not** change the scroll position during measurement, whereas a visible but **occluded** caption still triggers a scroll to uncover it. It preserves all prior tests for failing gradients, alpha composition, hidden elements, screenshot exceptions and pixel instability, each of which remains fail-closed.

Example rerun with external axe 4.14.0 path when it is not installed in the local worktree:

```powershell
$env:MADAR_UXQA_AXE_PATH='D:\CoS-Test\madar-uxqa-20261103\.qa-uxqa-tools\node_modules\axe-core\axe.min.js'
$env:MADAR_UXQA_WIDTHS='768'
$env:MADAR_UXQA_THEMES='dark,light'
node --test tests/madar_ux_rendered_contrast_20261103.test.cjs tests/madar_ux_acceptance_rules_20261103.test.cjs
node scripts/madar_ux_completion_audit_20261103.cjs
```

The accepted complete run must remove `MADAR_UXQA_WIDTHS` and `MADAR_UXQA_THEMES` and produce a source-SHA-backed `.qa-uxqa-20261103/acceptance.json`. Use the report to distinguish test-scope `BLOCKED`, contrast `FAIL` and actual `PASS`.
