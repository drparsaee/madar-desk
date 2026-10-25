'use strict';
/** BD13: disposable, pure-state tests; no bridge, filesystem data or APPDATA. */
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const Module = require('node:module');
const esbuild = require('esbuild');
const root = path.resolve(__dirname, '..');
const compiled = esbuild.buildSync({
  entryPoints: [path.join(root, 'src', 'listarchive.js')],
  bundle: true, platform: 'node', format: 'cjs', write: false
}).outputFiles[0].text;
const loader = new Module(path.join(root, 'src', 'listarchive-test.cjs'), module);
loader.filename = path.join(root, 'src', 'listarchive-test.cjs');
loader.paths = Module._nodeModulePaths(root);
loader._compile(compiled, loader.filename);
const {archiveListState, restoreListState, activeBoardLists} = loader.exports;
const ADMIN = Object.freeze({canManage: true});

function freezeDeep(object) {
  if (!object || typeof object !== 'object' || Object.isFrozen(object)) return object;
  for (const key of Object.keys(object)) freezeDeep(object[key]);
  return Object.freeze(object);
}

function task(id, listId, extras = {}) {
  return {
    id, projectId: 'project-a', boardId: 'board-a', listId,
    title: 'تسک ' + id, status: 'active', priority: 'high', cardOrder: 900,
    cost: 804500, costEnabled: true, costDate: '2026-01-05',
    costCategory: 'مواد چاپی', contractValue: 12500000,
    checklist: [{id: 'step-' + id, text: 'هزینه', done: false, cost: 66500}],
    checklists: [{id: 'group-' + id, name: 'گروه', items: [
      {id: 'nested-' + id, text: 'صحافی', done: true, cost: 2400}]}],
    reports: [{id: 'report-' + id, summary: 'تمام'}],
    assignees: ['operator'], labelIds: ['label-a'],
    customFieldValues: {fieldA: 'value'},
    financeExtension: {ledger: ['one', 'two']},
    ...extras
  };
}

function stateFixture() {
  return {
    version: 1,
    projects: [
      {id: 'project-a', name: 'الف', price: 91500000, financeMeta: {tax: 9}},
      {id: 'project-b', name: 'ب', price: 25000000}
    ],
    workspaces: [{id: 'workspace-legacy', name: 'پیش‌فرض', archived: false}],
    boards: [
      {id: 'board-a', workspaceId: 'workspace-legacy',
        projectId: 'project-a', name: 'برد چاپ', archived: false,
        stages: [
          {id: 'inbox', label: 'ورودی', color: '#123456', subtitle: 'اول', archived: false,
            extra: {icon: 'star'}},
          {id: 'print', label: 'چاپ', subtitle: 'در حال چاپ', color: '#123456'},
          {id: 'deliver', label: 'تحویل', subtitle: 'نهایی', color: '#123456'}
        ],
        customFields: [{id: 'fieldA', name: 'بسته', type: 'text'}],
        labelDefinitions: [{id: 'label-a', name: 'مهم', color: '#345678'}]},
      {id: 'board-b', workspaceId: 'workspace-legacy',
        projectId: 'project-b', name: 'برد دیگر', archived: false,
        stages: [
          {id: 'inbox', label: 'ورودی', color: '#567890'},
          {id: 'deliver', label: 'تحویل', color: '#567890'}
        ], customFields: [], labelDefinitions: []}
    ],
    stages: [{id: 'inbox', label: 'ورودی'},{id: 'active', label: 'فعال'}],
    templates: [{id: 'temp', boardId: 'board-a', listId: 'print'}],
    tasks: [
      task('one', 'print'),
      task('two', 'print', {archived: true, archivedByBoard: true}),
      task('three', 'deliver'),
      task('', 'inbox', {projectId: 'project-a', archived: false}),
      task('foreign', 'inbox', {projectId: 'project-b', boardId: 'board-b',
        cost: 91300000, financeExtension: {ledger: ['hidden-other-board']}})
    ],
    financeState: {invoices: [{id: 'invoice-1', sum: 35000000}]},
    collabState: {comments: [{id: 'note', cardId: 'one', text: 'حفظ شود'}]},
    settings: {theme: 'dark', costDefault: true},
    __remoteRevision: 'a'.repeat(64)
  };
}

