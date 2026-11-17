'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');
const {buildSync} = require('esbuild');

const root = path.resolve(__dirname, '..');
const dataPath = path.join(root, 'src', 'mtr_context_help_data.js');
const componentPath = path.join(root, 'src', 'mtr_context_help.jsx');
const stylesPath = path.join(root, 'src', 'mtr_context_help.css');
const appSource = fs.readFileSync(path.join(root, 'src', 'App.jsx'), 'utf8');

function bundle(entry) {
  const output = buildSync({
    entryPoints: [entry], bundle: true, format: 'cjs', platform: 'node',
    packages: 'external', write: false,
    loader: {'.jsx': 'jsx', '.css': 'empty'},
  }).outputFiles[0].text;
  const module = {exports: {}};
  // Execute deterministic local source bundled by esbuild, with the normal
  // test module's require. No generated files, browser or app side effects.
  new Function('require', 'module', 'exports', output)(
    require, module, module.exports,
  );
  return module.exports;
}

const {
  MADAR_HELP_SECTIONS, MADAR_HELP_CATEGORIES,
  filterMadarHelpSections, resolveMadarHelpSection,
} = bundle(dataPath);
const {MadarContextHelp, MadarContextHelpPanel} = bundle(componentPath);

test('each topic has a distinct id, recognized category and 1 to 3 short Persian steps', ()=>{
  assert.ok(MADAR_HELP_SECTIONS.length >= 35);
  const ids = new Set();
  const categories = new Set(MADAR_HELP_CATEGORIES);
  for (const item of MADAR_HELP_SECTIONS) {
    assert.equal(ids.has(item.id), false, 'duplicate help section: '+item.id);
    ids.add(item.id);
    assert.match(item.id, /^[a-z][a-z0-9-]*$/);
    assert.ok(categories.has(item.category), 'unlisted category: '+item.id);
    assert.ok(item.title.length>=3 && item.title.length<=60, item.id);
    assert.ok(item.steps.length>=1 && item.steps.length<=3, item.id);
    for (const step of item.steps) {
      assert.ok(step.length>=10 && step.length<=220, item.id);
      assert.match(step, /[آ-ی]/, 'non-Persian help step: '+item.id);
      assert.doesNotMatch(step, /ثبت خودکار سند|رسید رسمی تأیید شده|بدون نیاز به مجوز/);
    }
  }
});

test('observed App.jsx board modes and modal sections have matching help', ()=>{
  const required = {
    board: 'mode===\'board\'',
    list: 'mode===\'list\'',
    table: 'mode===\'table\'',
    time: 'mode===\'time\'',
    gantt: 'mode===\'gantt\'',
    projects: 'projectModal',
    workspace: 'WorkspaceManager',
    cards: '<TaskEditor',
    planner: '<PlannerPanel',
    reporting: 'setReportingOpen',
    automation: '<RulesPanel',
    'automation-buttons': '<AutomationButtonsPanel',
    notifications: '<NotificationsDialog',
    lan: '<LanPanel',
    'lan-users': 'openUserManagement',
    'taraz-exchange': 'tarazIntegrationPrepare',
    sync: 'manualRefresh',
    'web-sync': '<WebSyncDialog',
    settings: '<SettingsPanel',
    backup: '<DrivePanel',
    'project-chat': '<ProjectConversation',
    activity: '<ActivityDialog',
    'card-reports': 'گزارش پیشرفت',
    'card-checklist': 'مراحل انجام',
    'card-files': '<CardAttachments',
    archive: 'cardArchiveOpen',
    trash: 'trashOpen',
    import: '<TrelloImportPanel',
    export: '<PortableExportPanel',
    calendar: '<CalendarFilePanel',
    profile: '<ProfilePanel',
    search: '<SearchResultsPanel',
    filters: '<AdvancedFilters',
    'api-keys': '<IntegrationKeyPanel',
    labels: '<LabelEditor',
    theme: 'toggleTheme',
  };
  for (const [key, marker] of Object.entries(required)) {
    assert.ok(MADAR_HELP_SECTIONS.some(item=>item.id===key), key);
    assert.ok(appSource.includes(marker), 'feature missing in App.jsx: '+key);
  }
});

test('section aliases and missing section resolve safely without new features', ()=>{
  assert.equal(resolveMadarHelpSection('taraz').id, 'taraz-exchange');
  assert.equal(resolveMadarHelpSection('time-dashboard').id, 'time');
  assert.equal(resolveMadarHelpSection('task-editor').id, 'cards');
  assert.equal(resolveMadarHelpSection('unknown-magic-feature').id, 'board');
  assert.equal(resolveMadarHelpSection(null).id, 'board');
});

