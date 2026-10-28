'use strict';
/**
 * CD05 P0 App.jsx Trash integration contract.
 *
 * Static assertions check the real App handler/view/filter wiring.
 * React SSR compiles the exact inline Trash modal JSX extracted from App.jsx
 * into a standalone read-only harness. No browser, DOM, APPDATA or source edits.
 */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const esbuild = require('esbuild');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');

const root = path.resolve(__dirname, '..');
const appText = fs.readFileSync(path.join(root,'src','App.jsx'), 'utf8');
const trashModuleText = fs.readFileSync(path.join(root,'src','cardtrash.js'),'utf8');

function section(from, to) {
  const start = appText.indexOf(from);
  assert.ok(start >= 0, 'Missing App.jsx integration marker: ' + from);
  const end = appText.indexOf(to, start + from.length);
  assert.ok(end > start, 'Missing closing marker: ' + to);
  return appText.slice(start, end);
}

function inlineTrashSSR() {
  const jsx = section('{trashOpen&&<Modal title="زباله‌دان کارت‌ها"',
                      '\n    {show(\'workspaceManagement\')&&workspaceOpen&&').trim();
  // The exact Trash modal JSX is supplied by App.jsx, not recreated in a
  // fake component. Modal shell is stubbed because App's Modal is not public.
  const source = [
    'import React from "react";',
    'function Modal({title,children,onClose}){',
    ' return <section role="dialog" aria-label={title} data-close={typeof onClose}>{children}</section>;',
    '}',
    'export function TrashSSR(props){',
    ' const {trashOpen,trashCards,boards,workspaces,projects,canEdit,',
    '        restoreTrashedCard,setTrashOpen}=props;',
    ' return <main>' + jsx + '</main>;',
    '}',
  ].join('\n');
  const compiled = esbuild.buildSync({
    stdin: {contents:source,resolveDir:root,loader:'jsx',sourcefile:'cd05-inline-trash.jsx'},
    bundle:true,platform:'node',format:'cjs',write:false,
    external:['react','react/jsx-runtime'],
  }).outputFiles[0].text;
  const filename = path.join(root,'tests','cd05-inline-trash-readonly.cjs');
  const loader = new Module(filename,module);
  loader.filename = filename;
  loader.paths = Module._nodeModulePaths(path.dirname(filename));
  loader._compile(compiled,filename);
  return loader.exports.TrashSSR;
}

const TrashSSR = inlineTrashSSR();

function example(overrides={}) {
  const boards = [{id:'board-1',workspaceId:'workspace-1',projectId:'project-1',
                   name:'چاپ جعبه',archived:false}];
  const workspaces = [{id:'workspace-1',name:'کارگاه',archived:false}];
  const projects = [{id:'project-1',name:'مشتری نمونه'}];
  const trashed = {id:'card-one',title:'جعبه لوکس',projectId:'project-1',
                   boardId:'board-1',listId:'active',deleted:true,cost:125_000};
  return {
    trashOpen:true, trashCards:[trashed],
    boards,workspaces,projects,canEdit:true,
    restoreTrashedCard:()=>{},setTrashOpen:()=>{},
    ...overrides,
  };
}
const html = props => renderToStaticMarkup(React.createElement(TrashSSR,example(props)));
const buttons = markup => [...markup.matchAll(/<button\b[^>]*>/g)].map(m=>m[0]);
const restoreButtons = markup => buttons(markup).filter(tag=>tag.includes('aria-label="بازیابی کارت'));