test('archive marks only board-local stage archived and preserves all stage fields', () => {
  const before = freezeDeep(stateFixture());
  const after = archiveListState(before, 'board-a', 'print', ADMIN);
  assert.notStrictEqual(after, before);
  assert.notStrictEqual(after.boards, before.boards);
  assert.notStrictEqual(after.boards[0], before.boards[0]);
  assert.notStrictEqual(after.boards[0].stages, before.boards[0].stages);
  assert.deepEqual(after.boards[0].stages[1],
    {...before.boards[0].stages[1], archived: true});
  assert.equal(before.boards[0].stages[1].archived, undefined);
  assert.strictEqual(after.boards[0].stages[0], before.boards[0].stages[0]);
  assert.strictEqual(after.boards[0].stages[2], before.boards[0].stages[2]);
  assert.strictEqual(after.boards[1], before.boards[1]);
  assert.deepEqual(after.boards[0].stages.map(s => s.id), ['inbox', 'print', 'deliver']);
  assert.deepEqual(activeBoardLists(after.boards[0]).map(s => s.id), ['inbox', 'deliver']);
  assert.deepEqual(activeBoardLists(before.boards[0]).map(s => s.id),
    ['inbox', 'print', 'deliver']);
});

test('archive never edits task array, archived cards, child checklists or financial records', () => {
  const before = freezeDeep(stateFixture());
  const baseline = JSON.stringify(before);
  const after = archiveListState(before, 'board-a', 'print', ADMIN);
  assert.strictEqual(after.tasks, before.tasks);
  for (let i = 0; i < before.tasks.length; i++) {
    assert.strictEqual(after.tasks[i], before.tasks[i]);
  }
  assert.equal(after.tasks[0].boardId, 'board-a');
  assert.equal(after.tasks[0].listId, 'print');
  assert.equal(after.tasks[0].status, 'active');
  assert.equal(after.tasks[0].cardOrder, 900);
  assert.equal(after.tasks[0].cost, 804500);
  assert.equal(after.tasks[0].checklist[0].cost, 66500);
  assert.equal(after.tasks[0].checklists[0].items[0].cost, 2400);
  assert.equal(after.tasks[0].contractValue, 12500000);
  assert.deepEqual(after.tasks[0].financeExtension, {ledger: ['one', 'two']});
  assert.equal(after.tasks[1].archived, true);
  assert.equal(after.tasks[1].archivedByBoard, true);
  assert.strictEqual(after.projects, before.projects);
  assert.strictEqual(after.stages, before.stages);
  assert.strictEqual(after.settings, before.settings);
  assert.strictEqual(after.financeState, before.financeState);
  assert.strictEqual(after.collabState, before.collabState);
  assert.strictEqual(after.templates, before.templates);
  assert.equal(after.__remoteRevision, before.__remoteRevision);
  assert.equal(JSON.stringify(before), baseline);
});

test('restoration from archived state in place preserves all cards and finance', () => {
  const before = freezeDeep(stateFixture());
  const archived = archiveListState(before, 'board-a', 'print', ADMIN);
  const restored = restoreListState(archived, 'board-a', 'print', ADMIN);
  assert.equal(restored.boards[0].stages[1].archived, false);
  assert.deepEqual(restored.boards[0].stages.map(s => s.id),
    before.boards[0].stages.map(s => s.id));
  assert.deepEqual(activeBoardLists(restored.boards[0]).map(s => s.id),
    ['inbox', 'print', 'deliver']);
  assert.strictEqual(restored.tasks, before.tasks);
  assert.strictEqual(restored.financeState, before.financeState);
  assert.strictEqual(restored.projects, before.projects);
  assert.strictEqual(restored.boards[1], before.boards[1]);
});

