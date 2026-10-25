const test=require('node:test');
const assert=require('node:assert/strict');
const Module=require('node:module');
const path=require('node:path');
const esbuild=require('esbuild');
const {spawnSync}=require('node:child_process');
const root=path.resolve(__dirname,'..');
const output=esbuild.buildSync({entryPoints:[path.join(root,'src/trello_import.js')],platform:'node',format:'cjs',bundle:true,write:false}).outputFiles[0].text;
const m=new Module(path.join(root,'trello_test_generated.cjs'),module);
m.filename=path.join(root,'trello_test_generated.cjs');m.paths=Module._nodeModulePaths(root);m._compile(output,m.filename);
const {inspectTrelloExport,importTrelloBoard}=m.exports;
const seed={version:1,stages:[{id:'inbox',label:'صندوق ورودی',color:'#888888'}],
 projects:[{id:'base',name:'اصلی',color:'#123456',costEnabled:false,price:0}],tasks:[{id:'before',title:'قدیمی',projectId:'base',status:'inbox',priority:'medium',checklist:[],reports:[]}],
 boards:[],workspaces:[{id:'w-main',name:'اصلی'}],settings:{theme:'light'}};
const trello={name:'بازاریابی',lists:[{id:'l1',name:'To do'},{id:'l2',name:'Done'}],
 cards:[{id:'c1',idList:'l1',name:'=SUM(1,2)',desc:'متن',closed:false,labels:[{name:'مهم'}],idChecklists:['q1'],due:'2026-11-02T12:00:00Z'}],
 checklists:[{id:'q1',checkItems:[{id:'i1',name:'ثبت نیاز',state:'complete'},{id:'i2',name:'ارسال',state:'incomplete'}]}]};
test('inspect valid Trello export and reject missing list targets',()=>{
 assert.equal(inspectTrelloExport(trello).openCards,1);
 assert.throws(()=>inspectTrelloExport({...trello,cards:[{...trello.cards[0],idList:'missing'}]}));
});
test('create imported board without mutating preexisting tasks, IDs or sensitive amounts',()=>{
 const copy=structuredClone(seed);
 const state=importTrelloBoard(seed,trello);
 assert.deepEqual(seed,copy);
 assert.equal(state.projects.length,2);
 assert.equal(state.boards.length,1);
 assert.equal(state.boards[0].stages.length,2);
 assert.equal(state.tasks.length,2);
 assert.equal(state.tasks[0].checklist.length,2);
 assert.equal(state.tasks[0].checklist[0].done,true);
 assert.equal(state.tasks[0].cost,0);
 assert.equal(state.tasks[0].status,'inbox');
 assert.equal(state.tasks[1].id,'before');
 assert.notEqual(state.tasks[0].id,trello.cards[0].id);
});
test('reject oversized or malformed exports and forbid open board without active stages',()=>{
 assert.throws(()=>inspectTrelloExport({...trello,lists:[],cards:[]}));
 assert.throws(()=>importTrelloBoard(seed,{...trello,lists:trello.lists.map(l=>({...l,closed:true}))}));
});
test('imported Trello state passes actual native additive model validation',()=>{
  const state=importTrelloBoard(seed,trello);
  const command='import json,sys; from data_model import normalize_plus,validate_plus; state=normalize_plus(json.load(sys.stdin)); validate_plus(state); print("VALID_IMPORT")';
  const run=spawnSync('py',['-3.12','-c',command],{cwd:root,input:JSON.stringify(state),encoding:'utf8',timeout:15000});
  assert.equal(run.status,0,run.stderr||run.stdout);
  assert.match(run.stdout,/VALID_IMPORT/);
});
