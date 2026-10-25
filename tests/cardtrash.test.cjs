'use strict';
/** CD05 pure operations. No user data, I/O, network, backup, Git or UI mount. */
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const Module = require('node:module');
const esbuild = require('esbuild');

const root = path.resolve(__dirname, '..');
const code = esbuild.buildSync({
  entryPoints: [path.join(root, 'src', 'cardtrash.js')],
  bundle: true, platform: 'node', format: 'cjs', write: false,
}).outputFiles[0].text;
const loader = new Module(path.join(root, 'src', 'cardtrash-test.cjs'), module);
loader.filename = path.join(root, 'src', 'cardtrash-test.cjs');
loader.paths = Module._nodeModulePaths(root);
loader._compile(code, loader.filename);
const {
  softDeleteCardState, restoreDeletedCardState, MAX_TRASH_CARDS,
} = loader.exports;
const ADMIN = Object.freeze({canManage: true});
const EDITOR = Object.freeze({canEdit: true, grantedProjectIds: ['p-print']});

function deepFreeze(value) {
  if (!value || typeof value !== 'object' || Object.isFrozen(value)) return value;
  for (const child of Object.values(value)) deepFreeze(child);
  return Object.freeze(value);
}

function card(id, extras = {}) {
  return {
    id, projectId: 'p-print', boardId: 'b-print', listId: 'proof',
    status: 'active', title: 'Printed packaging ' + id, description: 'Never erase',
    priority: 'high', createdAt: '2026-10-20', updatedAt: '2026-10-21',
    cardOrder: 701, archived: false, archivedByBoard: false,
    cost: 903_001, costEnabled: true, costCategory: 'print', costDate: '2026-10-21',
    checklist: [{id:'check-1',text:'Die cut',done:true,cost:102_007,costCategory:'die'}],
    checklists: [{id:'group-1',name:'Production',items:[
      {id:'named-1',text:'Foil',done:false,cost:308_009,costDate:'2026-10-20'},
    ]}],
    reports: [{id:'report-1',summary:'Approved'}],
    assignees: ['editor'], labels: ['urgent'], labelIds: ['l-urgent'],
    customFieldValues: {'field-1': 'Gold'},
    fileLinks: [{id:'file-link-1',path:'\\\\server\\share\\test.pdf',name:'ref'}],
    attachments: [{id:'blob-1',storageRef:'SHA256-BLOB',filename:'proof.pdf'}],
    invoiceId: 'invoice-1', linkedFinanceIds:['contract-1'],
    cover: {type:'color',color:'#334455'}, extraUnknown: {nested:[1,2,3]},
    ...extras,
  };
}

function fixture() {
  const main = card('c1');
  const unrelated = card('c2',{listId:'print', status:'planned', cost:990_100,
    projectId:'p-other', boardId:'b-other', cardOrder:105});
  return {
    version: 1, __localRevision:'initial-sha256', __remoteRevision:'lan-rev-x',
    projects:[
      {id:'p-print',price:4_200_007,costEnabled:true,fileLinks:[{id:'f',name:'quote'}]},
      {id:'p-other',price:3_100_023,costEnabled:true},
    ],
    workspaces:[
      {id:'w1',name:'Workshop',archived:false},
      {id:'w2',name:'Second',archived:false},
    ],
    boards:[
      {id:'b-print',projectId:'p-print',workspaceId:'w1',archived:false,
       stages:[{id:'proof',label:'Proofing'}, {id:'print',label:'Printing',archived:false}]},
      {id:'b-other',projectId:'p-other',workspaceId:'w2',archived:false,
       stages:[{id:'print',label:'Print'}]},
    ],
    stages:[{id:'active',label:'Active'},{id:'planned',label:'Planned'}],
    tasks:[main, unrelated],
    settings:{theme:'light',costDefault:false},
    templates:[{id:'template-1',boardId:'b-print'}],
    finance:{
      contracts:[{id:'contract-1',cardId:'c1',sale:100_010}],
      invoices:[{id:'invoice-1',cardId:'c1',status:'Issued',amount:200_020}],
      payments:[{id:'payment-1',invoiceId:'invoice-1',amount:30_003}],
      ledger:[{id:'ledger-1',cardId:'c1',amount:400_004}],
    },
    collab:{comments:[{id:'comment-1',cardId:'c1'}]},
    completion_outbox:[{eventId:'completion-1',cardId:'c1'}],
    attachments:[{id:'blob-1',cardId:'c1',sha256:'aa00'}],
    audit:[{kind:'sale',projectId:'p-print',amount:1_002}],
  };
}

function originalNonTrashFields(task) {
  const {deleted, ...rest} = task;
  return rest;
}

