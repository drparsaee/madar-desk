'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const esbuild=require('esbuild');
const Module=require('node:module');
const path=require('node:path');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const root=path.join(__dirname,'..');
const bundled=esbuild.buildSync({entryPoints:[path.join(root,'src/vitrea_overview.jsx')],
  bundle:true,platform:'node',format:'cjs',external:['react','react-dom','lucide-react'],
  loader:{'.css':'empty'},write:false}).outputFiles[0].text;
const entry=new Module('vitrea_overview',module);entry.filename=path.join(root,'src/vitrea_overview.jsx');
entry.paths=Module._nodeModulePaths(root);entry._compile(bundled,entry.filename);
const {monthlyTaskActivity,overviewTaskSummary,VitreaOverview}=entry.exports;
const now=new Date(2026,9,27);
const stages=[
  {id:'inbox',label:'صندوق ورودی',color:'#dddddd'},
  {id:'review',label:'در انتظار بررسی',color:'#8888ff'},
  {id:'done',label:'تکمیل‌شده',color:'#44bb88'}
];
const projects=[{id:'a',name:'پروژه معتبر'},{id:'b',name:'پروژه دوم'}];
const tasks=[
  {id:'1',projectId:'a',title:'در انتظار',status:'review',listId:'review',createdAt:'2026-10-01T12:00:00Z',dueDate:'2026-10-27'},
  {id:'2',projectId:'a',title:'پایان یافته',status:'done',listId:'done',createdAt:'2026-09-05T12:00:00Z'},
  {id:'3',projectId:'b',title:'جدید',status:'inbox',listId:'inbox',createdAt:'2026-10-02T12:00:00Z'},
  {id:'4',projectId:'b',title:'حذف‌شده',status:'inbox',deleted:true,createdAt:'2026-10-04T12:00:00Z'}
];

test('overview summary honors project, stage, deletion and due-date state',()=>{
  const s=overviewTaskSummary(tasks,projects,stages,now);
  assert.equal(s.total,3);
  assert.equal(s.completed,1);
  assert.equal(s.active,2);
  assert.equal(s.reviewCount,1);
  assert.deepEqual(s.reviews.map(t=>t.id),['1']);
  assert.deepEqual(s.due.map(t=>t.id),['1']);
  assert.deepEqual(s.projects.map(p=>[p.count,p.done]),[[2,1],[1,0]]);
  assert.deepEqual(s.lanes.map(l=>l.count),[1,1,1]);
});

test('chart series is computed from actual task createdAt, not example revenue',()=>{
  const rows=monthlyTaskActivity(tasks.filter(t=>!t.deleted),now,3);
  assert.deepEqual(rows.map(row=>[row.id,row.count]),[
    ['2026-08',0],['2026-09',1],['2026-10',2]
  ]);
  assert.equal(monthlyTaskActivity([],now,1)[0].count,0);
  assert.equal(monthlyTaskActivity([{createdAt:'2026-02-31'}],new Date(2026,1,10),1)[0].count,0,
    'invalid calendar dates must not become fabricated monthly activity');
});

test('overview renders accessible real-data project and task entry points',()=>{
  const html=renderToStaticMarkup(React.createElement(VitreaOverview,{
    tasks,projects,stages,onOpenTask:()=>{},onSelectProject:()=>{}
  }));
  assert.match(html,/aria-label="نمای کلی فضای کار"/);
  assert.match(html,/پروژه معتبر/);
  assert.match(html,/در انتظار/);
  assert.match(html,/روند فعالیت/);
  assert.match(html,/تعداد کارهای ثبت‌شده/);
  assert.doesNotMatch(html,/\$[0-9]/);
  assert.equal((html.match(/class="vitrea-overview-kpi"/g)||[]).length,3,
    'the three real metrics should remain visible');
  assert.equal((html.match(/class="vitrea-overview-project"/g)||[]).length,2,
    'every project must retain its clickable navigation entry');
  assert.doesNotMatch(html,/tone-[0-9]/,
    'project tiles should not receive decorative index-based rainbow colors');
});
