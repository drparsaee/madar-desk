# M07 | Safety preflight for Madar automation rules

**Date:** 2026-10-21. **Status:** pure preflight tested; bounded host wiring added after RC7 build. Full M07 acceptance/GUI/EXE NOT verified.

Original worker contribution comprised ONLY rule_safety.py, tests/test_rule_safety.py and this file. Subsequently Prime added m07_host_guard.py and modified native_app.py; automation_v1.py, collab.py, real APPDATA, Git and existing RC7 release were not changed.

## Post-worker opt-in SQLite host wiring

`m07_host_guard.py` now calls `dry_run_events` and `preflight_due_batch` before `automation_v1.enqueue_events` / `run_batch`. Under existing host locking, `native_app.Bridge._save_local_state` calls `safe_card_events` for opt-in unified SQLite, while `_run_engine_scheduler` uses `safe_due_tick`. Only a safe bounded `safeLimit` with `maxAttempts=3` may execute. A `SafetyHold` rejects the candidate before SQLite CAS; no successful commit is claimed on rejection. Preflight and queued-event results use the same input snapshot and existing atomic host transaction.

Scope limitations are important: legacy JSON/old collaboration paths are not covered; neither a persisted causal ancestry map nor an independently protected audit hash head has been integrated. This does NOT achieve the full cross-restart loop-cutout/audit standard. The actual Windows RC7 EXE was built **before** these source edits and contains no assurance of this wiring. Focused host checks and full QA on the new source must be recorded separately.

## Existing engine, as inspected read-only

automation_v1.py is a bounded, opt-in deterministic journal for allowlisted event.publish commands. It has durable queued jobs, receipts, audit, ordered due scheduling, 60/120/240-second exponential retry backoff (max 3600 seconds) and a maximum of 8 attempts. Only collab.apply_command can execute those events. The collaboration engine supports strictly validated rule matches with comment and notify actions only, admin rule-owner restrictions, and card/project ACLs. Existing rules cannot execute arbitrary code, HTTP, shell, SQL or financial transfers. The M07 preflight never invokes collab.apply_command, automation_v1.run_batch or retry_dead.

## Public API (all operations are side-effect-free)

    from rule_safety import (
        DEFAULT_POLICY, validate_safety_policy, event_signature,
        inspect_replay, dry_run_events, preflight_due_batch,
        make_safety_audit, verify_safety_audit,
    )

    policy = validate_safety_policy()
    # Authenticated host session determines actor; never client-supplied.
    preview = dry_run_events(
        engine_state, collab_state, proposed_events,
        actor=authenticated_actor, accounts=current_accounts,
        cards=current_cards, projects=current_projects,
        now="2026-10-21T08:00:00Z", policy=policy,
        ancestry=trusted_host_causal_map,
    )
    if not preview["safeToExecute"]:
        # Reject the ENTIRE proposed enqueue, without modifying a domain.
        raise ValueError("Automation preflight blocked events")

    tick = preflight_due_batch(
        engine_state, collab_state,
        accounts=current_accounts, cards=current_cards,
        projects=current_projects, now="2026-10-21T08:01:00Z",
        policy=policy, ancestry=trusted_host_causal_map,
        offline=False,
    )
    if tick["safeToExecute"] and tick["safeLimit"]:
        # Under SAME host lock and original CAS revision used for preflight:
        result = automation_v1.run_batch(
            engine_state, collab_state, accounts=current_accounts,
            cards=current_cards, projects=current_projects,
            now="2026-10-21T08:01:00Z",
            limit=tick["safeLimit"],
            max_attempts=policy["maxAttempts"],
        )
        # Host owns atomically committing result state + collab + audit.

    audit = make_safety_audit(
        tick, now="2026-10-21T08:01:00Z",
        first_sequence=host_next_sequence,
        previous_hash=host_trusted_audit_head,
        policy=policy,
    )
    verify_safety_audit(
        audit["records"], first_sequence=host_next_sequence,
        previous_hash=host_trusted_audit_head,
        expected_final_hash=audit["lastHash"],
    )

The methods inspect validated, in-memory state and return *advisory* decisions. No data is saved and no command is executed. Results contain only event IDs, SHA256 signatures, fixed outcome/reason codes and counts of eligible/matched/skipped rules, comment/notify actions, duplicates, blocked decisions and deferred due jobs. They never copy comment text, notification targets, task costs, invoice or attachment values. An action count is a count of matching *definitions*, not the exact number of actual delivered notifications: the collaboration reducer may deduplicate or skip recipients.

## Default safety policy

| Field | Default | Permitted bounds | Meaning |
|---|---:|---:|---|
| maxEvents | 25 | 1-100 | Due/proposed events checked in one batch |
| maxActions | 40 | 1-500 | Hypothetical eligible action definitions across batch |
| maxChainDepth | 4 | 1-16 | Ancestry depth including current event |
| maxRepeatedSignature | 2 | 1-16 | Repeats of same event semantics across IDs/within causal chain |
| maxAttempts | 3 | 1-8 | Job retry stop-loss ceiling |
| maxRetriesPerBatch | 8 | 0-100 | Retrying jobs allowed in one checked batch |
| maxConsecutiveFailures | 4 | 1-100 | Consecutive dead/retry outcomes opening circuit breaker |
| maxAuditPreview | 100 | 1-100 | Pure audit records created per batch |

