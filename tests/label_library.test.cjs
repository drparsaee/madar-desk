'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const Module=require('node:module');
const esbuild=require('esbuild');
const root=path.resolve(__dirname,'..');
const entry=path.join(root,'src/label_library.js');
const bundle=esbuild.buildSync({entryPoints:[entry],platform:'node',bundle:true,
  format:'cjs',write:false,loader:{'.css':'empty'},external:['react','react/jsx-runtime','lucide-react']}).outputFiles[0].text;
const compiled=new Module(entry,module);
compiled.filename=entry;
compiled.paths=Module._nodeModulePaths(path.dirname(entry));
compiled._compile(bundle,entry);
const {sharedLabelLibrary,sharedLabelColor,editSharedLabelState}=compiled.exports;

const start=()=>({settings:{theme:'dark'},boards:[
  {id:'board-a',labelDefinitions:[{id:'old-1',name:'چاپ',color:'#123456'}]},
  {id:'board-b',labelDefinitions:[{id:'old-1',name:'تولید',color:'#abcdef'}]}],
  tasks:[{id:'a',boardId:'board-a',labels:['چاپ'],labelColors:{'چاپ':'#123456'}},
    {id:'b',boardId:'board-b',labels:[],labelColors:{}},
    {id:'c',boardId:'board-b',labels:['تولید'],labelColors:{'تولید':'#abcdef'}}]});

test('shared catalogue discovers older labels without assigning them to other cards',()=>{
  const before=start(),copy=JSON.stringify(before);
  const library=sharedLabelLibrary(before);
  assert.deepEqual(library.map(x=>x.name),['چاپ','تولید']);
  assert.equal(new Set(library.map(x=>x.id)).size,2,'board-local IDs may collide but shared IDs cannot');
  assert.deepEqual(before.tasks[1].labels,[]);
  assert.equal(JSON.stringify(before),copy,'discovery must not mutate the stored state');
});

test('creating a reusable label changes the catalogue only, no card is selected',()=>{
  const before=start();
  const next=editSharedLabelState(before,{action:'create',name:'فوری',color:'#00aabb'},()=> 'global-new');
  assert.equal(sharedLabelLibrary(next).find(x=>x.name==='فوری').id,'global-new');
  assert.deepEqual(next.tasks,before.tasks);
  assert.deepEqual(next.tasks[1].labels,[]);
  assert.equal(sharedLabelColor(sharedLabelLibrary(next),'فوری'),'#00aabb');
});

test('selection is explicitly per-card; renaming and recoloring update only cards already using the shared label',()=>{
  let current=editSharedLabelState(start(),{action:'create',name:'آماده',color:'#00aabb'},()=> 'ready');
  current=editSharedLabelState(current,{action:'toggle',id:'ready',taskId:'b',selected:true,at:'2026-11-05T10:00:00Z'});
  assert.deepEqual(current.tasks.map(t=>t.labels),[['چاپ'],['آماده'],['تولید']]);
  const second=editSharedLabelState(current,{action:'toggle',id:'ready',taskId:'b',selected:true});
  assert.equal(second,current,'reselecting an already selected label must be idempotent');
  current=editSharedLabelState(current,{action:'edit',id:'ready',name:'تحویل',color:'#112233'});
  assert.deepEqual(current.tasks.map(t=>t.labels),[['چاپ'],['تحویل'],['تولید']]);
  assert.equal(current.tasks[1].labelColors['تحویل'],'#112233');
  current=editSharedLabelState(current,{action:'toggle',id:'ready',taskId:'b',selected:false});
  assert.deepEqual(current.tasks[1].labels,[]);
  assert.equal(sharedLabelLibrary(current).find(x=>x.id==='ready').name,'تحویل',
    'unchecking removes the selection, not the shared definition');
});

test('global rename respects existing board definitions and rejects duplicate names and malformed colors',()=>{
  const initial=start();
  const current=editSharedLabelState(initial,{action:'edit',id:'old-1',name:'چاپ افست',color:'#ff0000'});
  assert.equal(current.boards[0].labelDefinitions[0].name,'چاپ افست');
  assert.deepEqual(current.tasks.map(t=>t.labels),[['چاپ افست'],[],['تولید']]);
  assert.throws(()=>editSharedLabelState(current,{action:'create',name:'تولید',color:'#ffffff'}),/تکراری/);
  assert.throws(()=>editSharedLabelState(current,{action:'edit',id:'old-1',name:'تولید',color:'#ff0000'}),/نام/);
  assert.throws(()=>editSharedLabelState(current,{action:'create',name:'X',color:'red'}),/رنگ/);
});

test('global deletion atomically prunes every selected card and legacy definition without touching a colliding local ID',()=>{
  const initial=start();
  initial.tasks[0].labelIds=['old-1','keep-a'];
  initial.tasks[0].labelColors.باقی='#112233';
  initial.tasks[1].labelColors={'چاپ':'#aaaaaa'};
  initial.tasks[2].labelIds=['old-1'];
  initial.tasks[2].labelColors.چاپ='#aabbcc';
  const before=JSON.stringify(initial);
  const next=editSharedLabelState(initial,{action:'delete',id:'old-1'});
  assert.equal(JSON.stringify(initial),before,'deletion is a pure state update');
  assert.deepEqual(sharedLabelLibrary(next).map(item=>item.name),['تولید']);
  assert.deepEqual(next.boards.map(board=>board.labelDefinitions.map(item=>item.name)),[[],['تولید']]);
  assert.deepEqual(next.tasks.map(task=>task.labels),[[],[],['تولید']]);
  assert.deepEqual(next.tasks[0].labelIds,['keep-a']);
  assert.deepEqual(next.tasks[2].labelIds,['old-1'], 'same local ID on another board must survive');
  for(const task of next.tasks)assert(!Object.hasOwn(task.labelColors||{},'چاپ'));
  assert.equal(next.tasks[0].labelColors.باقی,'#112233');
  assert.equal(next.tasks[2].labelColors.تولید,'#abcdef');
  assert.throws(()=>editSharedLabelState(next,{action:'delete',id:'old-1'}),/وجود ندارد/);
  const restored=editSharedLabelState(next,{action:'create',name:'چاپ',color:'#123456'},()=> 'again');
  assert.equal(restored.tasks[0].labels.length,0,'recreated labels do not reassign deleted selections');
});

test('deleting a global-only label also clears selections on every board and keeps unrelated task references',()=>{
  let state=editSharedLabelState(start(),{action:'create',name:'آماده',color:'#abcdef'},()=> 'global-ready');
  state=editSharedLabelState(state,{action:'toggle',id:'global-ready',taskId:'a',selected:true});
  state=editSharedLabelState(state,{action:'toggle',id:'global-ready',taskId:'b',selected:true});
  const next=editSharedLabelState(state,{action:'delete',id:'global-ready'});
  assert.deepEqual(next.tasks.map(task=>task.labels),[['چاپ'],[],['تولید']]);
  assert.deepEqual(sharedLabelLibrary(next).map(item=>item.name),['چاپ','تولید']);
  assert.equal(next.settings.labelLibrary.some(item=>item.id==='global-ready'),false);
});
