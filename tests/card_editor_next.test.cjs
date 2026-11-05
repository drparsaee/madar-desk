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
    metadata:false,description:true,assignees:false,attachments:false,checklist:true,
    tags:false,cover:false,time:false,dependencies:false,reports:false,
    accounting:false,settings:false});
  saveCardSectionPreferences(storage,'employee',{assignees:true,reports:true});
  assert.deepEqual(readCardSectionPreferences(storage,'employee'),{
    metadata:false,description:false,assignees:true,attachments:false,checklist:false,
    tags:false,cover:false,time:false,dependencies:false,reports:true,
    accounting:false,settings:false});
  assert.equal(readCardSectionPreferences(storage,'viewer').reports,false);
  assert.doesNotThrow(()=>saveCardSectionPreferences({setItem(){throw Error('no storage')}},'employee',{time:true}));
});
test('card editor shows only three main sections, with optional advanced tools in one menu',()=>{
  const app=text('src/App.jsx');
  for(const group of ['metadata','description','attachments','checklist','time','reports','accounting','settings']){
    assert.match(app,new RegExp('id="task-section-'+group+'"'));
  }
  assert.doesNotMatch(app,/id="task-section-cover"/);
  assert.doesNotMatch(app,/CardCover task=\{task\}/);
  assert.match(app,/onCoverChange=\{\(id,changes\)=>/);
  assert.doesNotMatch(app,/id="task-section-dependencies"/);
  assert.doesNotMatch(app,/CardDependencyPanel/);
  assert.match(app,/className="task-quick-actions task-quick-actions--minimal"/);
  assert.match(app,/advancedView==='settings'&&<section/);
  assert.match(app,/advancedView==='actions'&&canEdit&&<div/);
  assert.equal((app.match(/className="task-primary-section"/g)||[]).length,3);
  const nav=app.match(/<nav ref=\{quickNavRef\}[\s\S]*?<\/nav>/)?.[0]||'';
  for(const action of ['اعضا','تاریخ','برچسب','چک‌لیست','فایل','بیشتر']) assert.ok(nav.includes(action),action);
  assert.ok(!nav.includes('پیش‌نیازها'));
  assert.match(app,/className="task-activity-panel"/);
  assert.match(app,/id="task-section-settings"/);
  assert.match(app,/onArchive=\{\(\)=>archiveTask\(activeTask\.id\)\}/);
});
test('board automation buttons live in Settings and remain readable for viewers',()=>{
  const {SettingsPanel}=load('src/features.jsx');
  const data={tasks:[],stages:[{id:'todo',label:'انجام‌دادنی',color:'#64748B'}],
    settings:{theme:'dark',costDefault:false}};
  const html=renderToStaticMarkup(React.createElement(SettingsPanel,{
    data,boardId:'board-synthetic',priorityUsedIds:[],canManage:false,
    onCalendarChange:()=>{},onChange:()=>{},onClose:()=>{},onOpenBoardButtons:()=>{}
  }));
  assert.match(html,/تنظیمات مدار/);
  assert.match(html,/دکمه‌های برد/);
  assert.match(html,/<button[^>]*>دکمه‌های برد<\/button>/);
  const app=text('src/App.jsx');
  assert.match(app,/onOpenBoardButtons=\{\(\)=>\{setSettingsOpen\(false\);setAutomationButtonsScope\('board'\);\}\}/);
  assert.doesNotMatch(app,/<div className="page-controls"[^<]*<AutomationButtonsLauncher scope="board"/);
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
test('card cover strip colors the heading behind title, full colors entire card',()=>{
  const app=text('src/App.jsx');
  const component=app.slice(app.indexOf('function TaskCard('),app.indexOf('function WalletIcon('));
  assert.match(component,/className="task-card-head"/);
  assert.match(component,/task-card--cover-strip/);
  assert.match(component,/task-card--cover-full/);
  assert.match(text('src/kanban_compact.css'),/\.task-card--cover-strip \.task-card-head/);
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
