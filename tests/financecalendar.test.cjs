const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const Module = require('node:module');
const esbuild = require('esbuild');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');

const root = path.resolve(__dirname, '..');
function bundle(modulePath) {
  const generated = esbuild.buildSync({
    entryPoints: [path.join(root, modulePath)], bundle: true, write: false,
    platform: 'node', format: 'cjs', jsx: 'automatic',
    loader: {'.css': 'empty'}, external: ['react', 'react/jsx-runtime', 'lucide-react']
  }).outputFiles[0].text;
  const loaded = new Module(path.join(root, '__finance_calendar_test__.cjs'), module);
  loaded.filename = path.join(root, '__finance_calendar_test__.cjs');
  loaded.paths = Module._nodeModulePaths(root);
  loaded._compile(generated, loaded.filename);
  return loaded.exports;
}

const {FinanceOverview} = bundle('src/financeoverview.jsx');
const {CalendarField, fromJalali, jalaliDigits} = bundle('src/productivity.jsx');

function financeMarkup(calendar) {
  return renderToStaticMarkup(React.createElement(FinanceOverview, {
    api: {financeOverview: () => Promise.resolve({})},
    projects: [{id: 'p', name: 'پروژه تست'}], initialProjectId: 'p', calendar,
    onClose: () => {}
  }));
}

function calendarInputs(markup) {
  return [...markup.matchAll(/<input\b[^>]*\baria-label="(از تاریخ|تا تاریخ|تاریخ دریافت)"[^>]*>/g)]
    .map(match => ({label: match[1], html: match[0]}));
}

test('FinanceOverview renders CalendarField for both financial filters and the receipt form', () => {
  const markup = financeMarkup('jalali');
  const fields = calendarInputs(markup);
  assert.deepEqual(fields.map(field => field.label), ['از تاریخ', 'تا تاریخ', 'تاریخ دریافت']);
  for (const field of fields) {
    assert.match(field.html, /placeholder="1405\/07\/28"/);
    assert.doesNotMatch(field.html, /type="date"/);
    assert.match(field.html, /dir="ltr"/);
  }
  assert.equal((markup.match(/<small>شمسی<\/small>/g) || []).length, 3);
  assert.doesNotMatch(markup, /تاریخ دریافت \(میلادی\)|از تاریخ میلادی|تا تاریخ میلادی/);
});

test('FinanceOverview switches all three fields to Gregorian with the selected main calendar', () => {
  const markup = financeMarkup('gregorian');
  const fields = calendarInputs(markup);
  assert.equal(fields.length, 3);
  for (const field of fields) assert.match(field.html, /placeholder="2026\/10\/20"/);
  assert.equal((markup.match(/<small>میلادی<\/small>/g) || []).length, 3);
  assert.equal((markup.match(/<small>شمسی<\/small>/g) || []).length, 0);
});

test('Shared CalendarField continues to emit ISO dates for finance API filtering and receipts', () => {
  const iso = '2026-10-20';
  assert.equal(jalaliDigits(new Date(`${iso}T12:00:00Z`)), '1405/07/28');
  assert.equal(fromJalali('۱۴۰۵/۰۷/۲۸'), iso);
  assert.equal(fromJalali('1405/07/28'), iso);
  assert.equal(fromJalali('1405/07/32'), null);
  assert.equal(fromJalali('1405/13/01'), null);
  const converted = fromJalali('۱۴۰۵/۰۷/۲۸');
  const receiptTimestamp = `${converted}T12:00:00Z`;
  assert.equal(receiptTimestamp, '2026-10-20T12:00:00Z');
  // The standalone reusable field must have the same calendar labels and input syntax.
  const standalone = renderToStaticMarkup(React.createElement(CalendarField, {
    value: iso, calendar: 'jalali', label: 'تاریخ دریافت', onChange: () => {}
  }));
  assert.match(standalone, /تاریخ دریافت/);
  assert.match(standalone, /1405\/07\/28/);
});