test('already archived and already active calls are idempotent by reference', () => {
  const state = freezeDeep(stateFixture());
  assert.strictEqual(restoreListState(state, 'board-a', 'print', ADMIN), state);
  assert.strictEqual(restoreListState(state, 'board-a', 'inbox', ADMIN), state);
  const archived = archiveListState(state, 'board-a', 'print', ADMIN);
  assert.strictEqual(archiveListState(archived, 'board-a', 'print', ADMIN), archived);
  const restored = restoreListState(archived, 'board-a', 'print', ADMIN);
  assert.strictEqual(restoreListState(restored, 'board-a', 'print', ADMIN), restored);
});

test('last active list protected even though stored stages remain nonempty', () => {
  const input = stateFixture();
  input.boards[0].stages[0].archived = true;
  input.boards[0].stages[1].archived = true;
  assert.throws(() => archiveListState(input, 'board-a', 'deliver', ADMIN),
    /last active list/);
  assert.equal(input.boards[0].stages[2].archived, undefined);
  assert.strictEqual(archiveListState(input, 'board-a', 'print', ADMIN), input);
  const restored = restoreListState(input, 'board-a', 'print', ADMIN);
  assert.equal(restored.boards[0].stages[1].archived, false);
  assert.equal(restored.boards[0].stages[0].archived, true);
});

test('single-list board refuses archive and accepts no-op restore', () => {
  const input = stateFixture();
  input.boards[0].stages = [input.boards[0].stages[0]];
  assert.throws(() => archiveListState(input, 'board-a', 'inbox', ADMIN),
    /last active list/);
  assert.strictEqual(restoreListState(input, 'board-a', 'inbox', ADMIN), input);
});

test('permission gate refuses omitted, false, viewer/editor and coerced ACL values', () => {
  const input = freezeDeep(stateFixture());
  const original = JSON.stringify(input);
  for (const options of [undefined, {}, {canManage: false},
    {canManage: null}, {canManage: 1}, {canManage: 'true'},
    {canManage: 'admin'}, true, null]) {
    assert.throws(() => archiveListState(input, 'board-a', 'print', options),
      /PERMISSION_DENIED|must be an object/);
    const archived = {...input, boards: input.boards.map((b, i) =>
      i ? b : {...b, stages: b.stages.map(s =>
        s.id === 'print' ? {...s, archived: true} : s)})};
    assert.throws(() => restoreListState(archived, 'board-a', 'print', options),
      /PERMISSION_DENIED|must be an object/);
  }
  assert.equal(JSON.stringify(input), original);
});

test('cannot archive or restore a list under an archived board', () => {
  const state = stateFixture();
  state.boards[0].archived = true;
  assert.throws(() => archiveListState(state, 'board-a', 'print', ADMIN),
    /Archived board/);
  state.boards[0].stages[1].archived = true;
  assert.throws(() => restoreListState(state, 'board-a', 'print', ADMIN),
    /Archived board/);
});

test('cross-board IDs never resolve through the wrong board or global stage list', () => {
  const input = freezeDeep(stateFixture());
  const archived = archiveListState(input, 'board-b', 'inbox', ADMIN);
  assert.equal(archived.boards[1].stages[0].archived, true);
  assert.strictEqual(archived.boards[0], input.boards[0]);
  assert.strictEqual(archived.stages, input.stages);
  assert.throws(() => archiveListState(input, 'board-b', 'print', ADMIN),
    /Unknown list ID/);
  assert.throws(() => restoreListState(input, 'board-b', 'print', ADMIN),
    /Unknown list ID/);
  assert.throws(() => archiveListState(input, 'unknown-board', 'inbox', ADMIN),
    /Unknown board ID/);
});

test('global stage records are never toggled even if ID equals board-local list', () => {
  const input = freezeDeep(stateFixture());
  const globalBefore = JSON.stringify(input.stages);
  const archived = archiveListState(input, 'board-a', 'inbox', ADMIN);
  assert.strictEqual(archived.stages, input.stages);
  assert.equal(JSON.stringify(archived.stages), globalBefore);
  const restored = restoreListState(archived, 'board-a', 'inbox', ADMIN);
  assert.strictEqual(restored.stages, input.stages);
  assert.equal(JSON.stringify(restored.stages), globalBefore);
});

