# Madar Desk × Trello | Functional Parity Master 2026

**مبنای بررسی: 2026-10-21. هدف: ۱۰۰٪ پوشش عملکردهای مستند Trello با پیاده‌سازی مستقل، نه ادعای تحقق فعلی.**

**به‌روزرسانی Snapshot کد: 2026-10-21، پس از ادغام `src/cardorder.js` و `WorkspaceManager` در `src/App.jsx` و اعتبارسنجی `cardOrder` در میزبان Python.** این به‌روزرسانی تنها **بررسی خواندنی مسیرهای کد و وجود قراردادهای آزمون** است؛ تست GUI/EXE، ذخیره‌سازی end-to-end، LAN واقعی، REA یا ورود به Trello انجام نشده است. ممیزی ۴۰ موردیِ تاریخی همچنان Snapshot قدیمی است.

حفظ بدون مصالحه: فارسی و RTL، تقویم شمسی/میلادی، محاسبه هزینه و مالی/قرارداد/فاکتور/دریافت، Windows local-first، پشتیبانی شبکه محلی و تداوم/بازیابی آفلاین. خروجی نباید کپی کد، DOM، دارایی تصویری، برند، دیتابیس یا API غیرعمومی Trello باشد.

این سند ریزدانه‌تر از ممیزی ۴۰ خانواده‌ای قبلی در TRELLO_PARITY_REA_AUDIT_2026-10-21.md است. عدد 51.25٪ قبلی فقط برآورد انتخابی بود، نه پیشرفت واقعی ۱۰۰٪. مراجع صرفاً اسناد **عمومی رسمی** Atlassian هستند؛ هیچ REA، login، scraping یا بررسی حساب Trello در تهیه این سند انجام نشده است. قرارداد Atlassian می‌تواند تحلیل/استفاده برای ساخت رقیب را محدود کند؛ منبع عمومی برای تعریف نیازمندی مستقل استفاده می‌شود، نه مجوز مهندسی معکوس سرویس [LEGAL].

## روش تفسیر و سطح شواهد

- وضعیت covered = مسیر مدل/کد/UI برای هسته همین قابلیت مشاهده شد؛ به **معنای قبول‌شدن در EXE، دو کامپیوتر واقعی، و هم‌ارزی قطعی نیست**.
- وضعیت partial = بخشی از semantics یا UI موجود ولی کامل، end-to-end، امن یا تست‌شده نیست.
- وضعیت missing = مسیر قابل‌تأیید در فایل‌های بررسی‌شده دیده نشد. اگر بعداً شواهد پیدا شد، با شناسه ثابت بروزرسانی شود؛ «فقدان در کل کد» ادعا نمی‌شود.
- Priority: P0 ایمنی داده، مجوز و قابلیت بنیادی روزانه؛ P1 گردش‌کار پیشرفته پرکاربرد؛ P2 یکپارچگی/موبایل/اکوسیستم؛ P3 اقلام سازمانی یا کم‌تقاضا. این اولویت‌های **مدار** هستند نه Trello.
- Tier: F = Free/base؛ S+ = Standard, Premium, Enterprise؛ P+ = Premium, Enterprise؛ E = Enterprise؛ All = all plans؛ ? = برنامه دقیق از اسناد مشاهده‌شده قطعی نیست؛ var = ویژگی/Power-Up با شرایط وابسته. پرداخت/tiers مدام تغییر می‌کند: [PLAN] ملاک نهایی است. این برچسب در هیچ شرایطی مدل پرداخت مدار را تعیین نمی‌کند.
- Evidence اشاره به **مسیر واقعی فایل یا audit مشخص** است؛ در مورد missing، مدرکِ نبودن مطلق نیست. Acceptance **تست آینده** است، نه گزارشی از اجرا. هر مورد covered همچنان نیازمند قبولی end-to-end است.
- ستون Ref کد لینک به صفحه عمومی رسمی در انتهای سند است. برخی صفحات index دسته‌اند؛ پیش از ساخت جزئیات پیچیده، صفحه تخصصی همان قابلیت مجدداً بازبینی شود.

### خلاصه موجودی در این Snapshot

| شاخص | شمارش |
|---|---:|
| معیار مستقل با ID یکتا | **۲۲۰** |
| حوزه‌های عملکردی | **۱۳** |
| covered (پوشش در کد، نه پذیرش) | **۳۹** |
| partial | **۱۱۲** |
| missing / فاقد مسیر تأییدشده | **۶۹** |
| P0 | **۵۳** |
| P1 | **۱۱۰** |
| P2 | **۴۵** |
| P3 | **۱۲** |

تفکیک خانواده‌ها: BD=18، WS=16، CD=28، CL=9، CO=12، VW=19، TP=8، AU=24، PL=18، MB=14، IN=22، AD=14، EX=18. جمع هر دو محور وضعیت و اولویت باید همیشه با ۲۲۰ برابر باشد. **نسبت covered یعنی شواهد پیاده‌سازی در کد، نه «درصد شباهت یا عملکرد واقعی»**. الزام «۱۰۰٪» یک هدف باز و وابسته به Snapshot رسمی امکانات Trello است، نه نتیجه این ممیزی.

**تغییرات این Snapshot فقط چهار ارتقای شواهد هستند:** BD01، WS01 و WS03 از `partial` به `covered` و BD15 از `missing` به `covered`. BD18 و WS02–WS05 جز WS03 به‌دلیل دامنه گسترده‌تر از رابط پیاده‌شده، `partial` مانده‌اند؛ جزئیات و شرط قبولی کنار هر شناسه آمده است. جمع قبلی ۳۵/۱۱۵/۷۰، جمع جدید **۳۹/۱۱۲/۶۹**؛ اولویت‌های P0=53، P1=110، P2=45، P3=12 بدون تغییر.

## BD: برد، لیست، Kanban

