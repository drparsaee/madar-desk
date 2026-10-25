'use strict';
/** M03 source-only performance/permission contract, no APPDATA or I/O writes. */
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const Module = require('node:module');
const esbuild = require('esbuild');
const root = path.resolve(__dirname, '..');
function load(relative) {
  const filename = path.join(root,relative);
  const compiled = esbuild.buildSync({
    entryPoints:[filename], bundle:true,platform:'node',format:'cjs',write:false,
  }).outputFiles[0].text;
  const loader = new Module(filename+'.m03-test.cjs',module);
  loader.filename = filename+'.m03-test.cjs';
  loader.paths = Module._nodeModulePaths(path.dirname(filename));
  loader._compile(compiled,loader.filename);
  return loader.exports;
}
const {createBoardPerformanceIndex,BOARD_INDEX_LIMITS} = load('src/board_performance.js');
const {getOrderedLaneCards} = load('src/cardorder.js');
const GRANTS={permittedProjectIds:['p-a']};
function card(id,boardId='b-a',listId='doing',extra={}) {
  return {id,projectId:'p-a',boardId,listId,status:listId,priority:'medium',
    title:'کارت '+id,archived:false,deleted:false,cost:201007,
    checklist:[{id:'step',text:'برش',done:false,cost:80811}],reports:[],
    ...extra};
}
function fixture() {
  return {
    version:1,
    projects:[{id:'p-a',price:8000000},{id:'p-b',price:99999999}],
    workspaces:[{id:'w-1',name:'Workshop',archived:false},
                {id:'w-2',name:'Other',archived:false},
                {id:'w-old',name:'Old',archived:true}],
    boards:[
      {id:'b-a',projectId:'p-a',workspaceId:'w-1',archived:false,stages:[
        {id:'doing',label:'Doing'},{id:'done',label:'Done'},
        {id:'hidden',label:'Hidden',archived:true}]},
      {id:'b-second',projectId:'p-a',workspaceId:'w-2',archived:false,
       stages:[{id:'doing',label:'Doing'},{id:'done',label:'Done'}]},
      {id:'b-b',projectId:'p-b',workspaceId:'w-1',archived:false,
       stages:[{id:'doing',label:'Doing'}]},
      {id:'b-archive',projectId:'p-a',workspaceId:'w-1',archived:true,
       stages:[{id:'doing',label:'Doing'}]},
      {id:'b-old',projectId:'p-a',workspaceId:'w-old',archived:false,
       stages:[{id:'doing',label:'Doing'}]},
    ],
    stages:[{id:'doing',label:'Doing'},{id:'done',label:'Done'}],
    tasks:[
      card('legacy-no-order'),
      card('ordered10','b-a','doing',{cardOrder:10,cost:711112,priority:'high',
         reports:[{id:'report'}]}),
      card('ordered1','b-a','doing',{cardOrder:1}),
      card('tieA','b-a','doing',{cardOrder:10}),
      card('tieB','b-a','doing',{cardOrder:10}),
      card('last','b-a','done',{cardOrder:12}),
      card('second-workspace','b-second','doing'),
      card('foreign','b-b','doing',{projectId:'p-b',cost:989898}),
      card('archived-board','b-archive','doing'),
      card('archived-workspace','b-old','doing'),
      card('hidden-list','b-a','hidden'),
      card('archived-card','b-a','doing',{archived:true}),
      card('deleted-card','b-a','doing',{deleted:true}),
      card('board-archived-card','b-a','doing',{archivedByBoard:true}),
    ],
    finance:{contracts:[{id:'sensitive-contract'}],ledger:[{amount:999999999}]},
    payments:[{value:99999999}],
    audit:[{actor:'owner'}],
  };
}
function deepFreeze(o) {
  if (!o || typeof o !== 'object' || Object.isFrozen(o)) return o;
  for (const item of Object.values(o)) deepFreeze(item);
  return Object.freeze(o);
}
function index(state=fixture(), scope=GRANTS) {
  return createBoardPerformanceIndex(state,scope);
}
const ids=items=>items.map(item=>item.id);

