'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const postcss = require('postcss');
const {parse: parseJsx} = require('@babel/parser');
const root = path.resolve(__dirname, '..');
const css = fs.readFileSync(path.join(root,'src/vitrea_shell.css'),'utf8');
const app = fs.readFileSync(path.join(root,'src/App.jsx'),'utf8');
const tree = postcss.parse(css,{from:'src/vitrea_shell.css'});

function matched(selector, media) {
  const matches = [];
  tree.walkRules(node => {
    if (!node.selector.split(/,(?![^()]*\))/).map(x => x.trim()).includes(selector)) return;
    let ancestor = node.parent;
    let responsive = '';
    while (ancestor && ancestor !== tree) {
      if (ancestor.type === 'atrule' && ancestor.name === 'media') responsive = ancestor.params;
      ancestor = ancestor.parent;
    }
    if (responsive !== (media || '')) return;
    const declarations = Object.create(null);
    node.walkDecls(item => { declarations[item.prop] = item.value; });
    matches.push(declarations);
  });
  assert.ok(matches.length, 'Expected rule: '+selector+(media?' @'+media:''));
  return Object.assign({}, ...matches);
}

test('shell preserves existing view semantics and scopes chrome to App', () => {
  assert.ok(parseJsx(app,{sourceType:'module',plugins:['jsx']}).program.body.length);
  for (const classname of ['app-shell','sidebar','workspace','topbar','workspace-scroll','page-header','stats','list-mode'])
    assert.ok(app.includes('className="'+classname+'"') ||
      (classname==='sidebar'&&app.includes("className={'sidebar'")),
      classname+' is still rendered');
  assert.equal(matched('.app-shell').isolation,'isolate');
  assert.equal(matched('.app-shell > .workspace')['min-width'],'0');
  assert.match(matched('.app-shell > .workspace .topbar')['border-radius'], /999px/);
  assert.equal(matched('.app-shell > .workspace > .workspace-scroll')['min-width'],'0');
  assert.doesNotMatch(css,/\.(?:kanban|kanban-lane|lane-cards|task-card)\b/,
    'shell chrome cannot alter the owned Trello board layout');
  assert.doesNotMatch(css,/\.dialog\b|\.overlay\b|\.drawer\b/,
    'modals use their existing accessibility and viewport styles');
});

test('Vitrea glass, graphite, and pills are implemented with light/dark contrast', () => {
  const shell=matched('.app-shell');
  assert.equal(shell['--vs-bg'],'#eef0f4');
  assert.match(shell.background,/radial-gradient/);
  assert.equal(matched(':root[data-theme="dark"] .app-shell')['--vs-bg'],'#111113');
  assert.equal(matched(':root[data-theme="dark"] .app-shell')['--vs-ink'],'#f6f8fc');
  assert.equal(matched(':root[data-theme="dark"] .app-shell')['--vs-accent'],'#8dbcf6');
  const side=matched('.app-shell > .sidebar');
  assert.match(side.background,/var\(--vs-glass\)/);
  assert.match(side['backdrop-filter'],/blur/);
  assert.equal(matched('.app-shell .workspace-scroll .board-tabs')['border-radius'],'999px');
  assert.equal(matched('.app-shell .workspace-scroll .stats .stat-card')['min-width'],'0');
  assert.match(matched('.app-shell .workspace-scroll .list-mode').background,/var\(--vs-glass\)/);
  assert.equal(matched('.app-shell .workspace-scroll .list-mode .list-row').background,'transparent');
});

test('buttons keep keyboard outlines, named navigation and RTL layout', () => {
  assert.match(app,/aria-label="پیمایش برنامه"/);
  assert.match(app,/aria-controls="madar-sidebar"/);
  assert.match(app,/aria-expanded=\{mobileNavOpen\}/);
  const hover=matched('.app-shell > .sidebar .sidebar-nav button:focus-visible');
  assert.equal(hover.color,'var(--vs-ink)');
  assert.equal(matched('.app-shell .topbar .top-icon:is(:hover,:focus-visible)').color,'var(--vs-ink)');
  assert.match(matched('.app-shell > .sidebar .sidebar-nav button.active')['border-inline-start'],/var\(--vs-accent\)/);
  assert.match(matched('.app-shell > .sidebar')['margin-inline-start'],/12px/);
});

test('existing off-canvas drawer remains usable on narrow screens', () => {
  const small=matched('.app-shell > .sidebar','(max-width: 860px)');
  assert.equal(small.position,'fixed');
  assert.equal(small['z-index'],'302');
  assert.equal(small.width,'min(300px, 88vw)');
  assert.equal(small.margin,'0');
  assert.doesNotMatch(JSON.stringify(small),/display:\s*none|visibility:\s*hidden/);
  assert.match(matched('.app-shell .mobile-nav-toggle','(max-width: 860px)').background,/var\(--vs-well\)/);
  const phone=matched('.app-shell .topbar .top-actions','(max-width: 600px)');
  assert.equal(phone['overflow-x'],'auto');
  assert.equal(phone['max-width'],'100%');
  assert.equal(matched('.app-shell .topbar .searchplus-shell','(max-width: 600px)')['min-width'],'0');
  assert.match(css,/@media \(prefers-reduced-motion: reduce\)/);
  assert.match(css,/@media \(prefers-reduced-transparency: reduce\)/);
});
