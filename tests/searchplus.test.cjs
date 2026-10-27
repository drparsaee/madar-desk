const test = require('node:test');
const assert = require('node:assert/strict');
const Module = require('node:module');
const path = require('node:path');
const esbuild = require('esbuild');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');
const root = path.resolve(__dirname, '..');

function importBundle(entry, externals = []) {
  const content = esbuild.buildSync({
    entryPoints: [path.join(root, entry)], bundle: true, platform: 'node', format: 'cjs',
    write: false, jsx: 'automatic', loader: {'.css': 'empty'}, external: externals
  }).outputFiles[0].text;
  const loader = new Module(path.join(root, '__searchplus_test__.cjs'), module);
  loader.filename = path.join(root, '__searchplus_test__.cjs');
  loader.paths = Module._nodeModulePaths(root);
  loader._compile(content, loader.filename);
  return loader.exports;
}

const {filterTasks, matchesTaskSearch, parseTaskQuery, normalizeSearchText} = importBundle('src/searchplus.js');
const {SearchPlus} = importBundle('src/searchplus.jsx', ['react', 'react/jsx-runtime', 'lucide-react']);

const projects = [{id: 'p1', name: 'سفارش جعبه'}, {id: 'p2', name: 'خدمات دیجیتال'}];
const users = [{username: 'ali', displayName: 'علی رضایی'}, {username: 'sara', displayName: 'سارا محمدی'}];
const stages = [{id: 'printing', label: 'چاپ افست'}, {id: 'review', label: 'بازبینی'}];
const context = {projects, users, stages};
const tasks = [
  {id: 'one', projectId: 'p1', title: 'طراحی بسته‌بندی ۱۲۳', description: 'فایل نهایی PDF آماده است.',
    labels: [{name: 'فوری', color: '#ff0000'}, 'طراحي'],
    checklist: [{text: 'تایید رنگ چاپ', done: true}],
    reports: [{agent: 'ایجنت اول', summary: 'خروجی برای مشتری ارسال شد'}],
    assignees: ['ali'], status: 'active', listId: 'printing', priority: 'high',
    dueDate: '2026-10-23', createdAt: '2026-10-01T08:30:00Z', cost: 9000000,
    price: 12000000, profit: 3000000},
  {id: 'two', projectId: 'p2', title: 'بازبینی سایت فروش', description: 'مرحله اول انجام شد',
    labels: ['وب'], checklist: [{text: 'تست لینک‌ها'}], reports: [], assignees: ['sara'],
    status: 'review', priority: 'low', dueDate: '2026-11-08', createdAt: '2026-09-12'},
  {id: 'three', projectId: 'p1', title: 'جعبه‌سازی و برش', description: 'تغییر قالب لازم است',
    labels: [], checklist: [], reports: [{agent: 'Behrooz', summary: 'مرحله بعد فردا'}],
    assignees: [], status: 'planned', priority: 'medium', dueDate: '', createdAt: '2026-10-15'}
];
const ids = (query, ctx = context) => filterTasks(tasks, {query, ...ctx}).map(t => t.id);

test('Persian/Arabic variants, numerals, diacritics, ZWNJ and punctuation normalize', () => {
  assert.equal(normalizeSearchText('كِتاب يكى ۱۲٣، رنگ‌نما'), 'کتاب یکی 123 رنگ نما');
  assert.deepEqual(ids('طراحي بسته بندي ١٢٣'), ['one']);
  assert.deepEqual(ids('عنوان:«طراحی بسته بندی»'), ['one']);
  assert.deepEqual(ids('توضیح:pdf'), ['one']);
  assert.deepEqual(ids('تایید، رنگ'), ['one']);
});

test('Search combines AND, OR, negation and exact quoted phrases', () => {
  assert.deepEqual(ids('جعبه مشتری'), ['one']);
  assert.deepEqual(ids('title:طراحی OR title:بازبینی'), ['one', 'two']);
  assert.deepEqual(ids('title:طراحی | title:بازبینی'), ['one', 'two']);
  assert.deepEqual(ids('project:جعبه -priority:high'), ['three']);
  assert.deepEqual(ids('"فایل نهایی PDF"'), ['one']);
  assert.deepEqual(ids('"PDF فایل نهایی"'), []);
  assert.deepEqual(ids('title:طراحی description:"فایل نهایی"'), ['one']);
  assert.deepEqual(ids('title:بازبینی -member:sara'), []);
});

