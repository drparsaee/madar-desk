'use strict';
/**
 * BD13 App/SettingsPanel wiring contract.
 *
 * Read-only inspection of existing sources, SSR of SettingsPanel, and pure
 * synthetic state transitions. No DOM/browser, app Bridge, APPDATA or releases.
 *
 * Known unsafe pathways are intentionally RED assertions (not skipped):
 * the suite serves as a concrete integration regression gate for Prime.
 */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const esbuild = require('esbuild');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');

const root = path.resolve(__dirname, '..');
const appText = fs.readFileSync(path.join(root, 'src', 'App.jsx'), 'utf8');
const featureText = fs.readFileSync(path.join(root, 'src', 'features.jsx'), 'utf8');

function sourceModule(relative, jsx = false) {
  const filename = path.join(root, relative);
  const source = esbuild.buildSync({
    entryPoints: [filename], bundle: true, platform: 'node', format: 'cjs',
    write: false, jsx: 'automatic', loader: {'.jsx': 'jsx', '.css': 'empty'},
    external: ['react', 'react-dom', 'lucide-react']
  }).outputFiles[0].text;
  const loader = new Module(filename + '.test-loader.cjs', module);
  loader.filename = filename + '.test-loader.cjs';
  loader.paths = Module._nodeModulePaths(path.dirname(filename));
  loader._compile(source, loader.filename);
  return loader.exports;
}
const {archiveListState, restoreListState, activeBoardLists} =
  sourceModule('src/listarchive.js');
const {moveCardToBoard} = sourceModule('src/boardops.js');
const {duplicateCard} = sourceModule('src/taskops.js');
const {SettingsPanel} = sourceModule('src/features.jsx', true);
const ADMIN = {canManage: true};

function makeState() {
  return {
    version: 1,
    workspaces: [{id: 'w1', name: 'Workspace', archived: false}],
    projects: [{id: 'p1', name: 'چاپ', price: 50_000_000}],
    stages: [{id: 'inbox', label: 'ورودی'}, {id: 'active', label: 'انجام'}],
    boards: [{
      id: 'b1', workspaceId: 'w1', projectId: 'p1', name: 'نمونه',
      archived: false,
      stages: [
        {id: 'archived-list', label: 'بایگانی', subtitle: 'قدیمی',
          color: '#123456', archived: true},
        {id: 'working-list', label: 'فعال', subtitle: 'در حال کار',
          color: '#654321'}
      ]
    }],
    settings: {theme: 'light', costDefault: false},
    tasks: [
      {id: 'archived-card', boardId: 'b1', projectId: 'p1',
        listId: 'archived-list', status: 'inbox', priority: 'medium',
        title: 'کار قدیمی', archived: false, cost: 2_200_000,
        checklist: [{id: 'step-1', text: 'چاپ', done: false, cost: 300_000}],
        reports: [], financeMeta: {receipts: [1, 2]}},
      {id: 'active-card', boardId: 'b1', projectId: 'p1',
        listId: 'working-list', status: 'active', priority: 'medium',
        title: 'کار فعال', archived: false, cost: 9_700_000,
        checklist: [], reports: []}
    ]
  };
}

function settingsHtml({state = makeState(), canManage = true, boardId = 'b1'} = {}) {
  return renderToStaticMarkup(React.createElement(SettingsPanel, {
    data: {...state, stages: state.boards[0].stages},
    canManage, boardId,
    priorityUsedIds: ['medium'],
    calendar: 'jalali',
    onChange: () => {},
    onClose: () => {},
    onCalendarChange: () => {},
    onArchiveList: () => {},
    onRestoreList: () => {}
  }));
}
function actionButtons(html, title) {
  return [...html.matchAll(/<button\b[^>]*>/g)]
    .map(m => m[0]).filter(tag => tag.includes('title="' + title + '"'));
}

test('App uses presentation-only active stages; SettingsPanel receives full authoritative stages', () => {
  assert.match(appText, /import\s*\{archiveListState,restoreListState,activeBoardLists\}/);
  assert.match(appText, /const viewStages=activeBoard\?activeBoardLists\(activeBoard\):stages/);
  assert.match(appText, /data=\{activeBoard\?\{\.\.\.data,stages:activeBoard\.stages\}:data\}/);
  assert.match(appText, /onArchiveList=\{id=>updateBoardListArchive\(id,false\)\}/);
  assert.match(appText, /onRestoreList=\{id=>updateBoardListArchive\(id,true\)\}/);
});

