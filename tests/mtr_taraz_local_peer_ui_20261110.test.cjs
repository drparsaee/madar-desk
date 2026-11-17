'use strict';

// In-memory current-source JSX contract. No browser, user profile, EXE or LAN.
const test=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const fs=require('node:fs');
const Module=require('node:module');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const esbuild=require('esbuild');

const project=path.resolve(__dirname,'..');
const appSource=fs.readFileSync(path.join(project,'src','App.jsx'),'utf8');
const settingsPath=path.join(project,'src','features.jsx');
const settingsBundle=esbuild.buildSync({
  entryPoints:[settingsPath],bundle:true,platform:'node',format:'cjs',
  external:['react','react-dom','react-dom/server','react/jsx-runtime','lucide-react'],
  loader:{'.css':'empty'},write:false,logLevel:'silent',
}).outputFiles[0].text;
const loaded=new Module(settingsPath,module);
loaded.filename=settingsPath;
loaded.paths=Module._nodeModulePaths(path.dirname(settingsPath));
loaded._compile(settingsBundle,settingsPath);
const {SettingsPanel}=loaded.exports;

function renderStatus(localPeer){
  let openCalls=0;
  const html=renderToStaticMarkup(React.createElement(SettingsPanel,{
    data:{tasks:[],projects:[],boards:[],stages:[],settings:{}},
    priorityUsedIds:[],onChange:()=>{},onClose:()=>{},
    onOpenLocalTaraz:()=>{openCalls++;},
    tarazEnabled:false,
    tarazStatus:{supported:true,pending:0,postingEnabled:false,
      message:'Only metadata proposals',localPeer},
  }));
  return {html,openCalls};
}

test('Taraz settings render is inert and fail closed without verified install',()=>{
  const result=renderStatus({installed:false,approvedBuild:false,canOpenManually:false});
  assert.equal(result.openCalls,0);
  assert.match(result.html,/برنامهٔ تراز روی این رایانه/);
  assert.match(result.html,/نسخهٔ محلی مورد تأیید شناسایی نشد/);
  assert.match(result.html,/disabled=""[^>]*>بازکردن تراز/);
});

test('Taraz settings expose deliberate open only for verified same-user binary',()=>{
  const result=renderStatus({installed:true,approvedBuild:true,
    canOpenManually:true,version:'1.0.0',peerAuthenticated:false});
  assert.equal(result.openCalls,0);
  assert.match(result.html,/نسخهٔ بررسی‌شدهٔ 1\.0\.0 شناسایی شد/);
  assert.doesNotMatch(result.html,/disabled=""[^>]*>بازکردن تراز/);
  assert.match(result.html,/بازکردن تراز/);
});

test('App keeps launch tied to click, accepts only no-finance native acknowledgement',()=>{
  assert.match(appSource,/const openLocalTaraz=async\(\)=>\{/);
  assert.match(appSource,/approvedBuild!==true/);
  assert.match(appSource,/canOpenManually!==true/);
  assert.match(appSource,/api\.tarazIntegrationOpenLocal\(true\)/);
  assert.match(appSource,/result\?\.launchRequested!==true\|\|result\?\.financialEventCreated!==false/);
  assert.match(appSource,/onClick=\{openLocalTaraz\}>بازکردن تراز/);
  assert.match(appSource,/onOpenLocalTaraz=\{openLocalTaraz\}/);
  assert.doesNotMatch(appSource,/useEffect\([\s\S]{0,200}tarazIntegrationOpenLocal/);
});

test('real current-source Madar JS bundles in-memory with the connection UI',()=>{
  const bundle=esbuild.buildSync({entryPoints:[path.join(project,'src','App.jsx')],
    platform:'browser',format:'esm',bundle:true,write:false,
    loader:{'.css':'empty'},charset:'utf8',logLevel:'silent',outdir:'in-memory-mtr-connector'});
  const js=bundle.outputFiles.find(output=>output.path.endsWith('.js'));
  assert.ok(js?.text?.length>20000);
  assert.match(js.text,/tarazIntegrationOpenLocal/);
  assert.match(js.text,/بازکردن تراز/);
});

test('local receipt history never presents an unauthenticated peer as authenticated Taraz',()=>{
  assert.match(appSource,/tarazHistory\.peerVerified===true/);
  assert.match(appSource,/علامت بررسی‌شده در فایل محلی \(هویت تراز تأییدنشده\)/);
  assert.match(appSource,/علامت ردشده در فایل محلی \(هویت تراز تأییدنشده\)/);
  assert.doesNotMatch(appSource,/reviewed:'بررسی‌شده در تراز \(غیرمالی\)'/);
});
