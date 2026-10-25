const test=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const esbuild=require('esbuild');
const Module=require('node:module');
const root=path.resolve(__dirname,'..');
const output=esbuild.buildSync({entryPoints:[path.join(root,'src/reporting.js')],platform:'node',format:'cjs',bundle:true,write:false}).outputFiles[0].text;
const mod=new Module(path.join(root,'reporting_test_generated.cjs'),module);
mod.filename=path.join(root,'reporting_test_generated.cjs');
mod.paths=Module._nodeModulePaths(root);
mod._compile(output,mod.filename);
const {dateKey,reportRows,summarizeRows,taskReportCsv,timelineBuckets}=mod.exports;
const tasks=[
  {id:'a',title:'کارت تست',projectId:'p1',status:'active',priority:'high',createdAt:'2026-10-01T10:00:00Z',dueDate:'2026-10-22',estimatedMinutes:75,actualMinutes:30,checklist:[{done:true},{done:false}],labels:['urgent'],assignees:['ali'],cost:999999,privateFinance:'secret'},
  {id:'b',title:'=HYPERLINK("http://example.test","x")',projectId:'p2',status:'done',priority:'low',createdAt:'2026-10-02T10:00:00Z',dueDate:'',estimatedMinutes:0,actualMinutes:0,checklist:[],labels:[],reports:[]},
  {id:'c',title:'archived',projectId:'p1',status:'done',createdAt:'2026-10-01',archived:true}
];
const projects=[{id:'p1',name:'شرکت'}, {id:'p2',name:'=ABUSE()'}];
const stages=[{id:'active',label:'در حال انجام'}, {id:'done',label:'انجام‌شده'}];
test('date validation rejects impossible dates and retains ISO day',()=>{
  assert.equal(dateKey('2026-02-30'), '');
  assert.equal(dateKey('2026-10-21T16:00:00Z'),'2026-10-21');
});
test('project and date filters isolate active rows and preserve progress',()=>{
  const result=reportRows(tasks,projects,stages,{projectId:'p1',start:'2026-10-20',end:'2026-10-30'});
  assert.equal(result.length,1);
  assert.equal(result[0].progress,50);
  assert.equal(result[0].actualMinutes,30);
  assert.equal(result[0].cost,undefined);
  assert.equal(result[0].privateFinance,undefined);
});
test('summary and timeline use task dates and actual vs estimated time',()=>{
  const rows=reportRows(tasks,projects,stages);
  const summary=summarizeRows(rows);
  assert.equal(summary.tasks,2);
  assert.equal(summary.estimatedMinutes,75);
  assert.equal(summary.actualMinutes,30);
  assert.equal(summary.completedSteps,1);
  assert.equal(summary.totalSteps,2);
  assert.equal(timelineBuckets(rows).length,1);
});
test('CSV escapes formula payloads, quotes and never includes finance',()=>{
  const rows=reportRows(tasks,projects,stages);
  const csv=taskReportCsv(rows);
  assert.ok(csv.startsWith('\ufeff'));
  assert.match(csv,/"'=HYPERLINK/);
  assert.match(csv,/"'=ABUSE\(\)"/);
  assert.doesNotMatch(csv,/999999|privateFinance|secret|هزینه|سود/);
  assert.match(csv, /\r\n/);
});
