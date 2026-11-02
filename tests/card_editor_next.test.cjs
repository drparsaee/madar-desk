'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const Module=require('node:module');
const esbuild=require('esbuild');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const root=path.resolve(__dirname,'..');
const text=file=>fs.readFileSync(path.join(root,file),'utf8');
const load=(file)=>{
  const entry=path.join(root,file);
  const built=esbuild.buildSync({entryPoints:[entry],platform:'node',bundle:true,format:'cjs',write:false,
    loader:{'.css':'empty'},external:['react','react/jsx-runtime','react-dom','react-dom/client','lucide-react']}).outputFiles[0].text;
  const instance=new Module(entry,module);instance.filename=entry;instance.paths=Module._nodeModulePaths(path.dirname(entry));
  instance._compile(built,entry);return instance.exports;
};
test('disclosure layout is per-user and reused across cards without modifying task state',()=>{
  const {readCardSectionPreferences,saveCardSectionPreferences}=load('src/card_section_preferences.js');
  const memory=new Map(),storage={getItem:key=>memory.get(key)??null,setItem:(key,val)=>memory.set(key,val)};
  assert.deepEqual(readCardSectionPreferences(storage,'employee'),{
    assignees:false,time:false,dependencies:false,reports:false});
  saveCardSectionPreferences(storage,'employee',{assignees:true,reports:true});
  assert.deepEqual(readCardSectionPreferences(storage,'employee'),{
    assignees:true,time:false,dependencies:false,reports:true});
  assert.equal(readCardSectionPreferences(storage,'viewer').reports,false);
  assert.doesNotThrow(()=>saveCardSectionPreferences({setItem(){throw Error('no storage')}},'employee',{time:true}));
});
test('task drawer four shared details and source order match quick-action navigation',()=>{
  const app=text('src/App.jsx');
  for(const group of ['assignees','time','dependencies','reports']){
    assert.match(app,new RegExp('id="task-section-'+group+'"'));
    assert.match(app,new RegExp('open=\\{sectionOpen\\.'+group+'\\}'));
    assert.match(app,new RegExp("onSectionToggle\\('"+group+"'"));
  }
  const ids=['metadata','assignees','time','dependencies','description','cover','tags','checklist','reports','attachments'];
  const nav=app.slice(app.indexOf('<nav className="task-quick-actions"'),app.indexOf('</nav>',app.indexOf('<nav className="task-quick-actions"')));
  let previous=-1;
  for(const id of ids){
    const at=nav.indexOf("jumpToSection('"+id+"')");
    assert.ok(at>previous,'quick section order: '+id);
    previous=at;
  }
  assert.match(app,/onArchive=\{\(\)=>archiveTask\(activeTask\.id\)\}/);
});
test('legacy Toman conversion control is gone, old nonzero money is not silently rewritten',()=>{
  const source=text('src/order_finance_fields.jsx');
  assert.doesNotMatch(source,/تبدیل مبلغ قدیمی تومان به ریال/);
  assert.doesNotMatch(source,/const rialView/);
  assert.match(source,/disabled=\{!canEdit\|\|legacySale\}/);
  assert.match(source,/saleCurrency:'RIAL'/);
});
test('all six native color-pickers expose named common presets',()=>{
  for(const file of ['src/priorities.jsx','src/labels.jsx','src/members.jsx','src/features.jsx',
    'src/board_lane_actions.jsx','src/accounting_print_designer.jsx']){
    assert.match(text(file),/CommonColorOptions/,file);
  }
  const {CommonColorOptions,COMMON_COLORS}=load('src/common_color_palette.jsx');
  assert.ok(COMMON_COLORS.length>=12);
  const html=renderToStaticMarkup(React.createElement(CommonColorOptions,{value:'#EF4444',onChange:()=>{},label:'اولویت'}));
  assert.match(html,/aria-label="انتخاب قرمز برای اولویت"/);
  assert.match(html,/aria-pressed="true"/);
});
test('card cover renders at top for strip mode and across entire card for full mode',()=>{
  const app=text('src/App.jsx');
  const component=app.slice(app.indexOf('function TaskCard('),app.indexOf('function WalletIcon('));
  assert.ok(component.indexOf('task-card-cover task-card-cover-strip')<component.indexOf('className="task-title"'));
  assert.match(component,/task-card--cover-full/);
  assert.match(text('src/kanban_compact.css'),/\.task-card--cover-full/);
  assert.match(text('src/kanban_compact.css'),/background: var\(--card-cover-color\)/);
});
test('small Jalali calendar renders 42 selectable ISO days and month navigation',()=>{
  const {MiniCalendar}=load('src/mini_calendar.jsx');
  const html=renderToStaticMarkup(React.createElement(MiniCalendar,{
    value:'2026-11-02',calendar:'jalali',onSelect:()=>{},onClose:()=>{}}));
  const dates=[...html.matchAll(/aria-label="انتخاب (\d{4}-\d\d-\d\d)"/g)].map(m=>m[1]);
  assert.equal(dates.length,42);
  assert.ok(dates.includes('2026-11-02'));
  assert.match(html,/ماه بعد/);
  assert.match(text('src/productivity.jsx'),/pickerOpen&&/);
});
