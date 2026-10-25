'use strict';
/** M03 read-only progressive UI/data boundary, no browser or APPDATA. */
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const Module = require('node:module');
const esbuild = require('esbuild');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');

const root=path.resolve(__dirname,'..');
function load(relative) {
  const filename=path.join(root,relative);
  const compiled=esbuild.buildSync({
    entryPoints:[filename],bundle:true,platform:'node',
    format:'cjs',write:false,
  }).outputFiles[0].text;
  const mod=new Module(filename+'.progressive-tests.cjs',module);
  mod.filename=filename+'.progressive-tests.cjs';
  mod.paths=Module._nodeModulePaths(path.dirname(filename));
  mod._compile(compiled,mod.filename);
  return mod.exports;
}
const {
  PROGRESSIVE_LANE_LIMITS,
  createProgressiveLaneState,
  captureProgressiveLaneScroll,
  advanceProgressiveLaneState,
  reconcileProgressiveLaneState,
  revealProgressiveLaneCard,
  progressiveLaneNeighbor,
  getProgressiveLaneView,
}=load('src/board_progressive.js');
const {createBoardPerformanceIndex}=load('src/board_performance.js');
const create=(n=180,prefix='card')=>Array.from({length:n},(_,i)=>({
  id:prefix+'-'+i, boardId:'board-a',listId:'doing',projectId:'public',
  cardOrder:i,status:'active',title:'کار '+i, deleted:false,
  cost:300000+i,checklist:[{id:'step-'+i,text:'برش',cost:19000+i}],
  invoiceId:'invoice-'+i,attachments:[{id:'file-'+i}],
}));
const ids=items=>items.map(x=>x.id);
const entryIds=view=>view.entries.map(x=>x.card.id);
function view(cards,state,more) {
  return getProgressiveLaneView(cards,state,{
    regionId:'lane-123',laneLabel:'چاپ',...more,
  });
}
function frozen(value) {
  if (!value || typeof value !== 'object' || Object.isFrozen(value))return value;
  for(const sub of Object.values(value))frozen(sub);
  return Object.freeze(value);
}

test('empty and small lanes are bounded, with no phantom controls',()=>{
  const empty=[];
  const state=createProgressiveLaneState(empty);
  const v=view(empty,state);
  assert.equal(state.start,0);assert.equal(state.end,0);
  assert.equal(v.total,0);assert.equal(v.shown,0);
  assert.equal(v.hasNext,false);assert.equal(v.hasPrevious,false);
  assert.equal(v.focusTarget,null);
  assert.equal(v.controls.next,null);assert.equal(v.controls.previous,null);
  assert.match(v.liveStatus,/کارتی/);
  const tiny=create(3);
  const small=createProgressiveLaneState(tiny);
  assert.equal(small.end,3);
  assert.deepEqual(entryIds(view(tiny,small)),ids(tiny));
  assert.strictEqual(advanceProgressiveLaneState(tiny,small,'next'),small);
  assert.strictEqual(advanceProgressiveLaneState(tiny,small,'previous'),small);
});

test('defaults and strict page/window bounds prevent unbounded DOM items',()=>{
  assert.equal(PROGRESSIVE_LANE_LIMITS.defaultPageSize,48);
  assert.equal(PROGRESSIVE_LANE_LIMITS.defaultMaxRendered,240);
  assert.equal(PROGRESSIVE_LANE_LIMITS.maxRendered,300);
  assert.equal(PROGRESSIVE_LANE_LIMITS.maxPageSize,100);
  const cards=create(10000);
  let state=createProgressiveLaneState(cards);
  assert.equal(view(cards,state).entries.length,48);
  for(let i=0;i<260;i++) {
    state=advanceProgressiveLaneState(cards,state,'next');
    const v=view(cards,state);
    assert.ok(v.entries.length<=240);
    assert.ok(v.entries.length>0);
    assert.equal(v.rangeEnd-v.rangeStart+1,v.shown);
  }
  assert.equal(state.end,10000);
  assert.equal(state.start,10000-240);
  assert.equal(view(cards,state).remaining,0);
  assert.equal(view(cards,state).hasNext,false);
  assert.equal(view(cards,state).hasPrevious,true);
});

