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

test('every visible quick action has a unique, actual and focusable destination',()=>{
  const nav=app.match(/<nav className=\{'task-quick-actions'[\s\S]*?<\/nav>/)?.[0];
  assert.ok(nav,'the task edit toolbar exists');
  const ids=Array.from(nav.matchAll(/aria-controls="(task-section-[a-z]+)"/g),m=>m[1]);
  assert.equal(ids.length,10,'the complete ordered toolbar now includes metadata, time, dependencies and cover');
  assert.equal(new Set(ids).size,ids.length);
  for(const id of ids){
    assert.match(app,new RegExp('id="'+id+'" tabIndex=\\{-1\\}'),id+' should be keyboard focusable');
  }
  assert.match(app,/target\.scrollIntoView\(/);
  assert.match(app,/\(focusTarget\|\|target\)\.focus\(\{preventScroll:true\}\)/);
  assert.match(nav,/type="button"/,'navigation buttons must never submit forms');
  assert.match(nav,/aria-expanded=\{showExtraActions\}/,'secondary shortcuts should have an accessible disclosure');
  assert.match(css,/\.task-quick-actions:not\(\.task-quick-actions--expanded\) \.task-quick-action--extra\{display:none\}/);
});

test('compact task layout reserves legible inputs and responsive columns',()=>{
  assert.match(css,/grid-template-columns:repeat\(3,minmax\(0,1fr\)\)/);
  assert.match(css,/grid-template-columns:repeat\(2,minmax\(0,1fr\)\)/);
  assert.match(css,/min-height:36px/);
  assert.match(css,/scroll-margin-top:80px/);
  assert.match(css,/data-theme="dark"/);
  assert.match(css,/prefers-reduced-motion:reduce/);
  assert.match(css,/@media\(max-width:720px\)\{[\s\S]*?\.drawer \.task-quick-actions\{[\s\S]*?position:static;top:auto;z-index:auto;/);
});

test('less-used card features collapse safely while existing data opens them',()=>{
  // All detail panels, including cover, use the same per-user disclosure contract.
  assert.match(app, /className="task-optional-block task-shared-disclosure" id="task-section-cover" tabIndex=\{-1\} open=\{sectionOpen\.cover\}/);
  for(const key of ['assignees','time','dependencies','reports']){
    assert.match(app,new RegExp('open=\\{sectionOpen\\.'+key+'\\}'));
  }
  assert.match(app, /className="task-optional-block task-step-expenses" defaultOpen=\{!!step\.expenseItems\?\.length\}/);
  assert.match(app, /<summary>چک‌لیست‌های بیشتر<\/summary>/);
  assert.match(css, /\.task-optional-block\[open\]/);
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
  assert.match(app,/<summary><span>لینک فایل‌های اشتراکی<\/span>/);
  assert.match(app,/className="project-file-panel project-file-panel--compact"/);
});
