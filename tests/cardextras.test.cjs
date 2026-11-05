const {test} = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const Module = require('node:module');
const esbuild = require('esbuild');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');

const root = path.resolve(__dirname, '..');
const bundle = esbuild.buildSync({
  entryPoints: [path.join(root, 'src/cardextras.jsx')], bundle: true,
  platform: 'node', format: 'cjs', jsx: 'automatic', write: false,
  loader: {'.css': 'empty'}, external: ['react','react/jsx-runtime','lucide-react']
}).outputFiles[0].text;
const compiled = new Module(path.join(root,'cardextras.bundle.cjs'), module);
compiled.filename = path.join(root,'cardextras.bundle.cjs');
compiled.paths = Module._nodeModulePaths(root);
compiled._compile(bundle, compiled.filename);
const {
  cardChecklistGroups,editCardChecklists,normalizeCover,coverTextColor,editCardFieldValues,
  editBoardFields,CardChecklists,CardCover,CardCustomFields,BoardFieldEditor
} = compiled.exports;

const baseCard = () => ({id:'t',projectId:'p',boardId:'board',title:'Card',cost:500,
  checklist:[{id:'a',text:'Original paid',done:false,cost:100,costCategory:'transport',costDate:'2026-10-20'}],
  checklists:[{id:'checklist-legacy',name:'Original',items:[
    {id:'a',text:'Original paid',done:false,cost:100,costCategory:'transport',costDate:'2026-10-20'}]}],
  customFieldValues:{}});
const board={id:'board',customFields:[
  {id:'sku',name:'کد محصول',type:'text',options:[]},
  {id:'units',name:'تیراژ',type:'number',options:[]},
  {id:'done',name:'تایید',type:'checkbox',options:[]},
  {id:'due',name:'تحویل',type:'date',options:[]},
  {id:'option',name:'نوع چاپ',type:'select',options:[{id:'offset',label:'افست'}]}
]};
let counter=0;
const next=()=>`new-${++counter}`;

test('flat legacy steps are wrapped losslessly and deep cloned',()=>{
  const source=baseCard();delete source.checklists;
  const groups=cardChecklistGroups(source);
  assert.equal(groups[0].id,'checklist-legacy');
  assert.equal(groups[0].items[0].cost,100);
  groups[0].items[0].text='changed';
  assert.equal(source.checklist[0].text,'Original paid');
});

test('legacy toggle mirrors flat field, preserves all expense metadata',()=>{
  const task=baseCard();const before=JSON.stringify(task);
  const patch=editCardChecklists(task,{type:'toggle-item',groupId:'checklist-legacy',itemId:'a'});
  assert.equal(patch.checklist[0].done,true);
  assert.equal(patch.checklists[0].items[0].done,true);
  assert.equal(patch.checklist[0].cost,100);
  assert.equal(patch.checklist[0].costCategory,'transport');
  assert.equal(patch.checklist[0].costDate,'2026-10-20');
  assert.equal(JSON.stringify(task),before);
});

test('pending flat editor changes remain authoritative when editing another named group',()=>{
  const task=baseCard();
  task.checklists.push({id:'qa',name:'QA',items:[{id:'q1',text:'Inspect',done:false,cost:0}]});
  task.checklist[0]={...task.checklist[0],done:true,cost:777,costCategory:'confirmed'};
  // Simulate App's legacy flat editor changing the item without updating named mirror.
  const patch=editCardChecklists(task,{type:'toggle-item',groupId:'qa',itemId:'q1'});
  assert.equal(patch.checklist[0].cost,777);
  assert.equal(patch.checklist[0].costCategory,'confirmed');
  assert.equal(patch.checklist[0].done,true);
  assert.deepEqual(patch.checklists[0].items,patch.checklist);
  assert.equal(patch.checklists[1].items[0].done,true);
});

