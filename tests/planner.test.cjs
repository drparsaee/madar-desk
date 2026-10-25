const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const Module = require('node:module');
const esbuild = require('esbuild');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');
const root = path.resolve(__dirname, '..');

function load(relativePath) {
  const code = esbuild.buildSync({
    entryPoints: [path.join(root, relativePath)], bundle: true,
    platform: 'node', format: 'cjs', write: false, jsx: 'automatic',
    loader: {'.css': 'empty'},
    external: ['react', 'react/jsx-runtime', 'lucide-react']
  }).outputFiles[0].text;
  const compiled = new Module(path.join(root, 'src', 'planner-test-bundle.cjs'), module);
  compiled.filename = path.join(root, 'src', 'planner-test-bundle.cjs');
  compiled.paths = Module._nodeModulePaths(root);
  compiled._compile(code, compiled.filename);
  return compiled.exports;
}

const {
  validISO, shiftISO, nextRecurringDate, calendarDays, emptyPlanner,
  storageKey, readPlanner, writePlanner, addInboxItem, editInboxItem, completeInboxItem,
  planEntry, removeInboxItem, unplanEntry, agendaForDate,
  dueReminders, dismissReminder, normalizePlanner
} = load('src/planner.js');
const {PlannerPanel} = load('src/planner.jsx');
const {fromJalali, jalaliDigits} = load('src/productivity.jsx');
const item = (id = 'personal-1', extras = {}) => ({
  id, title: 'کار خصوصی', notes: '', createdDate: '2026-10-21',
  dueDate: '', repeat: 'none', ...extras
});
const storage = () => {
  const data = new Map();
  return {
    data,
    getItem: key => data.has(key) ? data.get(key) : null,
    setItem: (key, value) => {data.set(key, value);}
  };
};

test('local ISO dates are strict and calendar day shifts do not use local UTC offsets', () => {
  assert.equal(validISO('2028-02-29'), true);
  assert.equal(validISO('2026-02-29'), false);
  assert.equal(validISO('2026-04-31'), false);
  assert.equal(validISO('2026-2-02'), false);
  assert.equal(shiftISO('2026-12-31', 1), '2027-01-01');
  assert.equal(shiftISO('2026-03-29', -1), '2026-03-28');
});

test('recurrence skips past dates and preserves the original Gregorian month anchor', () => {
  const daily = {frequency: 'daily', interval: 2};
  assert.equal(nextRecurringDate('2026-10-21', daily, '2026-10-21'), '2026-10-23');
  assert.equal(nextRecurringDate('2026-10-21', daily, '2026-10-30'), '2026-10-31');
  assert.equal(nextRecurringDate('2026-10-21', {frequency: 'weekly', interval: 1}, '2026-11-07'), '2026-11-11');
  const repeat = {frequency: 'monthly', interval: 1};
  assert.equal(nextRecurringDate('2028-01-31', repeat, '2028-01-31'), '2028-02-29');
  assert.equal(nextRecurringDate('2028-01-31', repeat, '2028-02-29'), '2028-03-31');
  assert.equal(nextRecurringDate('2028-01-31', 'none', '2028-01-31'), null);
});

test('monthly Jalali recurrence follows Jalali months and clamps their last day', () => {
  const start = fromJalali('1405/06/31');
  assert(start);
  const repeat = {frequency: 'monthly', interval: 1, calendar: 'jalali'};
  const next = nextRecurringDate(start, repeat, start);
  assert.equal(jalaliDigits(new Date(next + 'T12:00:00Z')), '1405/07/30');
  const nextAgain = nextRecurringDate(start, repeat, next);
  assert.equal(jalaliDigits(new Date(nextAgain + 'T12:00:00Z')), '1405/08/30');
});