test('soft delete flips only a dedicated deleted marker, immutable even when deeply frozen', () => {
  const input = deepFreeze(fixture());
  const original = input.tasks[0];
  const result = softDeleteCardState(input,'c1',ADMIN);
  assert.notStrictEqual(result,input);
  assert.notStrictEqual(result.tasks,input.tasks);
  assert.notStrictEqual(result.tasks[0],original);
  assert.equal(result.tasks[1],input.tasks[1]);
  assert.equal(result.tasks[0].deleted,true);
  assert.equal(original.deleted,undefined);
  assert.deepEqual(originalNonTrashFields(result.tasks[0]),original);
  for (const key of Object.keys(input)) {
    if (key !== 'tasks') assert.strictEqual(result[key],input[key], key);
  }
  assert.equal(result.__localRevision,'initial-sha256');
  assert.equal(result.__remoteRevision,'lan-rev-x');
  assert.equal(result.tasks[0].archived,false);
  assert.equal(result.tasks[0].archivedByBoard,false);
});

test('restore is reversible and idempotent, preserving all costs, invoices, attachments, checklist and order', () => {
  const original = fixture();
  const before = structuredClone(original.tasks[0]);
  const trashed = softDeleteCardState(original,'c1',ADMIN);
  assert.strictEqual(softDeleteCardState(trashed,'c1',ADMIN),trashed);
  const restored = restoreDeletedCardState(trashed,'c1',ADMIN);
  assert.strictEqual(restoreDeletedCardState(restored,'c1',ADMIN),restored);
  assert.equal(restored.tasks[0].deleted,false);
  assert.deepEqual(originalNonTrashFields(restored.tasks[0]),before);
  assert.deepEqual(restored.projects,original.projects);
  assert.strictEqual(restored.finance,original.finance);
  assert.strictEqual(restored.attachments,original.attachments);
  assert.strictEqual(restored.collab,original.collab);
  assert.strictEqual(restored.completion_outbox,original.completion_outbox);
});

test('active non-deleted card restore is a no-op by reference, including legacy absent marker', () => {
  const input=deepFreeze(fixture());
  assert.strictEqual(restoreDeletedCardState(input,'c1',ADMIN),input);
  const explicit = fixture(); explicit.tasks[0].deleted=false;
  assert.strictEqual(restoreDeletedCardState(explicit,'c1',ADMIN),explicit);
  assert.equal(explicit.tasks[0].deleted,false);
});

test('pre-existing card archive and archivedByBoard flag remain unchanged throughout trash and restore', () => {
  const state=fixture();
  state.tasks[0].archived=true;state.tasks[0].archivedByBoard=true;
  const trashed=softDeleteCardState(state,'c1',ADMIN);
  const restored=restoreDeletedCardState(trashed,'c1',ADMIN);
  assert.equal(restored.tasks[0].archived,true);
  assert.equal(restored.tasks[0].archivedByBoard,true);
  assert.equal(restored.tasks[0].deleted,false);
});

test('archived board or archived workspace prevents BOTH trash and restore', () => {
  for (const field of ['board','workspace']) {
    for (const operation of [softDeleteCardState,restoreDeletedCardState]) {
      const state=fixture();
      state.tasks[0].deleted=true;
      if (field==='board') state.boards[0].archived=true;
      else state.workspaces[0].archived=true;
      const before=structuredClone(state);
      assert.throws(()=>operation(state,'c1',ADMIN),/Archived (board|workspace)/);
      assert.deepEqual(state,before);
    }
  }
});

test('archived LIST can hold restored trash card without changing its destination', () => {
  const input=deepFreeze(fixture());
  const changed=structuredClone(input);
  changed.boards[0].stages[0].archived=true;
  deepFreeze(changed);
  const restored=restoreDeletedCardState(softDeleteCardState(changed,'c1',ADMIN),'c1',ADMIN);
  assert.equal(restored.tasks[0].boardId,'b-print');
  assert.equal(restored.tasks[0].listId,'proof');
  assert.equal(restored.tasks[0].status,'active');
  assert.equal(restored.boards[0].stages[0].archived,true);
});

test('explicit editor grants permit only cards in granted projects; management requires strict true', () => {
  const state=deepFreeze(fixture());
  assert.equal(softDeleteCardState(state,'c1',EDITOR).tasks[0].deleted,true);
  assert.throws(()=>softDeleteCardState(state,'c2',EDITOR),/PERMISSION_DENIED/);
  assert.throws(()=>restoreDeletedCardState(state,'c2',EDITOR),/PERMISSION_DENIED/);
  assert.equal(softDeleteCardState(state,'c2',ADMIN).tasks[1].deleted,true);
  for (const unauthorized of [
    {},{canManage:false},{canManage:'true'}, {canEdit:true}, {canEdit:1},
    {canEdit:true,grantedProjectIds:[]},
    {canEdit:true,grantedProjectIds:['p-other']},
    {canEdit:true,grantedProjectIds:null},
    {canEdit:true,grantedProjectIds:'p-print'},
    {canEdit:true,grantedProjectIds:[false,'p-print']},
  ]) {
    assert.throws(()=>softDeleteCardState(state,'c1',unauthorized),
                  /PERMISSION_DENIED|grantedProjectIds/);
  }
});

