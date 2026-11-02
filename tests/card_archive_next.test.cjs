'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const Module=require('node:module');
const esbuild=require('esbuild');
const entry=path.resolve(__dirname,'../src/cardarchive.js');
const output=esbuild.buildSync({entryPoints:[entry],bundle:true,platform:'node',format:'cjs',write:false}).outputFiles[0].text;
const loaded=new Module(entry,module);loaded.filename=entry;loaded.paths=Module._nodeModulePaths(path.dirname(entry));
loaded._compile(output,entry);
const {archiveCardState,restoreArchivedCardState}=loaded.exports;
const state=()=>({
  projects:[{id:'p1'}],
  workspaces:[{id:'w1',archived:false}],
  boards:[{id:'b1',projectId:'p1',workspaceId:'w1',stages:[{id:'todo'}]}],
  tasks:[{id:'t1',projectId:'p1',boardId:'b1',listId:'todo',status:'inbox',
    deleted:false,archived:false,archivedByBoard:false,title:'Synthetic',
    cost:250,checklist:[{id:'step',done:false,cost:10}],cardOrder:2,invoiceId:'synthetic-invoice'}],
});
const editor={canEdit:true,grantedProjectIds:['p1']};
test('card archive is reversible and does not mutate money, order, identity, or input',()=>{
  const original=state(), saved=JSON.stringify(original);
  const archived=archiveCardState(original,'t1',editor);
  assert.equal(archived.tasks[0].archived,true);
  assert.equal(archived.tasks[0].archivedByBoard,false);
  assert.equal(archived.tasks[0].deleted,false);
  assert.equal(JSON.stringify(original),saved);
  assert.equal(archiveCardState(archived,'t1',editor),archived);
  assert.deepEqual(restoreArchivedCardState(archived,'t1',editor),original);
});
test('archive and restore deny viewers, out-of-scope users and trashed cards',()=>{
  assert.throws(()=>archiveCardState(state(),'t1',{canEdit:false}),/PERMISSION_DENIED/);
  assert.throws(()=>archiveCardState(state(),'t1',{canEdit:true,grantedProjectIds:[]}),/PERMISSION_DENIED/);
  const deleted=state();deleted.tasks[0].deleted=true;
  assert.throws(()=>archiveCardState(deleted,'t1',editor),/trash|deleted/i);
  const boardArchive=state();boardArchive.boards[0].archived=true;
  assert.throws(()=>archiveCardState(boardArchive,'t1',editor),/Archived board/);
});
test('restore never overrides a board-owned archive',()=>{
  const existing=state();existing.tasks[0].archived=true;existing.tasks[0].archivedByBoard=true;
  assert.throws(()=>restoreArchivedCardState(existing,'t1',editor),/board/i);
});