test('create/edit/reorder/delete extra checklist leaves legacy and task-level costs alone',()=>{
  const old=baseCard();
  let task={...old, ...editCardChecklists(old,{type:'add-group',name:'بازرسی'},next)};
  const extraId=task.checklists[1].id;
  task={...task,...editCardChecklists(task,{type:'add-item',groupId:extraId,text:'اول'},next)};
  task={...task,...editCardChecklists(task,{type:'add-item',groupId:extraId,text:'دوم'},next)};
  const firstId=task.checklists[1].items[0].id;
  task={...task,...editCardChecklists(task,{type:'toggle-item',groupId:extraId,itemId:firstId})};
  task={...task,...editCardChecklists(task,{type:'rename-item',groupId:extraId,itemId:firstId,text:'ویرایش شده'})};
  task={...task,...editCardChecklists(task,{type:'move-item',groupId:extraId,itemId:firstId,direction:'down'})};
  assert.deepEqual(task.checklists[1].items.map(i=>i.text),['دوم','ویرایش شده']);
  assert.equal(task.checklists[1].items[1].done,true);
  task={...task,...editCardChecklists(task,{type:'rename-group',groupId:extraId,name:'کنترل کیفیت'})};
  task={...task,...editCardChecklists(task,{type:'remove-item',groupId:extraId,itemId:firstId})};
  task={...task,...editCardChecklists(task,{type:'remove-group',groupId:extraId})};
  assert.equal(task.checklists.length,1);
  assert.deepEqual(task.checklist,old.checklist);
  assert.equal(task.cost,old.cost);
});

test('deletion of paid named or legacy items and groups is blocked',()=>{
  const task=baseCard();
  for(const command of [
    {type:'remove-item',groupId:'checklist-legacy',itemId:'a'},
    {type:'remove-group',groupId:'checklist-legacy'}
  ])assert.throws(()=>editCardChecklists(task,command),/هزینه/);
  const paid={...task,checklists:[...task.checklists,{id:'extra',name:'other',items:[{id:'b',text:'b',cost:1,done:false}]}]};
  assert.throws(()=>editCardChecklists(paid,{type:'remove-group',groupId:'extra'}),/هزینه/);
});

test('bounded and valid checklist commands reject malformed values',()=>{
  const task=baseCard();
  assert.throws(()=>editCardChecklists(task,{type:'add-group',name:'  '}));
  assert.throws(()=>editCardChecklists(task,{type:'add-item',groupId:'unknown',text:'Hi'}));
  assert.throws(()=>editCardChecklists(task,{type:'not-real',groupId:'checklist-legacy'}));
  assert.throws(()=>editCardChecklists(task,{type:'add-group',name:'Safe'},()=> 'checklist-legacy'),/شناسه/);
  assert.throws(()=>editCardChecklists(task,{type:'add-item',groupId:'checklist-legacy',text:'x'.repeat(5001)}));
});

test('named checklist item can carry its own assignee and due date without modifying financial fields',()=>{
  const source={...baseCard(),checklists:[{id:'independent',name:'QC',items:[{id:'i1',text:'Inspect',done:false,cost:2300}]}]};
  const patch=editCardChecklists(source,{type:'patch-item',groupId:'independent',itemId:'i1',
    changes:{assignees:['local','qa','qa'],dueDate:'2026-11-18'}});
  assert.deepEqual(patch.checklists[0].items[0].assignees,['local','qa']);
  assert.equal(patch.checklists[0].items[0].dueDate,'2026-11-18');
  assert.equal(patch.checklists[0].items[0].cost,2300);
  assert.deepEqual(patch.checklist,source.checklist);
  assert.throws(()=>editCardChecklists(source,{type:'patch-item',groupId:'independent',itemId:'i1',changes:{cost:0}}));
  assert.throws(()=>editCardChecklists(source,{type:'patch-item',groupId:'independent',itemId:'i1',changes:{dueDate:'bad-date'}}));
});

test('covers accept only solid HEX colors with fixed size, no URLs or arbitrary CSS',()=>{
  assert.deepEqual(normalizeCover({type:'color',color:'#cA9b11',size:'strip'}),
    {type:'color',color:'#CA9B11',size:'strip'});
  assert.equal(normalizeCover(null),null);
  for(const cover of [
    {type:'image',url:'https://invalid.example/x'},
    {type:'color',color:'red; background:url(javascript:alert(1))',size:'strip'},
    {type:'color',color:'#ABCDEF',size:'full',url:'javascript:alert(1)'},
    {type:'color',color:'#ABCDEF',size:'weird'},
    {type:'color',color:'url(data:image/svg+xml,<svg onload=alert(1)>)',size:'strip'}
  ])assert.throws(()=>normalizeCover(cover));
  assert.equal(coverTextColor('#102D67'),'#FFFFFF');
  assert.equal(coverTextColor('#FFFFFF'),'#142236');
  assert.equal(coverTextColor('url(https://evil)'), '#152238');
});

