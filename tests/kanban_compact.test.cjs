'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const postcss = require('postcss');

const root = path.resolve(__dirname, '..');
const css = fs.readFileSync(path.join(root, 'src/kanban_compact.css'), 'utf8');
const sheet = postcss.parse(css, {from: 'src/kanban_compact.css'});

function declarations(selector, media = null) {
  const found = [];
  sheet.walkRules(rule => {
    if (!rule.selector.split(/,(?![^()]*\))/).map(s => s.trim()).includes(selector)) return;
    let parent = rule.parent;
    let enclosingMedia = null;
    while (parent && parent !== sheet) {
      if (parent.type === 'atrule' && parent.name === 'media') enclosingMedia = parent.params;
      parent = parent.parent;
    }
    if (media !== enclosingMedia) return;
    const values = {};
    rule.walkDecls(decl => { values[decl.prop] = decl.value; });
    found.push(values);
  });
  assert.ok(found.length, 'Expected CSS rule for ' + selector + (media || ''));
  return Object.assign({}, ...found);
}

test('board keeps independent Trello-width lanes instead of growing or stretching them', () => {
  const board = declarations('.kanban');
  assert.equal(board.display, 'flex');
  assert.equal(board['flex-wrap'], 'nowrap');
  assert.equal(board['align-items'], 'flex-start');
  assert.equal(board['overflow-x'], 'auto');
  assert.equal(board['min-inline-size'], '0');
  const lane = declarations('.kanban > .kanban-lane');
  assert.match(lane.flex, /^0 0 var\(--kanban-column-width\)$/);
  assert.equal(lane['min-inline-size'], 'var(--kanban-column-width)');
  assert.equal(lane['max-inline-size'], 'var(--kanban-column-width)');
  assert.equal(lane['align-self'], 'flex-start');
  assert.equal(lane['flex-direction'], 'column');
  assert.equal(lane['min-block-size'], '0');
  assert.match(lane['max-block-size'], /--kanban-column-max-height/);
  assert.match(board['--kanban-column-width'], /^2(?:8|9)\dpx$/);
});

test('long lists scroll within the card region; a short list remains content-height', () => {
  const viewport = declarations('.kanban .kanban-lane > .lane-subtitle + div');
  assert.equal(viewport.flex, '0 1 auto');
  assert.equal(viewport['min-block-size'], '0');
  assert.equal(viewport['overflow-y'], 'auto');
  assert.equal(viewport['overflow-x'], 'hidden');
  const card = declarations('.kanban .task-card');
  assert.match(card.padding, /^8px /, 'card padding is reduced from the app default 10px');
  const empty = declarations('.kanban .lane-empty');
  assert.equal(empty['min-block-size'], '0', 'empty lists must not force a tall panel');
  assert.equal(declarations('.kanban .lane-empty-message')['text-align'], 'center');
  const app = fs.readFileSync(path.join(root, 'src/App.jsx'), 'utf8');
  assert.match(app, /className="lane-subtitle"[\s\S]{0,130}<ProgressiveLane\b/,
    'ProgressiveLane must remain the lane subtitle’s next sibling to allow inner scrolling');
});

test('inline add-list tile remains a fixed-width sibling, mobile sizes stay bounded', () => {
  const tile = declarations('.kanban > .kanban-add-list');
  assert.equal(tile.flex, '0 0 var(--kanban-column-width)');
  assert.equal(tile['max-inline-size'], 'var(--kanban-column-width)');
  const trigger = declarations('.kanban .kanban-add-list__trigger');
  assert.equal(trigger['inline-size'], '100%');
  assert.ok(Number.parseInt(trigger['min-block-size'], 10) >= 40);
  assert.notEqual(trigger.background, 'transparent', 'the Trello-style tile is visible at rest');
  const mobile = declarations('.kanban', '(max-width: 600px)');
  assert.match(mobile['--kanban-column-width'], /min\(276px, calc\(100vw - 28px\)\)/);
  assert.equal(declarations('.kanban .kanban-add-list__form input')['min-inline-size'], '0');
});

test('the settings portal has bounded scrolling, keyboard affordance, and dark theme', () => {
  const portal = declarations('.lane-actions-popover');
  assert.equal(portal.position, 'fixed');
  assert.equal(portal['overflow-y'], 'auto');
  assert.match(portal['max-block-size'], /100dvh/);
  assert.ok(Number(portal['z-index']) > 60 && Number(portal['z-index']) < 100,
    'the menu must sit over board controls but below modal overlays');
  assert.match(css, /\.lane-actions-popover button:is\(:hover, :focus-visible\)/);
  assert.match(css, /:root\[data-theme="dark"\] \.lane-actions-popover\s*\{/);
  assert.match(css, /:root\[data-theme="dark"\] \.kanban \.kanban-add-list__form input/);
  assert.match(css, /@media \(prefers-reduced-motion: reduce\)/);
});
