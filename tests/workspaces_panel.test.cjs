'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const Module=require('node:module');
const esbuild=require('esbuild');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const root=path.resolve(__dirname,'..');

function load(entry){
  const source=esbuild.buildSync({
    entryPoints:[path.join(root,'src',entry)],bundle:true,platform:'node',
    format:'cjs',write:false,jsx:'automatic',loader:{'.css':'empty'},
    external:['react','react/jsx-runtime','lucide-react'],
  }).outputFiles[0].text;
  const loader=new Module(path.join(root,'src','workspace-test-'+entry+'.cjs'),module);
  loader.filename=path.join(root,'src','workspace-test-'+entry+'.cjs');
  loader.paths=Module._nodeModulePaths(root);
  loader._compile(source,loader.filename);
  return loader.exports;
}

const w=load('workspaces_logic.js');
const {WorkspaceManager}=load('workspaces_panel.jsx');
const admin={canManage:true};
const unauthorized={canManage:false};

function state(){
  return {
    version:1,
    workspaces:[
      {id:'workspace-legacy',name:'فضای کاری من',archived:false},
      {id:'workspace-team',name:'تیم چاپ',archived:false},
      {id:'workspace-archive',name:'بایگانی',archived:true},
    ],
    projects:[
      {id:'p1',name:'چاپ',price:190000000,costEnabled:true,customer:{name:'private'}},
      {id:'p2',name:'بسته‌بندی',price:45000000,costEnabled:true},
    ],
    boards:[
      {id:'b1',workspaceId:'workspace-legacy',projectId:'p1',name:'برنامه',
        stages:[{id:'stage-a',label:'در جریان'}],archived:false,
        customFields:[{id:'field1',type:'text',name:'توضیحات'}]},
      {id:'b2',workspaceId:'workspace-team',projectId:'p2',name:'تولید',
        stages:[{id:'stage-b',label:'تمام'}],archived:false},
      {id:'b3',workspaceId:'workspace-archive',projectId:'p1',name:'قدیمی',
        stages:[{id:'stage-c',label:'صندوق'}],archived:true},
    ],
    tasks:[
      {id:'t1',boardId:'b1',listId:'stage-a',projectId:'p1',
        cost:1200000,costDate:'2026-10-20',costCategory:'چاپ',
        status:'active',checklist:[{id:'step',cost:100000,done:true,text:'دور برش'}],
        checklists:[{id:'legacy',items:[{id:'step',cost:100000}]}],
        customFieldValues:{field1:'مهم'},reports:[{id:'report1',summary:'در حال انجام'}]},
      {id:'t2',boardId:'b2',listId:'stage-b',projectId:'p2',
        cost:23000,status:'done',assignees:['user1']},
    ],
    finance:{invoices:[{id:'invoice1',price:50000000,customer:'حساس'}]},
    completion_outbox:[{eventId:'out1',cardId:'t2'}],
    templates:[{id:'tpl1',boardId:'b1',title:'الگو',customFieldValues:{}}],
    other:{keep:'unmodified'},
  };
}

const clone=x=>JSON.parse(JSON.stringify(x));

test('initial legacy-only workspace materializes losslessly without changing task finance',()=>{
  const before={version:1,projects:[{id:'p1'}],tasks:[{id:'t1',projectId:'p1',cost:100}],
    finance:{secret:'stay'}};
  const output=w.createWorkspaceState(before,'workspace-extra','جدید',admin);
  assert.deepEqual(output.workspaces.map(x=>x.id),['workspace-legacy','workspace-extra']);
  assert.deepEqual(output.boards,[]);
  assert.deepEqual(before.tasks,output.tasks);
  assert.deepEqual(before.finance,output.finance);
  assert.equal(before.workspaces,undefined);
  assert.equal(before.boards,undefined);
});

test('create preserves reference identity and no unrelated finance or task fields change',()=>{
  const before=state(), frozen=clone(before);
  const after=w.createWorkspaceState(before,'workspace-new','  سفارش‌ها  ',admin);
  assert.equal(after.workspaces[3].name,'سفارش‌ها');
  assert.strictEqual(after.projects,before.projects);
  assert.strictEqual(after.tasks,before.tasks);
  assert.strictEqual(after.boards,before.boards);
  assert.strictEqual(after.finance,before.finance);
  assert.deepEqual(before,frozen);
  assert.equal(w.validateWorkspaceLinks(after).workspaces.length,4);
});

test('rename legacy workspace allowed, ID remains stable, references untouched',()=>{
  const before=state();
  const after=w.renameWorkspaceState(before,'workspace-legacy','میراث',admin);
  assert.equal(after.workspaces[0].name,'میراث');
  assert.equal(after.workspaces[0].id,'workspace-legacy');
  assert.deepEqual(after.boards,before.boards);
  assert.deepEqual(after.tasks,before.tasks);
});

