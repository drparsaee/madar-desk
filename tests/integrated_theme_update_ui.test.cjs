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
const entry=path.join(root,'src/features.jsx');
const bundle=esbuild.buildSync({entryPoints:[entry],bundle:true,platform:'node',format:'cjs',
  write:false,jsx:'automatic',loader:{'.css':'empty'},
  external:['react','react/jsx-runtime','lucide-react']}).outputFiles[0].text;
const moduleFile=new Module(entry,module);
moduleFile.filename=entry;
moduleFile.paths=Module._nodeModulePaths(path.dirname(entry));
moduleFile._compile(bundle,entry);
const {SettingsPanel}=moduleFile.exports;
const render=(settings,theme,canManage=true,api=null)=>renderToStaticMarkup(React.createElement(SettingsPanel,{
  data:{settings,stages:[{id:'inbox',label:'ورودی',color:'#818181'}],tasks:[],projects:[]},
  theme,canManage,updateApi:api,onChange:()=>{},onThemeChange:()=>{},onClose:()=>{},
  onCalendarChange:()=>{},
}));

test('settings and sidebar use effective theme instead of stale shared fallback',()=>{
  const app=fs.readFileSync(path.join(root,'src/App.jsx'),'utf8');
  assert.match(app,/theme=\{uiTheme\} onThemeChange=\{chooseTheme\}/);
  assert.match(app,/toggleTheme=\(\)=>chooseTheme\(uiTheme==='dark'\?'light':'dark'\)/);
  const html=render({theme:'light',themeForAllUsers:false},'dark');
  assert.match(html,/aria-pressed="true"[^>]*>.*تاریک/);
  assert.match(html,/اعمال تم برای همهٔ کاربران/);
  assert.match(html,/در همین رایانه انتخاب می‌شود/);
});

test('shared theme disables non-admin change yet preserves manual updates for every role',()=>{
  const html=render({theme:'dark',themeForAllUsers:true},'dark',false,{
    releaseCheck:()=>{},releaseDownload:()=>{},releaseInstall:()=>{},
  });
  assert.match(html,/تم مشترک همهٔ کاربران فعال است/);
  assert.match(html,/<input type="checkbox" disabled="" checked=""/);
  assert.match(html,/بررسی به‌روزرسانی/);
  assert.match(html,/نصب فقط با تأیید کاربر و تطبیق هش SHA-256/);
});

test('no native desktop API is truthful about browser-only update limitations',()=>{
  const html=render({theme:'dark',themeForAllUsers:false},'dark',true);
  assert.match(html,/فقط در نسخهٔ نصب‌شدهٔ ویندوز در دسترس است/);
  assert.doesNotMatch(html,/در حال دریافت/);
});