test('stable absolute zero-based data indexes and one-based ARIA positions across sliding windows',()=>{
  const cards=create(27);
  let state=createProgressiveLaneState(cards,{pageSize:5,maxRendered:10});
  state=advanceProgressiveLaneState(cards,state,'next');
  assert.equal(state.start,0); assert.equal(state.end,10);
  state=advanceProgressiveLaneState(cards,state,'next');
  assert.equal(state.start,5); assert.equal(state.end,15);
  const snapshot=view(cards,state);
  assert.deepEqual(snapshot.entries.map(x=>x.index),[5,6,7,8,9,10,11,12,13,14]);
  assert.deepEqual(snapshot.entries.map(x=>x.ariaPosInSet),[6,7,8,9,10,11,12,13,14,15]);
  assert.ok(snapshot.entries.every(x=>x.ariaSetSize===27));
  assert.deepEqual(entryIds(snapshot),ids(cards.slice(5,15)));
  assert.equal(snapshot.rangeStart,6);
  assert.equal(snapshot.rangeEnd,15);
  assert.equal(snapshot.remaining,12);
  assert.equal(snapshot.total,27);
  assert.equal(snapshot.shown,10);
});

test('previous/next trim opposite side and preserve first newly loaded focus',()=>{
  const cards=create(60);
  let state=createProgressiveLaneState(cards,{pageSize:5,maxRendered:10});
  state=advanceProgressiveLaneState(cards,state,'next');
  state=advanceProgressiveLaneState(cards,state,'next');
  assert.equal(state.start,5);assert.equal(state.end,15);
  assert.deepEqual(view(cards,state).focusTarget,
    {cardId:'card-10',preventScroll:true});
  state=advanceProgressiveLaneState(cards,state,'previous');
  assert.equal(state.start,0);assert.equal(state.end,10);
  assert.deepEqual(view(cards,state).focusTarget,
    {cardId:'card-0',preventScroll:true});
  const first=advanceProgressiveLaneState(cards,state,'previous');
  assert.strictEqual(first,state);
});

test('capture anchor retains scroll context when advance keeps anchor rendered',()=>{
  const cards=create(100);
  let state=createProgressiveLaneState(cards,{pageSize:8,maxRendered:24});
  state=captureProgressiveLaneScroll(cards,state,{
    cardId:'card-3',offsetPx:-17.5,scrollTopPx:211.25,
  });
  state=advanceProgressiveLaneState(cards,state,'next');
  const v=view(cards,state);
  assert.equal(v.scrollRestore.cardId,'card-3');
  assert.equal(v.scrollRestore.offsetPx,-17.5);
  assert.equal(v.scrollRestore.fallbackScrollTopPx,211.25);
  assert.equal(v.scrollRestore.strategy,'measure-anchor-after-render');
  assert.equal(v.anchorLost,false);
  assert.equal(v.focusTarget.cardId,'card-8');
  assert.ok(Object.isFrozen(state));
});

test('when bounded window drops captured anchor, explicit loss and safe fallback are provided',()=>{
  const cards=create(100);
  let state=createProgressiveLaneState(cards,{pageSize:5,maxRendered:10});
  state=captureProgressiveLaneScroll(cards,state,{
    cardId:'card-1',offsetPx:20,scrollTopPx:90,
  });
  state=advanceProgressiveLaneState(cards,state,'next');
  state=advanceProgressiveLaneState(cards,state,'next');
  const v=view(cards,state);
  assert.equal(state.start,5);
  assert.equal(v.anchorLost,true);
  assert.equal(v.scrollRestore.cardId,'card-5');
  assert.equal(v.scrollRestore.offsetPx,0);
  assert.equal(v.scrollRestore.fallbackScrollTopPx,0);
  assert.equal(v.focusTarget.cardId,'card-10');
});

test('captures only currently rendered authorized anchor IDs, including legacy ID',()=>{
  const cards=create(20);
  cards[0].id='';
  cards[1].id='legacy\n\tcard';
  const state=createProgressiveLaneState(cards,{pageSize:5,maxRendered:10});
  const anchored=captureProgressiveLaneScroll(cards,state,{
    cardId:'',offsetPx:0,scrollTopPx:0,
  });
  assert.equal(anchored.anchorId,'');
  assert.equal(view(cards,anchored).scrollRestore.cardId,'');
  assert.equal(anchored.anchorIndexInWindow,0);
  assert.throws(()=>captureProgressiveLaneScroll(cards,state,{cardId:'card-19'}),
    /not in current permitted/);
  assert.throws(()=>captureProgressiveLaneScroll(cards,state,{cardId:'not-authorized'}),
    /not in current permitted/);
});

