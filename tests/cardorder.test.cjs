'use strict';
// Source-only, disposable state tests. No Bridge, APPDATA, Git or Windows RC.
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const Module = require('node:module');
const esbuild = require('esbuild');
const root = path.resolve(__dirname, '..');
const compiled = esbuild.buildSync({
  entryPoints: [path.join(root, 'src', 'cardorder.js')],
  bundle: true, platform: 'node', format: 'cjs', write: false
}).outputFiles[0].text;
const loader = new Module(path.join(root, 'src', 'cardorder-test-loader.cjs'), module);
loader.filename = path.join(root, 'src', 'cardorder-test-loader.cjs');
loader.paths = Module._nodeModulePaths(root);
loader._compile(compiled, loader.filename);
const {
  MAX_CARD_ORDER, getOrderedLaneCards, normalizeCardOrders, moveCardInState,
  prepareCardOrderCAS
} = loader.exports;

const revision = 'a'.repeat(64);
const stages = ['inbox', 'planned', 'done'];
function card(id, boardId = 'board-a', listId = 'inbox', extras = {}) {
  return {
    id, projectId: boardId === 'board-a' ? 'p-a' : 'p-b',
    boardId, listId, status: listId,
    title: 'کارت ' + id, cost: 250000, costCategory: 'print',
    price: 1000000, contractAmount: 9000000, financeFlags: {internal: true},
    checklist: [{id: 'step-' + id, text: 'کار', done: false, cost: 37000}],
    reports: [{id: 'report-' + id, summary: 'ok'}],
    labels: ['مهم'], labelIds: ['label-a'], assignees: ['person'],
    customFieldValues: {'field-a': 'confidential'},
    ...(extras || {})
  };
}
function makeState(tasks = []) {
  return {
    version: 1,
    settings: {theme: 'dark', costDefault: true},
    stages: stages.map(id => ({id})),
    projects: [
      {id: 'p-a', name: 'P A', price: 20_000_000},
      {id: 'p-b', name: 'P B', price: 70_000_000}
    ],
    boards: [
      {id: 'board-a', projectId: 'p-a',
        stages: [{id: 'inbox'}, {id: 'planned'}, {id: 'custom-a'}]},
      {id: 'board-b', projectId: 'p-b',
        stages: [{id: 'inbox'}, {id: 'planned'}, {id: 'custom-b'}]}
    ],
    tasks
  };
}
function ids(tasks) { return tasks.map(t => t.id); }
function lane(state, boardId = 'board-a', listId = 'inbox') {
  return getOrderedLaneCards(state.tasks, boardId, listId);
}
function deepFreeze(object) {
  if (!object || typeof object !== 'object' || Object.isFrozen(object)) return object;
  for (const key of Object.keys(object)) deepFreeze(object[key]);
  return Object.freeze(object);
}
function positions(state, board = 'board-a', list = 'inbox') {
  return lane(state, board, list).map(t => t.cardOrder);
}

test('exports bounded contract and stable legacy insertion order, no migration needed for read', () => {
  const old = makeState([card('z'), card('b'), card('a')]);
  const before = JSON.stringify(old);
  assert.equal(MAX_CARD_ORDER, 1_000_000);
  assert.deepEqual(ids(lane(old)), ['z', 'b', 'a']);
  assert.notStrictEqual(lane(old), old.tasks);
  assert.equal(JSON.stringify(old), before);
});

test('host-valid empty legacy task/project IDs remain visible and financially unchanged', () => {
  // data_model.py _records(...legacy_ids=True) and native_app.is_valid accept
  // unique empty task/project IDs. Normalized data still has real board/list IDs.
  const blank = card('', 'board-a', 'inbox', {
    projectId: '', cost: 874_003, price: 10_000_003,
    checklist: [{id: 'pay-step', text: 'هزینه', done: false, cost: 50_007}]
  });
  const ordered = card('next', 'board-a', 'inbox', {cardOrder: 0});
  const state = deepFreeze(makeState([blank, ordered]));
  const serialized = JSON.stringify(state);
  const visible = getOrderedLaneCards(state.tasks, 'board-a', 'inbox');
  assert.deepEqual(ids(visible), ['next', '']);
  assert.strictEqual(visible[1], blank);
  assert.equal(visible[1].projectId, '');
  assert.equal(visible[1].cost, 874_003);
  assert.equal(visible[1].price, 10_000_003);
  assert.equal(visible[1].checklist[0].cost, 50_007);
  assert.equal(JSON.stringify(state), serialized);
  assert.deepEqual(ids(getOrderedLaneCards(JSON.parse(serialized).tasks,
    'board-a', 'inbox')), ['next', '']);
  // Mutating a card, or merely normalizing a state containing an unsafe
  // legacy identity, must fail rather than corrupt key-based update maps.
  assert.throws(() => normalizeCardOrders(state), /task\.id/);
  assert.throws(() => moveCardInState(state, {
    cardId: '', toListId: 'inbox', placement: 'end'
  }), /task\.id/);
  assert.throws(() => moveCardInState(state, {
    cardId: 'next', toListId: 'inbox', placement: 'start'
  }), /task\.id/);
  assert.equal(JSON.stringify(state), serialized);
});