All policy keys are mandatory if the caller overrides it. Values require strict integers (not booleans). Unknown keys and unbounded input fail closed. An entire proposed enqueue/run is blocked when ANY decision is blocked; failed due run returns safeLimit=0 and the host must not bypass that by calling run_batch directly.

Independent input guardrails additionally cap the inspected rule collection at 2,000, accounts at 1,000, cards at 20,000 and projects at 2,000; existing engine journal/audit and matched-rule/action limits remain authoritative. This limits the size of an individual dry-run pass and prevents adversarial unbounded scans. These are explicit technical guardrails, not commercial or licensing limits.

## Deterministic replay, loop cutout, permissions and audit

1. event_signature hashes canonical [projectId,cardId,trigger,data], intentionally excluding eventId. New IDs with identical causal semantics cannot evade the signature repeat cutout. The caller can pass an optional host-verified mapping eventId to bounded ancestor signature hashes. Over-depth and over-repetition block. Within one batch repeated event signatures are limited even if ancestry is absent.
2. **Important limitation:** automation_v1's strict journal currently contains NO causal ancestry. M07 does NOT automatically catch cross-tick/restart cycles without Prime persisting a separate host-authored causal provenance map under the same CAS transaction. Never trust a client-supplied ancestry map for security.
3. inspect_replay compares the full actor+command fingerprint against the automation pending job, automation receipt and collab receipt. It distinguishes new, already_queued, already_applied and collab_committed (the documented crash gap). Reusing an event ID with another payload/actor causes a hard ValueError. A duplicate yields zero *new* action counts, not an altered receipt.
4. preflight_due_batch replicates deterministic due order (nextAttemptAt, queuedAt, eventId); respects future timestamps, offline zero-work, limited and deferred batches. It checks current card/project mapping, role and project access, collab receipt collisions, retry attempts, retry-job budget and last-failure streak. Rule owners must be currently authorized admins. If blocked, the host must pause, log a fixed reason and request admin review.
5. make_safety_audit returns fixed-code redacted, timestamped records with increasing sequence and SHA256 hash links; verify_safety_audit checks integrity, ordering, links and a caller-provided expected head. **This is not signed, immutable or tamper-proof**. Anyone with write access to both log and expected head can forge a new chain. A trusted/secured audit head and transactional persistence are necessary. Missing tail entries cannot be detected without an externally trusted expected last hash and sequence.

## Integration contract for Prime

1. Derive actor and account grants from authenticated host/LAN sessions, never from an event. Keep preflight/audit visibility admin-only or otherwise project scoped and redacted. The module's inspect_replay method is not a public viewer endpoint.
2. In the same host lock and same authoritative SQLite CAS snapshot used for enqueue or run, call dry_run_events before enqueue_events and preflight_due_batch immediately before run_batch. Execute only on safeToExecute, and supply the same safeLimit and maxAttempts. After any CAS conflict or role/task/rule change, re-read and re-run preflight.
3. Persist a trustworthy bounded causal ancestry map and policy version alongside event creation and journal state; the existing journal schema is exact, so DO NOT insert extra keys without a migration. Do not claim cross-restart loop prevention without provenance durability.
4. Audit output belongs to a **separate authorized log**, not the existing strict automation_v1.audit shape. Store with the same transaction/CAS as state and a protected expected head (or a signed integrity anchor). Protect from user-facing exports and finance/permission leaks.
5. An opened stop-loss circuit leaves queued/dead jobs intact. Manual retry_dead resets attempts in automation_v1 and MUST require an authenticated admin action, a global/per-event retry policy, history inspection and explicit approval. Never automatically requeue denied permission or project-change cases.
6. No reverse actions, automatic rollback or compensation are implemented. Previous notifications/financial effects cannot be undone by a preflight function. A compensation path would need separate audited domain commands and explicit approval.
7. After wiring: test host JSON/SQLite save/reopen, offline replay, atomic CAS, blocked enqueue and due tick, permission revocation, persisted causal provenance, two-client LAN and actual EXE. Until then, this is NOT an operational safety guarantee.

## Verification

    py -3.12 -m unittest tests.test_rule_safety -v
    py -3.12 -m unittest tests.test_rule_safety tests.test_automation_v1 tests.test_collab -v
    py -3.12 -m compileall -q rule_safety.py tests/test_rule_safety.py

**33/33 M07 tests PASS; 68/68 combined domain tests PASS; compileall PASS.** Cases cover event/schema injection and forbidden action refusal, strict ACL, rule-owner revocation, actual zero-reducer invocation, bounded dry-run budgets and input caps, same-semantics generated-ID loops, ancestry depth, stop-loss and retry budgets, future/offline jobs, sorted due runs, pure deterministic crash-gap replay, canonical hash-chain audit and tamper verification, unchanged financial/attachment inputs and serialized journals. No real APPDATA, Git, release or external services were used.