test('explicit host-visible project IDs are mandatory; no implicit all-access',()=>{
  assert.throws(()=>createBoardPerformanceIndex(fixture()),/permittedProjectIds/);
  assert.throws(()=>index(fixture(),{permittedProjectIds:null}),/permittedProjectIds/);
  assert.throws(()=>index(fixture(),{permittedProjectIds:'p-a'}),/permittedProjectIds/);
  assert.throws(()=>index(fixture(),{permittedProjectIds:[null]}),/string/);
  assert.equal(index(fixture(),{permittedProjectIds:[]}).visibleCount,0);
  assert.equal(index(fixture(),{permittedProjectIds:['missing']}).visibleCount,0);
});

test('visibility excludes trashed/archived board, workspace, list and card without changing raw records',()=>{
  const original=deepFreeze(fixture());
  const before=JSON.stringify(original);
  const i=index(original);
  assert.equal(i.visibleCount,7);
  assert.deepEqual(ids(i.selectActiveCards()),[
    'legacy-no-order','ordered10','ordered1','tieA','tieB','last','second-workspace']);
  assert.equal(JSON.stringify(original),before);
  assert.strictEqual(i.selectActiveCards()[1],original.tasks[1]);
  assert.equal(original.tasks[0].cost,201007);
  assert.equal(original.tasks[0].checklist[0].cost,80811);
});

test('foreign project never becomes visible via board ID, list ID, workspace, predicate or match IDs',()=>{
  const source=fixture();
  const i=index(source);
  const options=[
    {},{boardId:'b-b'},{workspaceId:'w-1'},{projectId:'p-b'},
    {boardId:'b-b',projectId:'p-b'},
    {matchIds:new Set(['foreign','ordered1'])},
    {predicate:()=>true},
  ];
  for (const option of options) {
    const candidates=i.selectActiveCards(option);
    assert.ok(!candidates.some(t=>t.id==='foreign'),JSON.stringify(option));
    assert.ok(candidates.every(t=>t.projectId==='p-a'));
  }
  assert.deepEqual(i.getOrderedLaneCards('b-b','doing'),[]);
  assert.equal(i.getLanePage('b-b','doing').total,0);
  assert.deepEqual([...i.groupActiveCards({boardId:'b-b'}).entries()],[]);
});

test('workspace and project intersect, board-scoped selection cannot escape selected workspace',()=>{
  const i=index();
  assert.deepEqual(ids(i.selectActiveCards({workspaceId:'w-1',projectId:'p-a'})),
    ['legacy-no-order','ordered10','ordered1','tieA','tieB','last']);
  assert.deepEqual(ids(i.selectActiveCards({workspaceId:'w-1',boardId:'b-second'})),[]);
  assert.deepEqual(ids(i.selectActiveCards({workspaceId:'w-2'})),['second-workspace']);
  assert.deepEqual(ids(i.selectActiveCards({workspaceId:'w-old'})),[]);
  assert.deepEqual(ids(i.selectActiveCards({projectId:'p-a',boardId:'b-a',listId:'done'})),['last']);
});

test('indexed lane matches cardorder.js stable explicit positions, ties and absent order',()=>{
  const source=fixture();
  const i=index(source);
  const fromIndex=i.getOrderedLaneCards('b-a','doing');
  assert.deepEqual(ids(fromIndex),
    ['ordered1','ordered10','tieA','tieB','legacy-no-order']);
  const expected=getOrderedLaneCards(source.tasks,'b-a','doing')
    .filter(t=>t.deleted!==true&&t.archivedByBoard!==true);
  assert.deepEqual(ids(fromIndex),ids(expected));
  assert.strictEqual(fromIndex[1],source.tasks[1]);
});

