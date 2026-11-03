'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const Module=require('node:module');
const {spawnSync}=require('node:child_process');
const esbuild=require('esbuild');
const root=path.resolve(__dirname,'..');
const built=esbuild.buildSync({entryPoints:[path.join(root,'src/notion_csv_import.js')],
  platform:'node',format:'cjs',bundle:true,write:false}).outputFiles[0].text;
const m=new Module(path.join(root,'notion_import_test.cjs'),module);
m.filename=path.join(root,'notion_import_test.cjs');
m.paths=Module._nodeModulePaths(root);m._compile(built,m.filename);
const {inspectNotionCsv,importNotionCsvBoard}=m.exports;
const seed={version:1,workspaces:[{id:'workspace',name:'Main'}],
  projects:[{id:'original',name:'Existing',color:'#556677',costEnabled:false,price:0}],
  boards:[],stages:[{id:'inbox',label:'Inbox',color:'#888888'}],
  tasks:[{id:'keep',projectId:'original',title:'Keep this',status:'inbox',priority:'medium',checklist:[],reports:[]}],
  settings:{theme:'light'}};

test('imports one Notion CSV into additive project, board, cards and text fields',()=>{
  const csv='\uFEFFName,Status,Description,Tags,Date,Client,Code\r\n'+
    '"First, item",Todo,"Multiline\nnotes","design; important",2026-11-03,Alice,007\r\n'+
    'Second,Done,"He said ""Hello""",done,2026-11-04,Bob,008\r\n';
  const prior=structuredClone(seed);
  assert.deepEqual(inspectNotionCsv(csv),{name:'Notion CSV',lists:2,cards:2,openCards:2,properties:2});
  const result=importNotionCsvBoard(seed,csv);
  assert.deepEqual(seed,prior,'import must not mutate existing state');
  assert.equal(result.tasks.length,3);
  assert.equal(result.tasks[2].id,'keep','existing task must survive');
  assert.equal(result.boards.length,1);
  assert.equal(result.boards[0].stages.length,2);
  assert.equal(result.boards[0].customFields.length,2);
  assert.equal(result.tasks[0].title,'First, item');
  assert.equal(result.tasks[0].description,'Multiline notes');
  assert.deepEqual(result.tasks[0].labels,['design','important']);
  assert.equal(result.tasks[0].dueDate,'2026-11-03');
  assert.equal(result.tasks[0].cost,0);
  assert.equal(Object.keys(result.tasks[0].customFieldValues).length,2);
  assert.notEqual(result.tasks[0].id,'keep');
  const command='import json,sys;from data_model import normalize_plus,validate_plus;state=normalize_plus(json.load(sys.stdin));validate_plus(state);print("VALID_NOTION")';
  const python=spawnSync('py',['-3.12','-c',command],{cwd:root,input:JSON.stringify(result),
    encoding:'utf8',timeout:15000});
  assert.equal(python.status,0,python.stderr||python.stdout);
  assert.match(python.stdout,/VALID_NOTION/);
});

test('rejects invalid CSV quotes, duplicate header, unknown status expansion and malformed row',()=>{
  assert.throws(()=>inspectNotionCsv('Name,Status\n"bad,Todo'));
  assert.throws(()=>inspectNotionCsv('Name,Name\nCard,Card'));
  assert.throws(()=>inspectNotionCsv('Name,Status\nCard,New,Other'));
  assert.throws(()=>inspectNotionCsv('Status\nTodo'));
  assert.throws(()=>inspectNotionCsv('Name\n'));
  assert.throws(()=>inspectNotionCsv('Name\n'+('x'.repeat(3*1024*1024+1))));
  const tooMany='Name,Status\n'+Array.from({length:41},(_,n)=>'Card'+n+',Stage'+n).join('\n');
  assert.throws(()=>inspectNotionCsv(tooMany));
});

test('safe title/date validation, no phantom costs or user roles',()=>{
  assert.throws(()=>inspectNotionCsv('Name\n   '));
  const x=importNotionCsvBoard(seed,'Name,Status,Date\nExample,Active,2026-02-30');
  assert.equal(x.tasks[0].dueDate,'');
  assert.equal(x.tasks[0].cost,0);
  assert.equal(x.tasks[0].assignees.length,0);
  assert.equal(x.tasks[0].fileLinks.length,0);
  assert.ok(!('financial' in x.tasks[0]));
});