test('reconcile inserting cards before visible anchor keeps identical ID + screen offset',()=>{
  const before=create(50);
  let state=createProgressiveLaneState(before,{pageSize:6,maxRendered:12});
  state=advanceProgressiveLaneState(before,state,'next');
  state=advanceProgressiveLaneState(before,state,'next');
  state=captureProgressiveLaneScroll(before,state,{
    cardId:'card-7',offsetPx:-42,scrollTopPx:760,
  });
  const injected=[
    {id:'new-1',title:'new private-free'},
    {id:'new-2',title:'new private-free'},...before,
  ];
  const reconciled=reconcileProgressiveLaneState(injected,state);
  assert.ok(reconciled.start>state.start);
  assert.ok(view(injected,reconciled).entries.some(x=>x.card.id==='card-7'));
  assert.equal(reconciled.anchorId,'card-7');
  assert.equal(reconciled.anchorOffsetPx,-42);
  assert.equal(reconciled.scrollTopPx,760);
  assert.equal(reconciled.anchorLost,false);
  assert.equal(view(injected,reconciled).scrollRestore.cardId,'card-7');
});

test('reconcile deleted/hidden anchor never leaks stale ID in visible output',()=>{
  const cards=create(60);
  let state=createProgressiveLaneState(cards,{pageSize:8,maxRendered:20});
  state=captureProgressiveLaneScroll(cards,state,{
    cardId:'card-2',offsetPx:-6,scrollTopPx:130,
  });
  const shrunk=cards.filter(x=>x.id!=='card-2');
  const adjusted=reconcileProgressiveLaneState(shrunk,state);
  const v=view(shrunk,adjusted);
  assert.equal(v.anchorLost,true);
  assert.ok(!entryIds(v).includes('card-2'));
  assert.notEqual(v.scrollRestore.cardId,'card-2');
  assert.equal(v.scrollRestore.offsetPx,0);
  assert.equal(v.scrollRestore.fallbackScrollTopPx,0);
});

test('reconcile empty scope clears anchors, focus and visible cards on permission revocation',()=>{
  const cards=create(25);
  let state=createProgressiveLaneState(cards);
  state=captureProgressiveLaneScroll(cards,state,{
    cardId:'card-3',offsetPx:6,scrollTopPx:60,
  });
  const denied=reconcileProgressiveLaneState([],state);
  const v=view([],denied);
  assert.equal(denied.start,0);assert.equal(denied.end,0);
  assert.equal(denied.anchorId,null);assert.equal(denied.focusCardId,null);
  assert.equal(v.scrollRestore.cardId,null);
  assert.equal(v.anchorLost,true);
  assert.deepEqual(v.entries,[]);
  assert.equal(v.total,0);
});

test('reconcile shrinking lane clamps bounds and eliminates stale focus',()=>{
  const cards=create(80);
  let state=createProgressiveLaneState(cards,{pageSize:8,maxRendered:24});
  for(let i=0;i<6;i++)state=advanceProgressiveLaneState(cards,state,'next');
  assert.equal(state.end,56);
  assert.equal(state.start,32);
  const smaller=cards.slice(0,15);
  const result=reconcileProgressiveLaneState(smaller,state);
  const v=view(smaller,result);
  assert.equal(result.start,0);assert.equal(result.end,15);
  assert.equal(v.total,15);
  assert.ok(v.entries.every(x=>x.card.id.startsWith('card-')));
  assert.equal(v.focusTarget,null);
});

test('jump-to-card reveals late authorized ID within bounded window and requests focus',()=>{
  const cards=create(500);
  let state=createProgressiveLaneState(cards,{pageSize:20,maxRendered:80});
  state=revealProgressiveLaneCard(cards,state,'card-403');
  const v=view(cards,state);
  assert.equal(v.shown,20);
  assert.ok(v.rangeStart<=404&&v.rangeEnd>=404);
  assert.equal(v.focusTarget.cardId,'card-403');
  assert.equal(v.scrollRestore.cardId,'card-403');
  assert.equal(state.anchorIndexInWindow,403-state.start);
  assert.throws(()=>revealProgressiveLaneCard(cards,state,'private-or-missing'),
    /not in current permitted/);
});