test('SettingsPanel SSR keeps archived list recovery, with active list actions on the board', () => {
  const html = settingsHtml();
  assert.match(html, /بایگانی‌شده/);
  assert.match(html, /aria-label="بازیابی ستون بایگانی"/);
  assert.doesNotMatch(html, /aria-label="بایگانی ستون فعال"/);
  assert.equal(actionButtons(html, 'بایگانی ستون بدون حذف کارت‌ها').length, 0);
  assert.equal(actionButtons(html, 'بازیابی ستون بدون تغییر کارت‌ها').length, 1);
  assert.match(appText, /<LaneActionsMenu stage=\{stage\}/);
  assert.match(appText, /onArchive=\{activeBoard\?/);
});

test('SettingsPanel SSR hides stage-management actions from viewer/editor', () => {
  const html = settingsHtml({canManage: false});
  assert.doesNotMatch(html, /aria-label="بایگانی ستون /);
  assert.doesNotMatch(html, /aria-label="بازیابی ستون /);
  assert.equal(actionButtons(html, 'حذف').length, 0);
  assert.match(featureText, /canManage&&<div className="stage-manage-actions"/);
});

test('App archive mutation is admin-gated and uses whole-state transform', () => {
  assert.match(appText, /if\(!canManage\|\|!activeBoard\)return/);
  assert.match(appText, /const action=restore\?restoreListState:archiveListState/);
  assert.match(appText, /const options=\{canManage:true\}/);
  assert.match(appText, /changeAdmin\(s=>\{try\{return action\(s,activeBoard\.id,listId,options\)/);
  assert.match(appText, /const changeAdmin=next=>\{if\(!canManage\)return;change\(next\)/);
});

test('last active list cannot be archived from per-list menu even with archived siblings', () => {
  const html = settingsHtml();
  assert.equal(actionButtons(html, 'بایگانی ستون بدون حذف کارت‌ها').length, 0);
  const menu = fs.readFileSync(path.join(__dirname,'../src/board_lane_actions.jsx'),'utf8');
  assert.match(menu, /disabled=\{total<=1\}/);
  const lastOnly = makeState();
  assert.throws(() => archiveListState(lastOnly,'b1','working-list',ADMIN), /last active list/i);
  assert.match(html, /بازیابی ستون/);
});

test('REGRESSION/P0: active-board settings has no destructive delete controls', () => {
  const html = settingsHtml();
  const deletions = actionButtons(html, 'حذف');
  assert.equal(deletions.length, 0);
  assert.doesNotMatch(html, /aria-label="حذف ستون/);
  assert.match(html, /مدیریت بازیابی ستون‌های بایگانی‌شده/);
});

test('pure archive/restore hides and reveals cards without touching amounts or task identity', () => {
  const state = makeState();
  const seen = list => state.tasks.filter(t =>
    activeBoardLists(list).some(stage => t.boardId === list.id && t.listId === stage.id));
  assert.deepEqual(seen(state.boards[0]).map(t => t.id), ['active-card']);
  const restored = restoreListState(state, 'b1', 'archived-list', ADMIN);
  assert.deepEqual(seen(restored.boards[0]).map(t => t.id),
    ['archived-card', 'active-card']);
  assert.strictEqual(restored.tasks, state.tasks);
  assert.equal(restored.tasks[0].cost, 2_200_000);
  assert.equal(restored.tasks[0].checklist[0].cost, 300_000);
  assert.deepEqual(restored.tasks[0].financeMeta, {receipts: [1, 2]});
  assert.deepEqual(seen(archiveListState(restored, 'b1', 'archived-list', ADMIN)
    .boards[0]).map(t => t.id), ['active-card']);
});

test('App filters archived-list cards across board/list/calendar views, not just Kanban', () => {
  // The M03 host-scoped index now rejects archived board/local-list cards at
  // source, rather than retaining the former inline O(boards) scan.
  assert.match(appText,/createBoardPerformanceIndex\(data,/);
  assert.match(appText,/boardIndex\.selectActiveCards\(/);
  assert.match(appText,/boardIndex\.groupActiveCards\(/);
  assert.match(appText, /const filtered=useMemo/);
  assert.match(appText, /<TimeDashboard tasks=\{filtered\}/);
  assert.match(appText, /<ProgressiveLane items=\{filtered\}.*containerClassName="progressive-list-rows" renderCard=\{t=><button key=\{t\.id\} className="list-row"/);
});

test('App create and drag paths restrict target stages to activeBoardLists', () => {
  assert.match(appText, /const targetBoard=workspaceBoards\.find\(b=>b\.id===adding\.boardId&&b\.projectId===adding\.projectId\)/);
  assert.match(appText, /const availableStages=activeBoardLists\(targetBoard\)/);
  assert.match(appText, /if\(!board\|\|!activeBoardLists\(board\)\.some\(stage=>stage\.id===status\)\)/);
  assert.match(appText, /if\(!board\|\|!board\.stages\.some\(item=>item\.id===stage&&!item\.archived\)\)return s/);
  assert.match(appText, /className="lane-quick-add"/);
  assert.match(appText, /if\(!activeBoardLists\(activeBoard\)\.some\(s=>s\.id===toListId\)\)return/);
  assert.match(appText, /if\(requestedList&&board\?\.stages\.some\(stage=>stage\.id===requestedList&&stage\.archived===true\)&&requestedList!==original\?\.listId\)return s/);
  assert.match(appText, /disabled=\{s\.archived===true&&s\.id!==\(task\.listId\|\|task\.status\)\}/);
});

test('REGRESSION/P1: cross-board card move must not choose an archived first stage', () => {
  const state = makeState();
  const target = state.boards[0];
  const outside = {id: 'move-from-another-board', projectId: 'p1',
    boardId: 'b-elsewhere', listId: 'other', status: 'inbox',
    cost: 58_000, checklist: [{cost: 200}]};
  const moved = moveCardToBoard(outside, target, state.stages);
  assert.equal(moved.listId, 'working-list',
    'choosing stages[0] archives an otherwise live moved card');
  assert.equal(moved.cost, 58_000);
});

test('REGRESSION/P1: duplication from archived-stage source must not silently create a hidden clone', () => {
  const state = makeState();
  const source = state.tasks[0];
  const board = state.boards[0];
  const draft = duplicateCard(source, 'duplicate-hidden', '2026-01-01', () => 'fresh');
  const {cardOrder: staleOrder, ...duplicate} = draft;
  const sourceListActive = board.stages.some(stage =>
    stage.id === duplicate.listId && stage.archived !== true);
  // Mirror the currently integrated App.jsx:630-648 active-stage fallback:
  if (!sourceListActive) {
    const fallback = activeBoardLists(board)[0];
    assert.ok(fallback);
    duplicate.listId = fallback.id;
    duplicate.status = 'inbox';
  }
  assert.match(appText, /const sourceListActive=board\?\.stages\.some\(stage=>stage\.id===t\.listId&&stage\.archived!==true\)/);
  assert.match(appText, /const fallback=activeBoardLists\(board\)\[0\]/);
  assert.equal(activeBoardLists(board).some(stage => stage.id === duplicate.listId), true);
  assert.equal(duplicate.cost, 0, 'duplicate must not copy direct financial cost');
  assert.deepEqual(source.financeMeta, {receipts: [1, 2]});
});

test('REGRESSION/P1: project removal must not relocate tasks into archived first list', () => {
  // App project deletion is static-inspected, never invoked against a Bridge.
  const deleteSection = appText.slice(appText.indexOf('const deleteProject='),
    appText.indexOf('const updateSettingsForBoard='));
  assert.match(deleteSection,/if\(tasks\.some\(t=>t\.projectId===projectSettings\)\)/,
    'any project containing cards must now refuse removal; financial links cannot be re-parented');
  assert.doesNotMatch(deleteSection,/tasks:s\.tasks\.map\(t=>t\.projectId===projectSettings/,
    'project deletion must never silently transfer associated cards');
});

test('REGRESSION/P1: duplicating an individually archived card must not keep clone archived', () => {
  const state = makeState();
  const individuallyArchived = {...state.tasks[0], archived: true};
  const duplicate = duplicateCard(individuallyArchived, 'duplicated',
    '2026-01-01', () => 'new');
  assert.equal(duplicate.cost, 0);
  // An archived:true clone remains invisible even after active-stage fallback.
  assert.equal(duplicate.archived, false,
    'clone must be explicitly unarchived before insertion into an active list');
});

test('settings edits must preserve all retained archived stages, never use activeBoardLists as persisted stages', () => {
  assert.match(appText, /const currentBoard=\(s\.boards\|\|\[\]\)\.find\(board=>board\.id===activeBoard\.id\)/);
  assert.match(appText, /const draft=\{\.\.\.s,stages:currentBoard\.stages,tasks:localTasks\}/);
  assert.match(appText, /const edited=fn\(draft\)/);
  assert.match(appText, /boards:s\.boards\.map\(b=>b\.id===activeBoard\.id\?\{\.\.\.b,stages:edited\.stages\}:b\)/);
  assert.match(featureText, /stages:s\.stages\.map\(stage=>stage\.id===id\?\{\.\.\.stage,\.\.\.fields\}:stage\)/);
  assert.doesNotMatch(featureText, /stages:activeBoardLists\(/);
});

test('controller code must keep whole-state CAS path rather than mutate global stages to archive', () => {
  assert.doesNotMatch(appText, /archiveListState\(\s*data\.stages/);
  assert.match(appText, /const action=restore\?restoreListState:archiveListState/);
  assert.match(appText, /api\.saveState\(snapshot\)/);
  assert.match(appText, /if\(result\?\.revision\|\|result\?\.localRevision\)/);
});
