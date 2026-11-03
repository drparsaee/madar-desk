'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const Module=require('node:module');
const esbuild=require('esbuild');
// Styles are bundled by Vite; the Node render test needs no CSS execution.
require.extensions['.css']=()=>{};
const root=path.resolve(__dirname,'..');
function load(file){
  const filename=path.join(root,file);
  const compiled=esbuild.buildSync({entryPoints:[filename],bundle:true,platform:'node',
    format:'cjs',write:false,external:['react','react-dom','lucide-react','*.css']}).outputFiles[0].text;
  const loader=new Module(filename+'.test.cjs',module);
  loader.filename=filename+'.test.cjs';
  loader.paths=Module._nodeModulePaths(path.dirname(filename));
  loader._compile(compiled,loader.filename);
  return loader.exports;
}
const {boardTableColumns,normalizeBoardViewPreferences,saveBoardViewPreferences,
  readBoardViewPreferences,safeNumericAggregate}=load('src/board_table_preferences.js');
const {BoardTableView}=load('src/board_table_view.jsx');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const board={id:'b-a',customFields:[
  {id:'quantity',name:'تعداد بسته',type:'number'},
  {id:'phase',name:'نوع خدمات',type:'select',options:[{id:'one',label:'چاپ'}]},
  {id:'note',name:'توضیح',type:'text'},
]};
function storage(){
  const map=new Map();
  return {getItem:key=>map.has(key)?map.get(key):null,
    setItem:(key,value)=>map.set(key,value),entries:()=>[...map]};
}

test('layout is per user and board; invalid storage is normalized and new fields join',()=>{
  const db=storage(),columns=boardTableColumns(board);
  const customized=columns.map(column=>({id:column.id,visible:column.id!=='custom:note',
    width:column.id==='stage'?222:column.width})).reverse();
  saveBoardViewPreferences(db,'ali','b-a',{mode:'table',columns:customized},columns);
  const saved=readBoardViewPreferences(db,'ali','b-a',columns);
  assert.equal(saved.mode,'table');
  assert.equal(saved.columns[0].id,'custom:note');
  assert.equal(saved.columns.find(c=>c.id==='stage').width,222);
  assert.equal(saved.columns.find(c=>c.id==='custom:note').visible,false);
  saveBoardViewPreferences(db,'ali','b-a',{mode:'list'},columns);
  const afterViewSwitch=readBoardViewPreferences(db,'ali','b-a',columns);
  assert.equal(afterViewSwitch.mode,'list');
  assert.equal(afterViewSwitch.columns.find(c=>c.id==='custom:note').visible,false);
  assert.equal(afterViewSwitch.columns.find(c=>c.id==='stage').width,222);
  assert.equal(readBoardViewPreferences(db,'sara','b-a',columns).mode,'board');
  assert.equal(readBoardViewPreferences(db,'ali','b-b',columns).mode,'board');
  assert.equal(saved.columns.find(c=>c.id==='title').visible,true);
  const extended=boardTableColumns({...board,customFields:[...board.customFields,
    {id:'extra',name:'جدید',type:'number'}]});
  assert.equal(readBoardViewPreferences(db,'ali','b-a',extended).columns.at(-1).id,'custom:extra');
  const removed=boardTableColumns({...board,customFields:[]});
  assert.ok(!readBoardViewPreferences(db,'ali','b-a',removed).columns.some(c=>c.id==='custom:note'));
  db.setItem('madar-board-view-v1:ali:b-a','{"mode":"finance","columns":[{"id":"title","visible":false,"width":9999},{"id":"not-real","width":2}]}');
  const recovered=readBoardViewPreferences(db,'ali','b-a',columns);
  assert.equal(recovered.mode,'board');
  assert.equal(recovered.columns[0].id,'title');
  assert.equal(recovered.columns[0].visible,true);
  assert.equal(recovered.columns[0].width,260);
  assert.equal(normalizeBoardViewPreferences(null,columns).columns.length,columns.length);
});