test('archive and restore workspace only; all cards and boards keep original statuses',()=>{
  const before=state(), snapshot=clone(before);
  const archived=w.archiveWorkspaceState(before,'workspace-team',admin);
  assert.equal(archived.workspaces[1].archived,true);
  assert.deepEqual(archived.boards,before.boards);
  assert.strictEqual(archived.tasks,before.tasks);
  assert.deepEqual(archived.finance,before.finance);
  assert.deepEqual(before,snapshot);
  const restored=w.restoreWorkspaceState(archived,'workspace-team',admin);
  assert.deepEqual(restored,before);
});

test('protect migrated legacy workspace and reject archiving last active',()=>{
  const source=state();
  assert.throws(()=>w.archiveWorkspaceState(source,'workspace-legacy',admin),/پیش‌فرض/);
  assert.throws(()=>w.archiveWorkspaceState(
    {...source,workspaces:[{id:'workspace-team',name:'تنها',archived:false}]},
    'workspace-team',admin),/Workspace ناشناخته|آخرین Workspace/);
  const solo={version:1,projects:[],boards:[],tasks:[],
    workspaces:[{id:'workspace-only',name:'تنها',archived:false}]};
  assert.throws(()=>w.archiveWorkspaceState(solo,'workspace-only',admin),/آخرین Workspace/);
  assert.throws(()=>w.archiveWorkspaceState(source,'workspace-archive',admin),/قبلاً بایگانی/);
  assert.throws(()=>w.restoreWorkspaceState(source,'workspace-team',admin),/فعال است/);
});

test('move board only changes workspaceId; project/finance/task/checklists byte-identical',()=>{
  const before=state(), frozen=JSON.stringify(before);
  const after=w.moveBoardWorkspaceState(before,'b1','workspace-team',admin);
  assert.equal(after.boards[0].workspaceId,'workspace-team');
  assert.equal(after.boards[0].projectId,'p1');
  assert.deepEqual(after.boards[0].customFields,before.boards[0].customFields);
  assert.strictEqual(after.boards[1],before.boards[1]);
  assert.strictEqual(after.tasks,before.tasks);
  assert.strictEqual(after.projects,before.projects);
  assert.strictEqual(after.finance,before.finance);
  assert.strictEqual(after.completion_outbox,before.completion_outbox);
  assert.strictEqual(after.templates,before.templates);
  assert.equal(JSON.stringify(before),frozen);
  assert.equal(w.validateWorkspaceLinks(after).boards[0].workspaceId,'workspace-team');
});

test('move archived board to active target permitted; moving to archived target rejected',()=>{
  const before=state();
  const moved=w.moveBoardWorkspaceState(before,'b3','workspace-team',admin);
  assert.equal(moved.boards[2].archived,true);
  assert.equal(moved.boards[2].workspaceId,'workspace-team');
  assert.throws(()=>w.moveBoardWorkspaceState(before,'b1','workspace-archive',admin),/مقصد/);
  assert.throws(()=>w.moveBoardWorkspaceState(before,'b1','missing',admin),/مقصد/);
  assert.throws(()=>w.moveBoardWorkspaceState(before,'unknown','workspace-team',admin),/برد پیدا نشد/);
});

test('all state mutations reject missing canManage or canManage false',()=>{
  const operations=[
    s=>w.createWorkspaceState(s,'workspace-new','جدید'),
    s=>w.createWorkspaceState(s,'workspace-new','جدید',unauthorized),
    s=>w.renameWorkspaceState(s,'workspace-team','نام جدید',unauthorized),
    s=>w.archiveWorkspaceState(s,'workspace-team',unauthorized),
    s=>w.restoreWorkspaceState(s,'workspace-archive',unauthorized),
    s=>w.moveBoardWorkspaceState(s,'b1','workspace-team',unauthorized),
  ];
  for(const op of operations)assert.throws(()=>op(state()),/مدیر/);
});

test('create rejects duplicate IDs even from stale concurrent state',()=>{
  const before=state();
  assert.throws(()=>w.createWorkspaceState(before,'workspace-team','تکراری',admin),/قبل/);
  const id='workspace-create1';
  const once=w.createWorkspaceState(before,id,'جدید',admin);
  assert.throws(()=>w.createWorkspaceState(once,id,'دوم',admin),/قبل/);
});

test('name sanitation rejects empty, controls and names beyond 180 chars',()=>{
  for(const name of ['', '   ', 'a\nb', 'a\r', 'x'.repeat(181),null,12]){
    assert.throws(()=>w.createWorkspaceState(state(),'workspace-extra',name,admin));
    assert.throws(()=>w.renameWorkspaceState(state(),'workspace-team',name,admin));
  }
  const after=w.renameWorkspaceState(state(),'workspace-team','  نام  ',admin);
  assert.equal(after.workspaces[1].name,'نام');
});

