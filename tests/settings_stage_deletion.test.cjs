'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const esbuild = require('esbuild');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');

const root = path.resolve(__dirname, '..');
function load(file) {
  const filename = path.join(root, file);
  const compiled = esbuild.buildSync({entryPoints: [filename], bundle: true,
    platform: 'node', format: 'cjs', write: false, jsx: 'automatic',
    loader: {'.css': 'empty'}, external: ['react', 'react/jsx-runtime', 'lucide-react']
  }).outputFiles[0].text;
  const moduleCopy = new Module(filename + '.test.cjs', module);
  moduleCopy.filename = filename + '.test.cjs';
  moduleCopy.paths = Module._nodeModulePaths(path.dirname(filename));
  moduleCopy._compile(compiled, moduleCopy.filename);
  return moduleCopy.exports;
}
const {deleteSettingsStage} = load('src/stage_delete_safe.js');
const {SettingsPanel} = load('src/features.jsx');

function makeState() {
  return {
    stages: [{id: 'inbox', label: 'ورودی'}, {id: 'active', label: 'فعال'}, {id: 'done', label: 'تمام'}],
    boards: [
      {id: 'board-a', stages: [{id: 'shared', label: 'مشترک'}, {id: 'archived', label: 'قدیمی', archived: true}, {id: 'next', label: 'بعدی'}]},
      {id: 'board-b', stages: [{id: 'shared', label: 'مشترک'}, {id: 'next', label: 'بعدی'}]}
    ],
    projects: [{id: 'project', price: 7000}],
    settings: {theme: 'light'},
    tasks: [
      {id: 'a', boardId: 'board-a', listId: 'shared', status: 'inbox', cost: 1225,
        checklist: [{id: 'c', cost: 500}], financeMeta: {receiptIds: ['r1']}},
      {id: 'a2', boardId: 'board-a', listId: 'next', status: 'done', cost: 550},
      {id: 'b', boardId: 'board-b', listId: 'shared', status: 'inbox', cost: 2500},
      {id: 'legacy', status: 'active', cost: 300},
    ]
  };
}
const manager = {canManage: true};

test('board delete moves only own cards to an active same-board fallback', () => {
  const before = makeState();
  const after = deleteSettingsStage(before, 'shared', {...manager, boardId: 'board-a'});
  assert.deepEqual(after.boards[0].stages.map(stage => stage.id), ['archived', 'next']);
  assert.strictEqual(after.boards[1], before.boards[1], 'foreign board identity unchanged');
  assert.strictEqual(after.stages, before.stages, 'global stages unchanged');
  assert.equal(after.tasks[0].listId, 'next', 'archive sibling is never a fallback');
  assert.equal(after.tasks[0].status, 'inbox', 'global status preserved');
  assert.equal(after.tasks[0].cost, 1225);
  assert.strictEqual(after.tasks[0].checklist, before.tasks[0].checklist);
  assert.strictEqual(after.tasks[0].financeMeta, before.tasks[0].financeMeta);
  assert.strictEqual(after.projects, before.projects);
  for (const i of [1, 2, 3]) assert.strictEqual(after.tasks[i], before.tasks[i]);
  assert(after.boards[0].stages.some(stage => stage.id === after.tasks[0].listId));
  assert(after.stages.some(stage => stage.id === after.tasks[0].status));
});

test('board projection deletes displayed stage and never changes foreign task identity', () => {
  const base = makeState();
  const projected = {...base, stages: base.boards[0].stages,
    tasks: base.tasks.filter(task => task.boardId === 'board-a')};
  const edited = deleteSettingsStage(projected, 'shared', {...manager, boardId: 'board-a'});
  assert.deepEqual(edited.stages.map(stage => stage.id), ['archived', 'next']);
  assert.strictEqual(edited.tasks[1], projected.tasks[1]);
  assert.strictEqual(edited.boards[1], base.boards[1]);
  // App.jsx's settings adapter can now consume edited.stages / edited.tasks.
  assert(edited.tasks.every(task => edited.stages.some(stage => stage.id === task.listId)));
});

test('global stage deletion refuses to orphan board-owned global statuses', () => {
  const state = makeState();
  const blocked = deleteSettingsStage(state, 'inbox', manager);
  assert.strictEqual(blocked, state);
  assert.strictEqual(blocked.tasks[2], state.tasks[2]);
  assert(state.boards[1].stages.some(stage => stage.id === state.tasks[2].listId));
});