test('search matches title, category and steps without changing help data', ()=>{
  const all = filterMadarHelpSections();
  const taraz = filterMadarHelpSections({query:'ارسال به تراز'});
  assert.ok(taraz.some(item=>item.id==='taraz-exchange'));
  assert.ok(filterMadarHelpSections({query:'گانت'}).some(item=>item.id==='gantt'));
  assert.ok(filterMadarHelpSections({query:'شبکه'}).some(item=>item.id==='lan'));
  assert.deepEqual(filterMadarHelpSections({query:'چهارگوش ناشناخته'}), []);
  assert.equal(filterMadarHelpSections({query:'  '}).length,all.length);
  assert.equal(filterMadarHelpSections({category:'پیداکردن'}).every(
    item=>item.category==='پیداکردن'), true);
  assert.equal(all.length,MADAR_HELP_SECTIONS.length);
});

test('parent-provided availableSections cannot show unavailable/unknown topics', ()=>{
  const allowed = ['board','cards','taraz','nonexistent','lan-connection'];
  assert.deepEqual(filterMadarHelpSections({availableSections: allowed}).map(x=>x.id),
    ['board','cards','lan','taraz-exchange']);
  assert.deepEqual(filterMadarHelpSections({availableSections: []}), []);
  assert.deepEqual(filterMadarHelpSections({
    availableSections: ['nonexistent'],
  }), []);
});

test('component server rendering starts closed with a small labeled help trigger', ()=>{
  const markup = renderToStaticMarkup(
    React.createElement(MadarContextHelp, {currentSection:'gantt'}),
  );
  assert.match(markup, /aria-label="راهنمای گانت"/);
  assert.match(markup, /aria-expanded="false"/);
  assert.match(markup, /aria-controls="/);
  assert.match(markup, /dir="rtl"/);
  assert.doesNotMatch(markup, /role="region"/);
  assert.doesNotMatch(markup, /راهنمای مدار/);
});

test('open panel uses Persian RTL ordered steps, selectable topics and labeled search', ()=>{
  const markup = renderToStaticMarkup(React.createElement(MadarContextHelpPanel,{
    panelId:'qa-madar-help', currentSection:'taraz-exchange',
    availableSections:['board','taraz-exchange','notifications'],
  }));
  assert.match(markup, /id="qa-madar-help"/);
  assert.match(markup, /role="region"/);
  assert.match(markup, /aria-labelledby="qa-madar-help-title"/);
  assert.match(markup, /<ol>/);
  assert.match(markup, /در برنامه مستقل تراز/);
  assert.match(markup, /id="qa-madar-help-search"/);
  assert.match(markup, /<label for="qa-madar-help-search"/);
  assert.match(markup, /aria-label="بستن راهنما"/);
  assert.match(markup, /aria-label="دسته‌های راهنما"/);
  assert.match(markup, /aria-label="موضوعات راهنما"/);
  assert.doesNotMatch(markup, /راهنمای گانت|راهنمای برنامه‌ریزی/);
});

test('rendered search result filters, empty allowed set and no-result state', ()=>{
  const searched = renderToStaticMarkup(React.createElement(
    MadarContextHelpPanel,{
      panelId:'help-search', currentSection:'board',
      availableSections:['board','cards','lan'],
      query:'اتصال',
    },
  ));
  assert.match(searched, /راهنمای مدار/);
  assert.match(searched, /aria-label="موضوعات راهنما"/);
  assert.match(searched, />اتصال شبکه LAN</);
  assert.doesNotMatch(searched, />کارت و جزئیات</);
  const noSections = renderToStaticMarkup(React.createElement(
    MadarContextHelpPanel, {panelId:'help-empty',availableSections:[]},
  ));
  assert.match(noSections, /برای این بخش راهنمای مجازی در دسترس نیست/);
  const noResults = renderToStaticMarkup(React.createElement(
    MadarContextHelpPanel,{
      panelId:'help-none', availableSections:['board'],
      query:'موضوع ساختگی بدون نتیجه',
    },
  ));
  assert.match(noResults, /نتیجه‌ای برای این جست‌وجو نیست/);
});

test('component includes Escape-to-close and focus return; stylesheet supports RTL themes', ()=>{
  const component = fs.readFileSync(componentPath, 'utf8');
  const css = fs.readFileSync(stylesPath, 'utf8');
  assert.match(component, /event\.key==='Escape'/);
  assert.match(component, /triggerRef\.current\?\.focus\(\)/);
  assert.match(component, /searchRef\.current\?\.focus\(\)/);
  assert.match(component, /aria-expanded=\{open\}/);
  assert.match(css, /:focus-visible/);
  assert.match(css, /var\(--surface/);
  assert.match(css, /direction: rtl/);
  assert.match(css, /@media \(max-width: 480px\)/);
});
