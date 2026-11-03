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
const load=source=>{
  const text=esbuild.buildSync({entryPoints:[path.join(root,source)],bundle:true,
    platform:'node',format:'cjs',write:false,
    external:['react','react/jsx-runtime','lucide-react'],
    loader:{'.css':'empty','.jpg':'dataurl'}}).outputFiles[0].text;
  const file=path.join(root,'tests','dual-settings-virtual.cjs');
  const moduleShim=new Module(file,module);
  moduleShim.filename=file;moduleShim.paths=Module._nodeModulePaths(path.dirname(file));
  moduleShim._compile(text,file);
  return moduleShim.exports;
};
test('shared update component renders explicit check, installed version and no fake update',()=>{
  const {UpdateSettings}=load('src/update_settings.jsx');
  const html=renderToStaticMarkup(React.createElement(UpdateSettings,{
    api:{releaseCheck:async()=>({available:false,current:'1.0.12',latest:'1.0.12'})},
    desktop:true,
  }));
  assert.match(html,/بررسی به‌روزرسانی/);
  assert.match(html,/v1\.0\.12/);
  assert.doesNotMatch(html,/نصب امن پس از خروج/);
  const browser=renderToStaticMarkup(React.createElement(UpdateSettings,{desktop:false}));
  assert.match(browser,/فقط در نسخهٔ نصب‌شدهٔ ویندوز/);
});
test('task settings clearly separate personal theme from shared default even for viewer',()=>{
  const {SettingsPanel}=load('src/features.jsx');
  const html=renderToStaticMarkup(React.createElement(SettingsPanel,{
    data:{tasks:[],projects:[],stages:[],settings:{theme:'dark',costDefault:false}},
    canManage:false,effectiveTheme:'light',onThemeChange:()=>{},
    calendar:'jalali',onCalendarChange:()=>{},onClose:()=>{},
    onChange:()=>{},releaseApi:{releaseCheck:async()=>({})},desktop:true,
  }));
  assert.match(html,/تم فعلی من/);
  assert.match(html,/تم پیش‌فرض مشترک کاربران/);
  assert.match(html,/بررسی به‌روزرسانی/);
  assert.match(html,/aria-label="تم فعلی من"/);
  assert.match(html,/aria-label="تم پیش‌فرض مشترک کاربران"/);
  assert.match(html,/پیش‌فرض تاریک/);
  assert.match(html,/aria-pressed="true"/);
});
test('accounting settings are a first-class route and exposed from the ribbon',()=>{
  const {StandaloneAccountingWorkspace}=load('src/standalone_accounting_workspace.jsx');
  const html=renderToStaticMarkup(React.createElement(StandaloneAccountingWorkspace,{
    api:{standaloneAccountingRead:async()=>({})},
    canManage:false,canDraft:false,canAdmin:false,
  }));
  assert.match(html,/تنظیمات برنامه/);
  assert.match(html,/تنظیمات و مدیریت/);
  const bridge=fs.readFileSync(path.join(root,'standalone_accounting_desktop.py'),'utf8');
  for(const name of ['releaseCheck','releaseDownload','releaseInstall']){
    assert.match(bridge,new RegExp("'"+name+"'"));
  }
});
test('company posting day is explicitly configurable as a fixed offset, not silently inferred',()=>{
  const source=fs.readFileSync(path.join(root,'src/accounting_operational_panels.jsx'),'utf8');
  assert.match(source,/postingUtcOffsetMinutes/);
  assert.match(source,/ایران، UTC\+03:30/);
  assert.match(source,/ساعت تابستانی/);
  assert.match(source,/حالت قبلی دفتر \(UTC، بدون تغییر\)/);
  assert.doesNotMatch(source,/Date\.parse\(.+postingUtcOffsetMinutes/);
});
