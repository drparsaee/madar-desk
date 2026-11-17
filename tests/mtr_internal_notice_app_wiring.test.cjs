'use strict';

/** Source/wiring and in-memory compilation checks; no browser/network/build. */
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const esbuild=require('esbuild');
const root=path.resolve(__dirname,'..');
const appPath=path.join(root,'src','App.jsx');
const panelPath=path.join(root,'src','mtr_internal_notice_panel.jsx');
const app=fs.readFileSync(appPath,'utf8');
const panel=fs.readFileSync(panelPath,'utf8');

function desktopGuard(){
  const match=app.match(/function isPinnedE6NoticeClient\(status\)\{[\s\S]*?\n\}/);
  assert.ok(match,'Missing E6 pinned client guard in App');
  return (status,{desktop=true,bridge=true}={})=>{
    const source=match[0]+'\nreturn isPinnedE6NoticeClient(status);';
    return Function('isDesktop','api','status',source)(desktop,{
      mtrNoticeCommand:bridge?()=>Promise.resolve({}):undefined,
    },status);
  };
}

const status={
  mode:'client',connected:true,transport:'https',
  url:'https://127.0.0.1:48370',
  fingerprint:'a'.repeat(64),
  user:{username:'editor-one',role:'editor',projects:['proj-1']},
};

test('actual App JSX and E6 panel bundle into memory without writing an app build',()=>{
  const bundle=esbuild.buildSync({
    entryPoints:[appPath],bundle:true,platform:'browser',
    format:'esm',write:false,outdir:'in-memory-mtr-e6-check',charset:'utf8',
    loader:{'.css':'empty'},logLevel:'silent',
  });
  assert.ok(bundle.outputFiles.length>0);
  const js=bundle.outputFiles.find(file=>file.path.endsWith('.js'));
  assert.ok(js && js.text.length>20000);
  assert.match(js.text,/صندوق آزمایشی اعلان‌های داخلی/);
  assert.match(js.text,/میزبان این پروژه/);
  assert.match(js.text,/mtrNoticeCommand/);
});

test('guard is executable, requires desktop client connected pinned HTTPS',()=>{
  const eligible=desktopGuard();
  assert.equal(eligible(status),true);
  for(const [candidate,options] of [
    [status,{desktop:false}],
    [status,{bridge:false}],
    [{...status,mode:'solo'},{}],
    [{...status,mode:'server'},{}],
    [{...status,connected:false},{}],
    [{...status,transport:'http'},{}],
    [{...status,url:'http://127.0.0.1:48370'},{}],
    [{...status,url:'https://user:pass@127.0.0.1:48370'},{}],
    [{...status,url:'https://127.0.0.1:48370/other'},{}],
    [{...status,url:'https://127.0.0.1:48370?actor=1'},{}],
    [{...status,url:'https://127.0.0.1'},{}],
    [{...status,fingerprint:''},{}],
    [{...status,fingerprint:'g'.repeat(64)},{}],
    [{...status,user:{role:'viewer'}},{}],
    [null,{}],
  ]){
    assert.equal(eligible(candidate,options),false,
      'guard must deny '+JSON.stringify(candidate));
  }
});

test('E6 is a manual optional modal for selected permitted project only',()=>{
  assert.match(app,/import \{MtrInternalNoticePanel\} from '\.\/mtr_internal_notice_panel\.jsx'/);
  assert.match(app,/const internalNoticeReady=isPinnedE6NoticeClient\(lanStatus\)/);
  assert.match(app,/permittedSearchProjects\.includes\(selectedProject\.id\)/);
  assert.match(app,/internalNoticeOpen\?\.session===lanStatus/);
  assert.match(app,/internalNoticeOpen\?\.projectId===selectedProject\?\.id/);
  assert.match(app,/useEffect\(\(\)=>\{\s*\/\/ A refresh,[\s\S]*?setInternalNoticeOpen\(null\)/);
  assert.match(app,/\{internalNoticeReady&&<button type="button"/);
  assert.match(app,/onClick=\{\(\)=>setInternalNoticeOpen\(\{session:lanStatus,projectId:selectedProject\.id\}\)\}/);
  assert.match(app,/\{showInternalNotice&&<Modal[\s\S]*?<MtrInternalNoticePanel command=\{internalNoticeCommand\}/);
  assert.match(app,/projectId=\{selectedProject\.id\} limit=\{50\} pageSize=\{10\}/);
  assert.match(app,/onClose=\{\(\)=>setInternalNoticeOpen\(null\)\}/);
  assert.match(app,/بستن صندوق داخلی/);
});

test('host callback is stable for the scoped session and refuses stale scope',()=>{
  assert.match(app,/const internalNoticeCommand=useMemo\(\(\)=>\{/);
  assert.match(app,/now\?\.session!==snapshot\|\|now\.projectId!==projectId\|\|!now\.ready/);
  assert.match(app,/envelope\.action==='list'&&envelope\.params\?\.projectId!==projectId/);
  assert.match(app,/return api\.mtrNoticeCommand\(envelope\)/);
  assert.match(app,/\},\[lanStatus,selectedProject\?\.id,internalNoticeReady\]\)/);
  assert.match(panel,/onClick=\{load\}/);
  assert.match(panel,/onClick=\{\(\)=>mark\(item\)\}/);
  assert.doesNotMatch(panel,/fetch\s*\(|XMLHttpRequest|WebSocket|sendBeacon/);
  assert.doesNotMatch(app,/api\.mtrNoticeCommand\(\{/,
    'App must never autonomously issue a notice host action');
});

test('existing collaboration inbox is still separately mounted',()=>{
  assert.match(app,/<NotificationsDialog api=\{api\}/);
  assert.match(app,/\{notificationsOpen&&<NotificationsDialog/);
  assert.match(app,/onOpenTarget=\{openNotificationTarget\}/);
});
