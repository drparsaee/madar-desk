const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const app=fs.readFileSync(path.join(root,'src/App.jsx'),'utf8');
const css=fs.readFileSync(path.join(root,'src/task_editor_compact.css'),'utf8');
const {parse}=require('@babel/parser');

test('task detail remains parseable and imports its separately scoped density styles',()=>{
  assert.ok(parse(app,{sourceType:'module',plugins:['jsx']}).program.body.length);
  assert.match(app,/import '\.\/task_editor_compact\.css'/);
  assert.match(css,/\.drawer\s*\.task-quick-actions/);
  assert.match(css,/@media\(max-width:480px\)/);
  assert.match(css,/\[id\^="task-section-"\]/);
  assert.doesNotMatch(css,/\.task-quick-actions(?:\s|\{)[^}]*display\s*:\s*none/s,'quick access must stay available');
});

test('every visible quick action has a unique, real destination or contextual editor',()=>{
  const nav=app.match(/<nav ref=\{quickNavRef\} className="task-quick-actions task-quick-actions--minimal"[\s\S]*?<\/nav>/)?.[0];
  assert.ok(nav,'the task edit toolbar exists');
  const ids=Array.from(nav.matchAll(/aria-controls="(task-section-[a-z]+)"/g),m=>m[1]);
  assert.deepEqual(ids,['task-section-attachments'],'only the file shortcut targets a full content section');
  assert.equal(new Set(ids).size,ids.length);
  for(const id of ids){
    assert.match(app,new RegExp('id="'+id+'" tabIndex=\\{-1\\}'),id+' should be keyboard focusable');
  }
  assert.match(app,/target\.scrollIntoView\(/);
  assert.match(app,/\(focusTarget\|\|target\)\.focus\(\{preventScroll:true\}\)/);
  assert.match(nav,/type="button"/,'navigation buttons must never submit forms');
  assert.match(nav,/aria-expanded=\{quickMenu==='more'\}/,'advanced actions should have a single accessible menu');
  for(const quick of ['date','members','labels','checklist','more']){
    assert.match(nav,new RegExp("quickMenu==='"+quick+"'"));
  }
  assert.match(nav,/jumpToSection\('attachments'\)/);
  assert.match(app,/setQuickMenu\(null\)/,'context menu must have a close path');
  assert.match(css,/\.drawer \.task-quick-actions\{[\s\S]*?display:flex;flex-wrap:wrap/);
  assert.doesNotMatch(nav,/پیش‌نیازها/);
});

test('compact task layout reserves legible inputs and responsive columns',()=>{
  assert.match(css,/grid-template-columns:repeat\(3,minmax\(0,1fr\)\)/);
  assert.match(css,/grid-template-columns:repeat\(2,minmax\(0,1fr\)\)/);
  assert.match(css,/min-height:31px/);
  assert.match(css,/scroll-margin-top:80px/);
  assert.match(css,/data-theme="dark"/);
  assert.match(css,/prefers-reduced-motion:reduce/);
  assert.match(css,/@media\(max-width:720px\)\{[\s\S]*?\.drawer \.task-quick-actions\{gap:4px\}/);
});

test('only core card content stays exposed; advanced tools are requested individually',()=>{
  for(const key of ['description','checklist','attachments']){
    assert.match(app,new RegExp('className="task-primary-section" id="task-section-'+key+'"'));
  }
  assert.doesNotMatch(app,/advancedView==='cover'&&<section/);
  assert.doesNotMatch(app,/<Palette size=\{15\}\/> کاور کارت/);
  const nav=app.match(/<nav ref=\{quickNavRef\}[\s\S]*?<\/nav>/)?.[0]||'';
  assert.doesNotMatch(nav,/ثبت گزارش<\/button>/);
  assert.match(app,/advancedView==='time'&&<section/);
  assert.match(app,/advancedView==='settings'&&<section/);
  assert.doesNotMatch(app,/CardDependencyPanel/);
  assert.doesNotMatch(app,/id="task-section-dependencies"/);
  assert.match(app, /className="task-activity-panel" id="task-section-reports" tabIndex=\{-1\}/);
  assert.match(app, /activityOpen&&<div className="task-activity-panel__content"/);
  assert.match(app, /ChecklistTaskRow key=\{step\.id\}/);
  const checklist=fs.readFileSync(path.join(root,'src/checklist_task_row.jsx'),'utf8');
  assert.match(checklist, /StageExpenseFields task=\{task\} step=\{step\}/);
  for(const action of ['date','members','cost','more']) assert.match(checklist,new RegExp("menu==='"+action+"'"));
  assert.doesNotMatch(app, /<summary>چک‌لیست‌های بیشتر<\/summary>/);
  assert.match(app,/\(task\.checklists\|\|\[\]\)\.some\(group=>group\.id!==/);
  assert.match(css, /\.task-primary-section\{/);
});

test('Trello reference keeps contextual edits and a separate conversation timeline',()=>{
  assert.match(app,/className="task-editor-layout"/);
  assert.match(app,/className="task-editor-main"/);
  assert.match(app,/task-quick-popover__create/);
  assert.match(app,/CardComments cardId=\{task.id\}/);
  assert.match(app,/className="task-activity-panel__reports"/);
  assert.match(css,/\.task-editor-layout\{display:grid;grid-template-columns:/);
  assert.match(css,/@media\(max-width:820px\)/);
  assert.match(css,/\.drawer \.task-quick-popover\{/);
});

test('task drawer has a keyboard focus trap, escape close and restores previous focus',()=>{
  assert.match(app,/const drawerRef=useRef\(null\)/);
  assert.match(app,/document\.addEventListener\('keydown',handleKey\)/);
  assert.match(app,/event\.key==='Escape'/);
  assert.match(app,/event\.key!=='Tab'/);
  assert.match(app,/document\.removeEventListener\('keydown',handleKey\)/);
  assert.match(app,/before\?\.isConnected\)before\.focus\(\)/);
  assert.match(css, /@media\(max-width:359px\)/);
});

test('reports composer is explicitly revealed and shared links remain discoverable',()=>{
  assert.match(app,/const \[reportComposerOpen,setReportComposerOpen\]=useState\(false\)/);
  assert.match(app,/canEdit&&reportComposerOpen&&<div className="report-composer"/);
  assert.match(app,/<SharedLinks links=\{task\.fileLinks\|\|\[\]\} compact/);
  assert.match(app,/className="project-file-panel project-file-panel--compact"/);
});
