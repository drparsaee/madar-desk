# Installed Madar → Taraz local proposal bridge: bounded evidence (2026-11-10)

## Exact goal and non-goals

Owner reprioritized **Madar–Taraz connection now**; Radar moves behind core finance, with later optional in-product Persian AI for novice Taraz/Radar users. This record covers **same-Windows-user local manual proposal handoff**, not official accounting integration or cross-PC networking.

## Checked installed programs (read-only)

| Shipped application | Installed relative to `%LOCALAPPDATA%/Programs` | SHA256 of EXE |
|---|---|---|
| Madar Desk | `MadarDesk/versions/1.0.26/Madar-Desk.exe` | `9bb1471944fc4b31aece7470e9d433fb68e207653d865ca3881c8d5654c943a4` |
| Taraz | `Taraz/versions/1.0.0/Taraz.exe` | `de5005579039bd86890c1dca1f5f1d9c760e6c47579a42f649f80096f158e70c` |

Both archives contain the relevant compiled UI methods and Python backend modules: Madar `tarazIntegrationStatus`, `tarazIntegrationQueue`, `taraz_exchange`; Taraz `tarazIntegrationList`, `tarazIntegrationReview`, `taraz_integration`. **The installed Madar v1.0.26 does not include the later source-only `tarazIntegrationPrepare` and `tarazIntegrationHistory` methods.** It must not be called a production bidirectional status/finance connector.

## Real shipped-backend compatibility, disposable fixture only

Execute from the isolated Madar worktree:

```
py -3.12 -B scripts/qa_installed_madar_taraz_bridge_20261110.py
```

This SHA-pins both installed EXEs, extracts their *actual packed* Python integration and native API **method bytecode** into a disposable Python process, verifies bundled UI method references, overrides `APPDATA`, `LOCALAPPDATA`, `HOME` and `USERPROFILE` with a `TemporaryDirectory`, and exercises:

1. Call packaged Madar's actual `Bridge.tarazIntegrationStatus` and `Bridge.tarazIntegrationQueue` method bytecode on a synthetic bridge/card; ensure `postingPerformed=false`.
2. Call packaged Taraz's actual `TarazAPI.tarazIntegrationList` on the shared disposable inbox, with an isolated fake authenticated instance. Verify its method invokes the authentication gate before listing.
3. Call packaged `TarazAPI.tarazIntegrationReview` as `reviewed` or `rejected` with a synthetic editor-role gate; ensure role denial before success and `financialEventCreated=false` after it.
4. Verify a processed request no longer appears in the pending inbox.

Observed exit **0** and JSON with `installedExecutableHashesMatched=true`, `installedUserInterfaceAssetsContainBridgeMethods=true`, `packagedNativeBridgeMethodsExercised=true`, `tarazNativeAuthAndEditorRoleEnforced=true`, `shippedBackendsConnected=true`, `manualReviewAndRejection=[reviewed,rejected]`, `ledgerPosted=false`, `realProfileAccessed=false`, `uiOrNetworkTested=false`. The synthetic `TarazAPI` instance's `_require_authenticated` function is a **test double**; its guard-invocation result does *not* certify real login, finance-role identity or installed UI navigation.

Separately, the detached current sources exercised 16/16 related source-level tests including consent, cross-project filtering, corruption and duplicate-ID handling. These are not tests of packaged v1.0.26's later missing status UI.

### Isolated installed Madar WebView2 smoke

The independent `scripts/qa_installed_madar_gui_bridge_20261110.py` launches the **SHA-pinned installed Madar EXE** with disposable APPDATA, LOCALAPPDATA, TEMP and WebView2 cache, uses the built-in `MADAR_QA_REPORT` hook and closes only the owned QA process/window. Observed exit **0**, `installedMadarGuiMounted=true`, `realProfileAccessed=false`, `tarazOrFinanceAccessed=false`. A further run with an explicitly seeded **synthetic board and four sample cards** reported `renderedCardCount=4`, `renderedStageCount=5`, yet **`packagedTaskEditorObserved=false`**; the packaged QA auto-click did not open the drawer. Therefore the actual installed send-button interaction remains *unverified*, even though the packed UI asset and native methods are present and the packed backend roundtrip passed. No installed Taraz GUI was launched because the shipped program requires a verified pre-existing accounting book and performs startup backup; testing it against the owner's live profile would violate the isolation boundary.

## Gates remaining before *operational* acceptance

- Installed **live UI** manual interaction and per-user authentication have **not** been exercised; the binary-inspection test does not open the windows. Taraz's installed executable exists but no running Taraz process was observed during this check.
- The actual `%LOCALAPPDATA%/Madar-Taraz-Bridge` directory exists and contains a `pending` directory, but **its contents were not read or changed**. Data in that location could be operational; never inject QA requests into the real folder for convenience.
- On a **single PC, same logged-in Windows user**, the two installed binaries support compatible manual metadata exchange. For operator confirmation, a permitted user must open Taraz and use its optional inbox; Madar must explicitly enable and manually send from a saved card; no automatic sharing. A real accepted test should use an expressly designated non-financial test card, not a customer document.
- There is no claim of end-to-end installed UI acceptance, official signed Taraz financial receipt, official party/catalog authority, invoice creation, ledger posting, cross-device LAN, backup/restore or release readiness. All E7 acceptance gates retain their documented `OPEN` / `NO_GO` state.

## Source follow-up for full goal

Upgrade from packaged schema-1 inbox to current-source stable-ID preparation, scoped readback, and server-authenticated signed host/peer protocol. Independently provision **official** Taraz identity/receipt/finance API before enabling any invoice/ledger action. Preserve existing user accounts, migration data and live accounting book. Do not auto-retry a possibly delivered request.
