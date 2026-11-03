# Madar UX-01: rendered background contrast gate

Date: 2026-11-03. Base: `25a99ae9b32229968255f5187d1639586a48ea03`. Scope: a synthetic RIAL accounting UI in Chromium (Edge), real screenshots, no financial mutations, no live profile, no CSS or accounting source changes.

The previous computed-style method could not establish foreground/background contrast when a background had a gradient, an alpha layer, or another transparent ancestor. **Axe-core 4.14.0 returning zero severe violations did not prove those ambiguous text samples passed the project's 4.5:1 threshold.**

The updated `scripts/madar_ux_completion_audit_20261103.cjs` resolves ambiguous samples with a rendered raster measurement. It scrolls the actual text into view, waits for fonts and two paint frames, captures a normal viewport screenshot, hides **only the glyph fill** using a temporary `-webkit-text-fill-color: transparent` rule, captures the rendered background, restores the rule and captures a third screenshot. Chrome decodes all three screenshots into canvas pixel arrays. For every changed glyph pixel (at least eight required), it computes the WCAG relative-luminance ratio using the computed foreground color, its actual alpha where applicable, and the pixel's rendered backdrop. **The minimum unrounded ratio over all painted glyph pixels** determines the result; never a gradient midpoint or an averaged background. This captures ancestor background images and ordinary translucent background overlays without flattening them to an invented CSS color.

The measurement stays `BLOCKED` when the text is missing, clipped or outside the viewport after scrolling, the midpoint is occluded, images fail to decode, a group opacity/filter/blend makes the ink composite ambiguous, text glyphs cannot be identified, pixel alpha is untrustworthy, images do not match the CSS viewport, or original/restored raster pixels differ. Temporary masking is removed even when screenshots fail. Mixed-color wrapper elements are split into the elements that actually contain their own text; 1-pixel placeholders and content inside closed `details` are excluded as unrendered. The report stores text, method, foreground, worst pixel coordinates, rendered backdrop, minimum ratio, glyph coverage and explicit failure/block reason. It never writes screenshot pixels or finance records into Git.

### Reproduce

With an existing Vite/Playwright installation and local Edge/Chromium:

```powershell
node --test tests/madar_ux_rendered_contrast_20261103.test.cjs tests/madar_ux_acceptance_rules_20261103.test.cjs
$env:MADAR_UXQA_AXE_PATH='D:\CoS-Test\madar-uxqa-20261103\.qa-uxqa-tools\node_modules\axe-core\axe.min.js'
$env:MADAR_UXQA_WIDTHS='390,1440'
$env:MADAR_UXQA_THEMES='dark,light'
node scripts/madar_ux_completion_audit_20261103.cjs
```

The axe path is an example of the independently available local 4.14.0 package, **not** a portable dependency path. By default the runner first uses `node_modules/axe-core/axe.min.js` from its own worktree and falls back to `.qa-uxqa-tools/node_modules/axe-core/axe.min.js`; environment overrides are supported. A run with width/theme filters is diagnostic only: every omitted scope is recorded `BLOCKED` for UX-01/02/06. Run without those overrides for the full **390/560/768/1440 × dark/light** acceptance matrix. Each run writes an ignored `.qa-uxqa-20261103/acceptance.json`, with the tested Git source SHA. The script deliberately exits nonzero on any missing, failed or blocked acceptance criterion.

### Real integrated source baseline findings

At `25a99ae`, on 390 and 1440 in both themes, 24 axe checks (home plus five invoice wizard stages × four scopes) reported **zero serious/critical violations**, while the independent project-normal-text threshold found **UX-01 FAIL**, not PASS. Other UX criteria were PASS 8 / FAIL 2 in total, with UX-06 touch target size still failing. The failed text samples included:

| Text / target | Computed foreground | Worst rendered background | Worst ratio |
| --- | --- | --- | --- |
| Light invoice ID / customer / date/due field captions | `#758590` | `#F7FAFC` | **3.633:1** |
| Light inline Jalali hint | `#758590` | `#F7FAFC` / `#F3F6F9` | **3.633:1 / 3.511:1** |
| Dark inline Jalali hint | `#758590` | `#262C38` | **3.677:1** |
| Light sticky amount caption | `#758590` | `#FFFFFF` | **3.808:1** |
| Light 390 wizard lines sticky amount caption | `#758590` | `#6687C1` | **1.052:1** |
| Dark 390 wizard lines sticky amount caption | `#BAC8D9` | `#99B7F0` | **1.189:1** |

The 390 sticky caption readings indicate an actual changing/blue backdrop in that state. Inspect the responsive footer and action overlap as well as foreground color; the screenshot alone does not establish the CSS rule responsible. The prime owns any CSS changes and must rerun the **new source SHA** after merging; none of these findings proves the updated production CSS remains defective.

Synthetic browser tests explicitly cover safe dark gradients, failing mixed-light gradients, semi-transparent background layers, low-alpha text, nested scrolling, closed details and 1px placeholders, group-opacity fail-closed handling, screenshot exceptions/mask restoration and unstable repaint. Pixel-based contrast is not a complete WCAG or screen-reader certification; complex paint types deliberately remain unresolved rather than receiving a guessed PASS.