test('App imports both pure transitions and never removes card from tasks in deleteTask',()=>{
  assert.match(appText,/import\s*\{softDeleteCardState,restoreDeletedCardState\}\s*from\s*['"]\.\/cardtrash\.js['"]/);
  const handler=section('const deleteTask=id=>','const restoreTrashedCard=id=>');
  assert.match(handler,/if\(!canEdit\)return/);
  assert.match(handler,/softDeleteCardState\(data,id,options\)/);
  assert.match(handler,/change\(s=>softDeleteCardState\(s,id,options\)\)/);
  assert.doesNotMatch(handler,/tasks\.filter\(/);
  assert.doesNotMatch(handler,/splice\(|\.pop\(/);
  assert.match(trashModuleText,/\{\.\.\.item, deleted\}/);
});

test('restore action applies pure transition, guarded by canEdit and grant-derived options',()=>{
  const restore=section('const restoreTrashedCard=id=>','const trashCards=');
  assert.match(restore,/if\(!canEdit\)return/);
  assert.match(restore,/restoreDeletedCardState\(data,id,options\)/);
  assert.match(restore,/change\(s=>restoreDeletedCardState\(s,id,options\)\)/);
  const grants=section('const cardTrashOptions=','const trashCards=');
  assert.match(grants,/canManage\?\{canManage:true\}/);
  assert.match(grants,/\{canEdit:true,grantedProjectIds:projects\.map\(p=>p\.id\)\}/);
  assert.match(appText,/const canEdit=lanStatus\?\.mode==='client'/);
});

test('normal board, count, reporting, planner, suggestions and card editor exclude deleted cards',()=>{
  const active=section('const filtered=useMemo(','const counts=useMemo(');
  // M03 index excludes deleted cards before the shared filtered set is built.
  assert.match(appText,/createBoardPerformanceIndex\(data,/);
  assert.match(active,/boardIndex\.selectActiveCards\(/);
  assert.match(appText,/const trashCards=tasks\.filter\(t=>t\.deleted===true/);
  assert.match(appText,/activeTask\.deleted!==true&&<TaskEditor/);
  assert.match(appText,/ReportingPanel tasks=\{tasks\.filter\(t=>t\.deleted!==true\)\}/);
  assert.match(appText,/PlannerPanel tasks=\{tasks\.filter\(t=>t\.deleted!==true\)\}/);
  assert.match(appText,/className="lane-quick-add"/);
  assert.match(appText,/allTasks=\{tasks\.filter\(t=>t\.deleted!==true\)\}/);
  assert.match(appText,/allTasks=\{tasks\.filter\(t=>t\.deleted!==true\)\}/);
});

test('Trash sidebar opens the modal and only deleted project/workspace cards are enumerated',()=>{
  assert.match(appText,/onClick=\{\(\)=>setTrashOpen\(true\)\} aria-label="زباله‌دان کارت‌ها"/);
  const selected=section('const trashCards=','const duplicateTask=');
  assert.match(selected,/t\.deleted===true/);
  assert.match(selected,/projects\.some\(p=>p\.id===t\.projectId\)/);
  assert.match(selected,/b\.workspaceId===activeWorkspaceId/);
  assert.doesNotMatch(selected,/\.filter\(t=>t\.id!==/);
});

test('SSR: real inline Trash modal shows preserved card title and restore button',()=>{
  const markup=html();
  assert.match(markup,/role="dialog"/);
  assert.match(markup,/aria-label="زباله‌دان کارت‌ها"/);
  assert.match(markup,/جعبه لوکس/);
  assert.match(markup,/مشتری نمونه/);
  assert.match(markup,/چاپ جعبه/);
  assert.match(markup,/حذف دائمی انجام نمی‌شود/);
  assert.equal(restoreButtons(markup).length,1);
  assert.doesNotMatch(restoreButtons(markup)[0],/\bdisabled\b/);
});

test('SSR: viewer can see trash cards but restore control is disabled',()=>{
  const markup=html({canEdit:false});
  assert.match(markup,/جعبه لوکس/);
  assert.equal(restoreButtons(markup).length,1);
  assert.match(restoreButtons(markup)[0],/\bdisabled\b/);
});

test('SSR: archived board disables restoration and labels its condition',()=>{
  const item=example();
  item.boards[0].archived=true;
  const markup=html(item);
  assert.match(markup,/فضای بایگانی‌شده/);
  assert.match(restoreButtons(markup)[0],/\bdisabled\b/);
});

test('SSR: archived workspace disables restoration and labels its condition',()=>{
  const item=example();
  item.workspaces[0].archived=true;
  const markup=html(item);
  assert.match(markup,/فضای بایگانی‌شده/);
  assert.match(restoreButtons(markup)[0],/\bdisabled\b/);
});

test('SSR: when no trashed card exists show empty state, never show restore button',()=>{
  const markup=html({trashCards:[]});
  assert.match(markup,/کارت حذف‌شده‌ای وجود ندارد/);
  assert.equal(restoreButtons(markup).length,0);
});

test('SSR: closing Trash hides the dialog entirely',()=>{
  const markup=html({trashOpen:false});
  assert.doesNotMatch(markup,/زباله‌دان کارت‌ها/);
  assert.doesNotMatch(markup,/جعبه لوکس/);
  assert.equal(restoreButtons(markup).length,0);
});

test('UI never offers permanent purge as an action in the Trash modal',()=>{
  const modal=section('{trashOpen&&<Modal title="زباله‌دان کارت‌ها"',
                      '\n    {show(\'workspaceManagement\')&&workspaceOpen&&');
  assert.doesNotMatch(modal,/(?:purge|permanentDelete|forceDelete|حذف دائمی.*onClick)/);
  assert.match(modal,/onClick=\{\(\)=>restoreTrashedCard\(t\.id\)\}/);
});