test('Field qualifiers search only selected field and support names in Persian', () => {
  assert.deepEqual(ids('title:جعبه'), ['three']);
  assert.deepEqual(ids('label:طراحی'), ['one']);
  assert.deepEqual(ids('checklist:رنگ'), ['one']);
  assert.deepEqual(ids('report:ایجنت'), ['one']);
  assert.deepEqual(ids('report:فردا'), ['three']);
  assert.deepEqual(ids('project:دیجیتال'), ['two']);
  assert.deepEqual(ids('member:"علی رضایی"'), ['one']);
  assert.deepEqual(ids('member:sara'), ['two']);
  assert.deepEqual(ids('status:"چاپ افست"'), ['one']);
  assert.deepEqual(ids('status:review'), ['two']);
  assert.deepEqual(ids('اولویت:بالا'), ['one']);
  assert.deepEqual(ids('priority:low'), ['two']);
});

test('Date ranges and comparisons accept inclusive Gregorian dates and timestamps', () => {
  assert.deepEqual(ids('due:2026-10-23'), ['one']);
  assert.deepEqual(ids('due:2026-10-01..2026-10-23'), ['one']);
  assert.deepEqual(ids('due:..2026-10-22'), []);
  assert.deepEqual(ids('due:2026-11-01..'), ['two']);
  assert.deepEqual(ids('due>=2026-11-08'), ['two']);
  assert.deepEqual(ids('due>2026-10-23'), ['two']);
  assert.deepEqual(ids('created:2026/10/01..2026/10/15'), ['one', 'three']);
  assert.deepEqual(ids('created<2026-10-01'), ['two']);
});

test('Date queries accept Jalali input and reject nonexistent calendar dates', () => {
  assert.deepEqual(ids('due:۱۴۰۵/۰۸/۰۱'), ['one']);
  assert.deepEqual(ids('due:1405/08/01..1405/08/30'), ['one', 'two']);
  assert.deepEqual(ids('created>=1405/07/09'), ['one', 'three']);
  assert.deepEqual(ids('due:1405/07/32'), []);
  assert.deepEqual(ids('due:2026-02-30'), []);
  assert.deepEqual(ids('due:2026-12-01..2026-01-01'), []);
});

test('Missing data, older checklists and unrecognized qualifiers are handled safely', () => {
  const legacy = {id: 'legacy', title: 'Legacy', checklists: [{title: 'تکمیل', items: [{text: 'آزمایش'}]}]};
  assert.equal(matchesTaskSearch(legacy, 'checklist:آزمایش'), true);
  assert.equal(matchesTaskSearch({title: 'ساده'}, 'report:done'), false);
  assert.deepEqual(filterTasks(null, {query: 'x'}), []);
  assert.deepEqual(filterTasks(tasks, {query: ''}), tasks);
  assert.deepEqual(ids('unknown:whatever'), []);
  assert.deepEqual(parseTaskQuery('a OR b').map(c => c.length), [1, 1]);
});

test('Text search is literal, never evaluates regex and does not expose financial fields', () => {
  assert.deepEqual(ids('.*'), []);
  assert.deepEqual(ids('['), []);
  assert.deepEqual(ids('(abc)+$'), []);
  assert.deepEqual(ids('-due:invalid'), []);
  assert.deepEqual(ids('9000000'), []);
  assert.deepEqual(ids('3000000'), []);
  assert.deepEqual(ids('price:12000000'), []);
  assert.equal(ids('a'.repeat(20000)).length, 0);
});

test('Result order is stable; original tasks and metadata are unchanged', () => {
  const before = JSON.stringify(tasks);
  assert.deepEqual(ids('project:p1'), ['one', 'three']);
  assert.deepEqual(ids('"سارا محمدی" OR "علی رضایی"'), ['one', 'two']);
  assert.equal(JSON.stringify(tasks), before);
});

test('React search control displays accessible help, clear action and result count', () => {
  const result = renderToStaticMarkup(React.createElement(SearchPlus, {
    query: 'title:جعبه', onQueryChange: () => {}, resultCount: 3, totalCount: 18
  }));
  assert.match(result, /role="search"/);
  assert.match(result, /data-no-floating-label=""/, 'search owns its own inline label and icon layout');
  assert.match(result, /type="search"/);
  assert.match(result, /placeholder="جست‌وجو در عنوان/);
  assert.match(result, /جست‌وجوی پیشرفته کارها/);
  assert.match(result, /پاک‌کردن جست‌وجو/);
  assert.match(result, /راهنمای جست‌وجوی پیشرفته/);
  assert.match(result, /۳ نتیجه از ۱۸ کار/);
  assert(!result.includes('searchplus-help-title'));
});
