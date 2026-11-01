# ExecPlan | Preserve user data in Madar upgrades

## Purpose and exclusions

Owner requirement: future updates must not lose task, attachment, user or accounting data. The modernization pilot applies the official Codex Cookbook's inventory / design / validation approach to the **existing update preflight**. Do not change installed 1.0.2, production data, Parsian databases or release installers.

Worktree: `D:\CoS-Test\madar-modernization-20261101`. Baseline source commit `fbe86e6c9c74c0988a8652e734888221ed6c43e5`; prior isolated branch commit `ba2d153353aeadf6f9d3debf349756941b29b3c3`.

## Existing behavior and documents

- [Overview](pilot_upgrade_overview.md): script entry points, snapshot flow, state boundaries.
- [Design](pilot_upgrade_design.md): no new API/service; drive-root path hardening.
- [CLI contract](pilot_upgrade_contract.yaml): inputs, outputs and permitted effects.
- [Validation](pilot_upgrade_validation.md): parity and negative cases.

## Plan of work

1. Establish existing test baseline on disposable profile: **VERIFIED 4/4**.
2. Identify one bounded fail-closed bug: passing a drive-root to profile/backup paths risks selecting volume-wide data. **VERIFIED from source; actual drive-wide write not attempted**.
3. Add drive-root guard before removing trailing backslashes; write regression test that uses an **unmounted** drive only. **VERIFIED 5/5 focused**.
4. Compare baseline and modified preflight outputs on synthetic fixtures for nested Unicode files, fresh profiles and overlap refusal. **VERIFIED: 3 parity tests passed**.
5. Run adjacent persistence/restore tests and inspect diff. **VERIFIED: combined 15/15 tests passed, git diff --check passed**. No customer release is authorized by these results.

## Progress and observed evidence

| Step | Result |
| --- | --- |
| Original preflight unit suite | 4 passed before edit |
| Updated preflight unit suite | 5 passed after edit |
| Baseline-versus-modified synthetic parity | 3 passed (normal, missing, overlapping profiles) |
| Combined relevant regression | 15 passed; 0 failed, 0 skipped (fresh isolated APPDATA and LOCALAPPDATA) |
| External Codex CLI review | Attempted read-only, no completed review report; not counted as verified |
| Full Python regression | Attempted in disposable profile; stopped after 386 seconds without a runner summary. No pass/fail total available; prior run was red, release remains blocked. |
| New customer installer | Not built; installed version unchanged |
| Git commit / push | To be recorded separately |

## Surprises and decisions

- This is a **PowerShell CLI boundary**, not an HTTP endpoint, so the Cookbook's OpenAPI step is adapted to a YAML command contract instead of inventing a REST API.
- The code already has a versioned binary design and backup SHA checks. The pilot deliberately retains them; a major architecture rewrite is unjustified without parity proof.
- Do not run the baseline script with a **real mounted drive root** as a repro case. Use a missing drive and assert failure in the new implementation.
- Native Codex CLI is installed and authenticated with ChatGPT. A noninteractive read-only review was started but did not return a review artifact; it cannot be cited as an independent approval.

## Validation and acceptance

The safety change is accepted only if the original four tests, new negative regression, parity on valid scenarios and adjacent persistence tests pass with a disposable profile. This is limited source-level acceptance. Product-level acceptance still needs full Python regression, accountant-approved migration and real Windows installer tests.
