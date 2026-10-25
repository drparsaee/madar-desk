# Madar Desk: Iranian money display and entry (UI bridge)

Scope: `src/ir_money_display.js`, `src/accounting_workspace.jsx`,
`src/accounting_workspace.css`, `tests/ir_money_display.test.cjs`,
`tests/accounting_workspace_ui.test.cjs`. This is a **legacy TOMAN host adapter**.

## Current behavior

- Accounting workspace presents a **تومان / ریال** selector. The default is
  **TOMAN**, matching existing snapshots and previously persisted documents.
  The selection lives only for this mounted UI session; it does not update
  company policy, persisted preferences, snapshots, the financial ledger or the
  `accountingRead/accountingCommand` wire protocol.
- All existing ledger, party, invoice, settlement, purchase intake, balance,
  trial balance, profit/loss and account statement *amount renderings* use the
  selected unit. The legacy host returns numeric TOMAN. The formatter validates
  safe integer values and multiplies by `10n` for RIAL without floating-point
  arithmetic. Values use Persian numerals and grouped thousands. Unknown,
  fractional or unsafe JS numbers display an explicit fallback.
- Forms use the selected unit for task-sale price, supplier intake price,
  standalone invoice unit price/discount/explicit tax, customer receipt,
  supplier payment and owner fund deposit. Non-amount quantities remain
  quantities.
- `parseMoneyInput(text, unit, {allowZero})` requires a nonnegative, correctly
  grouped whole number in ASCII/Persian/Arabic digits, with optional `,` or
  Arabic thousands `٬`. Malformed grouping, separators, decimals, exponent
  notation and sign prefixes are rejected. TOMAN returns an existing-host
  positive integer (discount/tax may explicitly allow zero).
- RIAL entry must be exactly divisible by **10**. For example, 150 RIAL becomes
  15 TOMAN in the `accountingCommand` payload, but 155 RIAL is **rejected**;
  the UI displays an explanation and never rounds or truncates it. The TOMAN
  backend cap `1,000,000,000,000,000` is checked with BigInt before conversion
  to a bounded safe JavaScript integer.
- Changing the selector converts recognizable typed monetary fields exactly.
  Unrecognized, partial, out-of-range or RIAL nonmultiple-of-10 typed values
  are cleared with a visible notice. Existing task price references pulled
  from cards are explicitly converted from legacy TOMAN on card selection.
  The unit switch is disabled while a command is in flight.
- A permanent notice near the header explains the temporary TOMAN ledger
  boundary; the selector never claims native RIAL support.

## Example boundary

```text
UI selected RIAL  | typed 1,250 ریال | parser -> 125 تومان | host payload 125
UI selected RIAL  | typed 1,255 ریال | parser -> ERROR     | no posting
UI selected TOMAN | typed 125 تومان   | parser -> 125 تومان | host payload 125
Read host amount  | 125 TOMAN         | RIAL display -> ۱,۲۵۰ ریال
```

## Verification performed

- `node --test tests/ir_money_display.test.cjs tests/accounting_workspace_ui.test.cjs`:
  **27 passed, 0 failed**, using synthetic test values and SSR/static UI
  contract checks. Covered parsing, Persian/Arabic numerals, signs, grouping,
  nonmultiples-of-ten, overflow, unit switching, label disclosure, command
  call-site conversion and original accounting workspace tests.
- `vite build --outDir <Windows TEMP>/madar-ir-money-worker9-build --emptyOutDir`:
  **passed**. Existing Vite size warning for a chunk over 500 kB; no release
  package was built.
- No live GUI click-flow, production host/API round trip, persisted-document
  migration, real financial posting or full Python integration was tested.

## Future integration contract

1. The host must **continue** interpreting existing `accountingCommand`
   amount fields as integer TOMAN until a separately planned, versioned,
   tested migration establishes canonical RIAL and verifies each source unit.
   This UI bridge intentionally sends the original TOMAN command shapes.
2. On migration, add an explicit `source_unit`/`amount_unit` and host
   schema/version handshake. UI should refuse to submit against an unknown
   schema or silently reinterpret an old TOMAN amount as RIAL.
3. Bind display unit to an explicit per-company preference only after the
   company identity, ownership and persistence contracts are established.
   Do not infer currency from names, raw numeric values or old snapshots.
4. The future canonical RIAL ledger must address amounts not divisible by
   ten. Legacy host cannot represent them. Preserve precise frozen amounts
   and audit/migration provenance at the domain layer. The existing UI
   rejects them only because this current backend is TOMAN.
5. Extend end-to-end tests for input changes, selector switches, command
   confirmation and retry paths under the real mounted GUI/host. Tests in
   this tranche do not establish release or finance migration readiness.

## Known limitations

- Selector choice is ephemeral within the workspace; there is no
  per-company or per-user persisted currency choice.
- Embedded amounts inside narrative descriptions, imported free text, source
  documents, or a future chart or export are outside this adapter. There is
  no numeric chart on the current accounting reports view.
- The current engine cannot post RIAL amounts that are not multiples of 10.
  They must wait for the separately verified RIAL storage migration.