test('global deletion rewrites only legacy tasks, never board-owned list IDs', () => {
  const state = makeState();
  const changed = deleteSettingsStage(state, 'active', manager);
  assert.deepEqual(changed.stages.map(stage => stage.id), ['inbox', 'done']);
  assert.strictEqual(changed.boards, state.boards);
  assert.strictEqual(changed.tasks[0], state.tasks[0]);
  assert.strictEqual(changed.tasks[1], state.tasks[1]);
  assert.strictEqual(changed.tasks[2], state.tasks[2]);
  assert.equal(changed.tasks[3].status, 'inbox');
  assert.equal(changed.tasks[3].cost, 300);
  assert(changed.stages.some(stage => stage.id === changed.tasks[3].status));
});

test('global deletion updates legacy listId when present, without changing unrelated fields', () => {
  const state = makeState();
  state.tasks.push({id: 'legacy-list', listId: 'active', status: 'done',
    cost: 950, checklist: [{id: 'c1', cost: 15}]});
  const changed = deleteSettingsStage(state, 'active', manager);
  assert.equal(changed.tasks[4].listId, 'inbox');
  assert.equal(changed.tasks[4].status, 'done');
  assert.strictEqual(changed.tasks[4].checklist, state.tasks[4].checklist);
});

test('archived target, sole active stage, nonexistent or archived board and denied user are no-ops', () => {
  const state = makeState();
  const cases = [
    ['archived', {...manager, boardId: 'board-a'}],
    ['shared', {...manager, boardId: 'missing'}],
    ['shared', {canManage: false, boardId: 'board-a'}],
    ['missing', {...manager, boardId: 'board-a'}]
  ];
  for (const [id, options] of cases)
    assert.strictEqual(deleteSettingsStage(state, id, options), state);
  state.boards[0].archived = true;
  assert.strictEqual(deleteSettingsStage(state, 'shared', {...manager, boardId: 'board-a'}), state);
  state.boards[0].archived = false;
  state.boards[0].stages = [{id: 'shared'}, {id: 'archived', archived: true}];
  assert.strictEqual(deleteSettingsStage(state, 'shared', {...manager, boardId: 'board-a'}), state);
  state.stages = [{id: 'only'}, {id: 'archived', archived: true}];
  assert.strictEqual(deleteSettingsStage(state, 'only', manager), state);
  state.stages = [{id: 'active'}, {id: 'active'}];
  assert.strictEqual(deleteSettingsStage(state, 'active', manager), state);
  state.boards.push({...state.boards[0]});
  assert.strictEqual(deleteSettingsStage(state, 'shared', {...manager, boardId: 'board-a'}), state);
});

function renderSettings(state, boardId, canManage = true) {
  const board = state.boards.find(item => item.id === boardId);
  return renderToStaticMarkup(React.createElement(SettingsPanel, {
    data: {...state, stages: board?.stages || state.stages}, boardId,
    canManage, priorityUsedIds: [], onChange: () => {}, onClose: () => {},
    onCalendarChange: () => {}, onRestoreList: () => {}
  }));
}

test('board SettingsPanel offers archived restore, not duplicate list management controls', () => {
  const state = makeState();
  const html = renderSettings(state, 'board-a');
  assert.match(html, /مدیریت بازیابی ستون‌های بایگانی‌شده/);
  assert.match(html, /aria-label="بازیابی ستون/);
  assert.doesNotMatch(html, /aria-label="حذف ستون/);
  assert.doesNotMatch(html, /aria-label="انتقال ستون/);
  assert.doesNotMatch(html, /aria-label="بایگانی ستون/);
  assert.doesNotMatch(html, /نام ستون جدید/);
  assert.doesNotMatch(renderSettings(state, 'board-a', false), /aria-label="بازیابی ستون/);
});

test('global SettingsPanel disables delete when a board status references a stage', () => {
  const state = makeState();
  const html = renderSettings(state, null);
  assert.match(html, /مرحله در وضعیت کارت‌های بردهای دیگر استفاده شده است/);
  assert.match(html, /aria-label="حذف ستون ورودی"/);
  const code = fs.readFileSync(path.join(root, 'src/features.jsx'), 'utf8');
  assert.match(code, /key=\{stage\.id\}/);
  assert.match(code, /if\(editing===id\)setEditing\(''\)/);
});