test('very long and control-character legacy IDs render in deterministic read order', () => {
  const longId = 'شناسه-قدیمی-' + 'x'.repeat(5_000);
  const newlineId = 'row\nlegacy\tid';
  const cards = [
    card(longId, 'board-a', 'inbox'),
    card(newlineId, 'board-a', 'inbox', {cardOrder: 5}),
    card('safe', 'board-a', 'inbox', {cardOrder: 5}),
    card('  ', 'board-a', 'inbox')
  ];
  const state = deepFreeze(makeState(cards));
  assert.deepEqual(ids(lane(state)), [newlineId, 'safe', longId, '  ']);
  assert.deepEqual(ids(lane(state)), [newlineId, 'safe', longId, '  ']);
  assert.deepEqual(state.tasks.map(t => t.cardOrder), [undefined, 5, 5, undefined]);
  for (const id of [longId, newlineId, '  ']) {
    assert.throws(() => moveCardInState(makeState([card(id)]), {
      cardId: id, toListId: 'inbox'
    }), /task\.id/);
    assert.throws(() => normalizeCardOrders(makeState([card(id)])), /task\.id/);
  }
  // A valid host ID may be long, but mutation must never silently truncate it.
  assert.equal(lane(state)[2].id.length, longId.length);
});

test('duplicate IDs cannot be read or mutated and non-string IDs are never silently accepted', () => {
  const duplicated = makeState([card(''), card('')]);
  const snapshot = JSON.stringify(duplicated);
  assert.throws(() => getOrderedLaneCards(duplicated.tasks, 'board-a', 'inbox'),
    /Duplicate card id/);
  assert.throws(() => moveCardInState(duplicated, {
    cardId: '', toListId: 'inbox'
  }), /task\.id|Duplicate card id/);
  assert.equal(JSON.stringify(duplicated), snapshot);
  const sameValidId = makeState([card('identical'), card('identical')]);
  assert.throws(() => getOrderedLaneCards(sameValidId.tasks, 'board-a', 'inbox'),
    /Duplicate card id/);
  assert.throws(() => normalizeCardOrders(sameValidId), /Duplicate card id/);
  for (const invalid of [undefined, null, 0, false, {}, []]) {
    const state = makeState([card('valid'), card(invalid)]);
    assert.throws(() => getOrderedLaneCards(state.tasks, 'board-a', 'inbox'),
      /task\.id must be a string/);
  }
});

test('explicit positions take precedence; ties preserve insertion; missing positions stay last', () => {
  const old = makeState([
    card('legacy-1'), card('ordered-7', 'board-a', 'inbox', {cardOrder: 7}),
    card('ordered-2a', 'board-a', 'inbox', {cardOrder: 2}),
    card('legacy-2'), card('ordered-2b', 'board-a', 'inbox', {cardOrder: 2})
  ]);
  assert.deepEqual(ids(lane(old)),
    ['ordered-2a', 'ordered-2b', 'ordered-7', 'legacy-1', 'legacy-2']);
  const fixed = normalizeCardOrders(old);
  assert.deepEqual(ids(lane(fixed)),
    ['ordered-2a', 'ordered-2b', 'ordered-7', 'legacy-1', 'legacy-2']);
  assert.deepEqual(positions(fixed), [0, 1, 2, 3, 4]);
  assert.equal(Object.hasOwn(old.tasks[0], 'cardOrder'), false);
});

test('normalization is immutable, dense, idempotent and safe on frozen nested finance state', () => {
  const old = deepFreeze(makeState([
    card('c', 'board-a', 'inbox', {cardOrder: 750}),
    card('a', 'board-a', 'inbox', {cardOrder: 0}),
    card('b'), card('other', 'board-b')
  ]));
  const fixed = normalizeCardOrders(old);
  assert.notStrictEqual(fixed, old);
  assert.notStrictEqual(fixed.tasks, old.tasks);
  assert.deepEqual(ids(lane(fixed)), ['a', 'c', 'b']);
  assert.deepEqual(positions(fixed), [0, 1, 2]);
  assert.equal(lane(fixed, 'board-b')[0].cardOrder, 0);
  assert.equal(normalizeCardOrders(fixed), fixed);
  assert.strictEqual(fixed.boards, old.boards);
  assert.strictEqual(fixed.projects, old.projects);
  assert.strictEqual(fixed.settings, old.settings);
  assert.strictEqual(fixed.tasks.find(t => t.id === 'c').checklist,
    old.tasks.find(t => t.id === 'c').checklist);
  assert.deepEqual(old.tasks.map(t => t.cardOrder), [750, 0, undefined, undefined]);
});