test('jump within already visible slice does not reorder or expand window',()=>{
  const cards=create(90);
  const state=createProgressiveLaneState(cards,{pageSize:10,maxRendered:30});
  const result=revealProgressiveLaneCard(cards,state,'card-7');
  assert.equal(result.start,0);assert.equal(result.end,10);
  assert.equal(result.focusCardId,'card-7');
  assert.equal(result.anchorId,null);
});

test('full-lane keyboard neighbors work across hidden window boundary',()=>{
  const cards=create(35);
  const state=createProgressiveLaneState(cards,{pageSize:5,maxRendered:10});
  assert.deepEqual(entryIds(view(cards,state)),ids(cards.slice(0,5)));
  assert.strictEqual(progressiveLaneNeighbor(cards,'card-4',1),cards[5]);
  assert.strictEqual(progressiveLaneNeighbor(cards,'card-5',-1),cards[4]);
  assert.equal(progressiveLaneNeighbor(cards,'card-0',-1),null);
  assert.equal(progressiveLaneNeighbor(cards,'card-34',1),null);
  assert.throws(()=>progressiveLaneNeighbor(cards,'private-card',1),/not in current permitted/);
});

test('source cards and money remain exactly unchanged through 200 page/jump/reconcile cycles',()=>{
  const cards=frozen(create(900));
  const original=JSON.stringify(cards);
  let state=createProgressiveLaneState(cards);
  for(let i=0;i<200;i++) {
    state=advanceProgressiveLaneState(cards,state,i%4===3?'previous':'next');
    if(i%19===0)state=reconcileProgressiveLaneState(cards,state);
    if(i%37===0)state=revealProgressiveLaneCard(cards,state,'card-'+((i*3)%900));
    const v=view(cards,state);
    assert.ok(v.entries.every(item=>item.card===cards[item.index]));
    assert.ok(v.shown<=240);
  }
  assert.equal(JSON.stringify(cards),original);
  assert.equal(cards[50].cost,300050);
  assert.equal(cards[50].checklist[0].cost,19050);
  assert.equal(cards[50].invoiceId,'invoice-50');
});

test('state, cards, numeric offsets, button region and malformed pager fail closed',()=>{
  const cards=create(50);
  const state=createProgressiveLaneState(cards);
  // [] is a valid empty lane and has its own dedicated test above.
  for(const bad of [null,{},'cards'])assert.throws(()=>createProgressiveLaneState(bad));
  for(const bad of [
    {pageSize:0},{pageSize:101},{pageSize:1.5},{maxRendered:0},
    {pageSize:50,maxRendered:49},{maxRendered:301},
  ])assert.throws(()=>createProgressiveLaneState(cards,bad));
  for(const bad of [
    {cardId:'card-2',offsetPx:Infinity},
    {cardId:'card-2',offsetPx:NaN},
    {cardId:'card-2',scrollTopPx:-1},
    {cardId:20},{cardId:'card-49'},
  ])assert.throws(()=>captureProgressiveLaneScroll(cards,state,bad));
  for(const bad of [
    {regionId:'1'}, {regionId:'lane bad'},{regionId:'lane:unsafe'},
    {regionId:''},{regionId:'a'.repeat(81)},
  ])assert.throws(()=>getProgressiveLaneView(cards,state,bad));
  assert.throws(()=>view(cards,state,{laneLabel:''}),/laneLabel/);
  assert.throws(()=>advanceProgressiveLaneState(cards,state,'top'),/direction/);
  assert.throws(()=>progressiveLaneNeighbor(cards,'card-0',0),/delta/);
  assert.throws(()=>view(cards,{...state,version:2}),/version/);
  assert.throws(()=>view(cards,{...state,end:400}),/render cap/);
  assert.throws(()=>view(cards,{...state,anchorOffsetPx:Infinity}),/finite/);
  assert.throws(()=>view(cards,{...state,focusCardId:1}),/focusCardId/);
  assert.throws(()=>view(cards,{...state,scrollTopPx:-3}),/nonnegative/);
  const shorter=cards.slice(0,3);
  assert.throws(()=>view(shorter,state),/reconcile/);
  assert.throws(()=>advanceProgressiveLaneState(shorter,state,'next'),/reconcile/);
});

