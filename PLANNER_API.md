# Madar Desk personal Planner, opt-in UI module

## Exact integration

This is an independent frontend component. No backend migrations, task writes, LAN
endpoints, npm packages or App.jsx edits are required inside this module.

1. In App.jsx import:

   ```jsx
   import {PlannerPanel} from './planner.jsx';
   ```

2. In App() state: `const [plannerOpen, setPlannerOpen] = useState(false);`
3. Add a visible button in sidebar/topbar:

   ```jsx
   <button type="button" onClick={() => setPlannerOpen(true)}>برنامه‌ریز من</button>
   ```

4. Render near the other modal panels:

   ```jsx
   {plannerOpen && <PlannerPanel
     tasks={tasks}
     projects={projects}
     calendar={calendar}
     accountId={lanStatus.user?.username}
     onClose={() => setPlannerOpen(false)}
     onOpenTask={id => {
       setPlannerOpen(false);
       setEditorId(id);
     }}
   />}
   ```

CSS is imported by `planner.jsx`. The component expects React 19, lucide-react
and `CalendarField` / `displayDate` from the existing `productivity.jsx`.
No `package.json` changes needed.

## API and ownership boundaries

`PlannerPanel({tasks = [], projects = [], calendar = 'jalali', onClose,
onOpenTask, accountId})`

- `tasks`: array of existing card objects with `id`, `title`, `dueDate`,
  `projectId` and optional `archived`. Only reads the array. Cards added to a
  daily plan are stored as ID references, never copies or modifications of
  card state. Archived cards are excluded from the Planner day view.
- `projects`: array with `id` and `name`, used for task labels only.
- `calendar`: `jalali` or `gregorian` preference. Uses the existing date
  input/formatting helpers; ISO Gregorian `YYYY-MM-DD` is the storage format.
  Monthly recurrence follows the **selected calendar at creation**, and
  clamps days missing in a shorter month.
- `onClose()`: called when closing the overlay.
- `onOpenTask(taskId)`: called when clicking a linked existing card. The host
  remains responsible for access control, card editor and all shared writes.
- `accountId`: recommended stable per-LAN-account username string. If absent,
  the panel queries `window.madar.lanStatus().user.username` on desktop. In
  browser-only preview, it uses the local `solo` namespace. If the account
  cannot be determined, it refuses private storage and displays an error.

The personal Inbox has no relationship to legacy `task.status === 'inbox'`
or a board's `listId`. Daily plan entries store references to existing cards
and private Inbox items. The panel does not call `saveState`, does not touch
LAN/network APIs other than reading LAN account identity, and does not
create shared board cards.

## Pure module exports: `src/planner.js`

| Export | Behavior |
| --- | --- |
| `emptyPlanner()` | returns `{version:1,inbox:[],entries:[]}` |
| `storageKey(accountId)` | derives `madar-planner-private-v1:<encoded-id>` |
| `normalizePlanner(value)` | validates and normalizes known schema; throws on corrupt or future versions |
| `readPlanner(storage,accountId)` | loads with `storage.getItem`; new key gives empty state; corrupt JSON/version throws |
| `writePlanner(storage,accountId,value)` | validates first, then calls `storage.setItem`; exceptions propagate |
| `addInboxItem(state,fields)` | adds validated private item; ID is caller-generated |
| `editInboxItem(state,id,fields)` | edits title, notes, deadline, recurrence and reminders; resets recurrence anchor |
| `completeInboxItem(state,id,date)` | completes once, or moves repeating due date past completion day, retaining original anchor |
| `planEntry(state,{id,source,refId,date})` | creates one plan reference per day/source/refId; prevents duplicates |
| `unplanEntry(state,id)`, `removeInboxItem(state,id)` | removes entry/item and related personal references |
| `agendaForDate(state,tasks,date)` | returns deduplicated daily items from plan entries and actual due dates |
| `nextRecurringDate(anchor,repeat,after)` | next occurrence strictly after `after`; daily/weekly/monthly, interval 1-12 |
| `dueReminders(state,now)`, `dismissReminder(state,id)` | calculate visible reminders and dismiss current occurrence |
| `validISO`, `shiftISO`, `isoToday`, `calendarDays`, `normalizeRepeat` | date/calendar and validation utilities |

Inbox item schema:

```json
{
  "id": "p-id", "title": "personal reminder", "notes": "",
  "createdDate": "2026-10-21", "dueDate": "2026-10-22",
  "repeatAnchor": "2026-10-22",
  "repeat": {"frequency":"monthly","interval":1,"calendar":"jalali"},
  "remindTime": "09:30", "dismissedFor": "", "doneAt": ""
}
```

An empty `dueDate` and `remindTime` are valid for nonrecurring items. For
repeating items, a due date is required. A one-time completion sets `doneAt`;
a recurring completion advances `dueDate` and resets reminder dismissal.
Plan entries have `{id, source: 'personal' | 'task', refId, date}`.

## Privacy and operational constraints

All private items, notes, recurrence settings, reminder times and personal
plan links live in the **renderer localStorage**, scoped by account ID and
this application's origin/browser profile. They are absent from LAN state,
JSON task backups, server-side SQLite, and Drive backups. Moving to another
device/browser profile will **not** transfer this private data.

LocalStorage provides **no encryption or authorization**. Someone with access
to the same Windows account, renderer profile or browser developer tools can
read or alter other namespaces and raw values. Namespace switching prevents
accidental cross-account display in the interface, not hostile access. For
strong per-user isolation an authenticated native encrypted store will be
needed later. The current panel refuses corrupt/unreadable/future-version
data without overwriting it.

Reminders are inline notifications that are reevaluated while Planner is
mounted. They do **not** work while the panel or application is closed, and
there is no OS notification/scheduler integration. The Focus Timer also
exists only while the component is mounted; closing it resets its runtime
state. The user's local clock and timezone determine day boundaries.

## Validation

- `node --test tests/planner.test.cjs`: 12 tests pass on Windows (see tool
  invocation result in worker chat). Tests cover date validity, Jalali/
  Gregorian monthly recurrence including last-day clamping, keeping the
  original repeat anchor, duplicate-free planning, immutable shared tasks,
  account-scoped storage and corruption handling, reminder trigger/dismissal,
  calendar grids and JSX bundle/SSR compilation.
  Additional coverage includes private item editing and CSS compilation.
- This worker did not integrate App.jsx (owned by prime), run the full app
  interactively or test background OS notifications. Parent integration and
  Windows EXE UI smoke checks are separate release gates.