test('group once per board using stable lane rank and with filters',()=>{
  const i=index();
  const result=i.groupActiveCards({boardId:'b-a'});
  assert.deepEqual([...result.keys()],['doing','done']);
  assert.deepEqual(ids(result.get('doing')),
    ['ordered1','ordered10','tieA','tieB','legacy-no-order']);
  assert.deepEqual(ids(result.get('done')),['last']);
  const filtered=i.groupActiveCards({
    boardId:'b-a',priority:'high',withReports:true,
  });
  assert.deepEqual([...filtered.keys()],['doing']);
  assert.deepEqual(ids(filtered.get('doing')),['ordered10']);
  assert.equal(i.groupActiveCards({boardId:'b-a',projectId:'p-b'}).size,0);
  assert.deepEqual(ids(i.groupActiveCards({workspaceId:'w-2'}).get('doing')),
    ['second-workspace']);
});

test('matchIds intersection and external advanced callback never search raw finance',()=>{
  const source=deepFreeze(fixture());
  const i=index(source);
  const matches=new Set(['foreign','ordered10','ordered1','last']);
  assert.deepEqual(ids(i.selectActiveCards({
    boardId:'b-a',matchIds:matches,predicate:t=>t.cost>300000,
  })),['ordered10']);
  assert.deepEqual(ids(i.selectActiveCards({boardId:'b-a',highOnly:true})),['ordered10']);
  assert.deepEqual(ids(i.selectActiveCards({boardId:'b-a',withReports:true})),['ordered10']);
  assert.strictEqual(source.finance.contracts[0].id,'sensitive-contract');
  assert.ok(!Object.hasOwn(i,'finance'));
  assert.ok(!Object.hasOwn(i,'projects'));
  assert.ok(!Object.hasOwn(i,'tasks'));
  assert.ok(Object.isFrozen(i));
});

test('progressive lane page bounds output and deterministic consecutive pages',()=>{
  const i=index();
  const first=i.getLanePage('b-a','doing',{limit:2});
  assert.deepEqual(ids(first.cards),['ordered1','ordered10']);
  assert.equal(first.total,5);
  assert.equal(first.nextOffset,2);
  assert.equal(first.hasMore,true);
  const second=i.getLanePage('b-a','doing',{limit:2,offset:first.nextOffset});
  assert.deepEqual(ids(second.cards),['tieA','tieB']);
  const last=i.getLanePage('b-a','doing',{limit:2,offset:second.nextOffset});
  assert.deepEqual(ids(last.cards),['legacy-no-order']);
  assert.equal(last.nextOffset,null);
  assert.equal(last.hasMore,false);
  assert.deepEqual(i.getLanePage('b-a','doing',{limit:2,offset:99}),{
    cards:[],total:5,nextOffset:null,hasMore:false,
  });
});

test('returns new array snapshots, never exposing mutable internal lane arrays',()=>{
  const i=index();
  const first=i.getOrderedLaneCards('b-a','doing');
  first.pop(); first.reverse();
  assert.equal(i.getOrderedLaneCards('b-a','doing').length,5);
  const page=i.getLanePage('b-a','doing',{limit:3});
  page.cards.splice(0,3);
  assert.equal(i.getLanePage('b-a','doing',{limit:3}).cards.length,3);
});

test('legacy v1 boardless stage view preserves original status and IDs',()=>{
  const source=fixture();
  source.boards=[];source.workspaces=[];
  source.tasks=[
    card('','unused','unused',{boardId:undefined,listId:undefined,status:'doing'}),
    card('id\nlegacy','unused','unused',{boardId:undefined,listId:undefined,status:'done',cost:80800}),
    card('orphan','b-a','doing'),
  ];
  const i=index(source);
  assert.equal(i.visibleCount,2);
  assert.deepEqual(ids(i.groupActiveCards().get('doing')),['']);
  assert.deepEqual(ids(i.groupActiveCards().get('done')),['id\nlegacy']);
  assert.deepEqual(ids(i.selectActiveCards({workspaceId:'workspace-legacy'})),['','id\nlegacy']);
  assert.equal(i.getOrderedLaneCards('b-a','doing').length,0);
});