test('numeric sums are exact for safe six-place decimals and reject unsafe inputs',()=>{
  const cards=[{customFieldValues:{quantity:0.1}},{customFieldValues:{quantity:0.2}},
    {customFieldValues:{quantity:4}},{customFieldValues:{quantity:null}}];
  assert.deepEqual(safeNumericAggregate(cards,'quantity'),{status:'ok',count:3,value:'۴٫۳'});
  assert.equal(safeNumericAggregate(cards,'missing').status,'empty');
  assert.equal(safeNumericAggregate([{customFieldValues:{quantity:1e30}}],'quantity').status,'unsafe');
  assert.equal(safeNumericAggregate([{customFieldValues:{quantity:0.0000001}}],'quantity').status,'unsafe');
  assert.equal(safeNumericAggregate([{customFieldValues:{quantity:NaN}}],'quantity').status,'unsafe');
  assert.equal(safeNumericAggregate([{customFieldValues:{quantity:9007199254740991}},
    {customFieldValues:{quantity:1}}],'quantity').status,'unsafe');
});

test('server-rendered table has real cards, configured columns and safe visible aggregations',()=>{
  const db=storage(),columns=boardTableColumns(board);
  saveBoardViewPreferences(db,'ali','b-a',{mode:'table',
    columns:columns.map(c=>({id:c.id,width:c.width,visible:c.id!=='priority'&&c.id!=='custom:note'}))},columns);
  const visible=[{id:'1',title:'سفارش ۱',listId:'doing',projectId:'p-a',priority:'low',
    customFieldValues:{quantity:12,phase:'one'}},
    {id:'2',title:'سفارش ۲',listId:'doing',projectId:'p-a',priority:'low',
      customFieldValues:{quantity:3,phase:'one'}}];
  const html=renderToStaticMarkup(React.createElement(BoardTableView,{
    board,scopeId:'b-a',identity:'ali',storage:db,tasks:visible,
    stages:[{id:'doing',label:'در جریان'}],projects:[{id:'p-a',name:'نمونه'}],
    priorities:[{id:'low',label:'کم'}],
  }));
  assert.match(html,/نمای جدول کارها/);
  assert.match(html,/سفارش ۱/);
  assert.match(html,/سفارش ۲/);
  assert.match(html,/جمع: ۱۵/);
  assert.match(html,/در جریان/);
  assert.match(html,/چاپ/);
  assert.doesNotMatch(html,/<th[^>]*>اولویت<\/th>/);
  assert.doesNotMatch(html,/<th[^>]*>توضیح<\/th>/);
  assert.doesNotMatch(html,/هزینه|بدهکار|بستانکار/);
  assert.equal((html.match(/<tr/g)||[]).length,4);
  assert.equal(db.entries().length,1,'reading must not mutate preferences');
});

test('large filtered boards page their rows but aggregate the entire permitted result',()=>{
  const cards=Array.from({length:251},(_,index)=>({
    id:String(index),title:'Synthetic '+index,projectId:'p-a',listId:'doing',
    customFieldValues:{quantity:1},
  }));
  const html=renderToStaticMarkup(React.createElement(BoardTableView,{
    board,scopeId:'b-a',identity:'viewer',storage:storage(),tasks:cards,
  }));
  assert.match(html,/Synthetic 199/);
  assert.doesNotMatch(html,/Synthetic 200/);
  assert.match(html,/نمایش ۲۰۰ کارت بعدی/);
  assert.match(html,/جمع: ۲۵۱/);
});

test('App mounts table with its existing filtered ACL-aware card collection',()=>{
  const app=fs.readFileSync(path.join(root,'src/App.jsx'),'utf8');
  assert.match(app,/mode==='table'\?<BoardTableView/);
  assert.match(app,/<BoardTableView[^\n]+tasks=\{filtered\}/);
  assert.match(app,/onOpen=\{setEditorId\}/);
  assert.match(app,/saveBoardViewPreferences\(localStorage,boardViewIdentity,boardViewScope/);
  assert.ok(!fs.readFileSync(path.join(root,'src/board_table_view.jsx'),'utf8').includes('saveState('));
});