test('completion keeps the original recurring anchor and removes previous plan entries', () => {
  let state = addInboxItem(emptyPlanner(), item('p', {
    createdDate: '2028-01-31', dueDate: '2028-01-31',
    repeat: {frequency: 'monthly', interval: 1}
  }));
  state = planEntry(state, {id: 'plan1', source: 'personal', refId: 'p', date: '2028-01-31'});
  state = completeInboxItem(state, 'p', '2028-01-31');
  assert.equal(state.inbox[0].dueDate, '2028-02-29');
  assert.equal(state.inbox[0].repeatAnchor, '2028-01-31');
  assert.equal(state.entries.length, 0);
  state = completeInboxItem(state, 'p', '2028-02-29');
  assert.equal(state.inbox[0].dueDate, '2028-03-31');
  assert.equal(state.inbox[0].doneAt, '');
});

test('private inbox never depends on task status inbox or changes shared cards', () => {
  const tasks = [
    {id: 'board-inbox', title: 'کارت همکار', status: 'inbox', dueDate: ''},
    {id: 'board-due', title: 'کار موعددار', dueDate: '2026-10-22'},
    {id: 'archived', title: 'آرشیو', dueDate: '2026-10-22', archived: true}
  ];
  const original = structuredClone(tasks);
  let state = addInboxItem(emptyPlanner(), item());
  state = planEntry(state, {id: 'planned-personal', source: 'personal', refId: 'personal-1', date: '2026-10-22'});
  state = planEntry(state, {id: 'planned-task', source: 'task', refId: 'board-inbox', date: '2026-10-22'});
  state = planEntry(state, {id: 'ignored-duplicate', source: 'task', refId: 'board-inbox', date: '2026-10-22'});
  assert.equal(state.entries.length, 2);
  assert.deepEqual(agendaForDate(state, tasks, '2026-10-22').map(e => e.record.id),
    ['personal-1', 'board-inbox', 'board-due']);
  assert.equal(agendaForDate(state, tasks, '2026-10-21').length, 0);
  assert.deepEqual(tasks, original);
  state = unplanEntry(state, 'planned-task');
  assert.equal(state.entries.length, 1);
  state = removeInboxItem(state, 'personal-1');
  assert.deepEqual(state.entries, []);
});

test('storage key isolates account namespaces, rejects corruption and future versions', () => {
  const db = storage();
  assert.notEqual(storageKey('alice'), storageKey('bob'));
  const alice = addInboxItem(emptyPlanner(), item('alpha'));
  writePlanner(db, 'alice', alice);
  assert.deepEqual(readPlanner(db, 'bob'), emptyPlanner());
  assert.equal(readPlanner(db, 'alice').inbox[0].id, 'alpha');
  db.setItem(storageKey('alice'), '{"version":99,"inbox":[],"entries":[]}');
  assert.throws(() => readPlanner(db, 'alice'), /قابل خواندن/);
  assert.equal(db.getItem(storageKey('alice')), '{"version":99,"inbox":[],"entries":[]}');
  db.setItem(storageKey('alice'), '{broken');
  assert.throws(() => readPlanner(db, 'alice'), /قابل خواندن/);
  assert.throws(() => storageKey(''), /شناسه حساب/);
  assert.throws(() => normalizePlanner({version: 1, inbox: 'bad', entries: []}), /ناسازگار/);
});

test('malformed entries, duplicate ids, and invalid recurrence cannot be persisted', () => {
  assert.throws(() => addInboxItem(emptyPlanner(), item('p', {
    repeat: {frequency: 'daily', interval: 1}
  })), /تاریخ/);
  assert.throws(() => addInboxItem(emptyPlanner(), item('p', {
    dueDate: '2026-02-29'
  })), /نامعتبر/);
  const first = addInboxItem(emptyPlanner(), item('p'));
  assert.throws(() => addInboxItem(first, item('p')), /نامعتبر/);
  assert.throws(() => planEntry(first, {id: 'e', source: 'personal', refId: 'missing', date: '2026-10-21'}), /پیدا نشد/);
  assert.throws(() => planEntry(first, {id: 'e', source: 'task', refId: 'b', date: '2026-13-01'}), /نامعتبر/);
  assert.throws(() => addInboxItem(emptyPlanner(), item('p', {
    dueDate: '2026-10-21', remindTime: '25:30'
  })), /نامعتبر/);
  assert.throws(() => addInboxItem(emptyPlanner(), item('p', {
    remindTime: '09:30'
  })), /تاریخ/);
});

