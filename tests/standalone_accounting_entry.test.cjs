const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const source = filename => fs.readFileSync(path.join(root, filename), 'utf8');

test('separate accounting HTML loads its own React entry, not task-manager App', () => {
  const html = source('accounting.html');
  const js = source('src/standalone_main.jsx');
  assert.match(html, /<html lang="fa" dir="rtl">/);
  assert.match(html, /src\/standalone_main\.jsx/);
  assert.doesNotMatch(html, /src\/main\.jsx/);
  assert.match(js, /StandaloneAccountingWorkspace/);
  assert.doesNotMatch(js, /from '\.\/App\.jsx'/);
  assert.doesNotMatch(js, /getState|financeRead|accountingRead\(/);
});

test('accounting page has a separate Vite input and a return path', () => {
  const vite = source('vite.config.js');
  const js = source('src/standalone_main.jsx');
  assert.match(vite, /accounting: resolve\(process\.cwd\(\), 'accounting\.html'\)/);
  assert.match(js, /window\.location\.assign\('\.\/index\.html'\)/);
});

test('main app opens standalone URL without passing tasks or project snapshots', () => {
  const app = source('src/App.jsx');
  assert.match(app, /مدیریت مالی<\/button>/);
  assert.match(app, /window\.location\.assign\('\.\/accounting\.html'\)/);
  assert.doesNotMatch(app, /حسابداری مرتبط با کارت‌ها \(قدیمی\)/);
  assert.match(app, /prepareStandaloneFromTask\(api,/);
});

test('accounting entry respects financeView and standalone host-verified edit capability', () => {
  const app=source('src/App.jsx');
  const entry=source('src/standalone_main.jsx');
  assert.match(app,/canViewStandalone=canManage/);
  assert.match(app,/financeView===true/);
  assert.match(app,/financeEdit===true/);
  assert.match(app,/canViewStandalone&&<button/);
  assert.match(entry,/payload\?\.capabilities\?\.canManage===true/);
  assert.match(entry,/payload\?\.capabilities\?\.canDraft===true/);
  assert.doesNotMatch(entry,/canManage=\{Boolean\(window\.madar\)\}/);
});
