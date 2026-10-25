const {test}=require('node:test');
const assert=require('node:assert/strict');
const esbuild=require('esbuild');
const Module=require('node:module');
const path=require('node:path');
const {spawnSync}=require('node:child_process');
const entry=path.join(__dirname,'../src/calendar_import_state.js');
const compiled=esbuild.buildSync({entryPoints:[entry],bundle:true,platform:'node',format:'cjs',write:false}).outputFiles[0].text;
const output=new Module(entry,module);output.filename=entry;output.paths=Module._nodeModulePaths(process.cwd());output._compile(compiled,entry);
const {importCalendarEvents}=output.exports;
const key='a'.repeat(64);
const base=()=>({version:1,settings:{theme:'light',costDefault:false},
  stages:[{id:'inbox',label:'Inbox',color:'#aaa',subtitle:''}],
  workspaces:[{id:'w',name:'Workspace',archived:false}],
  projects:[{id:'p',name:'Project',costEnabled:false,price:0,fileLinks:[]}],
  boards:[{id:'b',projectId:'p',workspaceId:'w',name:'Board',archived:false,
    stages:[{id:'planned-custom',label:'Plan',subtitle:'',color:'#abc'}],customFields:[],labelDefinitions:[]}],tasks:[]});
test('approved ICS events create zero-cost valid cards with idempotent keys',()=>{
  const state=base();const event={source_key:key,title:'Meeting',dueDate:'2026-11-01'};
  const first=importCalendarEvents(state,'p',[event,event],()=> 'imported', '2026-10-21T00:00:00Z');
  assert.equal(first.tasks.length,1);
  assert.equal(first.tasks[0].cost,0);
  assert.equal(first.tasks[0].status,'inbox');
  assert.equal(first.tasks[0].listId,'planned-custom');
  assert.equal(first.tasks[0].calendarSourceKey,key);
  const again=importCalendarEvents(first,'p',[event],()=> 'extra','2026-10-21T00:00:00Z');
  assert.equal(again.tasks.length,1);
  assert.equal(state.tasks.length,0);
});
test('malformed events or unauthorized project targets are rejected without mutation',()=>{
  const state=base();
  assert.throws(()=>importCalendarEvents(state,'other',[],()=> 'x','now'));
  assert.throws(()=>importCalendarEvents(state,'p',[{source_key:key,title:'bad',dueDate:'2026-02-30'}],()=> 'x','now'));
  assert.deepEqual(state.tasks,[]);
});
test('imported ICS card passes the real Python data model validator',()=>{
  const result=importCalendarEvents(base(),'p',[
    {source_key:key,title:'Persian meeting جلسه',dueDate:'2026-11-04'}
  ],()=>'ics-new','2026-10-21T00:00:00Z');
  const code='import json,sys; from data_model import normalize_plus,validate_plus; x=normalize_plus(json.load(sys.stdin)); validate_plus(x); print("ICS_MODEL_VALID")';
  const ran=spawnSync('py',['-3.12','-c',code],{cwd:path.resolve(__dirname,'..'),input:JSON.stringify(result),encoding:'utf8',timeout:20000});
  assert.equal(ran.status,0,ran.stderr||ran.stdout);
  assert.match(ran.stdout,/ICS_MODEL_VALID/);
});
