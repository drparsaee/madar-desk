# Madar Desk Agent Operating Rules

## Mandatory reading
Read PROJECT_CONTEXT.md, LOCALFORGE_SOURCE_OF_TRUTH.md, docs/decision-inventory/DECISIONS.md, docs/decision-inventory/IDEAS.md and task-specific contracts. Then read [shared agent standards](agent-standards/README.md) and the [Madar project profile](agent-standards/projects/madar-desk.md). Inspect Git HEAD, remote, dirty state and task-relevant code/tests before editing.

## Binding boundaries
- The owner's current instructions and existing project decisions, money-policy, security and migration gates take precedence over these supplementary standards.
- This is an independent Windows desktop application. Engineering-policy reuse does not make ForgeOS its runtime or another source of truth.
- Private LocalForge localadmin/madar-desk main is the canonical code/decision source; never silently publish to GitHub or follow stale copies.
- Preserve real Parsian backups, credentials, databases, installers, personal records and financial data outside Git. Use isolated test databases and backed-up/reconciled migration gates before any operational data changes.
- Preserve rial as the authoritative monetary storage unit; never guess a legacy toman conversion or claim production migration from an archive.
- For multi-agent tasks, coordinate owned files, prefer isolated changes, and preserve others' dirty work. No reset, clean, destructive deletion or history rewrite without explicit authorization.
- Reuse existing code and implement only the requested minimal functionality, with measurable acceptance criteria.
- Continue through safe reversible uncertainty; escalate destructive, credential, privilege, financial, spend, license, production or irreversible actions.
- Report separately what is implemented, tested, committed, pushed and released. A built executable does not prove real accounting migration or production acceptance.

See [coding principles](agent-standards/core/coding-principles.md), [change scope](agent-standards/core/change-scope.md) and [verification](agent-standards/core/verification-rules.md).

## Codex modernization and evidence gates
For modernization, follow the repository [ExecPlan standard](.agent/PLANS.md),
the [Madar modernization skill](.agents/skills/madar-code-modernization/SKILL.md)
and the [phase-2 evidence](docs/modernization/phase2_evidence.md). Characterize
existing behavior with disposable profiles before editing; preserve task and
accounting data, remote LAN host ACLs and the rial/toman migration boundary.
Keep branch source work distinct from commit, LocalForge push, installer build,
real-user migration and deployment. These rules extend, not replace, Unslop.

## Visual UI refinement with Codex
The project-local, attributed [Unslop skill](.agents/skills/unslop/SKILL.md) is installed for UI polish. Apply it to actual Madar screens with the owner's existing Vitrea design as the source of truth; never replace the theme, RTL/Estedad, navigation, user permissions, real task data, or independent accounting behavior simply to match a generic example. Scope any design pass, capture synthetic before/after screenshots, validate desktop/mobile and light/dark themes, and run existing React and browser tests. The third-party skill's optional snapshot/video scripts must not be run on private customer pages or profiles without explicit permission. Attribution: Damir Sokolovsky, [heydamir/unslop](https://github.com/heydamir/unslop), CC BY 4.0.