test('editor may restore only authorized trashed card, no authority gained from user-supplied task fields', () => {
  const input=fixture();
  input.tasks[0].deleted=true;
  input.tasks[0].assignees=['admin'];
  input.tasks[0].canManage=true;
  assert.equal(restoreDeletedCardState(input,'c1',EDITOR).tasks[0].deleted,false);
  assert.throws(()=>restoreDeletedCardState(input,'c1',{canEdit:true,grantedProjectIds:['p-other']}),/PERMISSION_DENIED/);
  assert.throws(()=>restoreDeletedCardState(input,'c1',{}),/PERMISSION_DENIED/);
});

test('pure legacy cards lacking board/list/workspaces remain reversible without invented IDs', () => {
  const original=fixture();
  delete original.boards; delete original.workspaces;
  delete original.tasks[0].boardId; delete original.tasks[0].listId;
  original.tasks=original.tasks.slice(0,1);
  const before=structuredClone(original);
  const trash=softDeleteCardState(original,'c1',ADMIN);
  const restore=restoreDeletedCardState(trash,'c1',ADMIN);
  assert.equal(restore.tasks[0].status,'active');
  assert.equal(restore.tasks[0].boardId,undefined);
  assert.equal(restore.tasks[0].listId,undefined);
  assert.deepEqual(original,before);
  assert.deepEqual(originalNonTrashFields(restore.tasks[0]),before.tasks[0]);
});

test('board IDs project-less legacy board still permits matching project and retains references', () => {
  const state=fixture(); delete state.boards[0].projectId;
  const result=softDeleteCardState(state,'c1',ADMIN);
  assert.equal(result.tasks[0].deleted,true);
  assert.equal(result.tasks[0].boardId,'b-print');
  assert.equal(result.tasks[0].projectId,'p-print');
});

test('legacy empty project ID is preserved and checked by exact grant, not replaced', () => {
  const state=fixture();
  state.projects[0].id='';
  state.boards[0].projectId='';
  state.tasks[0].projectId='';
  const options={canEdit:true,grantedProjectIds:['']};
  const removed=softDeleteCardState(state,'c1',options);
  const restored=restoreDeletedCardState(removed,'c1',options);
  assert.equal(restored.tasks[0].projectId,'');
  assert.equal(restored.boards[0].projectId,'');
  assert.equal(restored.projects[0].id,'');
  assert.equal(restored.tasks[0].deleted,false);
  assert.throws(()=>softDeleteCardState(state,'c1',EDITOR),/PERMISSION_DENIED/);
});

test('JSON roundtrip keeps trashed card attached to its finance and attachment records', () => {
  const input=deepFreeze(fixture());
  const removed=softDeleteCardState(input,'c1',ADMIN);
  const persisted=JSON.parse(JSON.stringify(removed));
  assert.equal(persisted.tasks[0].deleted,true);
  assert.equal(persisted.finance.invoices[0].cardId,'c1');
  assert.equal(persisted.attachments[0].cardId,'c1');
  const restored=restoreDeletedCardState(persisted,'c1',ADMIN);
  assert.equal(restored.tasks[0].deleted,false);
  assert.deepEqual(restored.tasks[0].checklists,input.tasks[0].checklists);
  assert.deepEqual(restored.finance,input.finance);
  assert.deepEqual(restored.attachments,input.attachments);
  assert.deepEqual(restored.completion_outbox,input.completion_outbox);
});

test('explicit invalid trash/archived flags reject without mutating state', () => {
  for (const prop of ['deleted','archived','archivedByBoard']) {
    for (const value of [null,0,1,'true','false',[],{},1.5]) {
      const input=fixture(); input.tasks[0][prop]=value;
      const before=structuredClone(input);
      assert.throws(()=>softDeleteCardState(input,'c1',ADMIN),/boolean/);
      assert.deepEqual(input,before);
    }
  }
});

test('invalid archived flags on board, workspace, stage reject both directions', () => {
  for (const which of ['board','workspace','stage']) {
    for (const operation of [softDeleteCardState,restoreDeletedCardState]) {
      const state=fixture();
      state.tasks[0].deleted=true;
      if (which==='board') state.boards[0].archived='false';
      if (which==='workspace') state.workspaces[0].archived='false';
      if (which==='stage') state.boards[0].stages[0].archived='false';
      assert.throws(()=>operation(state,'c1',ADMIN),/boolean/);
    }
  }
});