| ID | Capability | Tier | Status | Pri | Madar evidence | Testable acceptance | Ref |
|---|---|---|---|---|---|---|---|
| BD01 | Board create in selected Workspace | F | covered | P0 | src/App.jsx:492-499,630-635,720-725; makeBoard receives activeWorkspaceId and Workspace selector | Two workspaces, distinct boards, persisted links after restart; no claim of EXE/LAN acceptance | [BOARD] |
| BD02 | Board rename and description | F | partial | P1 | src/App.jsx:759 rename; description unclear | Save title and description across restart | [BOARD] |
| BD03 | Board color and image background | F | partial | P1 | src/styles.css; image background not evidenced | Image and color render per board and themes | [BOARD] |
| BD04 | Private/Workspace/public visibility | F | partial | P0 | lan.py:112-143 project-scoped, no full visibility policy | Direct read forbidden for private board and guest | [PERM] |
| BD05 | Starred boards and quick switcher | F | missing | P1 | src/App.jsx:685-708 navigation, no star model | Per-user stars survive relaunch; shortcut switch | [BOARD] |
| BD06 | Duplicate board with lists/cards | F | missing | P1 | src/boardops.js move/archive, not duplicate-board | New IDs, nested data preserved, no ACL leak | [BOARD] |
| BD07 | Close/archive board | F | covered | P0 | src/boardops.js:20-25 | Archive and hide with finance/attachments preserved | [BOARD] |
| BD08 | Reopen archived board | F | covered | P0 | src/boardops.js:29-33; src/App.jsx:705-707 | Restore nested cards across restart | [BOARD] |
| BD09 | Delete board with confirmation | F | partial | P1 | src/boardops.js archives rather than full deletion | Admin deletion semantics, retention and backup scope tested | [BOARD] |
| BD10 | Create and rename list | F | covered | P0 | src/features.jsx:43-46 stage editor | Separate stages in two boards, restart | [BOARD] |
| BD11 | Reorder lists | F | covered | P0 | src/features.jsx:47 | Reorder A/B/C to C/A/B persisted in two clients | [BOARD] |
| BD12 | Copy/move list to another board | F | missing | P1 | src/boardops.js task move only | IDs/ACL/attachments preserved after cross-board move | [CARD] |
| BD13 | Archive and restore list | F | partial | P0 | src/listarchive.js pure archive/restore; src/App.jsx + src/features.jsx wired; 16 focused Node PASS; native GUI acceptance pending | Reversible list archive without moving cards destructively | [BOARD] |
| BD14 | Drag card between lists | F | covered | P0 | src/App.jsx:122-145 card drag | EXE gesture, same result after restart and LAN sync | [BOARD] |
| BD15 | Persistent ordering within list | F | covered | P0 | src/cardorder.js:123-157,170-235; src/App.jsx:550-560,774-779 drag/keyboard and ordered rendering; data_model.py:365-369, native_app.py:162-164 accept bounded cardOrder; tests/cardorder.test.cjs, tests/test_card_order_contract.py exist | Validate reorder before/after/middle after restart, archive/restore, actual LAN simultaneous CAS conflict handling and finance preservation; EXE unverified | [BOARD] |
| BD16 | Sort list by due/name/criteria | F | partial | P1 | src/boardplus.jsx:40-85 filter, sort incomplete | Predictable sort with manual-order restore | [CARD] |
| BD17 | Move card across boards | F | covered | P0 | src/boardops.js:1-18 | Checklist, files, finance, assignee mapping survives | [CARD] |
| BD18 | Add card top/middle/bottom | F | partial | P1 | src/App.jsx:602-615 create at start and duplicate after template; src/App.jsx:550-560,774-779 + src/cardorder.js:177-221 reposition before/after/start/end; direct position on initial create is absent | One-step insert at 0, middle, end from create UI; stable ordered save and restore | [CARD] |

## WS: Workspace، Guest، نقش و عضو

| ID | Capability | Tier | Status | Pri | Madar evidence | Testable acceptance | Ref |
|---|---|---|---|---|---|---|---|
| WS01 | Create workspace in GUI | F | covered | P0 | src/workspaces_panel.jsx:18-80,140-148 WorkspaceManager create; src/App.jsx:720-725,790 wired; src/workspaces_logic.js:135-147 and data_model.py:516-525 validated state | Create two independently navigable workspaces, confirm actual save/restart and 2-PC LAN role gates; code coverage only | [WORK] |
| WS02 | Rename/profile workspace | F | partial | P1 | src/workspaces_panel.jsx:108-113,127-139 rename form; src/workspaces_logic.js:149-156; no Workspace profile/image settings | Rename persists without affecting board IDs; add/edit workspace profile/description/image | [WORK] |
| WS03 | Move board between workspaces | F | covered | P0 | src/workspaces_panel.jsx:159-173 destination selector wired through src/App.jsx:790; src/workspaces_logic.js:184-197 changes only board.workspaceId; data_model.py:552-562 | Board/card/finance preserved on real save/restart; actor/guest permissions re-evaluated after move; physical LAN unverified | [WORK] |
| WS04 | Archive/delete workspace safely | F | partial | P0 | src/workspaces_panel.jsx:114-125,149-158 archive/restore UI; src/workspaces_logic.js:158-182 guards last active; data_model.py:565-575 delete-empty pure helper only, no delete UI | Refuse last active, implement safe empty-workspace deletion UI and rollback without loss | [WORK] |
| WS05 | Board index/search by workspace | F | partial | P1 | src/App.jsx:491-499,720-745 filters board/project by selected Workspace; src/workspaces_panel.jsx:159-173 lists boards and moves them; no dedicated board name search in Workspace | Scope-filtered workspace switch/list and board-name search; verify search only allowed boards | [WORK] |
| WS06 | Board collections | P+ | missing | P2 | src/App.jsx no collection catalog | Create/manage collection, boards remain intact | [PREMIUM] |
| WS07 | Invite/manage workspace members | F | partial | P0 | src/features.jsx:75-117 LAN users, not workspace membership | Create/revoke invitation, deny unauthorized boards | [WORK] |
| WS08 | Workspace admins vs members | F/P+ | partial | P0 | lan.py:112-143 admin/editor/viewer at server/project | Exact workspace-actor ACL on direct API | [PREMIUM] |
| WS09 | Single-board guest | F | missing | P1 | lan.py project-scoped accounts only | Guest sees one board, nothing else | [GUEST] |
| WS10 | Multi-board guest / billed role | var | missing | P2 | no board-specific guest scope | Same account two boards, no privilege extension | [GUEST] |
| WS11 | Board admin/member/observer | P+ observer | partial | P0 | LAN viewer role != board observer | Observer can view/comment per policy, not mutate | [GUEST] |
| WS12 | Shareable board invite links | F | missing | P1 | src/features.jsx direct user creation | Expiring/revocable join URLs and role checks | [GUEST] |
| WS13 | Workspace editing/join policies | F/P+ | missing | P1 | lan.py:471-523 global view CAS/ACL | Member may join only allowed board | [GUEST] |
| WS14 | Restrict invites / board creation | P+ | missing | P2 | no scoped workspace creation rule | Admin restriction enforced through HTTP and GUI | [PREMIUM] |
| WS15 | Recover ownership if admin leaves | P+ | partial | P1 | native_app.py:1024-1035 LAN user management | Never orphan last admin, auditable transfer | [WORK] |
| WS16 | Workspace exports with attachments | P+ | partial | P0 | full_recovery.py CLI; UI SQLite backup excludes blobs | Proven full archive and restore of all governed domains | [WORK] |

## CD: کارت و محتوای آن