test('duplicate card IDs and host-sized overflow rejected before any display',()=>{
  const data=create(3);
  data[1].id=data[0].id;
  assert.throws(()=>createProgressiveLaneState(data),/Duplicate card ID/);
  const bigger=create(20001);
  assert.throws(()=>createProgressiveLaneState(bigger),/20000/);
  assert.throws(()=>createProgressiveLaneState([{id:20}]),/card.id/);
});

test('React SSR renders only bounded listitems with correct ARIA indexes and keyboard load control',()=>{
  const cards=create(100);
  let state=createProgressiveLaneState(cards,{pageSize:10,maxRendered:20});
  state=advanceProgressiveLaneState(cards,state,'next');
  state=advanceProgressiveLaneState(cards,state,'next');
  const v=view(cards,state);
  const elements=[
    React.createElement('div',{role:'list','aria-label':v.region['aria-label'],
      id:v.region.id,key:'list'},v.entries.map(entry=>React.createElement('article',{
        key:entry.key,role:'listitem','aria-posinset':entry.ariaPosInSet,
        'aria-setsize':entry.ariaSetSize,'data-cardid':entry.card.id,
      },entry.card.title))),
    v.controls.previous && React.createElement('button',{key:'prev',type:'button',
      'aria-controls':v.controls.previous['aria-controls'],
      'aria-label':v.controls.previous['aria-label']},v.controls.previous.text),
    v.controls.next && React.createElement('button',{key:'next',type:'button',
      'aria-controls':v.controls.next['aria-controls'],
      'aria-label':v.controls.next['aria-label']},v.controls.next.text),
    React.createElement('span',{key:'live','aria-live':'polite','aria-atomic':true},v.liveStatus),
  ];
  const html=renderToStaticMarkup(React.createElement(React.Fragment,null,...elements));
  assert.equal([...html.matchAll(/role="listitem"/g)].length,20);
  assert.match(html,/aria-posinset="11"/);
  assert.match(html,/aria-posinset="30"/);
  assert.match(html,/aria-setsize="100"/);
  assert.match(html,/aria-live="polite"/);
  assert.match(html,/aria-controls="lane-123"/);
  assert.match(html,/type="button"/);
  assert.doesNotMatch(html,/data-cardid="card-31"/);
});

test('permission-safe index.groupActiveCards feeds page without exposing forbidden board/project',()=>{
  const tasks=[
    ...create(65),
    {id:'secret',boardId:'board-b',listId:'doing',projectId:'secret-project',
      title:'Sensitive',cost:9999999,archived:false},
    {id:'trashed',boardId:'board-a',listId:'doing',projectId:'public',
      title:'Trashed',deleted:true},
  ];
  const index=createBoardPerformanceIndex({
    projects:[{id:'public',price:0},{id:'secret-project',price:999999}],
    workspaces:[{id:'workspace-a',archived:false}],
    boards:[
      {id:'board-a',workspaceId:'workspace-a',projectId:'public',
        stages:[{id:'doing',label:'doing'}]},
      {id:'board-b',workspaceId:'workspace-a',projectId:'secret-project',
        stages:[{id:'doing',label:'doing'}]},
    ],
    stages:[{id:'doing',label:'doing'}],tasks,
  },{permittedProjectIds:['public']});
  const lane=index.groupActiveCards({boardId:'board-a'}).get('doing');
  const state=createProgressiveLaneState(lane,{pageSize:20,maxRendered:40});
  const start=view(lane,state);
  assert.equal(start.total,65);
  assert.equal(start.shown,20);
  assert.ok(start.entries.every(x=>x.card.projectId==='public'));
  assert.ok(!entryIds(start).includes('secret'));
  assert.ok(!entryIds(start).includes('trashed'));
  const newLane=[]; // scope revoked by host; parent must rebuild index
  const revoked=reconcileProgressiveLaneState(newLane,state);
  assert.deepEqual(view(newLane,revoked).entries,[]);
  assert.throws(()=>revealProgressiveLaneCard(newLane,revoked,'secret'),
    /not in current permitted/);
});
