# Madar Desk 1.0: isolated Windows EXE GUI smoke

## Entry point

Reusable harness: scripts/v1_gui_smoke.py (Python 3.12, Windows; stdlib only).

Run from D:\CoS-Test\madar-desk:

    python -m unittest discover -s tests -p test_gui_smoke_harness.py -v
    python scripts\v1_gui_smoke.py --timeout 75
    python scripts\v1_gui_smoke.py --timeout 75 --screenshot --output-dir .

Default target: D:\CoS-Test\madar-desk\release\Madar-Desk-v1.0-rc1.exe.
The --exe override accepts only a canonical path to a .exe under the
project release directory. This runner does not create, build, copy,
overwrite or otherwise modify any release executable.

Timeout is bounded to 8–180 seconds. Exit codes: 0 all requested checks PASS;
1 FAIL; 2 missing EXE (NOT_RUN); 3 unsupported operating system. JSON output
uses ASCII escapes, so legacy Windows console code pages can print it.

## Isolation and owned process lifecycle

Each launch creates a new temporary scratch directory under the project root.
Only the *child* receives the following environment overrides:

| Variable | Child-only value |
| --- | --- |
| APPDATA | scratch/AppData/Roaming |
| LOCALAPPDATA | scratch/AppData/Local |
| TEMP, TMP | scratch/Temp |
| WEBVIEW2_USER_DATA_FOLDER | scratch/WebView2 |
| MADAR_QA_REPORT | scratch/diagnostics.json |
| MADAR_QA_VIEW | sample-project |
| MADAR_RELEASE_QA | 1 |
| MADAR_QA_SCREENSHOT | scratch/screenshot.png, only with --screenshot |

Inherited QA report, screenshot, view and theme paths are removed before
setting the safe values. The script never modifies global os.environ or
opens/copies/deletes the actual user's APPDATA/LOCALAPPDATA data.

It creates a new Windows Job Object with kill-on-close limits, launches the
requested EXE suspended using CreateProcessW, attaches that specific process
to the Job, then resumes it. This guarantees PyInstaller children start
inside the owned Job. On success, failure or timeout, it terminates only
that Job, waits for Job members to exit, and closes only the handles it owns.
If Job attachment fails, it terminates the specific suspended process that
the harness created. It never calls taskkill by image name, never scans
running user applications to terminate them and never touches unrelated PIDs.

The scratch directory is deleted after shutdown; transient PyInstaller DLL
locks are retried. If cleanup fails, the command reports FAIL explicitly.
When --output-dir is supplied, the directory must already exist and must
not be inside real APPDATA/LOCALAPPDATA or the release directory. It creates
a uniquely named v1-gui-smoke-* folder there to preserve report/PNG evidence.
No existing files are overwritten.

## Native report contract and checks

The existing native_app.py MADAR_QA_REPORT hook evaluates the DOM after launch.
The runner only reads that report; it does not inject JavaScript, spawn a
second browser, open DevTools or modify native source code.

| Check | Required result |
| --- | --- |
| loopback | URL exactly http://127.0.0.1:PORT/ and valid numeric port |
| dom_ready | readyState equals complete |
| root_mount | rootLength integer at least 200 |
| body_text | bodyTextStart nonempty and contains مدار |
| native_bridge | bridgeType and pywebviewType both object |
| font_loaded | fontLoaded exactly true (Vazirmatn) |
| board_columns | stageCount positive integer |
| visible_cards | cardCount positive integer for .task-card |
| screenshot (optional) | full PNG chunk CRCs, valid dimensions, final IEND and complete IDAT zlib stream |

Missing cardCount is UNVERIFIED and forces overall FAIL; stageCount does not
prove a card was rendered. Screenshot is checked only when explicitly
requested. When a complete PNG independently passes the structural,
integrity and zlib checks, native screenshot.done=false is retained as an
explicit warning about the asynchronous callback, rather than a false file
failure. Truncated or corrupt PNGs FAIL regardless of the native flag.
Complete PNG integrity is not a visual-quality assertion; image inspection
is a separate acceptance step.