test('project-less board works only for a task in an explicitly granted project',()=>{
  const source=fixture();
  source.boards[0].projectId=null;
  assert.deepEqual(ids(index(source).getOrderedLaneCards('b-a','doing')),
    ['ordered1','ordered10','tieA','tieB','legacy-no-order']);
  assert.deepEqual(index(source,{permittedProjectIds:['p-b']}).getOrderedLaneCards('b-a','doing'),[]);
});

test('invalid cardOrder and malformed archived flags reject rather than silently hiding cards',()=>{
  for (const invalid of [null,'7',false,-1,1_000_001,1.5]) {
    const source=fixture();
    source.tasks[0].cardOrder=invalid;
    assert.throws(()=>index(source),/cardOrder/);
  }
  for (const location of ['task','board','workspace','stage']) {
    const source=fixture();
    const target={
      task:source.tasks[0],board:source.boards[0],
      workspace:source.workspaces[0],stage:source.boards[0].stages[0],
    }[location];
    target.archived='true';
    assert.throws(()=>index(source),/archived must be boolean/);
  }
});

test('duplicate accessible card/board/workspace/project/stage fail closed',()=>{
  const cases=[
    s=>s.tasks.push({...s.tasks[0]}),
    s=>s.boards.push({...s.boards[0]}),
    s=>s.workspaces.push({...s.workspaces[0]}),
    s=>s.projects.push({...s.projects[0]}),
    s=>s.boards[0].stages.push({...s.boards[0].stages[0]}),
  ];
  for (const modify of cases) {
    const source=fixture();modify(source);
    assert.throws(()=>index(source),/Duplicate/);
  }
});

test('typed query options and page bounds reject unbounded or malformed inputs',()=>{
  const i=index();
  for (const opts of [
    null,[],{predicate:10},{matchIds:[]},{highOnly:1},{withReports:'true'},
    {boardId:13},{projectId:{}},{workspaceId:null},{status:4},
  ]) assert.throws(()=>i.selectActiveCards(opts));
  for (const opts of [
    {limit:0},{limit:301},{limit:-1},{limit:1.2},
    {offset:-1},{offset:1.3},{offset:Number.MAX_SAFE_INTEGER+1},
  ]) assert.throws(()=>i.getLanePage('b-a','doing',opts));
  assert.equal(BOARD_INDEX_LIMITS.page,300);
  assert.equal(BOARD_INDEX_LIMITS.tasks,20_000);
});

test('oversized arrays reject bounded host ceilings without modifying source',()=>{
  const source=fixture();
  source.tasks=Array.from({length:20_001},(_,n)=>card('c'+n));
  assert.throws(()=>index(source),/20000/);
  const boards=fixture(); boards.boards=Array.from({length:2001},(_,i)=>({id:'b'+i}));
  assert.throws(()=>index(boards),/2000/);
  const spaces=fixture();spaces.workspaces=Array.from({length:101},(_,i)=>({id:'w'+i}));
  assert.throws(()=>index(spaces),/100/);
});

test('10k cards spread across boards: indexed counts and pages match authored data',()=>{
  const source=fixture();
  source.tasks=Array.from({length:10000},(_,n)=>card('item-'+n,
    n%2?'b-a':'b-second', n%4===1?'done':'doing',
    {cardOrder:n,archived:n%37===0,deleted:n%41===0}));
  const beforeIds=source.tasks.map(t=>t.id);
  const i=index(source);
  const visible=source.tasks.filter(t=>!t.archived&&!t.deleted);
  assert.equal(i.visibleCount,visible.length);
  const a=i.selectActiveCards({boardId:'b-a'});
  assert.deepEqual(ids(a),ids(visible.filter(t=>t.boardId==='b-a')));
  const lane=i.getOrderedLaneCards('b-a','doing');
  assert.equal(lane.length,visible.filter(t=>t.boardId==='b-a'&&t.listId==='doing').length);
  assert.deepEqual(ids(i.getLanePage('b-a','doing',{limit:60}).cards),
    ids(lane.slice(0,60)));
  assert.deepEqual(source.tasks.map(t=>t.id),beforeIds);
});