test('projectless boards are valid; legacy empty project ID remains a legal reference', () => {
  const input = stateFixture();
  input.boards[0].projectId = null;
  assert.equal(archiveListState(input, 'board-a', 'inbox', ADMIN)
    .boards[0].stages[0].archived, true);
  input.boards[0].projectId = '';
  input.projects[0].id = '';
  assert.equal(archiveListState(input, 'board-a', 'inbox', ADMIN)
    .boards[0].stages[0].archived, true);
});

test('broken board/project/workspace references and duplicate board IDs refuse mutation', () => {
  for (const change of [
    state => { state.boards[0].projectId = 'missing-project'; },
    state => { state.boards[0].workspaceId = 'missing-workspace'; },
    state => { state.boards[0].projectId = 27; },
    state => { state.boards.push({...state.boards[0]}); },
    state => { state.boards[0].stages = null; },
    state => { state.workspaces = undefined; },
    state => { state.projects = null; },
    state => { state.tasks = {}; }
  ]) {
    const state = stateFixture();
    change(state);
    assert.throws(() => archiveListState(state, 'board-a', 'print', ADMIN));
  }
});

test('bad list IDs, repeated list IDs, invalid archive flag and malformed stage reject', () => {
  const base = stateFixture();
  for (const id of ['', ' ', null, 5, {}, [], 'x'.repeat(101)]) {
    assert.throws(() => archiveListState(base, 'board-a', id, ADMIN));
    assert.throws(() => restoreListState(base, id, 'print', ADMIN));
  }
  for (const mutate of [
    state => { state.boards[0].stages.push({...state.boards[0].stages[1]}); },
    state => { state.boards[0].stages[0].archived = 'false'; },
    state => { state.boards[0].stages[1].archived = null; },
    state => { state.boards[0].stages[1].id = ''; },
    state => { state.boards[0].stages[1] = null; },
    state => { state.boards[0].stages = []; }
  ]) {
    const input = stateFixture();
    mutate(input);
    assert.throws(() => archiveListState(input, 'board-a', 'print', ADMIN));
  }
});

test('roundtrip through JSON and future extension fields remains reversible', () => {
  const input = freezeDeep(stateFixture());
  const archived = archiveListState(input, 'board-a', 'print', ADMIN);
  const stored = JSON.parse(JSON.stringify(archived));
  assert.equal(stored.boards[0].stages[1].archived, true);
  assert.equal(stored.tasks[0].listId, 'print');
  const restored = restoreListState(stored, 'board-a', 'print', ADMIN);
  const secondCopy = JSON.parse(JSON.stringify(restored));
  assert.equal(secondCopy.boards[0].stages[1].archived, false);
  assert.equal(secondCopy.tasks[0].financeExtension.ledger[1], 'two');
  assert.equal(secondCopy.projects[0].price, 91500000);
  assert.equal(secondCopy.templates[0].listId, 'print');
  assert.equal(secondCopy.collabState.comments[0].cardId, 'one');
  assert.deepEqual(activeBoardLists(secondCopy.boards[0]).map(s => s.id),
    ['inbox', 'print', 'deliver']);
});

test('repeated archive and restore cycles do not reorder tasks or stages', () => {
  const original = freezeDeep(stateFixture());
  const originalTaskBytes = JSON.stringify(original.tasks);
  const originalStageIds = original.boards[0].stages.map(stage => stage.id);
  let current = original;
  for (let i = 0; i < 40; i++) {
    current = archiveListState(current, 'board-a', 'print', ADMIN);
    current = restoreListState(current, 'board-a', 'print', ADMIN);
    assert.deepEqual(current.boards[0].stages.map(stage => stage.id), originalStageIds);
    assert.equal(JSON.stringify(current.tasks), originalTaskBytes);
  }
  assert.equal(current.boards[0].stages[1].archived, false);
});

test('activeBoardLists only filters for presentation and never mutates input', () => {
  const board = freezeDeep(stateFixture().boards[0]);
  const first = activeBoardLists(board);
  assert.notStrictEqual(first, board.stages);
  assert.deepEqual(first, board.stages);
  first.pop();
  assert.equal(board.stages.length, 3);
  assert.throws(() => activeBoardLists({stages: null}), /stages must be an array/);
});