test('selection: viewer can select active workspace but cannot select archived or stale ID',()=>{
  assert.equal(w.selectWorkspaceId(state(),'workspace-team'),'workspace-team');
  assert.throws(()=>w.selectWorkspaceId(state(),'workspace-archive'),/فعال یا موجود/);
  assert.throws(()=>w.selectWorkspaceId(state(),'workspace-removed'),/فعال یا موجود/);
  assert.equal(w.activeWorkspaceId(state(),'workspace-archive'),'workspace-legacy');
  assert.equal(w.activeWorkspaceId(state(),'workspace-team'),'workspace-team');
});

test('ID generator retries collisions and validates bounded stable IDs',()=>{
  let count=0;
  const id=w.generateWorkspaceId(state(),()=>{
    count++;
    return count===1?'workspace-team':'workspace-safe-new';
  });
  assert.equal(id,'workspace-safe-new');
  assert.equal(count,2);
  assert.throws(()=>w.generateWorkspaceId(state(),()=> 'workspace-team'),/یکتای/);
  assert.throws(()=>w.generateWorkspaceId(state(),()=> 'https://evil'),/یکتای/);
  assert.throws(()=>w.createWorkspaceState(state(),'../hack','x',admin),/شناسه/);
});

test('refuse malformed existing references and duplicates instead of silently repairing data',()=>{
  const cases=[
    s=>s.boards[0].workspaceId='deleted-workspace',
    s=>s.boards[0].projectId='missing-project',
    s=>s.boards.push({...s.boards[0]}),
    s=>s.workspaces.push({...s.workspaces[0]}),
    s=>s.tasks[0].boardId='deleted-board',
    s=>s.tasks[0].projectId='missing-project',
    s=>s.tasks[0].projectId='p2',
    s=>s.tasks[0].listId='deleted-stage',
    s=>s.templates[0].boardId='deleted-board',
    s=>s.workspaces.forEach(ws=>ws.archived=true),
    s=>s.workspaces[1].archived='yes',
  ];
  for(const change of cases){
    const invalid=state(); change(invalid);
    assert.throws(()=>w.renameWorkspaceState(invalid,'workspace-team','تغییر',admin));
  }
  const raw=state();
  raw.workspaces=undefined;
  assert.throws(()=>w.createWorkspaceState(raw,'workspace-fake','پیشفرض',admin),/مهاجرت میزبان/);
});

test('capacity guard rejects workspace 101 without modifying existing 100',()=>{
  const initial=state();
  initial.workspaces=[
    ...initial.workspaces,
    ...Array.from({length:97},(_,i)=>({
      id:'workspace-extra-'+i,name:'فضا '+i,archived:false,
    })),
  ];
  assert.equal(w.validateWorkspaceLinks(initial).workspaces.length,100);
  assert.throws(()=>w.createWorkspaceState(initial,'workspace-overflow','اضافی',admin),/حداکثر/);
  assert.equal(initial.workspaces.length,100);
});

test('SSR read-only shows switching and board count, but no create/rename/archive/move controls',()=>{
  const html=renderToStaticMarkup(React.createElement(WorkspaceManager,{
    data:state(),currentWorkspaceId:'workspace-team',canManage:false,
    onSelect:()=>{},onChange:()=>{},
  }));
  assert.match(html,/aria-label="مدیریت فضاهای کاری"/);
  assert.match(html,/تیم چاپ/);
  assert.match(html,/aria-current="page"/);
  assert.match(html,/تولید/);
  assert.doesNotMatch(html,/ساخت Workspace/);
  assert.doesNotMatch(html,/تغییر نام تیم چاپ/);
  assert.doesNotMatch(html,/فضای مقصد برد/);
  assert.doesNotMatch(html,/بازیابی بایگانی/);
});

test('SSR manager contains creation/rename/archive, movement and restore UI',()=>{
  const html=renderToStaticMarkup(React.createElement(WorkspaceManager,{
    data:state(),currentWorkspaceId:'workspace-legacy',canManage:true,
    onSelect:()=>{},onChange:()=>{},
  }));
  assert.match(html,/ساخت Workspace/);
  assert.match(html,/تغییر نام تیم چاپ/);
  assert.match(html,/فضای مقصد برد برنامه/);
  assert.match(html,/بازیابی بایگانی/);
  assert.match(html,/نام Workspace جدید/);
  assert.match(html,/بایگانی فضای کاری، کارت یا برد را حذف/);
});

test('SSR protects default legacy workspace by disabling archive button',()=>{
  const html=renderToStaticMarkup(React.createElement(WorkspaceManager,{
    data:state(),currentWorkspaceId:'workspace-legacy',canManage:true,
  }));
  assert.match(html,/aria-label="بایگانی فضای کاری من" disabled/);
});

test('SSR invalid state renders explicit error, not management controls',()=>{
  const invalid=state();
  invalid.boards[0].workspaceId='gone';
  const html=renderToStaticMarkup(React.createElement(WorkspaceManager,{
    data:invalid,currentWorkspaceId:'workspace-legacy',canManage:true,
  }));
  assert.match(html,/role="alert"/);
  assert.doesNotMatch(html,/ساخت Workspace/);
});
