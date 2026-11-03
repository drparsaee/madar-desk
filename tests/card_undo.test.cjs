'use strict';
// In-memory synthetic card state only. No bridge, LAN connection or user profile.
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const Module = require('node:module');
const esbuild = require('esbuild');
const root = path.resolve(__dirname, '..');
const compiled = esbuild.buildSync({entryPoints:[path.join(root,'src','card_undo.js')],
  bundle:true,platform:'node',format:'cjs',write:false}).outputFiles[0].text;
const loader = new Module(path.join(root,'src','card-undo-loader.cjs'),module);
loader.filename=path.join(root,'src','card-undo-loader.cjs');
loader.paths=Module._nodeModulePaths(root);
loader._compile(compiled,loader.filename);
const {MAX_CARD_UNDO,emptyCardHistory,isUndoableCardPatch,recordCardEdit,
  cardHistoryAvailability,applyCardHistory}=loader.exports;
const scope='solo|local|workspace|board';
const clock='2026-11-03T00:00:00Z';
const board={id:'board',projectId:'p',archived:false,stages:[{id:'todo',archived:false}]};
const card={id:'task',boardId:'board',projectId:'p',listId:'todo',
  title:'اول',description:'محتوا',completed:false,priority:'normal',
  updatedAt:clock,deleted:false,archived:false,cost:76543,
  checklist:[{id:'paid',cost:9000,done:true}],
  invoiceId:'issued-789',reports:[{id:'audit',summary:'keep'}]};
const state=(task=card)=>({tasks:[structuredClone(task)],boards:[structuredClone(board)],
  projects:[{id:'p'}],__remoteRevision:'0001'});
const changed=(s,fields,iso='2026-11-03T00:01:00Z')=>({...s,tasks:s.tasks.map(t=>({...t,...fields,updatedAt:iso}))});
const record=(h,s,next,fields,id)=>recordCardEdit(h,s,next,'task',fields,scope,id);

test('undo/redo a title edit with all monetary and issued invoice references untouched',()=>{
  const first=state();const second=changed(first,{title:'دوم'});
  const h=record(emptyCardHistory(scope),first,second,{title:'دوم'},'a');
  assert.equal(cardHistoryAvailability(h,second,'undo',scope,true),true);
  const undo=applyCardHistory(h,second,'undo',scope,true,'2026-11-03T00:02:00Z');
  assert.equal(undo.applied,true);assert.equal(undo.state.tasks[0].title,'اول');
  for(const name of ['cost','checklist','invoiceId','reports'])
    assert.deepEqual(undo.state.tasks[0][name],card[name]);
  const redo=applyCardHistory(undo.history,undo.state,'redo',scope,true,'2026-11-03T00:03:00Z');
  assert.equal(redo.applied,true);assert.equal(redo.state.tasks[0].title,'دوم');
  assert.deepEqual(redo.state.tasks[0].checklist,card.checklist);
});

test('multi-step undo and redo preserve order without stale timestamp failure',()=>{
  const a=state();const b=changed(a,{title:'دو'});const c=changed(b,{description:'تغییر'},'2026-11-03T00:02:00Z');
  const h1=record(emptyCardHistory(scope),a,b,{title:'دو'},'one');
  const h2=record(h1,b,c,{description:'تغییر'},'two');
  const one=applyCardHistory(h2,c,'undo',scope,true,'2026-11-03T00:03:00Z');
  const two=applyCardHistory(one.history,one.state,'undo',scope,true,'2026-11-03T00:04:00Z');
  assert.equal(two.state.tasks[0].title,'اول');
  assert.equal(two.state.tasks[0].description,'محتوا');
  const three=applyCardHistory(two.history,two.state,'redo',scope,true,'2026-11-03T00:05:00Z');
  const four=applyCardHistory(three.history,three.state,'redo',scope,true,'2026-11-03T00:06:00Z');
  assert.equal(four.state.tasks[0].title,'دو');
  assert.equal(four.state.tasks[0].description,'تغییر');
});

test('network, viewer, another identity or board, concurrent edit and deletion fail closed',()=>{
  const a=state();const b=changed(a,{title:'دو'});
  const h=record(emptyCardHistory(scope),a,b,{title:'دو'},'a');
  for(const ctx of ['solo|other|workspace|board','solo|local|workspace|else','client|local|workspace|board']){
    assert.equal(cardHistoryAvailability(h,b,'undo',ctx,true),false);
    assert.equal(applyCardHistory(h,b,'undo',ctx,true,clock).applied,false);
  }
  assert.equal(cardHistoryAvailability(h,b,'undo',scope,false),false);
  assert.equal(applyCardHistory(h,b,'undo',scope,false,clock).applied,false);
  const colleague=changed(b,{description:'ویرایش دیگر'},'2026-11-03T00:03:00Z');
  assert.equal(applyCardHistory(h,colleague,'undo',scope,true,clock).applied,false);
  const deleted=changed(b,{deleted:true});
  assert.equal(applyCardHistory(h,deleted,'undo',scope,true,clock).applied,false);
  const archivedBoard={...b,boards:[{...board,archived:true}]};
  assert.equal(applyCardHistory(h,archivedBoard,'undo',scope,true,clock).applied,false);
});

test('financial changes, structural changes, untracked field mutation cannot be recorded',()=>{
  const a=state();
  for(const fields of [{cost:1},{checklist:[]},{invoiceId:null},{status:'done'},{deleted:true},{projectId:'q'},{}])
    assert.equal(!!isUndoableCardPatch(fields),false);
  const b=changed(a,{title:'دو',cost:500});
  const h=record(emptyCardHistory(scope),a,b,{title:'دو'},'unsafe');
  assert.equal(h.undo.length,0);
  const relocated=changed(a,{title:'دو',listId:'else'});
  assert.equal(record(emptyCardHistory(scope),a,relocated,{title:'دو'},'relocate').undo.length,0);
});

test('redo branch drops on new edits, duplicate React updater actions are idempotent',()=>{
  const a=state();const b=changed(a,{title:'دو'});
  const first=record(emptyCardHistory(scope),a,b,{title:'دو'},'id');
  const duplicate=record(first,a,b,{title:'دو'},'id');
  assert.deepEqual(first,duplicate);
  const reverted=applyCardHistory(first,b,'undo',scope,true,clock);
  const next=changed(reverted.state,{priority:'high'});
  const second=record(reverted.history,reverted.state,next,{priority:'high'},'later');
  assert.equal(second.redo.length,0);
  assert.equal(second.undo.length,1);
});

test('history stays bounded to 40 entries',()=>{
  let h=emptyCardHistory(scope);let previous=state();
  for(let i=0;i<MAX_CARD_UNDO+5;i++){
    const next=changed(previous,{title:'title-'+i});
    h=record(h,previous,next,{title:'title-'+i},'id'+i);
    previous=next;
  }
  assert.equal(h.undo.length,MAX_CARD_UNDO);
  assert.equal(h.undo[0].actionId,'id5');
});
