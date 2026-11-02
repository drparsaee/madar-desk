# Madar Desk 1.0.9: verified online distribution

## Single application source and two installer transports

- Canonical tested application source: `83336d74837e356b46f74704f246336e5fbb29e7`.
- Tested release source with test-only Playwright path fix: `7b5c480438e7186e26bf5fc23117cf4b69aa79e8`.
- LocalForge `main` was fast-forwarded to the latter source before the distribution build.
- The application executable is identical in both transports: SHA256
  `32d17bf248701fa65c9b209591780c173d15a0d1cbe676da8373a424f324aea8`.
- The full **offline** setup was installed locally on 2026-11-03:
  `Madar-Desk-1.0.9-Setup.exe`, 231,523,637 bytes, SHA256
  `d4a96facb5a621da45ad5fe2b9ff66ed99b60fbe6bc1c65c9f1ce0ef0314c9f7`.
- The public **online** setup contains the same app executable, with Microsoft's
  signed Evergreen WebView2 *bootstrapper*, not the 214 MB offline runtime:
  `Madar-Desk-1.0.9-Setup.exe`, 18,574,906 bytes, SHA256
  `3c52ccb0104b73047fa19591beb9b6fd945c3b257f901c22fbacf1917ede7e44`.
- Bootstrapper SHA256:
  `00c6e5a7413c37753bb92e176539dbf691a101846a622e00a9faec3f23e2816b`,
  1,888,976 bytes; Authenticode `Valid`, subject Microsoft Corporation.

## Reproducible online transport compilation

Build in a **new isolated staging worktree**, not in the offline release tree.
Copy the verified existing application executable into staging `release/`.
Download the official bootstrapper from
`https://go.microsoft.com/fwlink/p/?LinkId=2124703`, verify the Microsoft
signature, and copy its bytes into staging under
`release/.madar-inno-prereq/MicrosoftEdgeWebView2RuntimeInstallerX64.exe`.
The filename is the fixed, already-tested Inno prerequisite slot, *not* a claim
that these bytes are the standalone offline installer.

Then invoke the same `scripts/madar-update.iss` using Inno Setup 6,
with these definitions (PowerShell 5.1 compatible):

```powershell
$iscc = Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'
$programHash = (Get-FileHash 'release\Madar-Desk-v1.0.9-Cumulative-20261103.exe' -Algorithm SHA256).Hash
$common = @('/Qp', '/DMadarVersion=1.0.9',
  '/DExeFile=Madar-Desk-v1.0.9-Cumulative-20261103.exe',
  ('/DEXE_SHA256=' + $programHash))
& $iscc @common '/DQA' ('/DQA_ROOT=' + (Join-Path (Get-Location) '.qa-inno-v109-online')) '/DRCOutputBase=Madar-Desk-1.0.9-Setup-QA' 'scripts\madar-update.iss'
& $iscc @common '/DRCOutputBase=Madar-Desk-1.0.9-Setup' 'scripts\madar-update.iss'
```

Do not rebuild over an immutable output. The QA root must be entirely synthetic.
The online package requires internet **only when WebView2 is absent**, since the
bootstrapper then obtains the runtime. Missing-WebView2 installation was not
tested on an actual machine. The setup itself lacks a publisher code signature;
the prerequisite's Microsoft signature is a different claim.

## Evidence and publishing

- `npm test`: 189/189 executed Python modules, build PASS, Node 571/571 PASS.
- Synthetic online Inno upgrade and SHA-checked rollback: PASS.
- Synthetic online clean install: PASS.
- Installed local offline 1.0.9: prior 1.0.8, actual installer exit 0,
  180/180 user-profile files unchanged, newly created ZIP independently
  rehashed against all 180 files with no differences.
- GitHub public `v1.0.9`: exact online asset, 18,574,906 bytes and digest above;
  `releases/latest` returned `v1.0.9`. The old 231 MB upload attempt failed
  with HTTP 404; it was never published.
- Simulated old-client update discovery for 1.0.5/1.0.6/1.0.8: available
  1.0.9; current 1.0.9: unavailable. Public HTTPS download into a synthetic
  isolated folder verified the full online asset hash and size.
- Coworker machines have **not** independently downloaded or installed 1.0.9;
  screenshots were not pixel-compared to the original color-picker reference.

Public URL:
`https://github.com/drparsaee/madar-desk-updates/releases/tag/v1.0.9`.