test('typed field editing preserves values and rejects invalid numbers/dates/options',()=>{
  let task=baseCard();
  for(const [field,value] of [[board.customFields[0],'<script>alert(1)</script>'],
    [board.customFields[1],24],[board.customFields[2],false],
    [board.customFields[3],'2026-10-20'],[board.customFields[4],'offset']]){
    task={...task,...editCardFieldValues(task,field,value)};
  }
  assert.equal(task.customFieldValues.sku,'<script>alert(1)</script>');
  assert.equal(task.customFieldValues.option,'offset');
  assert.deepEqual(task.checklist,baseCard().checklist);
  assert.throws(()=>editCardFieldValues(task,board.customFields[1],Infinity));
  assert.throws(()=>editCardFieldValues(task,board.customFields[1],true));
  assert.throws(()=>editCardFieldValues(task,board.customFields[3],'2026-02-30'));
  assert.throws(()=>editCardFieldValues(task,board.customFields[3],'0000-01-01'));
  assert.throws(()=>editCardFieldValues(task,board.customFields[4],'delete'));
});

test('board custom field create/rename/delete uses stable IDs and blocks used entries',()=>{
  const original=JSON.stringify(board);
  let updated=editBoardFields(board,[],[],{type:'add',name:'وضعیت',fieldType:'select',options:['شروع','پایان']},next);
  assert.equal(updated.customFields.length,6);
  assert.equal(updated.customFields[5].options.length,2);
  const fieldId=updated.customFields[5].id;
  updated=editBoardFields(updated,[],[],{type:'rename',fieldId,name:'نتیجه'});
  assert.equal(updated.customFields[5].name,'نتیجه');
  assert.throws(()=>editBoardFields(updated,[{boardId:'board',customFieldValues:{[fieldId]:null}}],[],
    {type:'remove',fieldId}),/استفاده/);
  assert.throws(()=>editBoardFields(updated,[],[{boardId:'board',customFieldValues:{[fieldId]:'new-1'}}],
    {type:'remove',fieldId}),/استفاده/);
  updated=editBoardFields(updated,[],[],{type:'remove',fieldId});
  assert.equal(updated.customFields.length,5);
  assert.equal(JSON.stringify(board),original);
  assert.throws(()=>editBoardFields(board,[],[],{type:'add',name:'Test',fieldType:'select',options:['X','X']},next),/تکراری/);
});

test('SSR components expose expected controls and escape hostile text',()=>{
  const task=baseCard();
  task.checklists[0].items[0].text='<img src=x onerror=alert(1)>';
  task.checklist[0].text='<img src=x onerror=alert(1)>';
  task.cover={type:'color',color:'#ABCDEF',size:'full'};
  task.customFieldValues={sku:'<script>evil()</script>'};
  const chk=renderToStaticMarkup(React.createElement(CardChecklists,{task,onChange:()=>{}}));
  assert.match(chk,/چک‌لیست‌های کارت/);
  assert.match(chk,/&lt;img src=x onerror=alert\(1\)&gt;/);
  assert(!chk.includes('<img src=x'));
  assert.match(chk,/disabled=""[^>]*aria-label="حذف/);
  const hidden=renderToStaticMarkup(React.createElement(CardChecklists,{task,hideLegacy:true,onChange:()=>{}}));
  assert(!hidden.includes('Original paid'));
  assert(!hidden.includes('&lt;img'));
  assert.match(hidden,/چک‌لیست جدید/);
  const cover=renderToStaticMarkup(React.createElement(CardCover,{task,onChange:()=>{}}));
  assert.match(cover,/--cover-preview-color:#ABCDEF/i);
  assert.match(cover,/card-cover-editor__preview--full/);
  assert.match(cover,/رنگ تمام کارت/);
  assert.match(cover,/نوار بالای کارت/);
  assert.match(cover,/ساخت رنگ دلخواه/);
  const custom=renderToStaticMarkup(React.createElement(CardCustomFields,{task,board,calendar:'jalali',onChange:()=>{}}));
  assert.match(custom,/&lt;script&gt;evil\(\)&lt;\/script&gt;/);
  assert(!custom.includes('<script>'));
  assert.match(custom,/placeholder="1405\/07\/28"/);
  const definitions=renderToStaticMarkup(React.createElement(BoardFieldEditor,{board,onChange:()=>{}}));
  assert.match(definitions,/تعریف فیلدهای برد/);
});
