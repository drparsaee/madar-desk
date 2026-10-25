'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const Module = require('node:module');
const esbuild = require('esbuild');

const root = path.resolve(__dirname, '..');
const compiled = esbuild.buildSync({
  entryPoints: [path.join(root, 'src', 'boardops.js')],
  bundle: true, platform: 'node', format: 'cjs', write: false
}).outputFiles[0].text;
const loader = new Module(path.join(root, 'src', 'boardops-archive-test.cjs'), module);
loader.filename = path.join(root, 'src', 'boardops-archive-test.cjs');
loader.paths = Module._nodeModulePaths(root);
loader._compile(compiled, loader.filename);
const {moveCardToBoard, boardStageUpdate} = loader.exports;
const stages = [
  {id: 'inbox', label: 'Inbox'}, {id: 'review', label: 'Review'}
];
const card = Object.freeze({
  id: 'card-1', title: 'Keep cost', projectId: 'project-1',
  boardId: 'board-origin', listId: 'inbox', status: 'inbox',
  cardOrder: 4, cost: 310000, invoiceId: 'invoice-1',
  checklist: [{id: 'a', cost: 210000}],
  customFieldValues: {custom: 'data'},
  labelIds: ['label-1']
});
function target(stages) {
  return {id: 'board-target', projectId: 'project-1', archived: false, stages};
}

test('cross-board move skips archived first list and retains financial records', () => {
  const board = target([{id: 'inbox', archived: true}, {id: 'review', archived: false}]);
  const moved = moveCardToBoard(card, board, stages);
  assert.equal(moved.boardId, 'board-target');
  assert.equal(moved.listId, 'review');
  assert.equal(moved.status, 'review');
  assert.equal(moved.cost, card.cost);
  assert.equal(moved.invoiceId, card.invoiceId);
  assert.deepEqual(moved.checklist, card.checklist);
  assert.equal(card.boardId, 'board-origin');
  assert.equal(card.listId, 'inbox');
});

test('cross-board move refuses board with no active lists, preserving original input', () => {
  const board = target([{id: 'inbox', archived: true}, {id: 'review', archived: true}]);
  assert.throws(() => moveCardToBoard(card, board, stages), /فعال/);
  assert.equal(card.boardId, 'board-origin');
});

test('board local stage move retains its financial fields', () => {
  const moved = boardStageUpdate(card, target([{id: 'review', archived: false}]), stages, 'review');
  assert.equal(moved.listId, 'review');
  assert.equal(moved.cost, card.cost);
  assert.equal(moved.cardOrder, card.cardOrder);
  assert.deepEqual(moved.checklist, card.checklist);
});