test('editing private notes resets recurrence anchor safely and preserves the identifier', () => {
  let state = addInboxItem(emptyPlanner(), item('p', {
    dueDate: '2026-10-21', repeat: 'daily'
  }));
  state = editInboxItem(state, 'p', {
    title: 'برنامه تازه', notes: '<b>untrusted text</b>',
    dueDate: '2026-11-30', repeat: {frequency: 'monthly', interval: 1},
    remindTime: '09:15'
  });
  assert.equal(state.inbox[0].id, 'p');
  assert.equal(state.inbox[0].repeatAnchor, '2026-11-30');
  assert.equal(state.inbox[0].notes, '<b>untrusted text</b>');
  assert.equal(state.inbox[0].remindTime, '09:15');
  assert.throws(() => editInboxItem(state, 'p', {
    title: 'Title', dueDate: '', repeat: 'weekly'
  }), /تاریخ/);
});

test('reminders appear at the right local time, dismiss per occurrence, and do not require OS scheduling', () => {
  let state = addInboxItem(emptyPlanner(), item('p', {
    dueDate: '2026-10-21', remindTime: '09:30',
    repeat: {frequency: 'daily', interval: 1}
  }));
  const at = (day, hour, minute) => new Date(day + 'T' + hour + ':' + minute + ':00');
  assert.equal(dueReminders(state, at('2026-10-21', '09', '29')).length, 0);
  assert.equal(dueReminders(state, at('2026-10-21', '09', '30')).length, 1);
  state = dismissReminder(state, 'p');
  assert.equal(dueReminders(state, at('2026-10-21', '10', '00')).length, 0);
  state = completeInboxItem(state, 'p', '2026-10-21');
  assert.equal(dueReminders(state, at('2026-10-22', '09', '30')).length, 1);
});

test('calendar grid starts on Saturday for Jalali, Monday for Gregorian, and respects Jalali boundaries', () => {
  const jalali = calendarDays('2026-10-21', 'month', 'jalali');
  const gregorian = calendarDays('2026-10-21', 'month', 'gregorian');
  assert.equal(new Date(jalali[0] + 'T12:00:00Z').getUTCDay(), 6);
  assert.equal(new Date(gregorian[0] + 'T12:00:00Z').getUTCDay(), 1);
  assert.equal(jalali.length % 7, 0);
  assert.equal(gregorian.length % 7, 0);
  assert.equal(calendarDays('2026-10-21', 'week', 'jalali').length, 7);
  assert.deepEqual(calendarDays('2026-10-21', 'day', 'jalali'), ['2026-10-21']);
  assert(jalali.some(date => jalaliDigits(new Date(date + 'T12:00:00Z')).startsWith('1405/07/')));
});

test('PlannerPanel JSX compiles and renders its public integration surface', () => {
  const html = renderToStaticMarkup(React.createElement(PlannerPanel, {
    tasks: [], projects: [], calendar: 'jalali', onClose() {}, onOpenTask() {},
    accountId: 'tester'
  }));
  assert.match(html, /برنامه‌ریز من/);
  assert.match(html, /رمزنگاری‌شده نیست/);
  assert.match(html, /aria-modal="true"/);
  assert.doesNotMatch(html, /<script|onerror=/);
});

test('PlannerPanel CSS compiles with esbuild without writing or changing other project files', () => {
  const result = esbuild.buildSync({
    entryPoints: [path.join(root, 'src', 'planner.jsx')],
    bundle: true, platform: 'browser', format: 'esm', jsx: 'automatic', write: false,
    outdir: 'memory-only',
    external: ['react', 'react/jsx-runtime', 'lucide-react']
  });
  const css = result.outputFiles.find(file => file.path.endsWith('.css'));
  assert(css && css.text.includes('.planner-panel'));
});