| ID | Capability | Tier | Status | Pri | Madar evidence | Testable acceptance | Ref |
|---|---|---|---|---|---|---|---|
| CD01 | Create/edit title | F | covered | P0 | src/App.jsx:167-215,575 | Save on desktop/LAN; no silent lost update | [CARD] |
| CD02 | Markdown description | F | covered | P0 | src/boardplus.jsx:92-110; src/markdown.jsx | XSS escaping, links, RTL tested | [CARD] |
| CD03 | Duplicate card | F | covered | P0 | src/App.jsx:755; src/taskops.js | Clone distinct IDs; no double financial invoice | [CARD] |
| CD04 | Archive and restore card | F | covered | P0 | src/boardops.js; src/App.jsx:755 | Files, checklist costs and history retained | [CARD] |
| CD05 | Delete card safely | F | partial | P0 | src/cardtrash.js immutable softDeleteCardState/restoreDeletedCardState wired to src/App.jsx Trash UI; task.deleted strict validation in data_model.py/native_app.py; 10 isolated Python Bridge/LAN + 11 SSR UI + 18 pure JS PASS, RC5 built and 9/9 basic smoke PASS | Actual EXE Trash click/delete/restore after restart, financial visibility and physical two-PC LAN/editor/guest acceptance remain unverified | [CARD] |
| CD06 | Stable deep link to card | F | partial | P1 | src/App.jsx editorId but no verified URI handler | Open direct URI after restart with ACL check | [CARD] |
| CD07 | Quick edit card on board | F | partial | P1 | src/App.jsx editor modal | Edit label/member/due/move from quick surface | [CARD] |
| CD08 | Colored multiple card labels | F | covered | P0 | src/labels.jsx:21-84,93-125 | Label color/persistence across board reload | [CARD] |
| CD09 | Board label catalog rename/delete | F | partial | P1 | src/labels.jsx task level label editor | Rename label across every card in board without loss | [CARD] |
| CD10 | Multiple card members | F | covered | P0 | src/members.jsx; native_app.py:176-180 | Reject assignee outside authorized project | [MEMBER] |
| CD11 | Start date, due date, due time | F | partial | P0 | src/App.jsx:190 dueDate; start/time limited | ISO storage, timezone, Jalali and DST roundtrip | [CARD] |
| CD12 | Card completion independent of list | F | partial | P1 | status and finance completion logic in native_app.py | Complete/reopen without duplicate invoice | [CARD] |
| CD13 | Card due reminders | F | partial | P1 | automation_due.py; src/planner.jsx in-panel | Correct recipient/time after restart, idempotent | [NOTIFY] |
| CD14 | Repeating card/reminders | var | partial | P1 | src/planner.js personal recurrence only | Recurring board card no duplicate ID or charges | [CARD] |
| CD15 | Card photo/image cover | F | missing | P1 | data_model.py:252-263 explicitly color-only | Safe image thumbnail + file backup restore | [CARD] |
| CD16 | Card color cover & size | F | covered | P1 | src/cardextras.jsx, data_model.py:252-263 | Keep color/size per card after restart | [CARD] |
| CD17 | Card stickers | F | missing | P3 | src/cardextras.jsx no sticker subsystem | Add/move/remove sticker with accessibility | [CARD] |
| CD18 | Smart linked cards | F/var | partial | P2 | fileLinks only; no stable card reference graph | Link, preview, broken target and ACL safe | [CARD] |
| CD19 | File and URL attachments | F (size by tier) | partial | P0 | src/attachments.jsx; attachments.py | Upload/read/delete, MIME/size/ACL and restart | [CARD] |
| CD20 | Attachment preview/download | F | partial | P0 | native_app.py:1472-1489; src/attachments.jsx | File integrity, sandboxing, forbidden file rejection | [CARD] |
| CD21 | Drive/external attachments | var | partial | P2 | fileLinks, Google Drive backup, no link attachment connector | OAuth consent, no secret or data leak | [INT] |
| CD22 | 5 typed custom fields | S+ | covered | P1 | src/cardextras.jsx text/number/date/check/select | Validation, migration and permission tests | [FIELD] |
| CD23 | Custom field visible on card front | S+ | partial | P1 | src/cardextras.jsx fields, face visibility uncertain | Show/hide configured card front without info leak | [FIELD] |
| CD24 | Dropdown option reorder/rename/delete | S+ | partial | P1 | src/cardextras.jsx field definition | Existing values preserved or migrated safely | [FIELD] |
| CD25 | Custom field search/filter | S+ | partial | P1 | src/searchplus.js and src/boardplus.jsx subset | Full typed queries with no hidden field leaks | [FIELD] |
| CD26 | Add due date from natural title | ? | missing | P3 | src/App.jsx:575 plain title input | Explicit suggested due with user approval | [CARD] |
| CD27 | Rich linked Jira work items | var | missing | P2 | no Jira card model integration | Read-only safe preview and revoke support | [INT] |
| CD28 | Card template creation from card | F | partial | P1 | src/App.jsx similar-card template | Persist reusable template and reset private values | [TEMPLATE] |

## CL/CO: چک‌لیست، کامنت، اعلان

| ID | Capability | Tier | Status | Pri | Madar evidence | Testable acceptance | Ref |
|---|---|---|---|---|---|---|---|
| CL01 | Multiple named checklists | F | covered | P1 | src/cardextras.jsx; src/checklistguard.js | Two isolated titles/items/progress, restart | [CHECK] |
| CL02 | Checklist item CRUD | F | covered | P1 | src/App.jsx:202, src/cardextras.jsx | Do not lose recorded step costs on delete | [CHECK] |
| CL03 | Reorder items or move across lists | F | partial | P1 | src/cardextras.jsx grouped items | Drag between named lists preserving item IDs | [CHECK] |
| CL04 | Per-list progress/hide checked | F | partial | P2 | src/boardplus.jsx:21-39 aggregate/collapse | Accurate progress and hide/show without lost state | [CHECK] |
| CL05 | Copy checklist from another card | F | partial | P1 | template flow copies steps, not arbitrary card | Fresh IDs, safe cost/assignee reset | [CHECK] |
| CL06 | Convert checklist item to card | F | missing | P1 | src/cardextras.jsx no conversion UI | Transfer title/due/member safely exactly once | [CHECK] |
| CL07 | Assignee per checklist item | S+ | missing | P1 | src/App.jsx:202 no item member | Project ACL and Your Items query work | [ADVCHK] |
| CL08 | Due date per checklist item | S+ | missing | P1 | src/App.jsx:202 no item due | Date and reminder survive restart/timezone | [ADVCHK] |
| CL09 | Your Items across boards | S+ | partial | P1 | src/planner.jsx personal agenda, not checklist assignments | Scoped cross-board item list and due ordering | [ADVCHK] |
| CO01 | Multi-user card comments | F | covered | P0 | collab.py:319-340; src/teamplus.jsx:7-25 | ACL, saved ordering, safe offline retry | [NOTIFY] |
| CO02 | Edit/delete own comment | F | covered | P1 | collab.py:394-450; src/teamplus.jsx | Deny editing another actor's comment | [NOTIFY] |
| CO03 | @mentions in comments | F | covered | P1 | collab.py:162-187,319-335 | Mentioned actor receives one notice | [NOTIFY] |
| CO04 | Watch/unwatch card | F | partial | P1 | collab.py:263-270 watch.set | Membership, unsubscribe and visibility | [WATCH] |
| CO05 | Watch list and board | F | missing | P1 | collab.py watchers by cardId only | Future card events notify scoped subscribers | [WATCH] |
| CO06 | In-app notification feed/read | F | covered | P1 | src/teamplus.jsx:26-37 | Unread state survives restart, per actor | [NOTIFY] |
| CO07 | Due date, attachment, move alerts | F | partial | P1 | automation_due.py, collab.py subset | All specified triggers, suppress self-notifies | [NOTIFY] |
| CO08 | Email alerts/preferences/digest | F | missing | P2 | src/teamplus.jsx in-app only | Opt-in, unsubscribe, retry and SMTP safety | [NOTIFY] |
| CO09 | Desktop OS notifications | F | partial | P1 | src/planner.jsx:182-185 in-panel alert only | OS toast with focus/restart semantics | [NOTIFY] |
| CO10 | Card/board activity action history | F | partial | P0 | collab.py activity limited subset | Audit actor/at/action/scope, no silent deletion | [NOTIFY] |
| CO11 | Share and copy card/board links | F | partial | P1 | internal IDs, not verified URI sharing | Stable links, revocation, 403 when unauthorized | [MEMBER] |
| CO12 | Votes via optional Power-Up | var | missing | P3 | no voting module | At-most-one vote/actor; undo and count | [POWER] |

## VW: Search، Filter، نماها و Dashboard