test('normalize one lane only: other list and board tasks retain byte-equivalent object identity', () => {
  const a = card('a');
  const b = card('b', 'board-a', 'planned', {cardOrder: 500});
  const other = card('other', 'board-b', 'inbox', {cardOrder: 799});
  const source = makeState([a, b, other]);
  const next = normalizeCardOrders(source, {boardId: 'board-a', listId: 'inbox'});
  assert.equal(next.tasks[0].cardOrder, 0);
  assert.strictEqual(next.tasks[1], b);
  assert.strictEqual(next.tasks[2], other);
  assert.equal(next.tasks[2].cardOrder, 799);
  assert.deepEqual(ids(lane(next, 'board-b')), ['other']);
});

test('reorder before and after anchor within same lane; original task-array insertion untouched', () => {
  const old = deepFreeze(makeState([card('a'), card('b'), card('c'), card('d')]));
  const first = moveCardInState(old, {
    cardId: 'd', toListId: 'inbox', anchorCardId: 'b', placement: 'before'
  });
  assert.deepEqual(ids(lane(first)), ['a', 'd', 'b', 'c']);
  assert.deepEqual(positions(first), [0, 1, 2, 3]);
  assert.deepEqual(ids(first.tasks), ['a', 'b', 'c', 'd']);
  assert.deepEqual(ids(lane(old)), ['a', 'b', 'c', 'd']);
  const second = moveCardInState(first, {
    cardId: 'a', toListId: 'inbox', anchorCardId: 'b', placement: 'after'
  });
  assert.deepEqual(ids(lane(second)), ['d', 'b', 'a', 'c']);
  assert.deepEqual(positions(second), [0, 1, 2, 3]);
});

test('start/end are stable and repeated move is identity no-op after first canonical order', () => {
  const old = makeState([
    card('a', 'board-a', 'inbox', {cardOrder: 0}),
    card('b', 'board-a', 'inbox', {cardOrder: 1}),
    card('c', 'board-a', 'inbox', {cardOrder: 2})
  ]);
  const top = moveCardInState(old, {cardId: 'c', toListId: 'inbox', placement: 'start'});
  assert.deepEqual(ids(lane(top)), ['c', 'a', 'b']);
  assert.strictEqual(moveCardInState(top, {cardId: 'c', toListId: 'inbox',
    placement: 'start'}), top);
  const bottom = moveCardInState(top, {cardId: 'c', toListId: 'inbox', placement: 'end'});
  assert.deepEqual(ids(lane(bottom)), ['a', 'b', 'c']);
  assert.strictEqual(moveCardInState(bottom, {cardId: 'c', toListId: 'inbox',
    placement: 'end'}), bottom);
  assert.strictEqual(moveCardInState(bottom, {cardId: 'a', toListId: 'inbox',
    anchorCardId: 'a', placement: 'after'}), bottom);
});

test('insert into other list before or after target: compact source and destination, update compatibility status', () => {
  const state = deepFreeze(makeState([
    card('s0'), card('move'), card('s2'),
    card('x', 'board-a', 'planned'), card('y', 'board-a', 'planned')
  ]));
  const before = moveCardInState(state, {
    cardId: 'move', toListId: 'planned', anchorCardId: 'y', placement: 'before'
  });
  assert.deepEqual(ids(lane(before, 'board-a', 'inbox')), ['s0', 's2']);
  assert.deepEqual(ids(lane(before, 'board-a', 'planned')), ['x', 'move', 'y']);
  assert.deepEqual(positions(before, 'board-a', 'inbox'), [0, 1]);
  assert.deepEqual(positions(before, 'board-a', 'planned'), [0, 1, 2]);
  const moved = before.tasks.find(t => t.id === 'move');
  assert.equal(moved.listId, 'planned');
  assert.equal(moved.status, 'planned');
  assert.equal(moved.boardId, 'board-a');
  assert.equal(moved.projectId, 'p-a');
  assert.equal(moved.cost, 250000);
  assert.equal(moved.checklist[0].cost, 37000);
  assert.equal(moved.price, 1000000);
  assert.equal(moved.contractAmount, 9000000);
  assert.deepEqual(moved.financeFlags, {internal: true});
  assert.strictEqual(moved.checklist, state.tasks[1].checklist);
  assert.deepEqual(ids(lane(state, 'board-a', 'inbox')), ['s0', 'move', 's2']);
  const after = moveCardInState(before, {
    cardId: 'move', toListId: 'planned', anchorCardId: 'y', placement: 'after'
  });
  assert.deepEqual(ids(lane(after, 'board-a', 'planned')), ['x', 'y', 'move']);
  assert.strictEqual(moveCardInState(after, {
    cardId: 'move', toListId: 'planned', anchorCardId: 'y', placement: 'after'
  }), after);
});

