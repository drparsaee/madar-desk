# UX-06 touch target regression, 2026-11-03

Source baseline: integrated Madar 6cc045446b37a23bb217cda566d785e73aed4c9e.
The branch uses CSS-only production changes. This is a synthetic in-memory
accounting fixture, not a test of operational finance or a packaged EXE.

Run: node --test tests/accounting_touch_matrix_20261103.test.cjs
Local Chrome, Playwright, Python and Vite dependencies are required.
Optional MADAR_TOUCH_EVIDENCE_DIR writes screenshots and measurements.

Chrome coverage: viewport widths 390, 560, 768 and 1440 CSS px, light and
dark themes, simple and advanced modes, 16 combinations. All combinations
had 39 to 45 visible critical controls inspected, with observed minimum
width 44 CSS px, minimum height 44 CSS px, and no document-level horizontal
overflow. At widths up to 700px, the main simple navigation remained one
row in both modes. Search, display-mode buttons and Exit accepted keyboard
focus and rendered a visible focus outline after Tab.

Scoped controls include header search, Simple/Advanced, Exit, main navigation
and More, dashboard action buttons and card links. Checkbox marks, decorative
icons and unrelated forms are outside this target-size audit.

Screenshots: mobile 390 light/dark simple and dark advanced, and 1440
light/dark simple.

Limits: No user study, screen reader, installed WebView2, real ledger,
host mutation or native desktop install verification. Vite build yielded
the existing nonblocking large JavaScript chunk warning.