| ID | Capability | Tier | Status | Pri | Madar evidence | Testable acceptance | Ref |
|---|---|---|---|---|---|---|---|
| VW01 | Board search by card text | F | covered | P1 | src/searchplus.jsx; src/searchplus.js | Search title/description and Unicode RTL correctly | [SEARCH] |
| VW02 | Cross-board search and operators | F | partial | P1 | src/searchplus.js; board scope uncertain | Search only authorized boards; due/member/label operators | [SEARCH] |
| VW03 | Per-board member/label/due filters | F | covered | P1 | src/boardplus.jsx:39-85 | Combined filters and immediate clear | [SEARCH] |
| VW04 | Saved searches and reusable filters | S+ | partial | P1 | src/boardplus.jsx:61-86 uses localStorage | Persist per-user; do not reveal hidden projects via presets | [SEARCH] |
| VW05 | Sort all assigned cards across boards | F | partial | P1 | src/App.jsx all tasks, src/planner.jsx | Cross-board role-scoped due ordering | [SEARCH] |
| VW06 | Board Table view | P+ | partial | P1 | src/reporting.jsx:38-45 read-only | Inline edit list/label/member/due and refresh view | [TABLE] |
| VW07 | Workspace Table across boards | P+ | partial | P1 | src/reporting.jsx aggregates tasks, no true workspace view | At least two boards, inline edits with cross-board ACL | [WVIEW] |
| VW08 | Board Calendar month/week | P+ | partial | P1 | src/planner.jsx personal-only | Board card/calendar items shown by due/start date | [CAL] |
| VW09 | Drag/reschedule from Calendar | P+ | missing | P1 | no board calendar DnD | Drag date range, persist and audit with timezone | [CAL] |
| VW10 | Workspace Calendar across boards | P+ | missing | P1 | src/planner.jsx no multi-board shared calendar | Scope 2-20 boards, filter, reschedule safely | [WVIEW] |
| VW11 | Timeline date range and drag | P+ | partial | P1 | src/reporting.jsx:40-43 deadline buckets only | Start/end spanning bar, drag edges with persistence | [VIEWS] |
| VW12 | Timeline grouping/member filter | P+ | missing | P1 | src/reporting.jsx no lanes/bars | Group by member/list, maintain 1 card per ID | [VIEWS] |
| VW13 | Dashboard bar/pie charts | P+ | partial | P1 | src/reporting.jsx:32-44 numeric KPIs | By status/member/due/label, real chart with scoped data | [VIEWS] |
| VW14 | Configurable dashboard widgets | P+ | missing | P2 | no dashboard card configuration model | Add/remove/reorder widgets per-user, after restart | [VIEWS] |
| VW15 | Map view for location cards | P+ | missing | P2 | no lat/lon or map view in src/App.jsx | Add/edit location; map pins only visible cards | [VIEWS] |
| VW16 | View switcher and persistence | P+ | partial | P1 | src/App.jsx mode=board and reports modal | Per-board saved view, restore on reopen | [VIEWS] |
| VW17 | Workspace saved custom views | P+ | missing | P2 | no workspace-view persistence | Saved filter/view with multi-board ACL and owner | [WVIEW] |
| VW18 | Print task/card/board view | F | partial | P2 | src/reporting.jsx CSV but no documented print | Printable A4 LTR/RTL with privacy redaction | [EXPORT] |
| VW19 | Time/effort reporting dashboard | not Trello core | covered | P1 | src/reporting.jsx:32-44 estimated/actual minutes | Preserve Madar-specific KPI through all view changes | [SEARCH] |

## TP: Card Template، Board Template، کتابخانه

| ID | Capability | Tier | Status | Pri | Madar evidence | Testable acceptance | Ref |
|---|---|---|---|---|---|---|---|
| TP01 | Make card a reusable template | F | partial | P1 | src/App.jsx draftTemplate and src/cardextras.jsx | Save templates independent of card lifecycle | [TEMPLATE] |
| TP02 | Create card from template | F | partial | P1 | src/App.jsx:575 copies checklist and labels | Deep-copy IDs and safe reset finances/private data | [TEMPLATE] |
| TP03 | Template fields/members/due policy | F | partial | P1 | src/App.jsx:575 copies subset | Explicit include/exclude settings; no stale assignee leak | [TEMPLATE] |
| TP04 | Make a board a template | P+ private / F public | missing | P1 | src/App.jsx board CRUD without make-template | Freeze source and copy with new IDs/permissions | [BTEMPLATE] |
| TP05 | Board template visibility | P+ private | missing | P2 | no template visibility policy | Private/workspace/public templates only authorized users | [BTEMPLATE] |
| TP06 | Board templates gallery and search | P+ / public | missing | P3 | no gallery manager | List/select/sort templates with no private leak | [BTEMPLATE] |
| TP07 | Template duplication isolation | F / P+ | partial | P1 | src/taskops.js duplicate a task | Derived card editable without mutating template | [BTEMPLATE] |
| TP08 | Organization-wide template permissions | P+ | missing | P2 | lan.py project ACL only | Workspace/owner/admin permission enforced | [BTEMPLATE] |

## AU: Automation / Butler / Rules

| ID | Capability | Tier | Status | Pri | Madar evidence | Testable acceptance | Ref |
|---|---|---|---|---|---|---|---|
| AU01 | Rule on card created | All (quota) | partial | P1 | automation_events.py; src/rulespanel.jsx | Event fires exactly once and logged | [AUTO] |
| AU02 | Rule on card moved | All (quota) | partial | P1 | automation_events.py card_moved | No recursion; exact card list transition | [AUTO] |
| AU03 | Rule on label changed | All (quota) | partial | P1 | automation_events.py label_changed | Only actual change generates event | [AUTO] |
| AU04 | Rule on checklist completion | All (quota) | partial | P1 | automation_events.py; collab.py | One completion event, no repeat on retry | [AUTO] |
| AU05 | Rule on custom-field change | All (quota) | partial | P1 | src/rulespanel.jsx offers trigger, engine coverage unclear | Type-safe values, no private-field leak | [AUTO] |
| AU06 | Rule on due/overdue | All (quota) | partial | P1 | automation_due.py, native_app.py:1539-1606 | Due scan after restart and one receipt per event | [AUTO] |
| AU07 | Compound conditions (and/or) | All (quota) | missing | P1 | src/rulespanel.jsx:27-32 conditions:[] | Nested predicate evaluator with ACL and limits | [AUTO] |
| AU08 | Date/card/board variable interpolation | All (quota) | missing | P1 | rulespanel fixed message string | Template variables escaped, unknown rejected | [AVAR] |
| AU09 | Action: add comment | All (quota) | covered | P1 | src/rulespanel.jsx:29-32 | Comment created once, actor/scope auditable | [AUTO] |
| AU10 | Action: notify member | All (quota) | covered | P1 | src/rulespanel.jsx:29-32 | Authorized user gets one notification | [AUTO] |
| AU11 | Action: move card to list/board | All (quota) | missing | P1 | src/rulespanel.jsx only notify/comment | Move respects board ACL and handles cycles | [AUTO] |
| AU12 | Action: modify label/member/date | All (quota) | missing | P1 | src/rulespanel.jsx only notify/comment | Validated set/clear actions with idempotence | [AUTO] |
| AU13 | Action: checklist creation/completion | All (quota) | missing | P1 | no checklist action in rulespanel | No double creation on retries | [AUTO] |
| AU14 | Card button automation | All (quota) | missing | P1 | no card button builder | One click => atomic multi-action, permission | [AUTO] |
| AU15 | Board button automation | All (quota) | missing | P1 | no board button builder | Scope-limited bulk transaction, preview + audit | [AUTO] |
| AU16 | Scheduled interval/date automation | All (quota) | partial | P1 | native_app.py:1582-1606 hourly due scheduler | Scheduled daily/weekly when host on; resume/backfill policy | [AUTO] |
| AU17 | Automation activity log/history | All (quota) | partial | P0 | automation_v1.py audit/receipts, src/App.jsx engine status | Actor/time/input/outcome redacted, retryability | [AUTO] |
| AU18 | Enable/disable/copy/edit rule | All (quota) | partial | P1 | src/rulespanel.jsx:27-45 add/delete only | Edit/toggle/copy persists without changing rule ID | [AUTO] |
| AU19 | Automation suggested templates | All (quota) | missing | P2 | no suggestions generator | Suggest only; user approves; safe allowlist | [AUTO] |
| AU20 | Quick scheduled email reports | All (quota) | missing | P2 | src/reporting.jsx CSV on demand, no mail jobs | Opt-in schedule + bounded SMTP + unsubscribe | [AUTO] |
| AU21 | Quota/budget per workspace | F 250/mo, S+ varies | partial | P2 | automation_v1.py max jobs/batch but not product quotas | Bounded run usage, clear exhaustion policy | [PLAN] |
| AU22 | Loops/rate limit and retry after failure | All (quota) | partial | P0 | automation_v1.py durable receipts, bounded queue | Cycle detection, stop/retry no privilege bypass | [AUTO] |
| AU23 | Cross-board rule execution | All (quota) | missing | P2 | src/rulespanel.jsx tied to selected project | Explicit cross-board grants, no leakage | [AUTO] |
| AU24 | Reuse/share rule library | All (quota) | missing | P2 | no export/tagged rule catalog UI | Copy import with allowed destinations, no secrets | [AUTO] |