test('missing/ambiguous card, board, workspace, project and list references fail closed', () => {
  const variants = [
    [s=>s.tasks.push(structuredClone(s.tasks[0])),/Duplicate card/],
    [s=>s.tasks[0].projectId='unknown',/Unknown project/],
    [s=>s.projects.push(structuredClone(s.projects[0])),/Duplicate project/],
    [s=>s.tasks[0].boardId='unknown',/Unknown board/],
    [s=>s.boards.push(structuredClone(s.boards[0])),/Duplicate board/],
    [s=>s.boards[0].projectId='p-other',/does not match/],
    [s=>s.boards[0].workspaceId='missing',/Unknown workspace/],
    [s=>s.workspaces.push(structuredClone(s.workspaces[0])),/Duplicate workspace/],
    [s=>s.tasks[0].listId='nonexistent',/listId is not present/],
    [s=>s.boards[0].stages.push(structuredClone(s.boards[0].stages[0])),/Duplicate board list/],
    [s=>delete s.tasks[0].boardId,/incomplete board\/list/],
    [s=>delete s.tasks[0].listId,/incomplete board\/list/],
    [s=>s.boards[0].stages=[],/at least one list/],
  ];
  for (const [mutate,matcher] of variants) {
    const state=fixture(); mutate(state);
    const frozen=deepFreeze(state);
    assert.throws(()=>softDeleteCardState(frozen,'c1',ADMIN),matcher);
  }
});

test('legacy status guard and malformed state arguments fail without side effects', () => {
  for (const value of [null,[],0,'not-a-state']) {
    assert.throws(()=>softDeleteCardState(value,'c1',ADMIN),/object/);
  }
  const state=fixture();
  for (const id of [null,{},[],0,'  ','\x00test','c1\n']) {
    assert.throws(()=>softDeleteCardState(state,id,ADMIN),/cardId/);
  }
  assert.throws(()=>softDeleteCardState(state,'missing',ADMIN),/Unknown card/);
  const legacy=fixture();
  delete legacy.tasks[0].boardId;delete legacy.tasks[0].listId;
  legacy.tasks[0].status='nonexistent';
  assert.throws(()=>softDeleteCardState(legacy,'c1',ADMIN),/Legacy card status/);
});

test('array bounds and grant size bounds use host-aligned ceilings', () => {
  const tooManyTasks=fixture();
  tooManyTasks.tasks=Array.from({length:MAX_TRASH_CARDS+1},(_,i)=>({id:'id-'+i}));
  assert.throws(()=>softDeleteCardState(tooManyTasks,'c1',ADMIN),/20000/);
  const tooManyBoards=fixture();
  tooManyBoards.boards=Array.from({length:2001},(_,i)=>({id:'b'+i}));
  assert.throws(()=>softDeleteCardState(tooManyBoards,'c1',ADMIN),/2000/);
  const tooManyWorkspaces=fixture();
  tooManyWorkspaces.workspaces=Array.from({length:101},(_,i)=>({id:'w'+i}));
  assert.throws(()=>softDeleteCardState(tooManyWorkspaces,'c1',ADMIN),/100/);
  const tooManyStages=fixture();
  tooManyStages.boards[0].stages=Array.from({length:41},(_,i)=>({id:'stage'+i}));
  assert.throws(()=>softDeleteCardState(tooManyStages,'c1',ADMIN),/40/);
  const tooManyGrants=Array.from({length:2001},(_,i)=>'p'+i);
  assert.throws(()=>softDeleteCardState(fixture(),'c1',{canEdit:true,grantedProjectIds:tooManyGrants}),/2000/);
});

test('repeated trash and restore cycles do not shift task order, IDs, attachments or financial totals', () => {
  let state=fixture();
  const before=structuredClone(state);
  for (let i=0;i<200;i++) {
    state=softDeleteCardState(state,'c1',ADMIN);
    state=restoreDeletedCardState(state,'c1',ADMIN);
  }
  assert.deepEqual(state.tasks.map(t=>t.id),before.tasks.map(t=>t.id));
  assert.deepEqual(originalNonTrashFields(state.tasks[0]),before.tasks[0]);
  assert.deepEqual(state.finance,before.finance);
  assert.deepEqual(state.attachments,before.attachments);
  assert.deepEqual(state.projects,before.projects);
  assert.deepEqual(state.boards,before.boards);
  assert.deepEqual(state.workspaces,before.workspaces);
  assert.equal(state.tasks[0].deleted,false);
});