test('board-specific list stage maps to valid fallback global status without changing project', () => {
  const input = makeState([card('move'), card('other', 'board-a', 'custom-a')]);
  const next = moveCardInState(input, {cardId: 'move', toListId: 'custom-a',
    placement: 'end'});
  assert.equal(next.tasks[0].listId, 'custom-a');
  assert.equal(next.tasks[0].status, 'inbox'); // host boardops fallback behavior
  assert.equal(next.tasks[0].projectId, 'p-a');
  assert.deepEqual(ids(lane(next, 'board-a', 'custom-a')), ['other', 'move']);
});

test('multi-board isolation: only touched lanes in the same board change', () => {
  const untouchedA = card('keep-list', 'board-a', 'planned', {cardOrder: 120});
  const untouchedBoard = card('keep-board', 'board-b', 'inbox', {cardOrder: 200});
  const old = makeState([card('a'), card('b'), untouchedA, untouchedBoard]);
  const result = moveCardInState(old, {
    cardId: 'b', toListId: 'inbox', anchorCardId: 'a', placement: 'before'
  });
  assert.strictEqual(result.tasks[2], untouchedA);
  assert.strictEqual(result.tasks[3], untouchedBoard);
  assert.equal(result.tasks[2].cardOrder, 120);
  assert.equal(result.tasks[3].cardOrder, 200);
  assert.strictEqual(result.boards, old.boards);
  assert.strictEqual(result.projects, old.projects);
  assert.strictEqual(result.settings, old.settings);
});

test('cross-board move is refused to prevent board-local label/custom-field corruption', () => {
  const input = makeState([card('a'), card('target-b', 'board-b', 'inbox')]);
  const frozen = deepFreeze(input);
  assert.throws(() => moveCardInState(frozen, {
    cardId: 'a', toBoardId: 'board-b', toListId: 'inbox',
    anchorCardId: 'target-b', placement: 'after'
  }), /Cross-board/);
  assert.equal(frozen.tasks[0].boardId, 'board-a');
});

test('archived cards ignored by visible sorting and not renumbered', () => {
  const closed = card('archived', 'board-a', 'inbox', {archived: true, cardOrder: 678});
  const open = card('open');
  const input = makeState([closed, open]);
  assert.deepEqual(ids(lane(input)), ['open']);
  const next = normalizeCardOrders(input);
  assert.strictEqual(next.tasks[0], closed);
  assert.equal(next.tasks[1].cardOrder, 0);
  assert.throws(() => moveCardInState(input, {cardId: 'archived', toListId: 'inbox'}), /archived/);
  assert.throws(() => moveCardInState(input, {
    cardId: 'open', toListId: 'inbox', anchorCardId: 'archived', placement: 'after'
  }), /target-list/);
});

test('invalid cardOrder is rejected instead of silently converting or overflowing', () => {
  for (const value of [-1, MAX_CARD_ORDER + 1, 1.5, NaN, Infinity,
    -Infinity, '1', '0', null, true, {}, [], Number.MAX_SAFE_INTEGER + 1]) {
    withOrder(value);
  }
  function withOrder(value) {
    const input = makeState([card('bad', 'board-a', 'inbox', {cardOrder: value})]);
    assert.throws(() => getOrderedLaneCards(input.tasks, 'board-a', 'inbox'),
      /Invalid cardOrder/);
    assert.throws(() => normalizeCardOrders(input), /Invalid cardOrder/);
    assert.throws(() => moveCardInState(input, {cardId: 'bad', toListId: 'inbox'}),
      /Invalid cardOrder/);
  }
  const high = makeState([card('valid-high', 'board-a', 'inbox',
    {cardOrder: MAX_CARD_ORDER})]);
  assert.deepEqual(ids(lane(high)), ['valid-high']);
  assert.equal(normalizeCardOrders(high).tasks[0].cardOrder, 0);
});