## PL: Inbox و Personal Planner

| ID | Capability | Tier | Status | Pri | Madar evidence | Testable acceptance | Ref |
|---|---|---|---|---|---|---|---|
| PL01 | Global personal Inbox capture | F | partial | P1 | src/planner.jsx:300-364 localStorage personal | One-click capture independent of board, after restart | [INBOX] |
| PL02 | Move Inbox item to board card | F | missing | P1 | src/planner.jsx only plan/reference existing task | Explicit project/list selection, atomic convert/dedupe | [INBOX] |
| PL03 | Inbox search/edit/complete/delete | F | covered | P1 | src/planner.jsx:300-364 | Private items per actor; rename/complete/reopen | [INBOX] |
| PL04 | Inbox quick capture anywhere | F | partial | P1 | src/App.jsx opens planner overlay | Keyboard shortcut and global capture without modal loss | [INBOX] |
| PL05 | Inbox cross-device availability | F | missing | P2 | src/planner.jsx:100-109 localStorage per device | Consent-based encrypted per-identity sync and conflict | [INBOX] |
| PL06 | Inbox from mobile / Siri quick add | F / mobile | missing | P2 | no iOS/Android application | Create on handset; appears on authorized workspace | [INBOX] |
| PL07 | Personal Planner day/3-day/7-day | F | partial | P1 | src/planner.jsx:218-268 day/week/month, not 3-day layout | Day/3/7 range with resize and keyboard | [PLANNER] |
| PL08 | Calendar events next to board | F | partial | P1 | src/planner.jsx overlay not docked split pane | Side-by-side card/calendar, persistent sizing | [PLANNER] |
| PL09 | Assign focus block for card | F | partial | P1 | src/planner.jsx:157-161 task agenda and timer | Drag card into 09:00-10:00 block with correct timezone | [PLANNER] |
| PL10 | Google calendar events in Planner | F / connection | missing | P2 | src/App.jsx:358-369 offline ICS only | OAuth scoped read, refresh, revoke and event projection | [PLANNER] |
| PL11 | Outlook calendar events in Planner | F / connection | missing | P2 | offline ICS only | Microsoft consent/scopes, refresh and failures | [PLANNER] |
| PL12 | Edit/remove scheduled focus blocks | F | partial | P1 | src/planner.js plan/unplan | Drag resize/remove and no duplicated event | [PLANNER] |
| PL13 | Daily agenda linked to tasks | F | covered | P1 | src/planner.jsx:115-127,268-296 | Open task by ID with permission check | [PLANNER] |
| PL14 | Recurring private Inbox actions | F | covered | P1 | src/planner.js:160-222 and src/planner.jsx | Repeat one occurrence/day, no accidental clones | [INBOX] |
| PL15 | Personal reminders after restart | F | partial | P1 | src/planner.jsx:182-185,230-235 while panel open | OS reminder contract documented; no missed/duplicate alert | [PLANNER] |
| PL16 | Timezone-aware Planner event changes | F | partial | P1 | src/planner.js ISO dates; no external zone sync | DST/timezone change retains intended local time | [PLANNER] |
| PL17 | Focus timer with pause/reset | F / product variant | covered | P1 | src/planner.jsx:186-209 | Pause/resume accurately without timer drift | [PLANNER] |
| PL18 | Planner privacy from other board members | F | partial | P0 | localStorage isolated, not account-backed policy | Other LAN user/profile cannot see or export private items | [INBOX] |

## MB: پلتفرم، Mobile، آفلاین و دسترس‌پذیری

