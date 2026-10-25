# Madar Desk RC1 vs Trello: evidence-based feature-gap audit

**Date:** 2026-10-21  
**Target:** Madar Desk 1.0.0-rc.1, `D:\CoS-Test\madar-desk`  
**Baseline:** Public official Trello/Atlassian documentation as of 2026-10-21.  
**Scope:** Read-only feature parity analysis. No Trello account, protected bundle, private API, user APPDATA or production data inspected. No source or release artifact changed.

## Assessment result

**Estimated parity on 40 selected Trello feature families:** 20.5 / 40 = **51.25%** (roughly 50%; not a scientific coverage percentage). Each criterion below is equally weighted: present=1, limited/partially wired=0.5, no evidence/absent=0. Real end-to-end acceptance is NOT implied by a present code path; omitted features and scoring weights can materially change the percentage.

| Coverage group | Present | Limited | Absent | Illustrative score |
|---|---:|---:|---:|---:|
| Everyday boards/cards (15) | 10 | 3 | 2 | 11.5/15 = 76.7% |
| Collaboration/views (15) | 0 | 13 | 2 | 6.5/15 = 43.3% |
| Automation/integrations/enterprise (10) | 0 | 5 | 5 | 2.5/10 = 25% |
| **Selected criteria total (40)** | **10** | **21** | **9** | **20.5/40 = 51.25%** |

### Selected criteria and local evidence

Legend: **P** = present in code/wired UI; **L** = limited or unverified; **A** = absent/not evidenced. Where a subsystem has tests, `RELEASE_V1_RC1_VERIFICATION.md` summarizes prior isolated test evidence; this audit did not rerun that suite.

| # | Trello-like capability | Madar | Local evidence / primary gap |
|---:|---|:---:|---|
| 1 | Boards / projects CRUD | P | `src/App.jsx` create, rename, archive and restore board |
| 2 | Manage/reorder lists | P | `src/App.jsx` view stages and stage reorder |
| 3 | Cards CRUD/duplicate | P | `src/App.jsx` create/edit/duplicate/archive card flows |
| 4 | Drag between lists | P | `src/App.jsx` TaskCard drag and lane drop |
| 5 | Precise card ordering **within** a list | A | Lane drop changes status/listId only, no persisted per-card ordering |
| 6 | Labels/colors | P | `src/labels.jsx`, `src/boardplus.jsx` |
| 7 | Assign card members | P | `src/members.jsx`, `src/App.jsx` |
| 8 | Due/start dates and completion state | L | Due-date editor exists; full start-date semantics not verified |
| 9 | Multiple named checklists | P | `src/cardextras.jsx`, `src/checklistguard.js` |
| 10 | Advanced item assignee and item due date | A | `src/cardextras.jsx` lacks item-level member/date features |
| 11 | Comments and mentions | P | `src/teamplus.jsx`, `collab.py` |
| 12 | Attachments / preview | L | `src/attachments.jsx`, `attachments.py`; allowed types/4MB; backup scope limited |
| 13 | Color/photo covers | L | `src/cardextras.jsx` only HEX color, no photo cover |
| 14 | Typed custom fields | P | `src/cardextras.jsx`: text, number, date, checkbox, select |
| 15 | Search and saved filters | P | `src/boardplus.jsx`, `src/searchplus.js`, `src/App.jsx` |
| 16 | Full Workspace management UI | L | `data_model.py` workspace helpers; `src/App.jsx` selects first workspace |
| 17 | Workspace/board guests and granular roles | L | `lan.py` project-scoped admin/editor/viewer, not Trello board member/guest parity |
| 18 | Full card and board activity history | L | `collab.py` activity; not a complete Trello Actions trail |
| 19 | Email, mobile push, background notifications | L | `src/teamplus.jsx` in-app feed; `src/planner.js` explicitly foreground reminders |
| 20 | Proven two-device LAN collaboration | L | LAN + ACL + tests, but no physical two-PC acceptance |
| 21 | Continuous cross-device cloud sync | L | Drive task backups and preview peer-journal, not Trello-class always-on cloud sync |
| 22 | Native iOS/Android apps | A | Windows Python/pywebview host; CSS responsiveness is not mobile client |
| 23 | Editable Table view | L | `src/reporting.jsx` read-only report table, no inline card editing |
| 24 | Board/workspace Calendar view | L | `src/planner.jsx` personal device-local calendar, no equivalent shared board view |
| 25 | Interactive Timeline/Gantt | L | `src/reporting.jsx` deadline buckets, no start/end drag scheduling |
| 26 | Full analytic Dashboard | L | `src/reporting.jsx` task KPIs/basic CSV, not rich workspace dashboard |
| 27 | Map view | A | No evidenced geolocation/map surface |
| 28 | Inbox → board and connected Planner | L | `src/planner.jsx`, `src/planner.js` private device-local; no personal-to-board move |
| 29 | Persistent card/board templates | L | Template state and copy-from-similar; no first-class template manager |
| 30 | Offline conflict resolution and reconnect | L | `offline_exchange.py` + `native_app.py` queue/CAS; two-device conflicts unverified |
| 31 | Broad trigger-condition-action rules | L | `src/rulespanel.jsx`, `collab.py`: narrow notify/comment rules |
| 32 | Due-date/scheduled automations | L | `automation_due.py`, `automation_v1.py`: bounded server-host capabilities |
| 33 | Card and board automation buttons | A | No Trello Butler-equivalent user buttons |
| 34 | Connected external integrations | L | Google Drive backup and local `.ics`; no extensive app ecosystem |
| 35 | Power-Up marketplace/framework | A | No plug-in marketplace or Trello Power-Ups parity |
| 36 | Read/write REST surface and authorization | L | `integration_api_v1.py` scoped narrow GET and title PATCH, no full API |
| 37 | Live outbound webhooks | A | `webhook_outbox_v1.py` PURE signed queue only; no HTTP delivery/wiring |
| 38 | AI agent/MCP integration | L | Read-only legacy MCP sidecar with 3 tools; no broad writes/client certification |
| 39 | OAuth Calendar Google/Outlook syncing | A | `.ics` file interchange only; no OAuth external calendar sync |
| 40 | Enterprise SSO/SCIM/org policy | A | Local LAN accounts/roles, not enterprise identity management |