The report itself is limited to 512 KB. The runner polls for it until the
timeout and fails if the EXE exits without producing one. It never claims
application health based merely on a successful process launch.

## Validation performed on 21 October 2026

Focused harness unit tests:

    python -m unittest discover -s tests -p test_gui_smoke_harness.py -v

**13/13 PASS**, exit 0. Tests use disposable fixture directories and fake
process objects: no fake EXE is actually launched. Covered environment
isolation, path restrictions, owned-process stop calls, early exit, invalid
report, missing card evidence, bad font/bridge, optional screenshot and
PNG integrity, native callback discrepancy, truncation/CRC rejection, and
preserving QA output outside user-profile folders.

### Actual rebuilt RC1, core GUI smoke

Command: python scripts\v1_gui_smoke.py --timeout 75

**PASS**, exit 0:

| Check | Observed |
| --- | --- |
| loopback | http://127.0.0.1:11913/ |
| document | complete |
| root | 42,316 characters |
| body | Persian application text present |
| native bridge | madar object, pywebview object |
| Vazirmatn | fontLoaded true |
| board | 5 stages |
| cards | 4 visible |

Own process PID: 22012. Job termination and scratch cleanup completed
without exception. The test establishes startup/render health for this
build, not all application functions.

### Actual rebuilt RC1, screenshot requested

Command: python scripts\v1_gui_smoke.py --timeout 75 --screenshot --output-dir .

**FAIL under the original harness rule**, exit 1: the same eight core checks
passed (42,316 root characters, 5 stages, 4 task cards), but the screenshot
gate rejected native screenshot.done=false. Saved report:

D:\CoS-Test\madar-desk\v1-gui-smoke-aaz9gu51\diagnostics.json

Own process PID: 3212. The failed capture is a limitation of the existing
native screenshot QA callback flag. The file created by that invocation was
subsequently checked independently using the corrected harness and found to
contain a complete PNG with valid CRCs, IDAT decompression and IEND,
1484x921 pixels, 146471 bytes. The current harness would record a PASS for
the image file together with a warning preserving native screenshot.done=false.
This recheck does not retroactively change the original process exit code.
The corrected harness was subsequently run against the final rebuilt RC1
with its own fresh report and PNG, documented below.

### Final rebuilt RC1, full GUI + screenshot smoke

Command: python scripts\v1_gui_smoke.py --timeout 75 --screenshot --output-dir .

**PASS, exit code 0, all 9 requested gates PASS**, 21 October 2026:

| Check | Observed |
| --- | --- |
| loopback | http://127.0.0.1:13269/ |
| document | complete |
| root | 42,317 characters |
| body | Persian UI text present |
| native bridge | madar object, pywebview object |
| font | fontLoaded true |
| board | 5 stages |
| cards | 4 visible cards |
| screenshot | valid complete 1484x921 PNG, 146415 bytes |

Image completeness was verified independently by chunk CRCs, an IHDR with
reasonable dimensions/pixel format, terminal IEND, full IDAT zlib stream,
expected decompressed scanline size and valid PNG filter codes. The native
screenshot.done=false flag persists as a **warning** in the gate's evidence.
This proves file integrity; it does not imply visual correctness of every UI
element.

Only one final GUI instance was started, owned process PID **22612**. A
read-only process lookup after the run found PID **22612 absent**, and
the scratch-directory listing contained **zero** .qa-v1-gui-isolated-*
leftovers. The release EXE was only read/launched; it was not rewritten.

Saved evidence:

- D:\CoS-Test\madar-desk\v1-gui-smoke-t6080f7d\diagnostics.json
- D:\CoS-Test\madar-desk\v1-gui-smoke-t6080f7d\screenshot.png

The focused synthetic harness suite remains **13/13 PASS** after the PNG
integrity hardening.

## Coverage not established

No complete feature walkthrough, multi-PC LAN scenario, accounting flows,
calendar import UI, backup/restore acceptance, Google or Outlook live
integration, visual inspection of screenshots, production deployment or
testing of all operating-system WebView2 caches was performed. The isolated
child environment directs WebView2 user data to the disposable root.