| ID | Capability | Tier | Status | Pri | Madar evidence | Testable acceptance | Ref |
|---|---|---|---|---|---|---|---|
| MB01 | Windows native desktop experience | F | covered | P0 | native_app.py, release/Madar-Desk-v1.0-rc1.exe | Fresh install, launch, upgrade, uninstall and rollback | [BASE] |
| MB02 | Mac desktop application | F | missing | P2 | native_app.py Windows pywebview-focused | Supported macOS package/architecture with parity suite | [BASE] |
| MB03 | iOS client | F | missing | P2 | no iOS app/packaging | View, edit, upload, notify, offline/reconnect test | [MOBILE] |
| MB04 | Android client | F | missing | P2 | no Android project | Same feature and permissions as Windows core | [MOBILE] |
| MB05 | Mobile offline-create and eventual sync | F | missing | P2 | native_app.py desktop offline only | Create offline on handset; replay once and conflict safe | [MOBILE] |
| MB06 | Mobile push for due cards | F | missing | P2 | src/teamplus.jsx in-app, no mobile push | Permission granted/denied; no cross-user leak | [MOBILE] |
| MB07 | Camera/photo scan to card | F / mobile | missing | P3 | no camera pipeline | Optical capture as untrusted input with edit confirmation | [CARD] |
| MB08 | Mobile share sheet/deep links | F | missing | P2 | no mobile registration | URL shared into authorized list, deduplicated | [INBOX] |
| MB09 | Browser/Web client independent of EXE | F | partial | P2 | src/App.jsx React preview with fallback fake API | Real backend, auth, HTTPS, scope, offline state | [BASE] |
| MB10 | Desktop offline task editing queue | not Trello SaaS identical | partial | P0 | offline_exchange.py, native_app.py:430-515 | Disconnect/reconnect, CAS, no lost authorized updates | [MOBILE] |
| MB11 | Keyboard navigation/shortcuts | F | partial | P1 | src/App.jsx keyboard features limited, no full map | Board/card navigation, editable fields, conflicts with RTL/IME | [KEY] |
| MB12 | Screen reader/accessibility support | F | partial | P1 | accessible labels scattered src/*; no audited coverage | Full keyboard, WCAG contrast/focus, screenreader roles | [KEY] |
| MB13 | Disable shortcuts for accessibility | F | missing | P2 | no central toggle evidenced | User switch persists, accessibility test | [KEY] |
| MB14 | Dark theme and responsive layout | F | covered | P1 | src/styles.css:330; settings in src/features.jsx | Persist per user; keyboard/contrast and RTL QA | [BASE] |

## IN: Power-Ups، API، Webhook و پیوند خارجی

| ID | Capability | Tier | Status | Pri | Madar evidence | Testable acceptance | Ref |
|---|---|---|---|---|---|---|---|
| IN01 | Enable/disable board Power-Ups | All (app fees vary) | missing | P2 | no extension runtime or manifest manager | Install/remove isolated signed extension without data loss | [POWER] |
| IN02 | Power-Up marketplace/discovery | All (app fees vary) | missing | P3 | no registry/catalog UI | Curated catalog, permissions, install rollback | [POWER] |
| IN03 | Card badges/sections/buttons extension slots | var | missing | P2 | src/App.jsx fixed TaskEditor, no plugin slots | Sandbox plugin UI with granted data only | [POWER] |
| IN04 | Board-level Power-Up UI/actions | var | missing | P2 | no extension host | Allowlisted host APIs, revocable permission | [POWER] |
| IN05 | Connected third-party OAuth integrations | var | partial | P2 | native_app.py:1772-1859 Google Drive OAuth only | Per-provider least privilege, token lifecycle, revoke | [INT] |
| IN06 | Jira attachment/work-item link | var | missing | P2 | src/App.jsx fileLinks only | Authorized metadata preview; no auto-disclosure | [INT] |
| IN07 | Confluence attachment/page link | var | missing | P3 | no Confluence adapter | OAuth or share-link permission and safe preview | [INT] |
| IN08 | Slack / Teams activity delivery | var | missing | P2 | webhook_outbox_v1.py pure core not wired | Opt-in destinations, filtered content, HMAC, retry | [INT] |
| IN09 | Google Drive link integration beyond backup | var | partial | P2 | native_app.py Drive API for backups, attachments separate | File picker/link permission without moving entire blobs | [INT] |
| IN10 | Google Calendar / Outlook date sync | var | partial | P2 | native_app.py:912-929 and src/App.jsx:358-369 ICS only | OAuth connection and conflict-safe sync, user selected direction | [INT] |
| IN11 | REST versioned read Board/List/Card | API | partial | P1 | integration_api_v1.py:101-365 narrow readonly routes | List/get/paginate all visible models with ACL | [API] |
| IN12 | REST write model operations | API | partial | P1 | integration_api_v1.py title PATCH; broad CRUD lacking | Create/move/checklist/label PATCH with CAS, idempotency | [API] |
| IN13 | Token lifecycle and scoped auth | API | partial | P0 | native_app.py:896-919 issue/revoke, lan.py | Expiry/revoke and project/role ACL direct-request tests | [API] |
| IN14 | Pagination, rate limits, error codes | API | partial | P1 | integration_api_v1.py guarded surface | Stable pagination/cursors, 429, 403, 409, 400 contract | [API] |
| IN15 | Public API and SDK documentation | API | partial | P2 | INTEGRATION_API_V1.md plus HTTP tests | OpenAPI/examples and independently runnable test client | [API] |
| IN16 | Live outgoing webhook subscriptions | API | missing | P1 | webhook_outbox_v1.py disconnected from native_app.py/lan.py | Register URL, send signed event, remote 2xx receipt | [WEBHOOK] |
| IN17 | Webhook HMAC and receiver validation | API | partial | P0 | webhook_outbox_v1.py signature/core; no live endpoint | Tampered payload rejected; no secret logged | [WEBHOOK] |
| IN18 | Webhook retry/expiry/replay protection | API | partial | P0 | webhook_outbox_v1.py retry/dead; not host wired | Restart delivery, dead-letter and receiver dedupe | [WEBHOOK] |
| IN19 | OAuth consent to Trello user data | API (optional) | missing | P3 | src/trello_import.jsx file import only | Only if user has authorized export and terms permit; no credential harvesting | [API] |
| IN20 | Trello-compatible read-only data export | API | partial | P2 | src/trello_import.js import transform, no full compatible export | JSON schema mapping + schema version + unmapped report | [IMPORT] |
| IN21 | AI optional assistance | plan-specific | missing | P3 | ROADMAP.md:188-194 post-v1 opt-in | Human approval, cost limit, no financial data auto-send | [PLAN] |
| IN22 | MCP for bounded agent access (Madar differentiator) | not Trello core | partial | P2 | mcp_stdio_v1.py:36-50 three readonly tools | Permission-limited read/write with explicit confirmations | [API] |

## AD: Admin، امنیت، کنترل سازمانی

| ID | Capability | Tier | Status | Pri | Madar evidence | Testable acceptance | Ref |
|---|---|---|---|---|---|---|---|
| AD01 | Authenticated user/member management | F | covered | P0 | lan.py:221-463; native_app.py:1024-1035 | Session timeout/password rotation; offline preserve | [WORK] |
| AD02 | Board permissions and role visibility | F / P+ | partial | P0 | lan.py:112-143,471-523 project scope | Direct HTTP ACL matrix admin/editor/viewer/guest | [PERM] |
| AD03 | Board observer read-only/comment role | P+ | partial | P1 | viewer cannot edit, but comment semantics differ | Exact observer operations checked across endpoints | [PREMIUM] |
| AD04 | Enterprise SSO/SAML | E | missing | P3 | local LAN identities only | IdP login/logout and revoked-user denial | [PLAN] |
| AD05 | Enterprise SCIM/provisioning | E | missing | P3 | no directory provisioning API | Provision/deactivate groups and board scopes | [PLAN] |
| AD06 | Enterprise workspace-wide policies | E | missing | P3 | no org policy domain | Restrict external members/public boards org-wide | [PREMIUM] |
| AD07 | Domain/guest invitation restriction | P+ | missing | P2 | no email-domain policy | Unauthorized invite rejected at API boundary | [PREMIUM] |
| AD08 | Role-specific activity audit | P+ / E | partial | P0 | collab.py activity subset, finance audit separate | Append-only actor/outcome with finance redaction | [WORK] |
| AD09 | API revocation on role change | API | partial | P0 | integration_api_v1.py keys; lan sessions | Old token immediately loses revoked grants | [API] |
| AD10 | Secure HTTPS/PIN for LAN clients | Madar-owned | partial | P0 | lan.py:656-660 TLS optional; native_app.py:998-1009 pin | Two physical PCs, bad fingerprint blocked, no HTTP downgrade | [PERM] |
| AD11 | Concurrent multi-user edit safety | Madar-owned | partial | P0 | lan.py:481-523 whole-view CAS | Concurrent unrelated cards both persist; conflict same card | [PERM] |
| AD12 | Session/security settings and reset | F | covered | P0 | lan.py:342-378; native_app.py:558-578 | Revoke stale session on password reset | [WORK] |
| AD13 | Accessibility administration controls | F | partial | P1 | src/styles.css and buttons; no published audit | WCAG keyboard/high contrast and focus order | [KEY] |
| AD14 | Enterprise admin board inventory | P+ / E | partial | P2 | src/App.jsx lists accessible projects; admin global uncertain | Admin can locate owned boards without bypassing protected content | [PREMIUM] |

## EX: Import، Export، History، Backup و Restore

| ID | Capability | Tier | Status | Pri | Madar evidence | Testable acceptance | Ref |
|---|---|---|---|---|---|---|---|
| EX01 | Board JSON export | F | covered | P0 | native_app.py exportBackup / src/App.jsx:276 | JSON valid, normalized safe, re-import mapping | [EXPORT] |
| EX02 | Board CSV export | P+ | partial | P1 | src/reporting.jsx:41 task CSV only | Full board schema with safe formula escaping and UTF-8 | [EXPORT] |
| EX03 | Workspace bulk JSON/CSV export | P+ | partial | P1 | full_recovery.py offline full ZIP, not UI workspace export | Member/board scopes, attachment list and export log | [WORK] |
| EX04 | Export raw attachments and covers | P+ | partial | P0 | full_recovery.py offline + attachmentBackup separate | Manifest/hash/blob recovery on fresh disposable data root | [WORK] |
| EX05 | Print board/card | F | missing | P2 | src/reporting.jsx CSV, no print contract | RTL A4 print, no secrets/private data | [EXPORT] |
| EX06 | Public board/card links and export visibility | F | partial | P0 | lan.py scoped view, no public links policy | No access-token leakage in shared export | [EXPORT] |
| EX07 | Import via pasted multiline text | F | partial | P1 | src/App.jsx:575 one card creation | N lines -> N titled cards atomically, bounded | [IMPORT] |
| EX08 | Import user-owned Trello JSON export | local utility | partial | P1 | src/trello_import.jsx; src/trello_import.js | Board, lists, labels, cards; unmapped report; no corruption | [IMPORT] |
| EX09 | Preserve legacy IDs/source mappings on import | local utility | partial | P1 | src/trello_import.js mapping | Same export twice yields no duplicate source records | [IMPORT] |
| EX10 | Import checklist/items/comments/files correctly | local utility | partial | P1 | src/trello_import.js subset | Preserve fields and report unsupported attachments/metadata | [IMPORT] |
| EX11 | Backups named partial when incomplete | Madar-owned | covered | P0 | native_app.py:599-621 complete:false, scope/omitted/note | JSON and SQLite verified subset, never full claim | [EXPORT] |
| EX12 | Restore local subset backup safely | Madar-owned | partial | P0 | native_app.py:653-671, BACKUP_SCOPE_V1.md | Pre-restore safety copy, migrate and no finance overwrite | [EXPORT] |
| EX13 | Full host backup/restore with attachments | Madar-owned | partial | P0 | full_recovery.py and maintenance_recovery.py offline CLI only | Two-mode end-to-end verified ZIP, rollback + checksum | [WORK] |
| EX14 | Personal Planner backup/restore policy | Madar-owned | missing | P0 | src/planner.jsx localStorage excluded by host archives | Explicit export/encrypted backup or honest persistent retention policy | [PLANNER] |
| EX15 | Google Drive automatic cloud backup | optional | partial | P1 | native_app.py:1875-1907 JSON state only | Consent/scoped upload, restore, no false full claim | [EXPORT] |
| EX16 | Offline sync conflict and reconcile | Madar-owned | partial | P0 | offline_exchange.py; lan.py whole-view CAS | Two clients offline changed cards, deterministic reconcile | [MOBILE] |
| EX17 | Audit-grade version history/undo | F / optional | partial | P1 | collab.py and app_storage.py revision history | Undo safe card edit with actor/revision, never reverse paid invoice | [KEY] |
| EX18 | Recovery after update/crash + signed installer | Windows-specific | partial | P0 | scripts/Install-MadarDesk.ps1, maintenance_recovery.py | Clean Windows, rollback, artifact hashes, users/attachments intact | [BASE] |

## تحویل مرحله‌ای: گیت پیش‌نیاز، بسته‌های قابل‌انتشار و تعریف ۱۰۰٪

**ترتیب اجرا برای Prime (در این سند هیچ اجرا/بیلدی انجام نشده است):**

| Gate | انتخاب‌های اولویت‌دار و وابستگی | معیار پذیرش قابل گزارش | شکست غیرقابل چشم‌پوشی |
|---|---|---|---|
| **G0 / Data + Security، P0** | EX11-EX16، WS08/11، AD01/02/08-12، MB10، CO10. ابتدا مسیر data ownership/SQLite authoritative، rollback و بازگردانی همه دامنه‌ها/باینری‌ها. | Fixture نسخه قدیم، بکاپ/restore با hash و هویت LAN، ۲ Windows واقعی، TLS pinned، direct API 403، offline concurrent writes؛ PASS/FAIL با path و test log. | از دست‌رفتن کارت/هزینه/پیوست، نشت داده، بکاپ ناقص با برچسب «کامل»، override بدون CAS. |
| **G1 / Trello Essential Kanban، P0** | BD01/04/10-15/17، WS01/03/04/07، CD01-05/08/10/11/19/20 و CO01. **BD01، BD15، WS01، WS03 اکنون مسیر کد دارند، اما هنوز قبولی G1 نیستند.** | دو Workspace، چند برد با ترتیب List/Card پایدار در LAN؛ DnD+duplicate+archive/restore، role gating، restart و backup roundtrip. | فقدان ترتیب پایدار در شرایط واقعی، دخالت board دیگر در workspace، orphan attachments، double-invoice در card copy. |
| **G2 / Daily Fidelity، P1** | BD05-06/12/16/18؛ WS09-13؛ CD06-09/12-16/22-25؛ CL01-09؛ CO03-09؛ VW01-12/16؛ TP01-08؛ PL01-09/12-17. | کاربر روزانه بدون workaround: تبدیل Inbox→Card، Card cover تصویری، advanced checklist، editable Table، board+workspace Calendar، Timeline start/end، shortcut و contrast. | فقط اسم Feature در UI ولی جریان ذخیره، ACL یا local restore کار نمی‌کند. |
| **G3 / Butler + Insights، P1** | AU01-24 با اولویت 07-18/22، VW13-19 و گزارش مالی اختصاصی. ابتدا DSL محدود و host-authoritative بدون اجرای کد دلخواه. | Trigger+condition+action، دکمه Card/Board، restart/retry/idempotency و bounded quotas؛ گزارش CSV امن و reconciliation مالی. | حلقه بدون توقف، عمل خارج از نقش، duplicate notification/receipt یا ترکیب داده مالی بدون مجوز. |
| **G4 / Integrations، P1-P2** | IN01-22، EX01-10، PL10-11، VW17، CO08، MB09. خروجی‌های بیرونی کاملاً opt-in و مستقل از offline core. | REST auth/write/revoke/paging؛ webhook signed live delivery با retry و revoked destination؛ calendar OAuth user-consent؛ provider outage بدون قطع core. | نشت token/attachment، endpoint SSRF، دستکاری ناخواسته Trello یا الزام اینترنت برای بازشدن برنامه. |
| **G5 / Platform & Enterprise، P2-P3** | MB02-08، AD04-07/13-14، TP06، CD17/26، AU19/20/23/24، WS06. UI موبایل و هویت سازمانی با backend مجاز. | iOS/Android/macOS در صورت هدف «تمام قابلیت‌ها»؛ offline create/reconnect، push consent، SSO revoke، accessibility audit و recover. | ادعای ۱۰۰٪ با نبود کلاینت موبایل/Enterprise یا پیاده‌سازی نمایشی. |
| **G6 / Final parity certification** | تمام IDهای این موجودی، به اضافه تغییرات مستند آینده در Trello، باید ممیزی و تست شوند. | **هیچ missing و هیچ partial** در نسخه هدف باقی نماند؛ برای هر covered لینک commit/test/QA؛ ۳ تا ۱۰ کاربر واقعی، refresh رسمی tier و scope، سناریوهای نصب/Upgrade/Crash. | ۱۰۰٪ را فقط به خاطر موفقیت unit test، درصد وزنی یا نام فایل 1.0 نمایش دادن. |

**بسته بعدی پس از این ادغام:** به‌جای پیاده‌سازی دوباره BD15/WS01/WS03، **بستن گیت پذیرش کد موجود** با تست‌های هدفمند cardorder.js، تعامل Drag/keyboard در GUI ویندوز، saved/reloaded ordering، دو کلاینت واقعی و CAS برخورد تغییرات، بکاپ/restore و حفظ cost/receipts انجام شود. هم‌زمان BD18 هنوز به UI درج کارت مستقیم در ابتدا/وسط/انتها نیاز دارد و WS02/WS04/WS05 فقط زیرمجموعه قابلیت کامل را پوشش داده‌اند. وجود فایل‌های tests/cardorder.test.cjs، tests/workspaces_panel.test.cjs، tests/test_card_order_contract.py و tests/test_workspace_contract.py شواهد فایل آزمون است، **نه اجرای آنها در این Snapshot**. **G0/P0 حفظ داده و صحت LAN مستقل از این تغییرات باز مانده است.** موازی‌سازی تنها با مالکیت فایل‌های غیرهمپوشان و یک Prime برای ادغام.

### حفاظت الزام‌آور از توانایی‌های اختصاصی مدار

| Madar invariant | فایل/سطح فعلی | آزمون غیرقابل‌حذف در تمام مراحل |
|---|---|---|
| هزینه مرحله و کارت، تفکیک برآورد/واقعی، قرارداد و فاکتور | finance.py، src/financepanel.jsx، src/financeoverview.jsx | Card move/copy/merge/delete باعث دوباره‌ثبت فاکتور یا محو هزینه نشود؛ migration و restore دقیق باشند. |
| حسابداری داخلی و دفتر دریافت معتبر | finance.py، FINANCE_DOMAIN.md | نقش viewer داده مالی را نبیند؛ گردش invoice/receipt دارای idempotency و audit باشد؛ **ادعای انطباق مالیاتی رسمی نشود**. |
| فارسی، ارقام/حروف راست‌به‌چپ و تاریخ جلالی/میلادی | src/App.jsx، src/productivity.jsx، src/styles.css | RTL، فونت، تاریخ‌های مرزی، timezone و CSV UTF-8 در همه نماها و EXE بررسی شوند. |
| Windows local-first و کار بدون اینترنت | native_app.py، app_storage.py، offline_exchange.py | Boot/CRUD در نبود اینترنت؛ هیچ provider خارجی برای ورود یا ثبت کار لازم نباشد؛ بعد از reconnect داده از دست نرود. |
| مشارکت کنترل‌شده روی LAN | lan.py، collab.py و native_app.py | TLS pin، سناریوی واقعی ۲ Windows و direct API abuse با حساب‌های مجاز/غیرمجاز. |
| بازیابی واقعی، نه صرف نام Backup | full_recovery.py، maintenance_recovery.py، BACKUP_SCOPE_V1.md | ZIP کامل آفلاین شامل blobs/accounts با تأیید هش؛ quick JSON/SQLite همواره صریحاً partial بمانند؛ Planner policy مشخص. |
| اختیاری‌بودن AI و افزونه‌ها | ROADMAP.md:188-194؛ mcp_stdio_v1.py | هیچ دسترسی پیش‌فرض به اطلاعات مالی/خصوصی برای مدل یا Power-Up؛ عملیات نوشتنی با مجوز و تأیید. |

### برنامه آزمون و شواهد قابل حسابرسی

برای هر شناسه ID یک *feature contract* مستقل ایجاد شود: payload و پیش‌شرط‌ها، actor/role، success path، negative/security path، persistence بعد از restart، offline/reconnect و backup/restore (در صورت تأثیر داده)، localization/keyboard، expected event/audit و limits. **پیش از تغییر وضعیت به accepted** گزارش نام آزمون + تاریخ + محیط + commit + نسخه EXE + log/screenshot برای تست‌های گرافیکی الزامی است. معیارهای P0 و هر قابلیت حساس مالی/مجوزی تست «نقش غیرمجاز» و «کرش/بازاجرا» داشته باشند.

در زمان انتشار، ماتریس وضعیت باید کنار یک manifest قابل‌ماشین‌خواندن نگهداری شود؛ این جدول منبع اولیه‌ی IDهاست. محاسبه پیشرفت فقط در قالب **تعداد covered-code / accepted / missing / partial** اعلام شود، نه درصد تخمینی «برابری ۱۰۰٪» با Trello. Trello یک SaaS متغیر با entitlementهای Free/Standard/Premium/Enterprise است؛ برای ادعای parity واقعی تاریخ Snapshot رسمی، مرز plan-specific، شرط‌های محصول و ابزارهای شخص ثالث باید به‌طور شفاف ثابت و قابل بازنگری باشد. تفاوت معماری آنلاین Trello با local-first مدار، **حق حذف feature** نیست بلکه به قرارداد sync و handling آفلاین نیاز دارد.

## منابع رسمی عمومی (کلیدهای Ref)

[BASE]: https://support.atlassian.com/trello/docs/using-trello/
[BOARD]: https://support.atlassian.com/trello/docs/create-and-customize-a-board/
[CARD]: https://support.atlassian.com/trello/docs/add-and-customize-cards-and-lists/
[PERM]: https://support.atlassian.com/trello/docs/changing-permissions-on-a-board/
[WORK]: https://support.atlassian.com/trello/docs/the-workspace-overview/
[GUEST]: https://support.atlassian.com/trello/docs/adding-people-to-a-board/
[MEMBER]: https://support.atlassian.com/trello/docs/adding-a-member-to-a-card/
[PREMIUM]: https://support.atlassian.com/trello/docs/setting-up-your-premium-workspace/
[PLAN]: https://support.atlassian.com/trello/docs/which-trello-plan-is-best-for-me/
[TEMPLATE]: https://support.atlassian.com/trello/docs/add-and-customize-cards-and-lists/
[BTEMPLATE]: https://support.atlassian.com/trello/docs/creating-template-boards/
[CHECK]: https://support.atlassian.com/trello/docs/adding-checklists-to-cards/
[ADVCHK]: https://support.atlassian.com/trello/docs/how-to-use-advanced-checklists-to-set-due-dates
[FIELD]: https://support.atlassian.com/trello/docs/using-custom-fields/
[SEARCH]: https://support.atlassian.com/trello/docs/search-filter-and-custom-views/
[TABLE]: https://support.atlassian.com/trello/docs/workspace-table-view/
[WVIEW]: https://support.atlassian.com/trello/docs/workspace-views/
[VIEWS]: https://support.atlassian.com/trello/docs/search-filter-and-custom-views/
[CAL]: https://support.atlassian.com/trello/docs/calendar-view
[AUTO]: https://support.atlassian.com/trello/docs/automation-overview/
[AVAR]: https://support.atlassian.com/trello/docs/working-with-custom-fields/
[INBOX]: https://support.atlassian.com/trello/docs/trello-inbox/
[PLANNER]: https://support.atlassian.com/trello/docs/trello-planner/
[NOTIFY]: https://support.atlassian.com/trello/docs/receiving-trello-notifications/
[WATCH]: https://support.atlassian.com/trello/docs/watching-cards-lists-and-boards/
[MOBILE]: https://support.atlassian.com/trello/docs/trello-on-android/
[KEY]: https://support.atlassian.com/trello/docs/keyboard-shortcuts-in-trello/
[POWER]: https://support.atlassian.com/trello/docs/automation-power-ups-and-integrations/
[INT]: https://support.atlassian.com/trello/docs/automation-power-ups-and-integrations/
[API]: https://developer.atlassian.com/cloud/trello/guides/rest-api/api-introduction/
[WEBHOOK]: https://developer.atlassian.com/cloud/trello/guides/rest-api/webhooks/
[EXPORT]: https://support.atlassian.com/trello/docs/trello-premium-user-guide/
[IMPORT]: https://support.atlassian.com/trello/docs/importing-data-into-trello/
[LEGAL]: https://www.atlassian.com/legal/atlassian-customer-agreement

**منابع کد داخلی برای بازتولید ارزیابی:** TRELLO_PARITY_REA_AUDIT_2026-10-21.md، ROADMAP.md، ROADMAP_EXECUTION_2026-10-21.md، BACKUP_SCOPE_V1.md، REA بررسی قبلی (فقط کد مجاز خود مدار؛ بدون اسکن Trello). وضعیت این سند با تغییر کد/طرح یا مستندات عمومی باید مجدداً ممیزی شود.




