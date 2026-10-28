'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const Module=require('node:module');
const esbuild=require('esbuild');
const root=path.resolve(__dirname,'..');
const compiled=esbuild.buildSync({entryPoints:[path.join(root,'src','lane_operations.js')],bundle:true,
  platform:'node',format:'cjs',write:false}).outputFiles[0].text;
const loader=new Module(path.join(root,'src','lane-operations-test-loader.cjs'),module);
loader.filename=path.join(root,'src','lane-operations-test-loader.cjs');
loader.paths=Module._nodeModulePaths(root);loader._compile(compiled,loader.filename);
const {sortLaneState,moveAllLaneCardsState}=loader.exports;
const finance={cost:12345,invoice:{number:'INV-7',amount:777},assignees:['operator'],
  checklist:[{id:'step1',done:true,cost:435}]};
function task(id,title,createdAt,dueDate,listId='todo',projectId='p1'){
  return {id,title,createdAt,dueDate,projectId,boardId:'b1',listId,status:'todo',
    ...JSON.parse(JSON.stringify(finance))};
}
function fixture(){return {version:1,settings:{theme:'dark'},
  stages:[{id:'todo'},{id:'done'}],projects:[{id:'p1',name:'X'}],
  boards:[{id:'b1',projectId:'p1',stages:[{id:'todo'},{id:'done'}]}],
  tasks:[task('z','ب', '2026-10-02','2026-11-20'),
    task('y','آ', '2026-10-03','2026-11-18'),
    task('x','پ', '2026-10-01','2026-11-19'),
    task('foreign','خارجی', '2026-10-01','', 'done')]};}
function ordered(state,list='todo'){
  return state.tasks.filter(t=>t.listId===list).slice().sort((a,b)=>a.cardOrder-b.cardOrder).map(t=>t.id);
}
function stableFields(state){return state.tasks.map(({id,cost,invoice,assignees,checklist,projectId,title})=>
  ({id,cost,invoice,assignees,checklist,projectId,title}));}

test('sorting a list changes only card order and preserves finance metadata',()=>{
  const source=fixture();const before=JSON.stringify(source);
  const result=sortLaneState(source,'b1','todo','title');
  assert.deepEqual(ordered(result),['y','z','x']);
  assert.deepEqual(stableFields(result),stableFields(source));
  assert.equal(JSON.stringify(source),before);
  assert.deepEqual(ordered(sortLaneState(source,'b1','todo','newest')),['y','z','x']);
  assert.deepEqual(ordered(sortLaneState(source,'b1','todo','oldest')),['x','z','y']);
  assert.deepEqual(ordered(sortLaneState(source,'b1','todo','due')),['y','x','z']);
  assert.equal(result.tasks.find(t=>t.id==='foreign'),source.tasks[3]);
});

test('move all stays in one board, never drops costs and refuses bad targets',()=>{
  const source=fixture(), before=JSON.stringify(source);
  const result=moveAllLaneCardsState(source,'b1','todo','done');
  assert.deepEqual(ordered(result,'done'),['foreign','z','y','x']);
  assert.deepEqual(stableFields(result),stableFields(source));
  assert.equal(source.tasks[0].status,'todo');
  assert.equal(JSON.stringify(source),before);
  assert.equal(moveAllLaneCardsState(source,'b1','todo','todo'),source);
  assert.throws(()=>moveAllLaneCardsState(source,'b1','todo','missing'));
  assert.throws(()=>sortLaneState(source,'b1','todo','random'));
  assert.throws(()=>sortLaneState(source,'other','todo','title'));
});
