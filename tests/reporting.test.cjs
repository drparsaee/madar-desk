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
test('report treats explicitly completed task as finished without changing status or finance',()=>{
  const card={id:'completed-in-place',title:'وظیفه تکمیل‌شده',projectId:'p1',
    status:'active',listId:'active',completed:true,priority:'high',
    dueDate:'2020-01-01',createdAt:'2019-12-01'};
  const rows=reportRows([card],projects,stages);
  assert.equal(rows.length,1);
  assert.equal(rows[0].status,'در حال انجام');
  assert.equal(rows[0].completed,true);
  const summary=summarizeRows(rows);
  assert.equal(summary.done,1);
  assert.equal(summary.overdue,0);
  assert.equal(card.status,'active');
  assert.equal(card.listId,'active');
  const reopened={...card,completed:false,status:'done'};
  const reopenedSummary=summarizeRows(reportRows([reopened],projects,stages));
  assert.equal(reopenedSummary.done,0);
  assert.equal(reopenedSummary.overdue,1);
  const legacy={...reopened,completed:undefined};
  assert.equal(summarizeRows(reportRows([legacy],projects,stages)).done,1);
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
test('cross-board reporting uses each card local list, not the currently selected board list',()=>{
 const boards=[
   {id:'b1',name:'پیش‌ازچاپ',projectId:'p1',stages:[{id:'check',label:'بررسی فایل'}]},
   {id:'b2',name:'تولید',projectId:'p2',stages:[{id:'cut',label:'برش نهایی'}]}];
 const cards=[
   {id:'first',title:'A',projectId:'p1',boardId:'b1',listId:'check',status:'active'},
   {id:'second',title:'B',projectId:'p2',boardId:'b2',listId:'cut',status:'active'}];
 const rows=reportRows(cards,projects,stages,{boards});
 assert.deepEqual(rows.map(item=>item.status),['بررسی فایل','برش نهایی']);
 assert.deepEqual(rows.map(item=>item.board),['پیش‌ازچاپ','تولید']);
 assert.deepEqual(reportRows(cards,projects,stages,{boards,boardId:'b2'}).map(item=>item.id),['second']);
});

test('identically named projects remain different stable project identities in KPI',()=>{
 const sameNames=[{id:'p1',name:'سفارشات'},{id:'p2',name:'سفارشات'}];
 const cards=[{id:'a',title:'A',projectId:'p1',status:'active',estimatedMinutes:12},
   {id:'b',title:'B',projectId:'p2',status:'done',estimatedMinutes:25}];
 const summary=summarizeRows(reportRows(cards,sameNames,stages));
 assert.equal(summary.tasks,2);
 assert.equal(summary.byProject.length,2);
 assert.deepEqual(summary.byProject.map(group=>group.id).sort(),['p1','p2']);
});