## REA execution evidence and limits

Official source: https://github.com/morluto/rea, package `rea-agents` 6.7.0, invoked via an already-installed local CLI at `D:\CoS-Test\rea-lab\cli\node_modules\rea-agents\scripts\rea.mjs`. This did **not** register new MCP integrations, alter app config, authenticate to Trello or attach a browser. Analysis artifacts were placed outside Madar source in `D:\CoS-Test\rea-trello-audit-20261021`.

1. The first static pass targeted the bundled minified `dist` and returned partial Evidence with an explicit worker-heap resource constraint. It must not be called complete.
2. A second pass targeted eight unminified Madar JavaScript files copied to a disposable independent input folder (`boardops.js`, `taskops.js`, `planner.js`, `searchplus.js`, `reporting.js`, `trello_import.js`, `calendar_import_state.js`, `checklistguard.js`). **Exit 0**, 8/8 parsed, 0 parse failures, **7,533 AST nodes**, **41 findings**, Evidence ID `ev_f7a67057fafe6bc054a17bd5ab7834de9e3c8f37af58eeed9b4c2e6f0f4f1fd1`. Source digest `9b443a9732417e94e3ff719e1e337a8302cdb160da5ab9faec2bfb6155c1d77c`. Full raw CLI output: `D:\CoS-Test\rea-trello-audit-20261021\selected-src-rea.txt` (PowerShell redirected UTF-16LE text). REA explicitly states that static syntax observations do not prove runtime execution.
3. All Trello-side feature claims in this audit are from public official docs, not a REA capture or unauthorized live service inspection.

**Terms limitation:** Atlassian Customer Agreement effective 2026-10-01, section 2.2(d)-(e), contains restrictions on competing-product development and reverse engineering. The REA MIT license does not grant rights over Trello. Avoid Trello authenticated traffic/bundles/private APIs for this comparison without separate legal/contractual authorization. Public product documentation provides a suitable independent requirements baseline.

## Priorities: feature gap vs production safety

**P0 product fidelity:** stable per-card ordering inside lists (persist, optimistic CAS, LAN conflicting reorders, backup/restore tests); initial complete Workspace UX (create, switch, archive, members with scoped ACL). These are conspicuous daily Kanban omissions.

**P0 stable-release trust:** actual two-physical-PC LAN TLS/auth/offline/reconnect acceptance; require TLS for production-sensitive LAN use (current host can default to HTTP on trusted LAN); interactive installed Windows acceptance; safe, documented **complete** restore including attachment binaries, LAN identities and a conscious Planner preservation decision. Both quick backup types currently mark `complete:false`; offline full ZIP is unencrypted and should not be uploaded to Drive automatically. These are safety gates, not points that can be compensated by UI feature count.

**P1 feature parity:** advanced checklist assignments/due dates, first-class templates, shared board Calendar, editable Table, true Timeline, reliable background notifications, Inbox-to-board conversion, expanded automation builder/action history.

**P2 ecosystem:** live safe webhook delivery, wider API/Power-Up-style extensibility, supported OAuth Calendar, mobile clients, enterprise SSO if market demand justifies their costs.

## Public reference documentation

- Trello views: https://trello.com/guide/activate-views
- Trello advanced checklist items: https://support.atlassian.com/trello/docs/how-to-use-advanced-checklists-to-set-due-dates
- Trello Inbox: https://support.atlassian.com/trello/docs/trello-inbox
- Trello Planner: https://support.atlassian.com/trello/docs/trello-planner
- Trello automation: https://support.atlassian.com/trello/docs/create-and-manage-automations/
- Trello board permissions: https://support.atlassian.com/trello/docs/changing-permissions-on-a-board/
- Trello API/webhooks: https://developer.atlassian.com/cloud/trello/guides/rest-api/api-introduction/ and https://developer.atlassian.com/cloud/trello/guides/rest-api/webhooks/
- REA browser observation boundaries: https://github.com/morluto/rea/blob/main/docs/browser-observation.md
- Current Atlassian terms: https://www.atlassian.com/legal/atlassian-customer-agreement

### What this does NOT claim

No production rollout, two-computer acceptance, Atlassian internal feature inspection, live Trello session capture, full REA parity comparison, or independent rerun of the reported 447 Python/76 JavaScript tests occurred in this audit. Feature scoring is engineering judgment over **selected** capabilities, not code similarity or exact implementation effort. Madar's local-first Windows, Persian/Jalali and built-in financial features are product differentiators and not discounted because they differ from Trello.