test('card and list identifiers validated; missing anchor and accidental cross-lane anchor refuse', () => {
  const input = makeState([card('a'), card('other', 'board-a', 'planned')]);
  for (const id of ['', ' ', 44, null, {}, 'a\0b', 'x'.repeat(1_025)]) {
    assert.throws(() => moveCardInState(input, {cardId: id, toListId: 'inbox'}));
  }
  const duplicated = makeState([card('a'), card('a')]);
  assert.throws(() => normalizeCardOrders(duplicated), /Duplicate card id/);
  assert.throws(() => moveCardInState(input, {
    cardId: 'a', toListId: 'inbox', anchorCardId: 'other', placement: 'before'
  }), /target-list/);
  assert.throws(() => moveCardInState(input, {
    cardId: 'a', toListId: 'missing', placement: 'end'
  }), /Unknown board\/list/);
  assert.throws(() => moveCardInState(input, {
    cardId: 'a', toListId: 'inbox', placement: 'middle'
  }), /placement/);
  assert.throws(() => moveCardInState(input, {
    cardId: 'a', toListId: 'inbox', placement: 'before'
  }), /anchorCardId/);
  assert.throws(() => moveCardInState(input, {
    cardId: 'a', toListId: 'inbox', anchorCardId: 'other', placement: 'start'
  }), /only permitted/);
  assert.throws(() => normalizeCardOrders(input, {listId: 'inbox'}), /requires boardId/);
  assert.throws(() => normalizeCardOrders(input, {boardId: 'missing'}), /Unknown boardId/);
});

test('CAS preparation returns whole unchanged-meta state + original revision for host atomic save', () => {
  const old = deepFreeze(makeState([card('a'), card('b')]));
  const move = {cardId: 'b', toListId: 'inbox', placement: 'start'};
  const envelope = prepareCardOrderCAS(old, revision, move);
  assert.deepEqual(Object.keys(envelope).sort(), ['expectedRevision', 'nextState']);
  assert.equal(envelope.expectedRevision, revision);
  assert.deepEqual(ids(lane(envelope.nextState)), ['b', 'a']);
  assert.equal(envelope.nextState.projects[0].price, 20_000_000);
  assert.equal(envelope.nextState.tasks[0].financeFlags.internal, true);
  assert.equal(envelope.nextState.tasks[0].checklist[0].cost, 37000);
  assert.equal(old.tasks[0].cardOrder, undefined);
  for (const bad of ['', 'abcd', 12, null, 'z'.repeat(64)]) {
    assert.throws(() => prepareCardOrderCAS(old, bad, move), /expectedRevision/);
  }
});

test('dense order is stable after JSON persistence and task object rehydration', () => {
  const input = makeState([card('c'), card('a'), card('b')]);
  const sorted = moveCardInState(input, {
    cardId: 'c', toListId: 'inbox', anchorCardId: 'b', placement: 'after'
  });
  const roundTrip = JSON.parse(JSON.stringify(sorted));
  assert.deepEqual(ids(lane(roundTrip)), ['a', 'b', 'c']);
  assert.deepEqual(positions(roundTrip), [0, 1, 2]);
  assert.strictEqual(normalizeCardOrders(roundTrip), roundTrip);
});

test('repeated deterministic moves across mixed lanes never duplicate cards or change amounts', () => {
  let state = normalizeCardOrders(makeState(Array.from({length: 30}, (_, i) =>
    card('task-' + i, 'board-a', i % 3 ? 'inbox' : 'planned',
      i % 5 ? {} : {cardOrder: i * 90}))));
  const baseline = new Map(state.tasks.map(item => [item.id, {
    price: item.price, cost: item.cost, checklist: JSON.stringify(item.checklist),
    finance: JSON.stringify(item.financeFlags)
  }]));
  for (let pass = 0; pass < 20; pass++) {
    const id = 'task-' + pass;
    const toListId = pass % 2 ? 'inbox' : 'planned';
    state = moveCardInState(state, {cardId: id, toListId, placement: 'end'});
    assert.equal(new Set(state.tasks.map(item => item.id)).size, 30);
    for (const listId of ['inbox', 'planned']) {
      assert.deepEqual(positions(state, 'board-a', listId),
        Array.from({length: lane(state, 'board-a', listId).length}, (_, i) => i));
    }
  }
  for (const item of state.tasks) {
    const preserved = baseline.get(item.id);
    assert.equal(item.price, preserved.price);
    assert.equal(item.cost, preserved.cost);
    assert.equal(JSON.stringify(item.checklist), preserved.checklist);
    assert.equal(JSON.stringify(item.financeFlags), preserved.finance);
  }
});
